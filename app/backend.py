# -*- coding: utf-8 -*-
"""
backend.py — pywebview js_api：文章管理、预览、封图、三平台上传。
"""
import os
import re
import json
import time
import threading

import webview

import mdconvert
import zhihu_push
import toutiao_push
import paths
import jobs
import feishu_sync

BASE_DIR = paths.ROOT
DRAFTS_DIR = paths.DRAFTS_DIR
CONFIG_PATH = paths.CONFIG_PATH
FONT_R = "C:/Windows/Fonts/msyh.ttc"
FONT_B = "C:/Windows/Fonts/msyhbd.ttc"

DEFAULT_CONFIG = {
    "author": "人间旁听生",
    "wechat_config": r"C:\Users\33836\media\wx_config.json",
    "cover_tag": "深度观察",
    "cover_source": "",
    "api_enabled": True,
    "api_port": 8737,
    "api_token": "",
    "api_lan": True,
    "wechat_style": "red",
    "feishu_enabled": False,
    "feishu_app_id": "",
    "feishu_app_secret": "",
    "feishu_folder_token": "",
    "data_dir": "",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _slug(name):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", (name or "").strip())[:60]
    return s or "untitled"


def _rel_parts(rel):
    """'文件夹/slug' 或 'slug' -> (folder, slug)，逐段净化防路径逃逸。"""
    parts = [p for p in (rel or "").replace("\\", "/").split("/") if p.strip()]
    parts = [_slug(p) for p in parts]
    if not parts:
        return "", "untitled"
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], parts[-1]


def _paths(rel):
    """rel -> (md_path, meta_path)，保证落在 DRAFTS_DIR 内。"""
    folder, slug = _rel_parts(rel)
    d = os.path.join(DRAFTS_DIR, folder) if folder else DRAFTS_DIR
    return (os.path.join(d, slug + ".md"), os.path.join(d, slug + ".json"))


def _folder_dir(folder):
    if not folder:
        return DRAFTS_DIR
    return os.path.join(DRAFTS_DIR, _slug(folder))


