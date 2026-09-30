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
import hmac
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jobs

VERSION = "1.3.0"
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

    def _send_html(self, code, html):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return False
        if not Handler.token:
            return True
        return hmac.compare_digest(self.headers.get("X-Token", "").encode(), Handler.token.encode())

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 <= n <= 8 * 1024 * 1024:
            raise ValueError("请求不能超过 8 MB")
        if not n:
            return {}
        try:
            value = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("请求正文必须是 JSON 对象")
            return value
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求正文不是有效的 JSON") from exc

    def log_message(self, *a):  # 静音默认访问日志
        pass

    # ---- 路由 ----
    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/m":      # 手机端静态页不鉴权；其内部 API 调用仍走 X-Token
            return self._send_html(200, _mobile_page())
        if not self._auth_ok():
            return self._send(401, {"ok": False, "err": "unauthorized"})
        if p in ("", "/api"):
            return self._send(200, _doc())
        if p == "/api/health":
            return self._send(200, {"ok": True, "version": VERSION})
        if p == "/api/articles":
            return self._send(200, {"ok": True, "articles": _list_articles()})
        if p == "/api/tasks":
            return self._send(200, {"ok": True, "tasks": jobs.queue.recent()})
        if p.startswith("/api/tasks/"):
            jid = p.rsplit("/", 1)[-1]
            j = jobs.queue.detail(jid)
            if not j:
                return self._send(404, {"ok": False, "err": "task not found"})
            return self._send(200, {"ok": True, "task": j})
        return self._send(404, {"ok": False, "err": "not found"})

    def do_POST(self):
        if not self._auth_ok():
            return self._send(401, {"ok": False, "err": "unauthorized"})
        p = self.path.split("?")[0].rstrip("/")
        try:
            data = self._body()
        except (TypeError, ValueError) as exc:
            return self._send(400, {"ok": False, "err": str(exc)})
        if p == "/api/article":
            return self._submit("article", data,
                                required=["title", "md"],
                                allow=["wechat", "zhihu", "toutiao"])
        if p == "/api/video":
            return self._submit("video", data,
                                required=["title", "video_path"],
                                allow=["toutiao", "zhihu"])
        if p == "/api/feishu":
            if not isinstance(data.get("title"), str) or not data["title"].strip():
                return self._send(400, {"ok": False, "err": "缺少字段: title"})
            data["_source"] = "api"
            job = jobs.queue.submit("feishu", data)
            if data.get("wait"):
                done = job.completed.wait(180)
                return self._send(200 if done else 202, {"ok": job.status == "done",
                                        "task": job.to_dict()})
            return self._send(200, {"ok": True, "task_id": job.id,
                                    "status": job.status})
        return self._send(404, {"ok": False, "err": "not found"})

    def _submit(self, kind, data, required, allow):
        for k in required:
            if not isinstance(data.get(k), str) or not data[k].strip():
                return self._send(400, {"ok": False, "err": f"缺少字段: {k}"})
        plats = data.get("platforms")
        if isinstance(plats, list):
            bad = [x for x in plats if not isinstance(x, str) or x not in allow]
            if bad:
                return self._send(400, {"ok": False,
                                        "err": f"不支持的平台: {bad}，可选 {allow}"})
            data["platforms"] = {x: True for x in plats}
        plats = data.get("platforms")
        if not isinstance(plats, dict) or any(p not in allow for p in plats):
            return self._send(400, {"ok": False, "err": "platforms 包含不支持的平台或格式错误"})
        if not any(plats.values()):
            return self._send(400, {"ok": False, "err": "platforms 不能为空"})

        data["_source"] = "api"
        job = jobs.queue.submit(kind, data)

        if data.get("wait"):
            done = job.completed.wait(600)
            return self._send(200 if done else 202, {"ok": job.status == "done",
                                    "task": job.to_dict()})
        return self._send(200, {"ok": True, "task_id": job.id,
                                "status": job.status})


def _mobile_page():
    """手机端页面（/m）。静态页本身不鉴权，API 调用仍走 X-Token。"""
    import os
    import paths
    p = os.path.join(paths.WEB_DIR, "mobile.html")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<h1>mobile.html missing</h1>"


def _list_articles():
    """手机端文章列表：扫 DRAFTS_DIR 下 .md + 同名 .json 元信息。"""
    import os
    import paths
    out = []
    for root, _dirs, files in os.walk(paths.DRAFTS_DIR):
        _dirs[:] = [directory for directory in _dirs if not directory.startswith(".") and directory != "assets"]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            md = os.path.join(root, fn)
            slug = os.path.splitext(fn)[0]
            folder = os.path.relpath(root, paths.DRAFTS_DIR)
            folder = "" if folder == "." else folder.replace("\\", "/")
            rel = f"{folder}/{slug}" if folder else slug
            meta_p = os.path.splitext(md)[0] + ".json"
            meta = {}
            try:
                with open(meta_p, encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass
            try:
                with open(md, encoding="utf-8") as handle:
                    md_txt = handle.read()
            except Exception:
                md_txt = ""
            out.append({"rel": rel, "title": meta.get("title") or slug,
                        "folder": folder, "md": md_txt, "base_dir": root,
                        "author": meta.get("author", ""),
                        "digest": meta.get("digest", ""),
                        "cover_path": meta.get("cover_path", ""),
                        "style": meta.get("style", ""),
                        "mtime": os.path.getmtime(md)})
    out.sort(key=lambda a: a["mtime"], reverse=True)
    return out


def start(port, token="", lan=False):
    global _server
    if _server:
        return _server
    Handler.token = token or ""
    host = "0.0.0.0" if lan else "127.0.0.1"
    _server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _server
