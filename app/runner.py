# -*- coding: utf-8 -*-
"""
runner.py — 任务执行器。按 job.kind 分发：
- article: Markdown/HTML 图文 → 公众号API + 知乎/头条浏览器填稿（+API来源自动飞书备份）
- video:   视频文件 → 各平台视频上传处理器（可插拔注册）
- feishu:  Markdown → 飞书云文档备份
"""
import os
import time

import paths
import mdconvert
import cover as cover_mod
import wechat_push
import zhihu_push
import toutiao_push
import feishu_sync

FONT_R = "C:/Windows/Fonts/msyh.ttc"
FONT_B = "C:/Windows/Fonts/msyhbd.ttc"

DEFAULT_CONFIG_PATH = paths.CONFIG_PATH


def _config():
    import json
    cfg = {
        "author": "人间旁听生",
        "wechat_config": r"C:\Users\33836\media\wx_config.json",
        "cover_tag": "深度观察",
        "cover_source": "",
    }
    try:
        cfg.update(json.load(open(DEFAULT_CONFIG_PATH, encoding="utf-8")))
    except Exception:
        pass
    return cfg


# ---------- 图文 ----------

def run_article(job):
    p = job.payload
    title = (p.get("title") or "").strip()
    author = (p.get("author") or "").strip() or _config()["author"]
    digest = (p.get("digest") or "").strip()
    md = p.get("md") or ""
    base_dir = p.get("base_dir") or paths.DRAFTS_DIR
    plats = p.get("platforms") or {}
    if isinstance(plats, list):
        plats = {k: True for k in plats}
    results = {}
    cfg = _config()

    # 封面：指定 > 自动生成
    cover_path = (p.get("cover_path") or "").strip()
    if plats.get("wechat"):
        if not cover_path or not os.path.exists(cover_path):
            job.log("[封面] 未选图，按标题自动生成…")
            cover_path = cover_mod.gen_cover(
                title, subtitle=digest[:30],
                tag=cfg["cover_tag"], source=cfg["cover_source"])
            job.log(f"[封面] 已生成: {cover_path}")

    if plats.get("wechat"):
        job.log("===== 公众号 =====")
        try:
            html = mdconvert.style_for_wechat(
                md, base_dir, FONT_R, FONT_B,
                theme=p.get("style") or cfg.get("wechat_style") or
                mdconvert.DEFAULT_THEME)
            mid = wechat_push.push_draft(
                title, html, cover_path, author, digest,
                config_path=cfg["wechat_config"], log=job.log)
            results["wechat"] = {"ok": True, "media_id": mid}
        except Exception as e:
            job.log(f"公众号失败: {e}")
            results["wechat"] = {"ok": False, "err": str(e)}

    need_rich = plats.get("zhihu") or plats.get("toutiao")
    if need_rich:
        try:
            job.log("解析正文段落流…")
            segs = mdconvert.make_segments(md, base_dir, FONT_R, FONT_B)
        except Exception as e:
            segs = None
            job.log(f"段落流解析失败: {e}")

        if plats.get("zhihu"):
            job.log("===== 知乎 =====")
            if not segs:
                results["zhihu"] = {"ok": False, "err": "段落流解析失败"}
            else:
                try:
                    zhihu_push.push_draft(title, segs, log=job.log)
                    results["zhihu"] = {"ok": True}
                except Exception as e:
                    job.log(f"知乎失败: {e}")
                    results["zhihu"] = {"ok": False, "err": str(e)}

        if plats.get("toutiao"):
            job.log("===== 头条 =====")
            if not segs:
                results["toutiao"] = {"ok": False, "err": "段落流解析失败"}
            else:
                try:
                    toutiao_push.push_draft(title, segs, log=job.log)
                    results["toutiao"] = {"ok": True}
                except Exception as e:
                    job.log(f"头条失败: {e}")
                    results["toutiao"] = {"ok": False, "err": str(e)}

    # API 投递的图文顺手备份飞书（UI 文章在"保存"时已备份）
    if (p.get("_source") != "ui" and cfg.get("feishu_enabled")
            and feishu_sync.configured(cfg)):
        job.log("===== 飞书备份 =====")
        try:
            r = feishu_sync.backup_article(cfg, title, md, log=job.log)
            results["feishu"] = {"ok": True, "url": r["url"]}
        except Exception as e:
            job.log(f"飞书备份失败: {e}")
            results["feishu"] = {"ok": False, "err": str(e)}

    if not results:
        raise RuntimeError("没有可执行的平台任务")
    return results


