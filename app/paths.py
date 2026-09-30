# -*- coding: utf-8 -*-
"""paths.py — 区分可写数据目录与只读资源目录（兼容 PyInstaller frozen）。"""
import os
import sys
import json
import shutil
import uuid

import storage

STARTUP_WARNING = ""

if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)          # exe 旁边：可写
    RES = os.path.join(sys._MEIPASS, "app")         # 打包内资源：只读
else:
    ROOT = RES = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(ROOT, "config.json")
WEB_DIR = os.path.join(RES, "web")


def _data_dir():
    """数据根目录：config.json 里的 data_dir，缺省为 ROOT。"""
    try:
        global STARTUP_WARNING
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
        old_dir = os.path.abspath(config.get("data_dir") or ROOT)
        pending = config.get("pending_data_dir")
        if pending:
            target = os.path.abspath(pending)
            names = ("drafts", "profiles", "assets", "history.json", "templates.json", ".draft-recovery.json")
            staged = []
            installed = []
            staging = os.path.join(target, ".migration-" + uuid.uuid4().hex)
            try:
                common = os.path.normcase(os.path.commonpath([old_dir, target])) if os.path.splitdrive(old_dir)[0] == os.path.splitdrive(target)[0] else ""
                if common in (os.path.normcase(old_dir), os.path.normcase(target)):
                    raise ValueError("目标目录必须在当前目录之外")
                if any(os.path.exists(os.path.join(target, name)) for name in names):
                    raise ValueError("目标目录已存在软件数据")
                os.makedirs(staging, exist_ok=True)
                for name in names:
                    source = os.path.join(old_dir, name)
                    if os.path.isdir(source):
                        shutil.copytree(source, os.path.join(staging, name))
                        staged.append(name)
                    elif os.path.isfile(source):
                        shutil.copy2(source, os.path.join(staging, name))
                        staged.append(name)
                for name in staged:
                    # Rebase local picture paths and retry payloads in copied documents.
                    copied = os.path.join(staging, name)
                    documents = []
                    if name == "drafts":
                        for directory, subdirs, filenames in os.walk(copied):
                            subdirs[:] = [d for d in subdirs if d != "assets"]
                            documents.extend(os.path.join(directory, filename) for filename in filenames
                                             if filename.endswith((".md", ".json")))
                    elif name.endswith(".json"):
                        documents = [copied]
                    def rebase(value):
                        if isinstance(value, str):
                            return value.replace(old_dir, target).replace(old_dir.replace("\\", "/"), target.replace("\\", "/"))
                        if isinstance(value, dict):
                            return {key: rebase(item) for key, item in value.items()}
                        if isinstance(value, list):
                            return [rebase(item) for item in value]
                        return value
                    for document in documents:
                        with open(document, encoding="utf-8") as handle:
                            content = handle.read()
                        if document.endswith(".json"):
                            storage.atomic_json(document, rebase(json.loads(content)))
                        else:
                            storage.atomic_text(document, rebase(content))
                    os.replace(os.path.join(staging, name), os.path.join(target, name))
                    installed.append(name)
                config["data_dir"] = target
                config.pop("pending_data_dir", None)
                storage.atomic_json(CONFIG_PATH, config)
                os.rmdir(staging)
                return target
            except Exception as exc:
                for name in installed:
                    try:
                        os.replace(os.path.join(target, name), os.path.join(staging, name))
                    except OSError:
                        pass
                STARTUP_WARNING = f"数据迁移未完成，继续使用原目录：{exc}"
                return old_dir
        return old_dir
    except Exception:
        pass
    return ROOT


DATA_DIR = _data_dir()
DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
ASSETS_DIR = os.path.join(DATA_DIR, "assets")

for d in (DRAFTS_DIR, PROFILES_DIR, ASSETS_DIR):
    os.makedirs(d, exist_ok=True)
