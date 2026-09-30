"""Exercise the real UI and backend against isolated data with Edge."""
import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path

import conftest_support as support
import backend
import jobs
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else support.DATA / 'screenshots'
OUTPUT.mkdir(parents=True, exist_ok=True)
api = backend.Api()
results = []
errors = []
delay_save = False

buffer = io.BytesIO()
picture = Image.new('RGB', (1200, 640), '#e9eff9')
draw = ImageDraw.Draw(picture)
draw.rounded_rectangle((130, 80, 1070, 560), 45, fill='#ffffff')
draw.rounded_rectangle((210, 140, 990, 210), 18, fill='#d8e6fa')
draw.rounded_rectangle((210, 250, 780, 280), 12, fill='#ecedf1')
draw.rounded_rectangle((210, 320, 920, 350), 12, fill='#ecedf1')
draw.rounded_rectangle((210, 390, 720, 420), 12, fill='#ecedf1')
picture.save(buffer, 'PNG')
image_data = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
article = api.save_article('', '把注意力留给创作', '作者', '一处写作，处处发布。', '',
    '## 好的工具，让思路自然流动\n\n从一个想法开始，把它变成值得分享的文章。\n\n> 写作时，只需要专注于下一句话。\n\n### 写作的三个小习惯\n\n- 先记录灵感，再慢慢完善结构\n- 用图片让复杂的内容更容易理解\n- 把常用的文章结构保存为自己的模板\n\n## 发布前，再看一眼\n\n确认标题、摘要与配图，让每个平台都呈现合适的样子。\n', 'blue', '', True)
second = api.save_article('', '一个更清晰的产品测评框架', '作者', '', '', '## 使用体验\n\n从实际的使用场景出发。\n', 'green', '', True)
jobs.queue._hist['sample-failure'] = {'id': 'sample-failure', 'kind': 'article', 'status': 'partial',
    'source': 'ui', 'logs': ['公众号：草稿已保存', '知乎：连接超时，请稍后重试'], 'results': {'wechat': {'ok': True}, 'zhihu': {'ok': False, 'err': '连接超时'}},
    'title': '把注意力留给创作', 'platforms': ['wechat', 'zhihu'], 'created': time.time(), 'finished': time.time(),
    '_payload': {'title': '把注意力留给创作', 'md': '示例', 'platforms': {'wechat': True, 'zhihu': True}}}


async def native_call(source, method, args):
    if method == 'api_status': return {'running': False, 'enabled': False, 'port': 8737}
    if method == 'win_geom': return {'maxed': False}
    if method in ['native_drag', 'win_minimize', 'win_toggle_max', 'win_resize']: return None
    if method == 'save_article' and delay_save: await asyncio.sleep(.6)
    if method in ['upload', 'upload_video', 'retry_job']:
        return {'ok': False, 'msg': '测试模式不连接外部平台'}
    return await asyncio.to_thread(getattr(api, method), *args)


def passed(name):
    results.append(name)
    print('PASS ' + name, flush=True)


