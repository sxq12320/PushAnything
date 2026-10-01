"""A hidden WebView2 smoke test with real bridge calls and close handling."""
import json
import sys
import time
import traceback
from pathlib import Path
import conftest_support as support
import backend
import webview

report = {'passed': [], 'errors': []}
api = backend.Api()
backend.save_config({'api_enabled': False, 'author': '测试作者'})
window = webview.create_window('PushAnything native test', url=str(support.ROOT / 'app/web/index.html'),
    js_api=api, width=1360, height=880, hidden=True, focus=False, frameless=True, easy_drag=False,
    min_size=(720, 520))
api.bind(window)
window.events.closing += api.request_close


def check():
    try:
        if not window.events.loaded.wait(25):
            raise RuntimeError('Native page did not load')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if window.evaluate_js('typeof api !== "undefined" && api !== null && vdReady'):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('Native editor/bridge did not initialize')
        report['passed'].append('WebView2 and pywebview bridge initialize')
        window.evaluate_js("setPage('write'); document.getElementById('title').value='原生桥接验证'; setMd(" + json.dumps('## 真实桥接\n\n内容已经写入。') + "); markDirty(true);")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if window.evaluate_js('curRel !== null && !dirty && !saveInFlight'):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('Native autosave failed: ' + str(window.evaluate_js('document.getElementById("toast").textContent + " / " + document.getElementById("stLeft").textContent')))
        rel = window.evaluate_js('curRel')
        if '真实桥接' not in api.load_article(rel)['md']:
            raise RuntimeError('Autosaved content mismatch')
        report['passed'].append('Native bridge autosaves to isolated data directory')
        math_source = '$$x=x+x$$\n\n$$x=' + '+'.join(['x'] * 35) + '$$'
        window.evaluate_js('setMd(' + json.dumps(math_source) + ');markDirty(true);updatePreview();')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if window.evaluate_js('document.getElementById("preview").contentDocument.images.length === 2 && Array.from(document.getElementById("preview").contentDocument.images).every(i=>i.complete)'):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('Native formula image preview failed')
        if not window.evaluate_js('Array.from(document.querySelectorAll("#vditor [data-math] .katex")).every(n=>getComputedStyle(n).fontSize === "18px")'):
            raise RuntimeError('Native formula font size changed')
        report['passed'].append('Native formulas render at a fixed font size through the real bridge')
        window.evaluate_js('openFormula(true);document.getElementById("formulaSource").value="\\\\frac{a}{b}";renderFormulaEditor();')
        if not window.evaluate_js('formulaValid && !document.getElementById("formulaMask").classList.contains("hidden")'):
            raise RuntimeError('Native formula editor did not validate')
        window.evaluate_js('closeFormula();')
        report['passed'].append('Native formula editor validates and closes')
        window.evaluate_js('openTemplates();')
        time.sleep(.5)
        if not window.evaluate_js('!document.getElementById("templateMask").classList.contains("hidden")'):
            raise RuntimeError('Native templates did not open')
        report['passed'].append('Native template preview opens')
        window.evaluate_js('closeTemplates();')
        window.destroy()
        if not window.events.closed.wait(8):
            raise RuntimeError('Guarded native close failed')
        report['passed'].append('Native close event flushes and exits')
    except Exception:
        report['errors'].append(traceback.format_exc())
        api._close_allowed = True
        window.destroy()


webview.start(check, private_mode=False, storage_path=str(support.DATA / 'desktop'), gui='edgechromium')
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
if len(sys.argv) > 1:
    Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
sys.exit(1 if report['errors'] else 0)