# ---------- 飞书备份 ----------

def run_feishu(job):
    """payload: {title, md, slug?} → 备份为飞书云文档并回写 meta。"""
    import json
    p = job.payload
    cfg = _config()
    title = (p.get("title") or "").strip() or "文章"
    md = p.get("md") or ""
    slug = (p.get("slug") or "").strip()

    old_token = None
    meta_p = os.path.join(paths.DRAFTS_DIR, slug + ".json") if slug else ""
    if meta_p and os.path.exists(meta_p):
        try:
            old_token = json.load(open(meta_p, encoding="utf-8")
                                  ).get("feishu_token")
        except Exception:
            pass

    r = feishu_sync.backup_article(cfg, title, md, log=job.log)

    if old_token and old_token != r["token"]:
        if feishu_sync.delete_doc(cfg, old_token):
            job.log("已清理旧版本备份")
    if meta_p:
        meta = {}
        if os.path.exists(meta_p):
            try:
                meta = json.load(open(meta_p, encoding="utf-8"))
            except Exception:
                pass
        meta.update({"feishu_token": r["token"], "feishu_url": r["url"],
                     "feishu_time": time.time()})
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    return {"feishu": {"ok": True, "url": r["url"]}}


# ---------- 视频 ----------

VIDEO_HANDLERS = {}


def video_handler(platform):
    def deco(fn):
        VIDEO_HANDLERS[platform] = fn
        return fn
    return deco


def run_video(job):
    """
    payload: {title, video_path, cover_path?, desc?, platforms:{toutiao:1,zhihu:1}}
    处理器模块在文件底部注册。
    """
    p = job.payload
    title = (p.get("title") or "").strip()
    video = (p.get("video_path") or "").strip()
    if not video or not os.path.exists(video):
        raise RuntimeError(f"视频文件不存在: {video}")
    plats = p.get("platforms") or {}
    if isinstance(plats, list):
        plats = {k: True for k in plats}

    # 确保处理器已注册
    import toutiao_video, zhihu_video  # noqa: F401

    results = {}
    for plat in plats:
        if not plats[plat]:
            continue
        handler = VIDEO_HANDLERS.get(plat)
        job.log(f"===== {plat} =====")
        if not handler:
            msg = f"平台 {plat} 暂无视频上传处理器"
            job.log(msg)
            results[plat] = {"ok": False, "err": msg}
            continue
        try:
            r = handler(job=job, title=title, video_path=video,
                        cover_path=p.get("cover_path") or "",
                        desc=p.get("desc") or "", log=job.log)
            results[plat] = r or {"ok": True}
        except Exception as e:
            job.log(f"{plat} 失败: {e}")
            results[plat] = {"ok": False, "err": str(e)}
    if not results:
        raise RuntimeError("没有可执行的平台任务")
    return results


# ---------- 分发 ----------

_RUNNERS = {"article": run_article, "video": run_video,
            "feishu": run_feishu}


def register(kind, fn):
    """外部模块可注册新的任务类型处理器。"""
    _RUNNERS[kind] = fn


def run_job(job):
    fn = _RUNNERS.get(job.kind)
    if not fn:
        raise RuntimeError(f"未知任务类型: {job.kind}")
    return fn(job)
