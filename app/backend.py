# -*- coding: utf-8 -*-
"""
backend.py — pywebview js_api：文章管理、预览、封图、三平台上传。
"""
import os
import re
import json
import time
import threading
import functools
import html
import base64
from collections import deque

import storage
import image_store

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
    "api_lan": False,
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
    with storage.lock:
        storage.atomic_json(CONFIG_PATH, cfg)


def _slug(name):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", (name or "").strip())[:60]
    s = s.rstrip(". ") or "untitled"
    if s.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        s = "_" + s
    return s


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


def _locked(fn):
    @functools.wraps(fn)
    def call(*args, **kwargs):
        with storage.lock:
            return fn(*args, **kwargs)
    return call


def _unique_rel(folder, slug):
    prefix = (_slug(folder) + "/") if folder else ""
    rel = prefix + slug
    count = 2
    while any(os.path.exists(p) for p in _paths(rel)):
        rel = prefix + f"{slug}_{count}"
        count += 1
    return rel


class Api:
    def __init__(self):
        self._window = None
        self._busy = False
        self._close_allowed = False
        self._events = deque(maxlen=2000)
        self._event_lock = threading.Lock()
        jobs.queue.add_listener(self._on_job_event)

    def bind(self, window):
        self._window = window

    # ---- 无边框窗口控制 ----

    def _is_maxed(self):
        """真实窗口状态（含系统 Snap 造成的最大化）。"""
        try:
            import System.Windows.Forms as WF
            return self._window.native.WindowState == WF.FormWindowState.Maximized
        except Exception:
            return bool(getattr(self, "_maxed", False))

    def win_minimize(self):
        if self._window:
            self._window.minimize()

    def win_toggle_max(self):
        if not self._window:
            return
        if self._is_maxed():
            self._window.restore()
            self._maxed = False
        else:
            self._window.maximize()
            self._maxed = True

    def win_close(self):
        if self._window:
            self._close_allowed = True
            self._window.destroy()

    def request_close(self, *args):
        if self._close_allowed:
            return True
        self._emit("close", None)
        return False

    def win_geom(self):
        """当前窗口几何（物理像素）+ 是否最大化，供前端拖拽缩放。"""
        w = self._window
        if not w:
            return {}
        try:
            return {"x": w.x, "y": w.y, "w": w.width, "h": w.height,
                    "maxed": self._is_maxed()}
        except Exception:
            return {}

    def _unmax(self):
        if self._is_maxed():
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

    def setup_native(self):
        """窗口创建后补 Win32 样式：去掉 WS_POPUP、加回可缩放边框样式。
        frameless 的窗口对系统是"弹出窗"，Aero Snap/贴边吸附不生效；
        加回 WS_THICKFRAME 后视觉仍无边框（DWM 已把框架延伸进客户区），
        但系统 Snap、隐形缩放边框、任务栏窗口管理全部恢复。"""
        w = self._window
        if not w or not getattr(w, "native", None):
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = w.native.Handle.ToInt32()
            GWL_STYLE = -16
            WS_POPUP = 0x80000000
            WS_CAPTION = 0x00C00000      # WS_BORDER | WS_DLGFRAME
            WS_THICKFRAME = 0x00040000
            WS_MAXIMIZEBOX = 0x00010000
            WS_MINIMIZEBOX = 0x00020000
            getl = u.GetWindowLongPtrW if hasattr(u, "GetWindowLongPtrW") \
                else u.GetWindowLongW
            setl = u.SetWindowLongPtrW if hasattr(u, "SetWindowLongPtrW") \
                else u.SetWindowLongW
            style = getl(hwnd, GWL_STYLE)
            style &= ~(WS_POPUP | WS_CAPTION)
            style |= WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
            setl(hwnd, GWL_STYLE, style)
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                           0x0020 | 0x0002 | 0x0001 | 0x0004)
        except Exception:
            pass

    def native_drag(self, ratio=0.5):
        """标题栏拖动：转交系统原生移动循环（WM_NCLBUTTONDOWN/HTCAPTION），
        获得 Aero Snap：拖到屏幕顶部=最大化，左/右缘=半屏。
        ratio = 点击处在标题栏中的横向比例，用于最大化下先还原再拖动。"""
        w = self._window
        if not w:
            return
        import ctypes
        u = ctypes.windll.user32
        try:
            hwnd = w.native.Handle.ToInt32()
        except Exception:
            return
        if self._is_maxed():
            class _PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = _PT()
            u.GetCursorPos(ctypes.byref(pt))
            scale = (u.GetDpiForWindow(hwnd) or 96) / 96.0
            cx, cy = pt.x / scale, pt.y / scale
            self._unmax()
            r = max(0.0, min(1.0, float(ratio or 0.5)))
            w.move(int(cx - w.width * r), int(cy - 16))

        def _do():
            u.ReleaseCapture()
            u.SendMessageW(hwnd, 0xA1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION

        try:
            from System import Action
            w.native.Invoke(Action(_do))
        except Exception:
            _do()

    def _on_job_event(self, kind, job, msg):
        if kind == "log":
            prefix = "" if job.source == "ui" else f"[{job.source.upper()}] "
            self._emit("log", prefix + str(msg))
        elif kind == "done":
            self._emit("done", job.to_dict())
        elif kind == "status":
            self._emit("status", job.to_dict())

    def _emit(self, kind, data):
        # The worker never waits for the webview/UI thread to render a log line.
        with self._event_lock:
            self._events.append({"kind": kind, "data": data})

    def drain_events(self):
        with self._event_lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _log(self, msg):
        self._emit("log", msg)

    # ---------- 目录管理 ----------

    @_locked
    def list_folders(self):
        """草稿目录下的子文件夹 + 文章数。"""
        out = []
        for name in sorted(os.listdir(DRAFTS_DIR)):
            d = os.path.join(DRAFTS_DIR, name)
            if os.path.isdir(d) and not name.startswith(".") and name != "assets":
                n = sum(1 for f in os.listdir(d) if f.endswith(".md"))
                out.append({"name": name, "count": n})
        return out

    @_locked
    def create_folder(self, name):
        folder = _slug(name)
        os.makedirs(_folder_dir(folder), exist_ok=True)
        return {"folder": folder}

    def rename_folder(self, old, new):
        with storage.lock:
            if not old or not new:
                return {"ok": False, "msg": "文件夹名称不能为空"}
            old_d, new_d = _folder_dir(old), _folder_dir(new)
            if os.path.normcase(old_d) == os.path.normcase(new_d):
                return {"ok": True, "folder": _slug(new)}
            if os.path.exists(new_d):
                return {"ok": False, "msg": "已存在同名文件夹"}
            if not os.path.isdir(old_d):
                return {"ok": False, "msg": "文件夹不存在"}
            os.rename(old_d, new_d)
            for filename in os.listdir(new_d):
                document = os.path.join(new_d, filename)
                if filename.endswith(".md"):
                    with open(document, encoding="utf-8") as handle:
                        content = handle.read()
                    content = content.replace(old_d, new_d).replace(old_d.replace("\\", "/"), new_d.replace("\\", "/"))
                    storage.atomic_text(document, content)
                elif filename.endswith(".json"):
                    with open(document, encoding="utf-8") as handle:
                        meta = json.load(handle)
                    cover = meta.get("cover_path") or ""
                    meta["cover_path"] = cover.replace(old_d, new_d).replace(old_d.replace("\\", "/"), new_d.replace("\\", "/"))
                    storage.atomic_json(document, meta)
            return {"ok": True, "folder": _slug(new)}

    def delete_folder(self, name):
        with storage.lock:
            d = _folder_dir(name)
            if not name or not os.path.isdir(d):
                return {"ok": False, "msg": "文件夹不存在"}
            moved = {}
            for filename in os.listdir(d):
                if filename.endswith(".md"):
                    old_rel = _slug(name) + "/" + filename[:-3]
                    result = self.move_article(old_rel, "")
                    moved[old_rel] = result["rel"]
            # Retain orphan images and all unrelated contents instead of deleting them.
            trash = os.path.join(DRAFTS_DIR, ".trash")
            os.makedirs(trash, exist_ok=True)
            os.rename(d, os.path.join(trash, f"folder_{time.time_ns()}_{_slug(name)}"))
            return {"ok": True, "moved": moved}

    def move_article(self, rel, folder):
        with storage.lock:
            md_p, meta_p = _paths(rel)
            if not os.path.exists(md_p):
                return {"ok": False, "msg": "文章不存在"}
            old_folder, slug = _rel_parts(rel)
            if old_folder == (folder or ""):
                return {"ok": True, "rel": rel}
            new_rel = _unique_rel(folder, slug)
            new_md, new_meta = _paths(new_rel)
            os.makedirs(os.path.dirname(new_md), exist_ok=True)
            with open(md_p, encoding="utf-8") as handle:
                md = handle.read()
            md = image_store.relocate_markdown(md, os.path.dirname(md_p), os.path.dirname(new_md))
            storage.atomic_text(new_md, md)
            if os.path.exists(meta_p):
                with open(meta_p, encoding="utf-8") as handle:
                    meta = json.load(handle)
                cover_path = meta.get("cover_path") or ""
                if cover_path and os.path.isfile(cover_path):
                    cover = image_store.import_file(cover_path, os.path.dirname(new_md))
                    meta["cover_path"] = cover["path"]
                storage.atomic_json(new_meta, meta)
            os.remove(md_p)
            if os.path.exists(meta_p):
                os.remove(meta_p)
            return {"ok": True, "rel": new_rel}

    @_locked
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
                        with open(mp, encoding="utf-8") as handle:
                            meta = json.load(handle)
                    except Exception:
                        pass
                out.append({
                    "slug": slug,
                    "rel": (folder + "/" if folder else "") + slug,
                    "folder": folder,
                    "title": meta.get("title", slug),
                    "author": meta.get("author", ""),
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

    @_locked
    def load_article(self, rel):
        md_p, meta_p = _paths(rel)
        if not os.path.exists(md_p):
            return None
        with open(md_p, encoding="utf-8") as handle:
            md = handle.read()
        meta = {}
        if os.path.exists(meta_p):
            try:
                with open(meta_p, encoding="utf-8") as handle:
                    meta = json.load(handle)
            except Exception:
                pass
        folder, slug = _rel_parts(rel)
        return {"slug": slug, "rel": rel, "folder": folder, "md": md,
                "base_dir": os.path.join(DRAFTS_DIR, folder) if folder else DRAFTS_DIR,
                "title": meta.get("title", slug),
                "author": meta.get("author", load_config()["author"]),
                "digest": meta.get("digest", ""),
                "style": meta.get("style", ""),
                "feishu_url": meta.get("feishu_url", ""),
                "cover_path": meta.get("cover_path", "")}

    def save_article(self, rel, title, author, digest, cover_path, md,
                     style="", folder="", autosave=False):
        with storage.lock:
            title = (title or "").strip() or "无标题"
            if rel:
                old_folder, slug = _rel_parts(rel)
                new_rel = (old_folder + "/" if old_folder else "") + slug
            else:
                new_rel = _unique_rel(folder, _slug(title))
            md_p, meta_p = _paths(new_rel)
            meta = {}
            if os.path.exists(meta_p):
                with open(meta_p, encoding="utf-8") as handle:
                    meta = json.load(handle)
            meta.update({"title": title, "author": author, "digest": digest,
                         "cover_path": cover_path, "saved": time.time()})
            if style:
                meta["style"] = style
            storage.atomic_text(md_p, md or "")
            storage.atomic_json(meta_p, meta)
        cfg = load_config()
        feishu_queued = False
        if not autosave and cfg.get("feishu_enabled") and feishu_sync.configured(cfg):
            jobs.queue.submit("feishu", {"slug": new_rel, "title": title, "md": md or "", "_source": "feishu"})
            feishu_queued = True
        return {"slug": _rel_parts(new_rel)[1], "rel": new_rel, "feishu_queued": feishu_queued}

    def save_recovery(self, snapshot):
        with storage.lock:
            storage.atomic_json(os.path.join(paths.DATA_DIR, ".draft-recovery.json"), snapshot)
        return True

    def get_recovery(self):
        try:
            with open(os.path.join(paths.DATA_DIR, ".draft-recovery.json"), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def clear_recovery(self, session, revision):
        with storage.lock:
            snapshot = self.get_recovery()
            if snapshot and snapshot.get("session") == session and snapshot.get("revision") == revision:
                os.remove(os.path.join(paths.DATA_DIR, ".draft-recovery.json"))
        return True

    def delete_article(self, rel):
        with storage.lock:
            md_p, meta_p = _paths(rel)
            if not os.path.isfile(md_p):
                return {"ok": False, "msg": "文章不存在"}
            token = str(time.time_ns())
            folder = os.path.join(DRAFTS_DIR, ".trash", token)
            os.makedirs(folder, exist_ok=True)
            storage.atomic_json(os.path.join(folder, "restore.json"), {"rel": rel})
            for source in (md_p, meta_p):
                if os.path.isfile(source):
                    os.rename(source, os.path.join(folder, os.path.basename(source)))
            return {"ok": True, "token": token}

    def restore_article(self, token):
        if not re.fullmatch(r"[0-9]+", str(token)):
            return {"ok": False, "msg": "无效的恢复记录"}
        with storage.lock:
            directory = os.path.join(DRAFTS_DIR, ".trash", str(token))
            with open(os.path.join(directory, "restore.json"), encoding="utf-8") as handle:
                old_rel = json.load(handle)["rel"]
            folder, slug = _rel_parts(old_rel)
            new_rel = _unique_rel(folder, slug)
            new_md, new_meta = _paths(new_rel)
            os.makedirs(os.path.dirname(new_md), exist_ok=True)
            for destination in (new_md, new_meta):
                source = os.path.join(directory, slug + os.path.splitext(destination)[1])
                if os.path.isfile(source):
                    os.rename(source, destination)
            return {"ok": True, "rel": new_rel}

    def preview(self, md, platform, theme="", rel=""):
        try:
            base_dir = os.path.dirname(_paths(rel)[0]) if rel else DRAFTS_DIR
            if platform == "wechat":
                rendered = mdconvert.style_for_wechat(md, base_dir, FONT_R, FONT_B,
                    theme or load_config().get("wechat_style") or mdconvert.DEFAULT_THEME,
                    preview=True)
            else:
                rendered = mdconvert.richtext_html(md, preview=True)
                def embed(match):
                    src = match.group(1)
                    if not mdconvert.is_local(src):
                        return match.group(0)
                    try:
                        uri = mdconvert.path_to_data_uri(mdconvert.local_path_of(src, base_dir))
                        return match.group(0).replace(src, uri, 1)
                    except OSError:
                        return match.group(0)
                rendered = mdconvert._IMG_RE.sub(embed, rendered)
            return {"html": rendered}
        except Exception as exc:
            return {"html": "<p style='color:#c43b47'>预览失败: " + html.escape(str(exc)) + "</p>"}

    def wechat_themes(self):
        return mdconvert.theme_names()

    def pick_image(self):
        r = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("图片文件 (*.png;*.jpg;*.jpeg;*.gif;*.webp)", "所有文件 (*.*)"))
        return r[0] if r else ""

    def save_pasted_image(self, rel, data_url):
        match = re.match(r"data:image/[\w.+-]+;base64,(.*)$", data_url or "", re.S)
        if not match or len(match[1]) > image_store.MAX_BYTES * 4 // 3 + 8:
            return {"ok": False, "msg": "支持小于 40 MB 的图片"}
        try:
            raw = base64.b64decode(match[1], validate=True)
            base = os.path.dirname(_paths(rel)[0]) if rel else DRAFTS_DIR
            result = image_store.import_bytes(raw, base)
            if not rel:
                result["src"] = result["path"].replace("\\", "/")
            return result
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    def import_image(self, rel, path):
        try:
            base = os.path.dirname(_paths(rel)[0]) if rel else DRAFTS_DIR
            result = image_store.import_file(path, base)
            if not rel:
                result["src"] = result["path"].replace("\\", "/")
            return result
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

    def list_templates(self):
        try:
            with open(os.path.join(paths.DATA_DIR, "templates.json"), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return []

    def save_template(self, name, md, style="blue", rel=""):
        with storage.lock:
            templates = self.list_templates()
            entry = {"id": "custom_" + str(time.time_ns()), "name": (name or "").strip()[:60],
                     "description": "我的模板", "md": md or "", "style": style}
            if not entry["name"] or not entry["md"].strip():
                return {"ok": False, "msg": "模板名称和正文不能为空"}
            # Make custom templates independent of the source article's folder.
            if entry["md"]:
                base = os.path.dirname(_paths(rel)[0]) if rel else DRAFTS_DIR
                entry["md"] = image_store.relocate_markdown(entry["md"], base, paths.DATA_DIR)
                entry["md"] = re.sub(r'(!\[[^\]]*\]\()(<assets/[^>]+>|assets/[^)\s]+)([^)]*\))',
                    lambda m: m[1] + "<" + os.path.join(paths.DATA_DIR, m[2].strip("<>")).replace("\\", "/") + ">" + m[3], entry["md"])
            templates.append(entry)
            storage.atomic_json(os.path.join(paths.DATA_DIR, "templates.json"), templates)
            return {"ok": True, "template": entry}

    def delete_template(self, template_id):
        with storage.lock:
            templates = [t for t in self.list_templates() if t["id"] != template_id]
            storage.atomic_json(os.path.join(paths.DATA_DIR, "templates.json"), templates)
        return {"ok": True}

    def pick_json(self):
        r = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("JSON 文件 (*.json)", "所有文件 (*.*)"))
        return r[0] if r else ""

    def pick_dir(self):
        r = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return r[0] if r else ""

    def set_data_dir(self, path):
        import shutil
        if not path:
            return {"ok": False, "msg": "未选择目录"}
        new_dir, old_dir = os.path.abspath(path), os.path.abspath(paths.DATA_DIR)
        if os.path.normcase(new_dir) == os.path.normcase(old_dir):
            return {"ok": True, "msg": "已是当前数据目录", "data_dir": old_dir}
        common = os.path.normcase(os.path.commonpath([old_dir, new_dir])) if os.path.splitdrive(old_dir)[0] == os.path.splitdrive(new_dir)[0] else ""
        if common in (os.path.normcase(old_dir), os.path.normcase(new_dir)):
            return {"ok": False, "msg": "请选择当前数据目录之外的独立文件夹"}
        if any(os.path.exists(os.path.join(new_dir, name)) for name in ("drafts", "profiles", "assets", "history.json", "templates.json")):
            return {"ok": False, "msg": "目标目录已有软件数据，请选择空目录，以免混用文章与登录态"}
        try:
            os.makedirs(new_dir, exist_ok=True)
            probe = os.path.join(new_dir, ".pushanything-write-test")
            storage.atomic_text(probe, "ok")
            os.remove(probe)
            cfg = load_config()
            cfg["pending_data_dir"] = new_dir
            save_config(cfg)
            return {"ok": True, "msg": "已安排下次启动时迁移；当前继续保存到原目录，原始数据会保留", "data_dir": new_dir}
        except OSError as exc:
            return {"ok": False, "msg": f"目录不可用: {exc}"}

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
        return self._submit_ui("video", payload)

    def list_jobs(self):
        return jobs.queue.recent(30)

    def get_config(self):
        cfg = load_config()
        cfg["startup_warning"] = paths.STARTUP_WARNING
        cfg["active_data_dir"] = paths.DATA_DIR
        cfg["data_dir"] = cfg.get("pending_data_dir") or paths.DATA_DIR   # 返回实际生效的数据目录
        return cfg

    def save_config(self, cfg):
        cur = load_config()
        update = dict(cfg or {})
        if "api_port" in update:
            try:
                port = int(update["api_port"])
                if not 1024 <= port <= 65535:
                    raise ValueError()
                update["api_port"] = port
            except (TypeError, ValueError):
                return {"ok": False, "msg": "端口应为 1024–65535 的整数"}
        cur.update(update)
        save_config(cur)
        return cur

    # ---------- 登录检查 ----------

    def check_login(self, platform):
        if platform not in ("zhihu", "toutiao"):
            return {"ok": False, "msg": "不支持的平台"}
        if self._busy or any(j["status"] in ("running", "queued") for j in jobs.queue.recent()):
            return {"ok": False, "msg": "有任务进行中"}
        self._busy = True
        threading.Thread(target=self._check_login, args=(platform,),
                         daemon=True).start()
        return {"ok": True}

    def _check_login(self, platform):
        import browser
        pw = ctx = None
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
        except Exception as e:
            self._emit("toast", f"检查登录失败: {e}")
        finally:
            if pw and ctx:
                browser.stop(pw, ctx)
            self._busy = False

    # ---------- 上传 ----------

    def upload(self, payload):
        return self._submit_ui("article", payload)

    def _submit_ui(self, kind, payload):
        if self._busy:
            return {"ok": False, "msg": "请先完成或关闭登录窗口，再提交上传"}
        payload = dict(payload or {})
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            return {"ok": False, "msg": "标题不能为空"}
        platforms = payload.get("platforms", {})
        allowed = {"wechat", "zhihu", "toutiao"} if kind == "article" else {"zhihu", "toutiao"}
        if not isinstance(platforms, dict) or not any(platforms.values()) or any(p not in allowed for p, enabled in platforms.items() if enabled):
            return {"ok": False, "msg": "请至少勾选一个支持的平台"}
        if kind == "video" and not os.path.isfile(payload.get("video_path") or ""):
            return {"ok": False, "msg": "请先选择有效的视频文件"}
        if kind == "article" and not (payload.get("md") or "").strip():
            return {"ok": False, "msg": "文章正文不能为空"}
        payload["_source"] = "ui"
        payload.setdefault("base_dir", DRAFTS_DIR)
        payload.setdefault("style", load_config().get("wechat_style") or mdconvert.DEFAULT_THEME)
        job = jobs.queue.submit(kind, payload)
        return {"ok": True, "task_id": job.id}

    def retry_job(self, job_id):
        try:
            job = jobs.queue.retry(job_id)
            return {"ok": True, "task_id": job.id}
        except ValueError as exc:
            return {"ok": False, "msg": str(exc)}

    def cancel_job(self, job_id):
        ok = jobs.queue.cancel(job_id)
        return {"ok": ok, "msg": "已取消排队任务" if ok else "任务已开始执行，请等待结果"}

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
            "lan": bool(cfg.get("api_lan", False)),
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
