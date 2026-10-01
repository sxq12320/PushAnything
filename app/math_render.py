"""Offline KaTeX images with fixed CSS font sizes and explicit pixel density."""
import atexit
from concurrent.futures import Future
from dataclasses import dataclass
import functools
import os
from pathlib import Path
import queue
import tempfile
import threading

INLINE_FONT = 16
DISPLAY_FONT = 18
PIXEL_RATIO = 3
EXPORT_WIDTH = 320


class MathRenderError(ValueError):
    pass


class MathLayoutError(MathRenderError):
    pass


@dataclass(frozen=True)
class FormulaImage:
    path: str
    width: float
    height: float
    baseline: float
    font_size: int


class _Renderer:
    def __init__(self):
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        self.thread = None
        self.stopped = False
        self.directory = None

    def render(self, tex, display, max_width):
        with self.lock:
            if self.stopped:
                raise MathRenderError('公式渲染器已关闭')
            if self.thread is None:
                self.thread = threading.Thread(target=self._work, name='formula-renderer', daemon=True)
                self.thread.start()
            future = Future()
            self.jobs.put((future, tex, display, max_width))
        try:
            return future.result(timeout=35)
        except TimeoutError:
            future.cancel()
            raise MathRenderError('公式渲染超时，请减少公式复杂度后重试') from None

    def _work(self):
        playwright = browser = page = None
        try:
            while True:
                job = self.jobs.get()
                if job is None:
                    break
                future, tex, display, max_width = job
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    if page is None:
                        from playwright.sync_api import sync_playwright
                        from paths import WEB_DIR
                        playwright = sync_playwright().start()
                        browser = playwright.chromium.launch(channel='msedge', headless=True)
                        context = browser.new_context(viewport={'width':1800, 'height':900},
                            device_scale_factor=PIXEL_RATIO, offline=True)
                        context.route('**/*', lambda route: route.continue_()
                            if route.request.url.startswith(('file:', 'data:')) else route.abort())
                        page = context.new_page()
                        page.goto((Path(WEB_DIR) / 'math-render.html').as_uri())
                        if self.directory is None:
                            self.directory = tempfile.TemporaryDirectory(prefix='pushanything-formulas-')
                    font = DISPLAY_FONT if display else INLINE_FONT
                    info = page.evaluate('renderFormula', {'tex':tex, 'display':display,
                        'fontSize':font, 'maxWidth':max_width})
                    if not info['ok']:
                        error_type = MathLayoutError if info.get('kind') == 'layout' else MathRenderError
                        raise error_type(info['error'])
                    image = page.locator('#formula').screenshot(omit_background=True, timeout=8000)
                    from PIL import Image
                    from PIL.PngImagePlugin import PngInfo
                    import io
                    with Image.open(io.BytesIO(image)) as bitmap:
                        width, height = bitmap.width / PIXEL_RATIO, bitmap.height / PIXEL_RATIO
                        metadata = PngInfo()
                        for key, value in {'formula_font_px':font, 'formula_pixel_ratio':PIXEL_RATIO,
                                'formula_css_width':width, 'formula_css_height':height,
                                'formula_baseline':info['baseline']}.items():
                            metadata.add_text(key, str(value))
                        fd, path = tempfile.mkstemp(suffix='.png', dir=self.directory.name)
                        os.close(fd)
                        bitmap.save(path, pnginfo=metadata, dpi=(96 * PIXEL_RATIO, 96 * PIXEL_RATIO))
                    future.set_result(FormulaImage(path, width, height, info['baseline'], font))
                except MathRenderError as error:
                    future.set_exception(error)
                except Exception as error:
                    future.set_exception(MathRenderError('无法启动本地公式排版，请检查 Microsoft Edge：' + str(error)[:220]))
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    if playwright:
                        try:
                            playwright.stop()
                        except Exception:
                            pass
                    playwright = browser = page = None
        finally:
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
            if self.directory:
                self.directory.cleanup()

    def close(self):
        with self.lock:
            self.stopped = True
            thread = self.thread
            if thread:
                self.jobs.put(None)
        if thread:
            thread.join(timeout=5)


_renderer = _Renderer()
atexit.register(_renderer.close)


@functools.lru_cache(maxsize=128)
def render_formula(tex, display=False, max_width=None):
    tex = (tex or '').strip()
    if not tex:
        raise MathRenderError('请输入公式')
    if len(tex) > 16000:
        raise MathRenderError('公式过长，请拆分为多个公式')
    return _renderer.render(tex, bool(display), max_width)