async def main():
    global delay_save
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1360, 'height': 880}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: print('CONSOLE ' + message.text[:240], flush=True) if message.type == 'error' else None)
        await page.expose_binding('nativeCall', native_call)
        await page.add_init_script('''
          window.pywebview = {api: new Proxy({}, {get: (_, method) => (...args) => window.nativeCall(method, args)})};
          document.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
        ''')
        await page.goto((support.ROOT / 'app/web/index.html').as_uri())
        try:
            await page.wait_for_function('vdReady && allArticles.length >= 2 && api !== null', timeout=20000)
        except Exception:
            print('ERRORS ' + json.dumps(errors, ensure_ascii=False), flush=True)
            print(await page.evaluate('({ready:vdReady, api:!!api, articles:allArticles.length, toast:document.getElementById("toast").textContent})'), flush=True)
            await page.screenshot(path=str(OUTPUT / 'debug.png'))
            raise
        await page.wait_for_timeout(200)
        await page.screenshot(path=str(OUTPUT / '01-home.png'))
        passed('offline editor initialization')

        await page.evaluate('(rel) => loadArticle(rel)', article['rel'])
        await page.evaluate("setPage('write')")
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(OUTPUT / '02-writing.png'))
        assert await page.evaluate("getMd().includes('自然流动')")
        passed('open saved article and themed preview')

        await page.click('#btnSource')
        await page.fill('#sourceEditor', '## 快速切稿前的最新内容\n\n这段文字必须保存。')
        await page.evaluate('(rel) => loadArticle(rel)', second['rel'])
        assert '最新内容' in api.load_article(article['rel'])['md']
        passed('switch article flushes latest source edits')

        await page.click('#btnTemplates')
        await page.wait_for_selector('.template-choice.selected')
        await page.wait_for_function("document.getElementById('templatePreviewFrame').srcdoc.includes('WILD NOTES')")
        await page.wait_for_timeout(350)
        await page.screenshot(path=str(OUTPUT / '03-templates.png'))
        await page.click('#btnUseTemplate')
        assert await page.evaluate("getMd().includes('最有分量的证据')")
        await page.fill('#title', '同名新稿')
        await page.wait_for_function('curRel !== null && !dirty', timeout=10000)
        first_rel = await page.evaluate('curRel')
        await page.evaluate('() => newArticle()')
        await page.fill('#title', '同名新稿')
        await page.fill('#sourceEditor', '这是另一篇同名文章。')
        await page.evaluate('() => saveArticle(true, true)')
        assert await page.evaluate('curRel') != first_rel
        passed('templates start a new draft and same title stays separate')

        await page.fill('#sourceEditor', '先写下第一版。')
        delay_save = True
        await page.evaluate('saveArticle(true, true);')
        await page.wait_for_timeout(120)
        await page.fill('#sourceEditor', '保存过程中继续输入的第二版。')
        await page.wait_for_function('!dirty && !saveInFlight', timeout=10000)
        rel = await page.evaluate('curRel')
        assert '第二版' in api.load_article(rel)['md']
        delay_save = False
        passed('typing during a slow save preserves the newer revision')

        await page.evaluate('data => { window.testImageData = data; }', image_data)
        await page.evaluate('''() => {
          const bytes = Uint8Array.from(atob(testImageData.split(',')[1]), c => c.charCodeAt(0));
          const transfer = new DataTransfer(); transfer.items.add(new File([bytes], '配图.png', {type:'image/png'}));
          document.getElementById('sourceEditor').dispatchEvent(new ClipboardEvent('paste', {clipboardData: transfer, bubbles: true, cancelable: true}));
        }''')
        await page.wait_for_function("getMd().includes('![配图]')", timeout=10000)
        await page.evaluate('() => flushDraft()')
        await page.wait_for_timeout(700)
        assert await page.evaluate("document.getElementById('preview').contentDocument.querySelector('img').naturalWidth > 0")
        passed('clipboard image is inserted, saved and visible in preview')

        await page.evaluate('''() => {
          const bytes = Uint8Array.from(atob(testImageData.split(',')[1]), c => c.charCodeAt(0));
          const transfer = new DataTransfer(); transfer.items.add(new File([bytes], '拖入图.png', {type:'image/png'}));
          document.getElementById('editorWrap').dispatchEvent(new DragEvent('drop', {dataTransfer:transfer, bubbles:true, cancelable:true}));
        }''')
        await page.wait_for_function("getMd().includes('![拖入图]')")
        passed('dragged image inserts into the source editor')
        await page.click('#btnIR')
        await page.wait_for_timeout(300)
        assert await page.evaluate("document.querySelector('#vditor img').naturalWidth > 0")
        passed('local image is visible in the instant-render editor')

        await page.evaluate('''() => renderPreviewHTML('<img src="https://example.invalid/a.png" onerror="parent.window.previewEscaped=true"><script>parent.window.previewEscaped=true</script><a href="javascript:alert(1)">link</a>')''')
        assert await page.evaluate("!window.previewEscaped && !document.getElementById('preview').contentDocument.querySelector('[onerror],script,[href]')")
        passed('article preview blocks scripts, event attributes and script links')

        await page.click('#btnFocus')
        assert not await page.locator('#sidebar').is_visible()
        await page.screenshot(path=str(OUTPUT / '04-focus.png'))
        await page.keyboard.press('Escape')
        assert await page.locator('#sidebar').is_visible()
        passed('focus mode and Escape restoration')

        await page.click('#btnTemplates')
        await page.fill('#templateName', '我的图片模板')
        await page.click('#btnSaveTemplate')
        await page.wait_for_selector('.template-choice.selected:has-text("我的图片模板")')
        assert any(item['name'] == '我的图片模板' for item in api.list_templates())
        await page.click('#btnCloseTemplates')
        passed('custom template persists with imported pictures')

        await page.evaluate("pubRel = allArticles[0].rel; setPage('publish'); renderPubCard();")
        await page.wait_for_selector('#histList .h-item')
        assert await page.locator('#histList').get_by_text('重试失败平台').count() == 1
        await page.screenshot(path=str(OUTPUT / '05-distribution.png'))
        passed('partial failure and retry action are visible')

        await page.set_viewport_size({'width': 760, 'height': 580})
        await page.evaluate("setPage('write')")
        await page.screenshot(path=str(OUTPUT / '06-small-window.png'))
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        passed('small window has no page overflow')
        await page.set_viewport_size({'width': 1360, 'height': 880})
        example = await page.evaluate('WILD_EXAMPLE')
        skeleton = await page.evaluate("BUILTIN_TEMPLATES.find(item => item.id === 'wild').md")
        sample = api.save_article('', '这工具，怎么比写稿还费劲？', '作者', '', '', example.split('\n', 1)[1], 'wild', '', True)
        await page.evaluate('(rel) => loadArticle(rel)', sample['rel'])
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(OUTPUT / '07-wild-writing.png'))
        target = OUTPUT.parent
        (target / '旷野-写作模板.md').write_text('# 旷野 · 野生观察\n\n' + skeleton, encoding='utf-8')
        (target / '旷野-示例文章.md').write_text(example, encoding='utf-8')
        html = api.preview(example, 'wechat', 'wild')['html']
        document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>旷野 · 野生观察</title><style>body{margin:0;background:#e8e3d8;font-family:Georgia,"Microsoft YaHei",sans-serif}main{max-width:660px;margin:32px auto;box-shadow:0 12px 60px #29251d12}img{max-width:100%}@media(max-width:700px){main{margin:0}}</style></head><body><main>' + html + '</main></body></html>'
        preview_path = target / '旷野-排版预览.html'
        preview_path.write_text(document, encoding='utf-8')
        await page.goto(preview_path.as_uri())
        await page.set_viewport_size({'width': 720, 'height': 1000})
        await page.screenshot(path=str(OUTPUT / '08-wild-reading.png'), full_page=True)
        passed('wild theme preview and reusable template are exported')
        assert not errors, errors
        passed('no JavaScript runtime errors')
        await browser.close()
    (OUTPUT / 'ui-checks.json').write_text(json.dumps({'passed': results, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
