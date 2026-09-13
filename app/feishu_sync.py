# -*- coding: utf-8 -*-
"""
feishu_sync.py — 飞书云文档备份。

原理：本地 .md → medias/upload_all 上传为导入素材
     → drive/v1/import_tasks 导入为 docx 云文档（飞书官方 Markdown 导入）
     → 轮询任务拿到文档 token + 链接。

需要：自建应用（tenant_access_token），目标文件夹需把应用机器人加为协作者。
"""
import time

import requests

BASE = "https://open.feishu.cn"
_cache = {"token": None, "exp": 0.0}


def _tenant_token(cfg):
    app_id = (cfg.get("feishu_app_id") or "").strip()
    secret = (cfg.get("feishu_app_secret") or "").strip()
    if not app_id or not secret:
        raise RuntimeError("未配置飞书 App ID / App Secret（设置里填写）")
    if _cache["token"] and time.time() < _cache["exp"] - 120:
        return _cache["token"]
    r = requests.post(
        BASE + "/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": secret}, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"飞书鉴权失败: {d.get('msg') or d}")
    _cache["token"] = d["tenant_access_token"]
    _cache["exp"] = time.time() + int(d.get("expire", 7200))
    return _cache["token"]


def _h(cfg):
    return {"Authorization": "Bearer " + _tenant_token(cfg)}


def configured(cfg):
    return bool((cfg.get("feishu_app_id") or "").strip()
                and (cfg.get("feishu_app_secret") or "").strip()
                and (cfg.get("feishu_folder_token") or "").strip())


def test_connection(cfg):
    """校验凭证 + 文件夹对应用可见。返回 {"ok": True, "count": n}。"""
    folder = (cfg.get("feishu_folder_token") or "").strip()
    if not folder:
        raise RuntimeError("未配置飞书文件夹 Token")
    r = requests.get(BASE + "/open-apis/drive/v1/files",
                     params={"folder_token": folder, "page_size": 1},
                     headers=_h(cfg), timeout=15)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(
            f"飞书文件夹访问失败: {d.get('msg')} "
            "（文件夹需添加应用机器人为协作者）")
    files = (d.get("data") or {}).get("files") or []
    return {"ok": True, "count": len(files)}


def _upload_md(cfg, title, md):
    """md 文本 → 导入素材，返回 file_token。"""
    body = ("# %s\n\n%s" % (title or "文章", md or "")).encode("utf-8")
    name = (title or "文章") + ".md"
    r = requests.post(
        BASE + "/open-apis/drive/v1/medias/upload_all",
        data={"file_name": name, "parent_type": "ccm_import_open",
              "size": str(len(body))},
        files={"file": (name, body, "text/markdown")},
        headers=_h(cfg), timeout=60)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"飞书上传素材失败: {d.get('msg') or d}")
    return d["data"]["file_token"]


def _import_docx(cfg, file_token, title, folder):
    r = requests.post(
        BASE + "/open-apis/drive/v1/import_tasks",
        json={"file_extension": "md", "file_token": file_token,
              "type": "docx", "file_name": title or "文章",
              "point": {"mount_type": 1, "mount_key": folder}},
        headers=_h(cfg), timeout=30)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"飞书创建导入任务失败: {d.get('msg') or d}")
    return d["data"]["ticket"]


def _poll_import(cfg, ticket, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(BASE + "/open-apis/drive/v1/import_tasks/" + ticket,
                         headers=_h(cfg), timeout=15)
        d = r.json()
        if d.get("code") != 0:
            raise RuntimeError(f"飞书查询导入失败: {d.get('msg') or d}")
        res = (d.get("data") or {}).get("result") or {}
        status = res.get("job_status")
        if status == 0:
            return res
        if status not in (1, 2):  # 1 初始化 2 处理中
            raise RuntimeError(
                f"飞书导入失败: {res.get('job_error_msg') or res}")
        time.sleep(1.5)
    raise RuntimeError("飞书导入超时")


def delete_doc(cfg, token):
    """删除一篇 docx 文档（清理旧备份用）。失败静默。"""
    try:
        r = requests.delete(BASE + "/open-apis/drive/v1/files/" + token,
                            params={"type": "docx"},
                            headers=_h(cfg), timeout=15)
        return r.json().get("code") == 0
    except Exception:
        return False


def backup_article(cfg, title, md, log):
    """备份一篇 Markdown 为飞书云文档，返回 {"token":..,"url":..}。"""
    folder = (cfg.get("feishu_folder_token") or "").strip()
    if not folder:
        raise RuntimeError("未配置飞书文件夹 Token")
    log("上传 Markdown 素材…")
    ft = _upload_md(cfg, title, md)
    log("导入为云文档…")
    res = _poll_import(cfg, _import_docx(cfg, ft, title, folder))
    url = res.get("url") or ""
    log(f"飞书备份完成 {url}")
    return {"token": res.get("token"), "url": url}
