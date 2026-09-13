# -*- coding: utf-8 -*-
"""
browser.py — Playwright 共享工具：持久化 Edge 上下文、登录等待、
富文本编辑器粘贴/插图。
"""
import os
import re
import time
from playwright.sync_api import sync_playwright

import paths

PROFILE_ROOT = paths.PROFILES_DIR
SHOT_DIR = paths.ASSETS_DIR


def launch(platform: str, headless: bool = False):
    """启动持久化 Edge 上下文。返回 (pw, ctx, page)。"""
    pw = sync_playwright().start()
    profile = os.path.join(PROFILE_ROOT, platform)
    os.makedirs(profile, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        profile,
        channel="msedge",
        headless=headless,
        viewport={"width": 1280, "height": 860},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, ctx, page


def stop(pw, ctx):
    try:
        ctx.close()
    finally:
        pw.stop()


def first_locator(page, selectors, timeout=8000):
    """返回第一个可见的 locator；都不可见返回 None。"""
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                pass
        page.wait_for_timeout(400)
    return None


def wait_editor(page, editor_selectors, log, timeout_ms=300000):
    """等编辑器出现；若未登录，等用户在弹出的窗口里手动登录。"""
    deadline = time.time() + timeout_ms / 1000
    logged_tip = False
    while time.time() < deadline:
        for sel in editor_selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                pass
        if not logged_tip:
            log("未检测到编辑器，可能未登录 —— 请在打开的浏览器窗口中登录，登录后自动继续")
            logged_tip = True
        page.wait_for_timeout(1500)
    raise RuntimeError("等待编辑器超时（5分钟），请检查登录状态后重试")


_PASTE_JS = """(html) => {
    const dt = new DataTransfer();
    dt.setData('text/html', html);
    dt.setData('text/plain', html.replace(/<[^>]+>/g, ''));
    const ev = new ClipboardEvent('paste', {
        clipboardData: dt, bubbles: true, cancelable: true
    });
    document.activeElement.dispatchEvent(ev);
}"""

_CLIP_WRITE_JS = """async (html) => {
    const item = new ClipboardItem({
        'text/html': new Blob([html], {type: 'text/html'}),
        'text/plain': new Blob([html.replace(/<[^>]+>/g, '')], {type: 'text/plain'})
    });
    await navigator.clipboard.write([item]);
}"""


def _content_len(loc):
    try:
        return len(loc.inner_text() or "")
    except Exception:
        return -1


def paste_html(page, body_loc, html: str):
    """向 contenteditable 粘贴 HTML：先试合成事件，不生效再走真实剪贴板。"""
    before = _content_len(body_loc)
    page.evaluate(_PASTE_JS, html)
    page.wait_for_timeout(700)
    after = _content_len(body_loc)
    if after >= 0 and after != before:
        return "synthetic"

    # 兜底：真实剪贴板 + Ctrl+V
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        page.evaluate(_CLIP_WRITE_JS, html)
        body_loc.click()
        page.keyboard.press("Control+V")
        page.wait_for_timeout(700)
        if _content_len(body_loc) != before:
            return "clipboard"
    except Exception:
        pass

    # 最后兜底：纯文本键入
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'</p>\s*<p[^>]*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    page.keyboard.insert_text(text)
    page.wait_for_timeout(300)
    return "typein"


def fill_segments(page, body_loc, segments, log,
                  img_button_selectors, img_input_wait_ms=15000):
    """按段落流填充正文：html 段粘贴，image 段走编辑器上传。"""
    body_loc.click()
    page.wait_for_timeout(300)
    for i, seg in enumerate(segments):
        if seg["type"] == "html":
            mode = paste_html(page, body_loc, seg["html"])
            log(f"  文本段 {i+1}/{len(segments)} 已粘贴({mode})")
        else:
            _upload_image(page, seg["path"], img_button_selectors,
                          img_input_wait_ms, log)
            log(f"  图片 {i+1}/{len(segments)} 已插入: {os.path.basename(seg['path'])}")


def _upload_image(page, path, btn_selectors, wait_ms, log):
    """定位编辑器图片上传 input 并塞入文件；找不到 input 则先点工具栏图片按钮。"""
    editor = page.locator('[contenteditable="true"]').first
    try:
        before = editor.locator("img").count()
    except Exception:
        before = 0

    inp = page.locator('input[type="file"][accept*="image"], '
                       'input[type="file"][accept*="jpg"], '
                       'input[type="file"]').last
    if not inp.count():
        btn = first_locator(page, btn_selectors, timeout=3000)
        if btn:
            btn.click()
            page.wait_for_timeout(800)
            inp = page.locator('input[type="file"]').last
    if not inp.count():
        raise RuntimeError("找不到图片上传入口（input[type=file]）")

    inp.set_input_files(path)

    # 等待编辑器内图片节点增加或上传进度结束
    deadline = time.time() + wait_ms / 1000
    while time.time() < deadline:
        try:
            if editor.locator("img").count() > before:
                return
        except Exception:
            pass
        page.wait_for_timeout(500)
    log("  图片上传超时（可能仍在后台上传），继续")


def screenshot(page, name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    p = os.path.join(SHOT_DIR, name)
    try:
        page.screenshot(path=p, full_page=False)
    except Exception:
        pass
    return p
