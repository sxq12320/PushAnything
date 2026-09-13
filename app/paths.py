# -*- coding: utf-8 -*-
"""paths.py — 区分可写数据目录与只读资源目录（兼容 PyInstaller frozen）。"""
import os
import sys

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
        import json
        d = (json.load(open(CONFIG_PATH, encoding="utf-8"))
             .get("data_dir") or "").strip()
        if d:
            return os.path.abspath(d)
    except Exception:
        pass
    return ROOT


DATA_DIR = _data_dir()
DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
ASSETS_DIR = os.path.join(DATA_DIR, "assets")

for d in (DRAFTS_DIR, PROFILES_DIR, ASSETS_DIR):
    os.makedirs(d, exist_ok=True)
