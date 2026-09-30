"""Isolated data paths; tests never touch the user's drafts or credentials."""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
TEMP = tempfile.TemporaryDirectory(prefix='pushanything-tests-')
DATA = Path(TEMP.name)
paths = types.ModuleType('paths')
for name, value in {'ROOT': DATA, 'RES': ROOT / 'app', 'DATA_DIR': DATA,
                    'DRAFTS_DIR': DATA / 'drafts', 'ASSETS_DIR': DATA / 'assets',
                    'PROFILES_DIR': DATA / 'profiles', 'CONFIG_PATH': DATA / 'config.json',
                    'WEB_DIR': ROOT / 'app/web'}.items():
    setattr(paths, name, str(value))
paths.STARTUP_WARNING = ''
for directory in ('drafts', 'assets', 'profiles'):
    (DATA / directory).mkdir()
sys.modules['paths'] = paths
