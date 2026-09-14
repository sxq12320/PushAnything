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
                               lan=bool(cfg.get("api_lan", True)))
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
        min_size=(1100, 700),
        frameless=True,
    )
    api.bind(win)
    webview.start()


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


if __name__ == "__main__":
    try:
        if "--serve" in sys.argv:
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
