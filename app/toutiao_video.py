# -*- coding: utf-8 -*-
"""
toutiao_video.py — 头条号视频投稿（best-effort，需真实登录态下校正选择器）。
策略：打开视频发布页 → 塞视频文件 → 填标题/简介 → 有"存草稿"就点；
没有草稿入口则保留窗口给用户手动发布（视频草稿机制各平台不统一，不替用户点发布）。
"""
import browser
from runner import video_handler

URL_CANDIDATES = [
    "https://mp.toutiao.com/profile_v4/xigua/upload-video",
    "https://mp.toutiao.com/profile_v4/video/publish",
    "https://mp.toutiao.com/profile_v4/index",
]

FILE_INPUT_SEL = ['input[type="file"][accept*="video"]', 'input[type="file"]']
TITLE_SEL = [
    'input[placeholder*="标题"]', 'textarea[placeholder*="标题"]',
    '[class*="title"] input', '[class*="title"] textarea',
]
DESC_SEL = [
    'textarea[placeholder*="简介"]', 'textarea[placeholder*="描述"]',
    '[class*="desc"] textarea', 'div[contenteditable="true"]',
]
DRAFT_BTN_SEL = [
    'button:has-text("存草稿")', 'button:has-text("保存草稿")',
    'span:has-text("存草稿")',
]
READY_SEL = ['input[type="file"]', 'text=上传视频', 'text=选择视频',
             '[class*="upload"]']


@video_handler("toutiao")
def push(job, title, video_path, cover_path="", desc="", log=print):
    pw, ctx, page = browser.launch("toutiao", headless=False)
    keep_open = False
    try:
        opened = False
        for url in URL_CANDIDATES:
            try:
                page.goto(url, wait_until="load", timeout=30000)
            except Exception:
                continue
            if browser.first_locator(page, READY_SEL, timeout=6000):
                opened = True
                log(f"发布页就绪: {page.url}")
                break
        if not opened:
            log("未找到视频发布页，等待手动登录/导航（5分钟内）…")
            browser.wait_editor(page, READY_SEL, log, timeout_ms=300000)

        inp = browser.first_locator(page, FILE_INPUT_SEL, timeout=8000)
        if not inp:
            raise RuntimeError("找不到视频上传入口 input[type=file]")
        inp.set_input_files(video_path)
        log("视频文件已提交，等待上传处理…")
        page.wait_for_timeout(8000)

        t = browser.first_locator(page, TITLE_SEL, timeout=10000)
        if t:
            t.click(); t.fill(title); log("标题已填入")
        if desc:
            d = browser.first_locator(page, DESC_SEL, timeout=5000)
            if d:
                d.click(); d.fill(desc); log("简介已填入")

        shot = browser.screenshot(page, "toutiao_video.png")
        btn = browser.first_locator(page, DRAFT_BTN_SEL, timeout=5000)
        if btn:
            btn.click()
            page.wait_for_timeout(3000)
            log(f"已点击「存草稿」 截图:{shot}")
            return {"ok": True}
        log(f"未找到存草稿入口，窗口保留请手动发布 截图:{shot}")
        keep_open = True  # 留给用户手动点发布
        return {"ok": True, "note": "已填好内容，窗口保留待手动发布"}
    finally:
        if not keep_open:
            browser.stop(pw, ctx)
