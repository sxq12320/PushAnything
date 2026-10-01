# -*- coding: utf-8 -*-
"""main.py — PushAnything 桌面端入口（pywebview）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import webview
import paths
from backend import Api, load_config

INDEX = os.path.join(paths.WEB_DIR, "index.html")


def start_api_server():
    import api_server
    cfg = load_config()
    if not cfg.get("api_enabled"):
        return None
    try:
        srv = api_server.start(int(cfg.get("api_port", 8737)),
                               cfg.get("api_token") or "",
                               lan=bool(cfg.get("api_lan", False)))
        print(f"[api] 本地接口已启动: http://127.0.0.1:{cfg.get('api_port', 8737)}/api")
        return srv
    except Exception as e:
        print(f"[api] 启动失败: {e}")
        return None


def main():
    start_api_server()
    api = Api()
    win = webview.create_window(
        "PushAnything",
        url=INDEX,
        js_api=api,
        width=1360,
        height=880,
        min_size=(720, 520),
        frameless=True,
        easy_drag=False,   # 关掉 JS 模拟拖动——它在任意位置拖都会移动窗口，
    )                      # 且抢占文本选择；标题栏拖动走 native_drag 原生循环
    api.bind(win)
    win.events.shown += lambda *a: api.setup_native()
    win.events.closing += api.request_close
    webview.start(private_mode=False, storage_path=os.path.join(paths.PROFILES_DIR, "desktop"))


def serve():
    """--serve: 无窗口纯服务模式（给外部工具调用）。"""
    import time
    start_api_server()
    print("[serve] 纯服务模式运行中，Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def check_math(output_path):
    """Headless diagnostics for the packaged fonts and formula renderer."""
    import json
    import math_render
    from pathlib import Path
    report = {'ok':False}
    try:
        short = math_render.render_formula('x=x+x', True)
        long = math_render.render_formula('x=' + '+'.join(['x'] * 45), True)
        wrapped = math_render.render_formula('x=' + '+'.join(['x'] * 45), True, max_width=320)
        aligned = math_render.render_formula(r'\begin{aligned}a&=b+c\\d&=e+f\end{aligned}', True)
        assert short.height == long.height
        assert wrapped.width <= 320 and wrapped.height > short.height
        assert aligned.height > short.height
        report.update(ok=True, fixed_font_size=True, offline_aligned=True,
            short_css_size=[short.width, short.height], long_css_size=[long.width, long.height],
            wrapped_css_size=[wrapped.width, wrapped.height])
    except Exception as error:
        report['error'] = str(error)
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__ == "__main__":
    try:
        if "--check-math" in sys.argv:
            sys.exit(check_math(sys.argv[sys.argv.index('--check-math') + 1]))
        elif "--serve" in sys.argv:
            serve()
        else:
            main()
    except Exception:
        import traceback
        log = os.path.join(paths.ROOT, "crash.log")
        with open(log, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n" % __import__("datetime").datetime.now())
            f.write(traceback.format_exc())
        raise
