"""Formula UI regression with real local assets and isolated native API calls."""
import asyncio
import json
import sys
from pathlib import Path

import conftest_support as support
import backend
from playwright.async_api import async_playwright

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else support.DATA / 'math-ui'
OUT.mkdir(parents=True, exist_ok=True)
api = backend.Api()
errors = []
passed = []
SHORT = 'x=x+x'
LONG = 'x=' + '+'.join(['x'] * 45)


async def native_call(source, method, args):
    if method == 'api_status': return {'running':False, 'enabled':False, 'port':8737}
    if method == 'win_geom': return {'maxed':False}
    if method in ['native_drag', 'win_minimize', 'win_toggle_max', 'win_resize']: return None
    if method in ['upload', 'upload_video', 'retry_job']: return {'ok':False, 'msg':'Isolated test'}
    return await asyncio.to_thread(getattr(api, method), *args)


def check(name):
    passed.append(name)
    print('PASS ' + name, flush=True)


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width':1360, 'height':900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.expose_binding('nativeCall', native_call)
        await page.add_init_script('''window.pywebview={api:new Proxy({},{get:(_,method)=>(...args)=>window.nativeCall(method,args)})};document.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));''')
        await page.goto((support.ROOT / 'app/web/index.html').as_uri())
        await page.wait_for_function('vdReady && api !== null')
        article = api.save_article('', '公式字号回归', '', '', '', '短公式\n\n$$'+SHORT+'$$\n\n长公式\n\n$$'+LONG+'$$\n\n行内分式 $\\frac{a}{b}$ 与正文。', 'wild', '', True)
        await page.evaluate('(rel)=>{setPage("write");return loadArticle(rel);}', article['rel'])
        await page.wait_for_function('document.querySelectorAll("#vditor [data-math] .katex").length >= 3')
        fonts = await page.evaluate('Array.from(document.querySelectorAll("#vditor [data-math] .katex")).map(n=>getComputedStyle(n).fontSize)')
        assert fonts == ['18px','18px','16px'], fonts
        check('editor font size is independent of formula length')
        await page.wait_for_function('document.getElementById("preview").contentDocument.images.length >= 3 && Array.from(document.getElementById("preview").contentDocument.images).every(i=>i.complete)', timeout=15000)
        metrics = await page.evaluate('Array.from(document.getElementById("preview").contentDocument.images).slice(0,2).map(i=>({width:i.getBoundingClientRect().width,height:i.getBoundingClientRect().height,naturalWidth:i.naturalWidth,scale:i.getBoundingClientRect().width/i.naturalWidth,scrollWidth:i.parentElement.scrollWidth,containerWidth:i.parentElement.clientWidth}))')
        assert metrics[1]['height'] > metrics[0]['height'] * 2, metrics
        assert all(abs(item['scale'] - 1/3) < .002 for item in metrics), metrics
        assert metrics[1]['width'] <= 320, metrics
        (OUT / 'after-metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
        await page.screenshot(path=str(OUT / 'fixed-writing.png'))
        check('preview keeps image density and wraps long formulas without shrinking')

        await page.click('#btnSource')
        baseline = '前段保留。\n\n后段保留。'
        await page.fill('#sourceEditor', baseline)
        await page.evaluate('()=>{const e=document.getElementById("sourceEditor");e.focus();e.setSelectionRange(6,6);}')
        await page.get_by_title('独立公式 $$…$$', exact=True).click()
        await page.fill('#formulaSource', r'\frac{a}{b}')
        await page.wait_for_function('formulaValid')
        await page.click('#btnApplyFormula')
        inserted = await page.evaluate('getMd()')
        assert r'\frac{a}{b}' in inserted and '前段保留' in inserted and '后段保留' in inserted, inserted
        await page.keyboard.press('Control+z')
        assert await page.evaluate('getMd()') == baseline
        check('insertion preserves surrounding text and native undo')

        await page.fill('#sourceEditor', '前段保留。\n\n$$\nx=x+x\n$$\n\n后段保留。')
        await page.evaluate('()=>{const e=document.getElementById("sourceEditor");const p=e.value.indexOf("x=x");e.focus();e.setSelectionRange(p+2,p+2);}')
        await page.keyboard.press('Control+Shift+m')
        assert await page.input_value('#formulaSource') == 'x=x+x'
        await page.fill('#formulaSource', 'x=y+y')
        await page.keyboard.press('Control+Enter')
        revised = await page.evaluate('getMd()')
        assert revised.count('$$') == 2 and 'x=y+y' in revised and 'x=x+x' not in revised, revised
        check('source mode updates the existing formula in place')

        await page.click('#btnIR')
        await page.wait_for_selector('#vditor [data-math="x=y+y"]')
        await page.locator('#vditor [data-math="x=y+y"]').dblclick()
        await page.wait_for_selector('#formulaMask:not(.hidden)', timeout=5000)
        await page.fill('#formulaSource', 'x=z+z')
        await page.click('#btnApplyFormula')
        revised = await page.evaluate('getMd()')
        assert revised.count('$$') == 2 and 'x=z+z' in revised and '前段保留' in revised and '后段保留' in revised, revised
        check('instant render mode edits a block formula without losing paragraphs')
        await page.wait_for_timeout(300)
        await page.keyboard.press('Control+z')
        undo = await page.evaluate('getMd()')
        assert 'x=y+y' in undo and 'x=z+z' not in undo and '后段保留' in undo, undo
        check('instant render formula updates can be undone')

        await page.evaluate('setMd("前句 $a+b$ 后句。");')
        await page.wait_for_selector('#vditor [data-math="a+b"]')
        await page.locator('#vditor [data-math="a+b"]').dblclick()
        await page.wait_for_selector('#formulaMask:not(.hidden)', timeout=5000)
        await page.fill('#formulaSource', r'\frac{a}{b}')
        await page.keyboard.press('Control+Enter')
        revised = await page.evaluate('getMd()')
        assert r'$\frac{a}{b}$' in revised and '前句' in revised and '后句' in revised, revised
        check('instant render mode edits inline math without losing text')

        await page.evaluate('setMd("前句 x+y 后句。");')
        await page.evaluate('''() => {
          const node=document.querySelector('#vditor [contenteditable="true"] p').firstChild;
          const range=document.createRange(); range.setStart(node,3); range.setEnd(node,6);
          vditor.focus(); const selection=window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
          openFormula(false);
        }''')
        assert await page.input_value('#formulaSource') == 'x+y'
        await page.click('#btnApplyFormula')
        inserted = await page.evaluate('getMd()')
        assert inserted.count('x+y') == 1 and '$x+y$' in inserted and '后句' in inserted, inserted
        check('instant render insertion replaces selected source text')

        await page.evaluate('openFormula(true)')
        await page.fill('#formulaSource', r'\frac{')
        await page.wait_for_function('!formulaValid && document.getElementById("formulaError").textContent.length > 0')
        assert await page.is_disabled('#btnApplyFormula')
        await page.fill('#formulaSource', '')
        await page.get_by_role('button', name='多行对齐', exact=True).click()
        assert await page.evaluate('formulaValid'), await page.input_value('#formulaSource')
        await page.screenshot(path=str(OUT / 'formula-editor.png'))
        current = await page.evaluate('getMd()')
        await page.keyboard.press('Escape')
        assert await page.evaluate('getMd()') == current
        check('live validation, aligned preset and cancel preserve source')

        await page.evaluate('(md)=>setMd(md)', '$$'+SHORT+'$$\n\n$$'+LONG+'$$')
        await page.set_viewport_size({'width':760,'height':580})
        await page.wait_for_function('document.querySelectorAll("#vditor [data-math] .katex").length === 2')
        assert await page.evaluate('Array.from(document.querySelectorAll("#vditor [data-math] .katex")).every(n=>getComputedStyle(n).fontSize === "18px")')
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        check('narrow windows retain formula font size without page overflow')

        html = api.preview('短公式\n\n$$'+SHORT+'$$\n\n长公式\n\n$$'+LONG+'$$\n\n多行公式\n\n$$\\begin{aligned}a&=b+c\\\\d&=e+f\\end{aligned}$$', 'wechat', 'wild')['html']
        target = OUT / '公式字号修复预览.html'
        target.write_text('<!doctype html><meta charset="utf-8"><title>公式字号修复</title><style>body{margin:24px auto;max-width:400px;font:16px Microsoft YaHei;background:#e8e3d8}img{max-width:100%}</style>'+html, encoding='utf-8')
        await page.set_viewport_size({'width':720,'height':760})
        await page.goto(target.as_uri())
        await page.screenshot(path=str(OUT / 'fixed-reading.png'))
        assert not errors, errors
        check('formula comparison preview exports without JavaScript errors')
        await browser.close()
    (OUT / 'ui-checks.json').write_text(json.dumps({'passed':passed,'errors':errors}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
