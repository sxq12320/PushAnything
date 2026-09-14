# -*- coding: utf-8 -*-
"""
api_server.py — 本地 HTTP API（127.0.0.1 仅本机）。其他软件/脚本通过它投递投稿任务。

接口：
  GET  /api                → 接口说明
  GET  /api/health         → {"ok":true,"version":...}
  GET  /api/tasks          → 最近任务列表
  GET  /api/tasks/<id>     → 任务详情（status/logs/results）
  POST /api/article        → 图文投稿
       {"title":..,"author":..,"digest":..,"md":..,"cover_path":..,
        "platforms":["wechat","zhihu","toutiao"], "wait":false}
  POST /api/video          → 视频投稿
       {"title":..,"video_path":..,"cover_path":..,"desc":..,
        "platforms":["toutiao","zhihu"], "wait":false}
  POST /api/feishu         → 飞书云文档备份
       {"title":..,"md":..,"slug":..(可选), "wait":false}

鉴权：config.json 里 api_token 非空时，请求需带 X-Token 头。
wait=true 时同步等待任务完成并返回 results（默认异步返回 task_id）。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jobs

VERSION = "1.0.0"
_server = None


def _doc():
    return {
        "name": "PushAnything API", "version": VERSION,
        "endpoints": {
            "GET /api": "接口说明",
            "GET /api/health": "存活检查",
            "GET /api/tasks": "最近任务",
            "GET /api/tasks/<id>": "任务详情",
            "POST /api/article": {
                "title": "必填", "md": "markdown正文",
                "author": "可选", "digest": "可选", "cover_path": "可选",
                "platforms": ["wechat", "zhihu", "toutiao"],
                "wait": "可选, true=同步等待完成",
            },
            "POST /api/video": {
                "title": "必填", "video_path": "必填,本地视频文件",
                "desc": "可选", "cover_path": "可选",
                "platforms": ["toutiao", "zhihu"],
                "wait": "可选",
            },
            "POST /api/feishu": {
                "title": "必填", "md": "markdown正文",
                "slug": "可选,回写本地文章meta",
                "wait": "可选",
            },
        },
    }


class Handler(BaseHTTPRequestHandler):
    token = ""

    # ---- 工具 ----
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        if not Handler.token:
            return True
        return self.headers.get("X-Token", "") == Handler.token

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, *a):  # 静音默认访问日志
        pass

    # ---- 路由 ----
    def do_GET(self):
        if not self._auth_ok():
            return self._send(401, {"ok": False, "err": "unauthorized"})
        p = self.path.split("?")[0].rstrip("/")
        if p in ("", "/api"):
            return self._send(200, _doc())
        if p == "/api/health":
            return self._send(200, {"ok": True, "version": VERSION})
        if p == "/api/tasks":
            return self._send(200, {"ok": True, "tasks": jobs.queue.recent()})
        if p.startswith("/api/tasks/"):
            jid = p.rsplit("/", 1)[-1]
            j = jobs.queue.get(jid)
            if not j:
                return self._send(404, {"ok": False, "err": "task not found"})
            return self._send(200, {"ok": True, "task": j.to_dict()})
        return self._send(404, {"ok": False, "err": "not found"})

    def do_POST(self):
        if not self._auth_ok():
            return self._send(401, {"ok": False, "err": "unauthorized"})
        p = self.path.split("?")[0].rstrip("/")
        data = self._body()
        if p == "/api/article":
            return self._submit("article", data,
                                required=["title"],
                                allow=["wechat", "zhihu", "toutiao"])
        if p == "/api/video":
            return self._submit("video", data,
                                required=["title", "video_path"],
                                allow=["toutiao", "zhihu"])
        if p == "/api/feishu":
            if not (data.get("title") or "").strip():
                return self._send(400, {"ok": False, "err": "缺少字段: title"})
            data["_source"] = "api"
            job = jobs.queue.submit("feishu", data)
            if data.get("wait"):
                import time
                t0 = time.time()
                while job.status in ("queued", "running") and time.time() - t0 < 180:
                    time.sleep(0.5)
                return self._send(200, {"ok": job.status == "done",
                                        "task": job.to_dict()})
            return self._send(200, {"ok": True, "task_id": job.id,
                                    "status": job.status})
        return self._send(404, {"ok": False, "err": "not found"})

    def _submit(self, kind, data, required, allow):
        for k in required:
            if not (data.get(k) or "").__str__().strip():
                return self._send(400, {"ok": False, "err": f"缺少字段: {k}"})
        plats = data.get("platforms")
        if isinstance(plats, list):
            bad = [x for x in plats if x not in allow]
            if bad:
                return self._send(400, {"ok": False,
                                        "err": f"不支持的平台: {bad}，可选 {allow}"})
            data["platforms"] = {x: True for x in plats}
        if not data.get("platforms"):
            return self._send(400, {"ok": False, "err": "platforms 不能为空"})

        data["_source"] = "api"
        job = jobs.queue.submit(kind, data)

        if data.get("wait"):
            import time
            t0 = time.time()
            while job.status in ("queued", "running") and time.time() - t0 < 600:
                time.sleep(0.5)
            return self._send(200, {"ok": job.status == "done",
                                    "task": job.to_dict()})
        return self._send(200, {"ok": True, "task_id": job.id,
                                "status": job.status})


def start(port, token=""):
    global _server
    if _server:
        return _server
    Handler.token = token or ""
    _server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _server
