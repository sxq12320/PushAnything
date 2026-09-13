# -*- coding: utf-8 -*-
"""
wechat_push.py — 推送草稿到公众号草稿箱（官方 draft/add API）。
逻辑移植自 ~/media/scripts/push_mp_draft.py，保持同一凭证文件与 relay 机制。
"""
import os
import re
import json
import base64
import tempfile
import requests

DEFAULT_CONFIG = r"C:\Users\33836\media\wx_config.json"


def load_config(path=None):
    p = path or DEFAULT_CONFIG
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _base(cfg):
    relay = (cfg.get("relay_url") or "").strip().rstrip("/")
    return f"{relay}/wx" if relay else "https://api.weixin.qq.com"


def _headers(cfg):
    h = {}
    if (cfg.get("relay_url") or "").strip() and cfg.get("relay_token"):
        h["X-Relay-Token"] = cfg["relay_token"]
    return h


def _token(cfg):
    url = (f"{_base(cfg)}/cgi-bin/token?grant_type=client_credential"
           f"&appid={cfg['mp_appid']}&secret={cfg['mp_appsecret']}")
    r = requests.get(url, headers=_headers(cfg), timeout=15).json()
    if "access_token" not in r:
        raise RuntimeError(f"获取 access_token 失败: {r}")
    return r["access_token"]


def _upload(cfg, token, image_path):
    url = f"{_base(cfg)}/cgi-bin/material/add_material?access_token={token}&type=image"
    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/png")}
        r = requests.post(url, files=files, headers=_headers(cfg), timeout=30).json()
    if "media_id" not in r:
        raise RuntimeError(f"上传素材失败: {r}")
    return r["media_id"], r.get("url", "")


_IMG_RE = re.compile(r'<img[^>]*src="(data:image/[^"]+|https?://[^"]+)"[^>]*>')


def _inline_images(cfg, token, content, log):
    """data:image 与 http(s) 图片统一上传为微信素材并替换 URL。"""
    def _rep(m):
        src = m.group(1)
        tmp = None
        try:
            if src.startswith("data:image/"):
                header, b64 = src.split(",", 1)
                fmt = header.split("/")[1].split(";")[0]
                fd, tmp = tempfile.mkstemp(suffix="." + fmt)
                with os.fdopen(fd, "wb") as f:
                    f.write(base64.b64decode(b64))
            else:
                r = requests.get(src, timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                fd, tmp = tempfile.mkstemp(suffix=".png")
                with os.fdopen(fd, "wb") as f:
                    f.write(r.content)
            _, url = _upload(cfg, token, tmp)
            log(f"  正文图片已上传 ({os.path.getsize(tmp)}B)")
            return f'<img src="{url}"/>'
        except Exception as e:
            log(f"  正文图片上传失败，已移除: {e}")
            return ""
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
    return _IMG_RE.sub(_rep, content)


def _cut(s, n):
    b = (s or "").encode("utf-8")
    return b[:n].decode("utf-8", "ignore") if len(b) > n else (s or "")


def push_draft(title, content_html, thumb_path, author="", digest="",
               config_path=None, log=print):
    cfg = load_config(config_path)
    token = _token(cfg)
    log("access_token 获取成功")

    if not thumb_path or not os.path.exists(thumb_path):
        raise RuntimeError(f"封面图不存在: {thumb_path}")
    thumb_id, _ = _upload(cfg, token, thumb_path)
    log("封面图上传成功")

    content = _inline_images(cfg, token, content_html, log)

    payload = {"articles": [{
        "title": title,
        "author": _cut(author or cfg.get("author", ""), 20),
        "digest": _cut(digest, 60),
        "content": content,
        "thumb_media_id": thumb_id,
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
        "copyright_type": 1,
    }]}
    url = f"{_base(cfg)}/cgi-bin/draft/add?access_token={token}"
    hdrs = dict(_headers(cfg))
    hdrs["Content-Type"] = "application/json; charset=utf-8"
    r = requests.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers=hdrs, timeout=60).json()
    if "media_id" not in r:
        raise RuntimeError(f"draft/add 失败: {r}")
    log(f"草稿推送成功 media_id={r['media_id']}")
    return r["media_id"]
