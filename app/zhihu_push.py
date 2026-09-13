# -*- coding: utf-8 -*-
"""zhihu_push.py — 知乎文章草稿：zhuanlan.zhihu.com/write 自动填稿，依赖自动存草稿。"""
import browser

WRITE_URL = "https://zhuanlan.zhihu.com/write"

TITLE_SEL = [
    'textarea[placeholder*="标题"]',
    'input[placeholder*="标题"]',
    '.WriteIndex-titleInput input',
    '[class*="title"] input',
]
BODY_SEL = [
    '.public-DraftEditor-content',
    'div[contenteditable="true"]',
    '.ProseMirror',
]
IMG_BTN_SEL = [
    'button[aria-label*="图片"]',
    '[title="图片"]',
    'button:has-text("图片")',
    '[class*="toolbar"] button:has-text("图")',
]
SAVED_SEL = ['text=已保存', 'text=草稿已保存', 'text=保存成功',
             '[class*="save"]:has-text("保存")']


def push_draft(title, segments, headless=False, log=print):
    pw, ctx, page = browser.launch("zhihu", headless=headless)
    try:
        page.goto(WRITE_URL, wait_until="domcontentloaded", timeout=30000)
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

        # 知乎为自动保存：等待保存指示出现
        saved = browser.first_locator(page, SAVED_SEL, timeout=15000)
        if saved:
            log("检测到草稿已保存")
        else:
            page.wait_for_timeout(5000)
            log("未检测到保存指示，已等待额外5秒（知乎通常自动存草稿）")

        shot = browser.screenshot(page, "zhihu_done.png")
        log(f"完成截图: {shot}")
        return True
    finally:
        browser.stop(pw, ctx)