class Api:
    def __init__(self):
        self._window = None
        self._busy = False
        self._ui_job_id = None
        jobs.queue.add_listener(self._on_job_event)

    def bind(self, window):
        self._window = window

    # ---- 无边框窗口控制 ----

    def win_minimize(self):
        if self._window:
            self._window.minimize()

    def win_toggle_max(self):
        if not self._window:
            return
        if getattr(self, "_maxed", False):
            self._window.restore()
        else:
            self._window.maximize()
        self._maxed = not getattr(self, "_maxed", False)

    def win_close(self):
        if self._window:
            self._window.destroy()

    def win_geom(self):
        """当前窗口几何（物理像素）+ 是否最大化，供前端拖拽缩放。"""
        w = self._window
        if not w:
            return {}
        try:
            return {"x": w.x, "y": w.y, "w": w.width, "h": w.height,
                    "maxed": bool(getattr(self, "_maxed", False))}
        except Exception:
            return {}

    def _unmax(self):
        if getattr(self, "_maxed", False):
            try:
                self._window.restore()
            except Exception:
                pass
            self._maxed = False

    def win_rect(self, x, y, w, h):
        """贴边布局：设窗口位置与尺寸（逻辑像素）。"""
        if not self._window:
            return
        self._unmax()
        w = max(int(w), 560)
        h = max(int(h), 420)
        self._window.move(int(x), int(y))
        self._window.resize(int(w), int(h))

    def win_resize(self, w, h, dir=""):
        """拖边缩放：单次 SetWindowPos，fix_point 钉住对侧边缘。"""
        if not self._window:
            return
        self._unmax()
        w = max(int(w), 560)
        h = max(int(h), 420)
        from webview.platforms.winforms import FixPoint
        dir = str(dir)
        fx = FixPoint.EAST if "w" in dir else FixPoint.WEST
        fy = FixPoint.SOUTH if "n" in dir else FixPoint.NORTH
        self._window.resize(w, h, fix_point=fx | fy)

    def _on_job_event(self, kind, job, msg):
        """队列事件 -> 前端。API 来源任务带前缀。"""
        if kind == "log":
            prefix = ("" if job.source == "ui"
                      else f"[{job.source.upper()}] ")
            self._emit("log", prefix + str(msg))
        elif kind == "done":
            if job.source == "ui" and job.id == self._ui_job_id:
                self._ui_job_id = None
                self._emit("done", job.results)
            elif job.source != "ui":
                ok = job.status == "done"
                self._emit("log",
                           f"[{job.source.upper()}] 任务 {job.id} "
                           f"{'完成' if ok else '失败'}")
                self._emit("refresh", None)

    def _emit(self, kind, data):
        if self._window:
            try:
                self._window.evaluate_js(
                    "window.onBackendEvent(%s)" % json.dumps(
                        {"kind": kind, "data": data}, ensure_ascii=False))
            except Exception:
                pass

    def _log(self, msg):
        self._emit("log", msg)

    # ---------- 目录管理 ----------

    def list_folders(self):
        """草稿目录下的子文件夹 + 文章数。"""
        out = []
        for name in sorted(os.listdir(DRAFTS_DIR)):
            d = os.path.join(DRAFTS_DIR, name)
            if os.path.isdir(d):
                n = sum(1 for f in os.listdir(d) if f.endswith(".md"))
                out.append({"name": name, "count": n})
        return out

    def create_folder(self, name):
        folder = _slug(name)
        os.makedirs(_folder_dir(folder), exist_ok=True)
        return {"folder": folder}

    def rename_folder(self, old, new):
        old_d = _folder_dir(old)
        new_d = _folder_dir(new)
        if os.path.isdir(old_d) and not os.path.exists(new_d):
            os.rename(old_d, new_d)
        return {"folder": _slug(new)}

    def delete_folder(self, name):
        """删除文件夹：里面文章挪回根目录，不丢稿。"""
        d = _folder_dir(name)
        if not os.path.isdir(d) or d == DRAFTS_DIR:
            return False
        for fn in os.listdir(d):
            src = os.path.join(d, fn)
            dst = os.path.join(DRAFTS_DIR, fn)
            if os.path.exists(dst):
                base, ext = os.path.splitext(fn)
                i = 2
                while os.path.exists(os.path.join(DRAFTS_DIR, f"{base}_{i}{ext}")):
                    i += 1
                dst = os.path.join(DRAFTS_DIR, f"{base}_{i}{ext}")
            os.rename(src, dst)
        os.rmdir(d)
        return True

    def move_article(self, rel, folder):
        """把文章移进文件夹（folder="" 表示根目录）。"""
        md_p, meta_p = _paths(rel)
        if not os.path.exists(md_p):
            return {"ok": False}
        _, slug = _rel_parts(rel)
        d = _folder_dir(folder)
        os.makedirs(d, exist_ok=True)
        new_rel = ((_slug(folder) + "/") if folder else "") + slug
        for p in (md_p, meta_p):
            if os.path.exists(p):
                dst = os.path.join(d, os.path.basename(p))
                os.replace(p, dst)
        return {"ok": True, "rel": new_rel}

    # ---------- 文章 CRUD ----------

    def list_articles(self):
        """全部文章（含子文件夹），rel 唯一标识。"""
        out = []

        def scan(d, folder):
            if not os.path.isdir(d):
                return
            for fn in os.listdir(d):
                if not fn.endswith(".md"):
                    continue
                slug = fn[:-3]
                meta = {}
                mp = os.path.join(d, slug + ".json")
                if os.path.exists(mp):
                    try:
                        meta = json.load(open(mp, encoding="utf-8"))
                    except Exception:
                        pass
                out.append({
                    "slug": slug,
                    "rel": (folder + "/" if folder else "") + slug,
                    "folder": folder,
                    "title": meta.get("title", slug),
                    "style": meta.get("style", ""),
                    "feishu": bool(meta.get("feishu_token")),
                    "feishu_url": meta.get("feishu_url", ""),
                    "mtime": os.path.getmtime(os.path.join(d, fn)),
                })

        scan(DRAFTS_DIR, "")
        for f in self.list_folders():
            scan(os.path.join(DRAFTS_DIR, f["name"]), f["name"])
        out.sort(key=lambda x: -x["mtime"])
        return out

    def load_article(self, rel):
        md_p, meta_p = _paths(rel)
        if not os.path.exists(md_p):
            return None
        md = open(md_p, encoding="utf-8").read()
        meta = {}
        if os.path.exists(meta_p):
            try:
                meta = json.load(open(meta_p, encoding="utf-8"))
            except Exception:
                pass
        folder, slug = _rel_parts(rel)
        return {"slug": slug, "rel": rel, "folder": folder, "md": md,
                "base_dir": os.path.join(DRAFTS_DIR, folder) if folder else DRAFTS_DIR,
                "title": meta.get("title", ""),
                "author": meta.get("author", load_config()["author"]),
                "digest": meta.get("digest", ""),
                "style": meta.get("style", ""),
                "feishu_url": meta.get("feishu_url", ""),
                "cover_path": meta.get("cover_path", "")}

    def save_article(self, rel, title, author, digest, cover_path, md,
                     style="", folder="", autosave=False):
        old_folder, old_slug = _rel_parts(rel or title)
        folder = _slug(folder) if folder else old_folder
        new_rel = (folder + "/" if folder else "") + old_slug
        md_p, meta_p = _paths(new_rel)
        os.makedirs(os.path.dirname(md_p), exist_ok=True)

        with open(md_p, "w", encoding="utf-8") as f:
            f.write(md or "")
        meta = {}
        if os.path.exists(meta_p):
            try:
                meta = json.load(open(meta_p, encoding="utf-8"))
            except Exception:
                pass
        meta.update({"title": title, "author": author, "digest": digest,
                     "cover_path": cover_path, "saved": time.time()})
        if style:
            meta["style"] = style
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        cfg = load_config()
        feishu_queued = False
        if (not autosave and cfg.get("feishu_enabled")
                and feishu_sync.configured(cfg)):
            jobs.queue.submit("feishu", {
                "slug": new_rel, "title": title, "md": md or "",
                "_source": "feishu"})
            feishu_queued = True
        return {"slug": old_slug, "rel": new_rel, "feishu_queued": feishu_queued}

    def delete_article(self, rel):
        md_p, meta_p = _paths(rel)
        for p in (md_p, meta_p):
            if os.path.exists(p):
                os.remove(p)
        return True

    # ---------- 预览 / 封图 ----------

    def preview(self, md, platform, theme=""):
        try:
            if platform == "wechat":
                return {"html": mdconvert.style_for_wechat(
                    md, DRAFTS_DIR, FONT_R, FONT_B,
                    theme or load_config().get("wechat_style") or
                    mdconvert.DEFAULT_THEME)}
            return {"html": mdconvert.richtext_html(md)}
        except Exception as e:
            return {"html": f"<p style='color:red'>预览失败: {e}</p>"}

    def wechat_themes(self):
        return mdconvert.theme_names()

    def pick_image(self):
        r = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("图片文件 (*.png;*.jpg;*.jpeg;*.gif;*.webp)", "所有文件 (*.*)"))
        return r[0] if r else ""

    def save_pasted_image(self, rel, data_url):
        """编辑器粘贴图片：存到文章目录 assets/ 下，返回可写进 md 的 src。
        已保存文章用相对路径（随文章走），未保存文章用绝对路径。"""
        import base64
        m = re.match(r"data:image/(\w+);base64,(.*)$", data_url or "", re.S)
        if not m:
            return {"ok": False, "msg": "不是图片数据"}
        ext = m.group(1).lower().replace("jpeg", "jpg")
        try:
            raw = base64.b64decode(m.group(2))
        except Exception:
            return {"ok": False, "msg": "图片解码失败"}
        folder, _ = _rel_parts(rel or "")
        base = _folder_dir(folder) if rel else DRAFTS_DIR
        adir = os.path.join(base, "assets")
        os.makedirs(adir, exist_ok=True)
        stem = "pasted_" + time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(adir, stem + "." + ext)
        i = 2
        while os.path.exists(path):
            path = os.path.join(adir, f"{stem}_{i}.{ext}")
            i += 1
        with open(path, "wb") as f:
            f.write(raw)
        src = ("assets/" + os.path.basename(path)) if rel \
            else path.replace("\\", "/")
        return {"ok": True, "src": src}

    def pick_json(self):
        r = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("JSON 文件 (*.json)", "所有文件 (*.*)"))
        return r[0] if r else ""

    def pick_dir(self):
        r = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return r[0] if r else ""

    def set_data_dir(self, path):
        """切换数据目录：迁移 drafts/profiles/assets/history.json，写配置，重启生效。"""
        import shutil
        path = (path or "").strip()
        if not path:
            return {"ok": False, "msg": "未选择目录"}
        new_dir = os.path.abspath(path)
        old_dir = paths.DATA_DIR
        if os.path.normcase(new_dir) == os.path.normcase(old_dir):
            return {"ok": True, "msg": "已是当前数据目录", "data_dir": new_dir}
        try:
            os.makedirs(new_dir, exist_ok=True)
        except Exception as e:
            return {"ok": False, "msg": f"目录不可用: {e}"}

        moved, skipped = [], []
        for name in ("drafts", "profiles", "assets", "history.json"):
            src = os.path.join(old_dir, name)
            dst = os.path.join(new_dir, name)
            if not os.path.exists(src):
                continue
            if os.path.exists(dst):
                skipped.append(name)   # 目标已有同名数据，不覆盖
                continue
            try:
                shutil.move(src, dst)
                moved.append(name)
            except Exception as e:
                return {"ok": False,
                        "msg": f"迁移 {name} 失败: {e}（已迁移: {'、'.join(moved) or '无'}）"}

        cfg = load_config()
        cfg["data_dir"] = new_dir
        save_config(cfg)
        msg = "数据已迁移，重启软件后生效"
        if skipped:
            msg += f"；目标位置已存在 {('、'.join(skipped))}，未覆盖"
        return {"ok": True, "msg": msg, "data_dir": new_dir,
                "moved": moved, "skipped": skipped}

    def pick_video(self):
        r = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("视频文件 (*.mp4;*.mov;*.mkv;*.avi;*.flv;*.wmv;*.webm)",
                        "所有文件 (*.*)"))
        if not r:
            return {}
        p = r[0]
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        return {"path": p, "name": os.path.basename(p), "size": size}

    def upload_video(self, payload):
        if self._ui_job_id:
            return {"ok": False, "msg": "上一个上传任务还在进行中"}
        payload = dict(payload or {})
        vp = (payload.get("video_path") or "").strip()
        if not vp or not os.path.exists(vp):
            return {"ok": False, "msg": "请先选择视频文件"}
        if not (payload.get("title") or "").strip():
            return {"ok": False, "msg": "标题不能为空"}
        plats = payload.get("platforms", {})
        if not any(plats.values()):
            return {"ok": False, "msg": "请至少勾选一个平台"}
        payload["_source"] = "ui"
        job = jobs.queue.submit("video", payload)
        self._ui_job_id = job.id
        return {"ok": True, "task_id": job.id}

    def list_jobs(self):
        return jobs.queue.recent(30)

    def get_config(self):
        cfg = load_config()
        cfg["data_dir"] = paths.DATA_DIR   # 返回实际生效的数据目录
        return cfg

    def save_config(self, cfg):
        cur = load_config()
        cur.update(cfg or {})
        save_config(cur)
        return cur

    # ---------- 登录检查 ----------

    def check_login(self, platform):
        if self._busy:
            return {"ok": False, "msg": "有任务进行中"}
        threading.Thread(target=self._check_login, args=(platform,),
                         daemon=True).start()
        return {"ok": True}

    def _check_login(self, platform):
        import browser
        self._busy = True
        try:
            pw, ctx, page = browser.launch(platform)
            url = (zhihu_push.WRITE_URL if platform == "zhihu"
                   else toutiao_push.PUBLISH_URL)
            sels = (zhihu_push.BODY_SEL if platform == "zhihu"
                    else toutiao_push.BODY_SEL)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                browser.wait_editor(page, sels, self._log, timeout_ms=240000)
                self._emit("toast", f"{platform} 已登录，会话已保存")
            except RuntimeError:
                self._emit("toast", f"{platform} 登录超时未完成")
            browser.stop(pw, ctx)
        except Exception as e:
            self._emit("toast", f"检查登录失败: {e}")
        finally:
            self._busy = False

    # ---------- 上传 ----------

    def upload(self, payload):
        if self._ui_job_id:
            return {"ok": False, "msg": "上一个上传任务还在进行中"}
        if not (payload.get("title") or "").strip():
            return {"ok": False, "msg": "标题不能为空"}
        plats = payload.get("platforms", {})
        if not any(plats.values()):
            return {"ok": False, "msg": "请至少勾选一个平台"}
        payload = dict(payload)
        payload["_source"] = "ui"
        payload.setdefault("base_dir", DRAFTS_DIR)
        payload.setdefault("style",
                         load_config().get("wechat_style") or
                         mdconvert.DEFAULT_THEME)
        job = jobs.queue.submit("article", payload)
        self._ui_job_id = job.id
        return {"ok": True, "task_id": job.id}

    # ---------- 飞书备份 ----------

    def feishu_backup(self, payload):
        """手动备份当前文章到飞书。"""
        payload = dict(payload or {})
        if not (payload.get("title") or "").strip():
            return {"ok": False, "msg": "标题不能为空"}
        cfg = load_config()
        if not feishu_sync.configured(cfg):
            return {"ok": False, "msg": "先在设置里配置飞书凭证"}
        payload["_source"] = "feishu"
        job = jobs.queue.submit("feishu", payload)
        return {"ok": True, "task_id": job.id}

    def test_feishu(self, creds):
        """设置页"测试连接"：用表单里的临时凭证验证，不写配置。"""
        cfg = load_config()
        creds = creds or {}
        for k in ("feishu_app_id", "feishu_app_secret", "feishu_folder_token"):
            if creds.get(k):
                cfg[k] = creds[k]
        try:
            r = feishu_sync.test_connection(cfg)
            return {"ok": True,
                    "msg": f"连接成功，文件夹内有 {r['count']} 个文件"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    # ---------- HTTP API 状态 ----------

    def api_status(self):
        cfg = load_config()
        import api_server
        return {
            "enabled": bool(cfg.get("api_enabled")),
            "port": int(cfg.get("api_port", 8737)),
            "running": api_server._server is not None,
            "auth": bool(cfg.get("api_token")),
            "lan": bool(cfg.get("api_lan", True)),
        }

    # ---------- 手机端（局域网网页） ----------

    def _lan_ip(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))   # 不实际发包，只为拿到出口网卡 IP
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def mobile_url(self):
        cfg = load_config()
        url = f"http://{self._lan_ip()}:{int(cfg.get('api_port', 8737))}/m"
        return {"url": url, "token": cfg.get("api_token") or "",
                "lan": bool(cfg.get("api_lan", True)),
                "enabled": bool(cfg.get("api_enabled"))}

    def mobile_qr(self):
        """生成手机端地址的二维码，返回 PNG data URL。"""
        try:
            import base64, io
            import qrcode
            img = qrcode.make(self.mobile_url()["url"])
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return {"ok": True,
                    "qr": "data:image/png;base64," +
                          base64.b64encode(buf.getvalue()).decode()}
        except ImportError:
            return {"ok": False, "msg": "未安装 qrcode"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}
