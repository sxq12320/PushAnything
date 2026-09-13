# -*- coding: utf-8 -*-
"""toutiao_push.py — 头条号文章草稿：mp.toutiao.com 图文编辑器 + 存草稿按钮。"""
import browser

PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

TITLE_SEL = [
    'textarea[placeholder*="标题"]',
    'input[placeholder*="标题"]',
    '[class*="title"] textarea',
    '[class*="title"] input',
]
BODY_SEL = [
    '.ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"]',
    '[class*="editor"] [contenteditable="true"]',
]
IMG_BTN_SEL = [
    'button[aria-label*="图片"]',
    '[title="图片"]',
    'button:has-text("图片")',
    '[class*="toolbar"] :has-text("图片")',
]
DRAFT_BTN_SEL = [
    'button:has-text("存草稿")',
    '[class*="draft"]:has-text("存草稿")',
    'button:has-text("保存草稿")',
    'span:has-text("存草稿")',
]
SAVED_SEL = ['text=已保存', 'text=保存成功', 'text=草稿', '[class*="toast"]']


def push_draft(title, segments, headless=False, log=print):
    pw, ctx, page = browser.launch("toutiao", headless=headless)
    try:
        page.goto(PUBLISH_URL, wait_until="load", timeout=45000)
        body = browser.wait_editor(page, BODY_SEL, log)
        log("编辑器就绪")

        title_loc = browser.first_locator(page, TITLE_SEL, timeout=5000)
        if title_loc:
            title_loc.click()
            title_loc.fill(title)
            log("标题已填入")
        else:
            log("未找到标题框（仍继续填正文）")

        body.click()
        page.keyboard.press("End")
        browser.fill_segments(page, body, segments, log, IMG_BTN_SEL)

        # 点"存草稿"
        btn = browser.first_locator(page, DRAFT_BTN_SEL, timeout=8000)
        if not btn:
            raise RuntimeError("找不到「存草稿」按钮")
        btn.click()
        log("已点击「存草稿」")

        saved = browser.first_locator(page, SAVED_SEL, timeout=10000)
        if saved:
            log("检测到保存反馈")
        else:
            page.wait_for_timeout(3000)

        shot = browser.screenshot(page, "toutiao_done.png")
        log(f"完成截图: {shot}")
        return True
    finally:
        browser.stop(pw, ctx)
