# -*- coding: utf-8 -*-
"""
mdconvert.py — Markdown -> 各平台 HTML/段落流

平台差异：
- 公众号(wechat)：单段 HTML，所有样式 inline；数据表格渲染成 PIL PNG(base64)，
  图片全部转 base64/本地路径，由 wechat_push 上传素材接口替换。
- 知乎/头条：返回"段落流" segments：[{"type":"html"}|{"type":"image","path":...}]
  文本段走剪贴板粘贴进 contenteditable；图片段走编辑器上传按钮插入，
  保证本地图、网络图、表格图都能进正文。
"""
import os
import re
import io
import base64
import tempfile
import requests
import markdown

MD_EXTS = ["extra", "tables", "fenced_code", "sane_lists", "nl2br"]

TMP_DIR = os.path.join(tempfile.gettempdir(), "md_publisher")
os.makedirs(TMP_DIR, exist_ok=True)


# ---------- 基础转换 ----------

def md_to_html(md_text: str) -> str:
    return markdown.markdown(md_text or "", extensions=MD_EXTS, output_format="html5")


_IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"[^>]*>', re.I)
_MD_IMG_RE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)[^)]*\)')

TABLE_RE = re.compile(r'<table>.*?</table>', re.S | re.I)


def is_remote(src: str) -> bool:
    return src.startswith("http://") or src.startswith("https://")


def is_local(src: str) -> bool:
    if src.startswith("data:"):
        return False
    if is_remote(src):
        return False
    # windows 绝对路径 / 相对路径 / file://
    return True


def download_image(url: str) -> str:
    """下载网络图到临时文件，返回本地路径。"""
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    ext = ".png"
    m = re.search(r'\.(png|jpe?g|gif|webp|bmp)(?:\?|$)', url, re.I)
    if m:
        ext = "." + m.group(1).lower().replace("jpeg", "jpg")
    fd, path = tempfile.mkstemp(suffix=ext, dir=TMP_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(r.content)
    return path


def local_path_of(src: str, base_dir: str) -> str:
    src = src.replace("file://", "")
    if not os.path.isabs(src):
        src = os.path.join(base_dir, src)
    return os.path.normpath(src)


def path_to_data_uri(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/{ext};base64,{b64}"


# ---------- 数学公式：LaTeX -> PNG ----------

_FENCE_RE = re.compile(r'```[^\n]*\n.*?```', re.S)
_CODE_RE = re.compile(r'`[^`\n]+`')
_MATH_BLOCK_RE = re.compile(r'\$\$(.+?)\$\$', re.S)
_MATH_INLINE_RE = re.compile(r'(?<![\\$])\$(?!\$)([^$\n]+?)(?<!\s)\$(?!\$)')


def extract_math(md_text: str):
    """保护代码块/行内代码后提取 $..$ 与 $$..$$，返回 (干净md, {token:(tex,display)})。"""
    prot = {}
    cnt = [0]

    def keep(m):
        tok = "ZCODE%dX" % cnt[0]; cnt[0] += 1
        prot[tok] = m.group(0)
        return tok

    text = _FENCE_RE.sub(lambda m: "\n\n" + keep(m) + "\n\n", md_text or "")
    text = _CODE_RE.sub(keep, text)

    maths = {}

    def block(m):
        tok = "ZMATHBLK%dX" % cnt[0]; cnt[0] += 1
        maths[tok] = (m.group(1).strip(), True)
        return "\n\n" + tok + "\n\n"

    def inl(m):
        tok = "ZMATHIN%dX" % cnt[0]; cnt[0] += 1
        maths[tok] = (m.group(1).strip(), False)
        return tok

    text = _MATH_BLOCK_RE.sub(block, text)
    text = _MATH_INLINE_RE.sub(inl, text)
    for tok, val in prot.items():
        text = text.replace(tok, val)
    return text, maths


def render_math_png(tex: str, display: bool = False):
    """LaTeX -> PNG 路径。本地 mathtext 优先；复杂语法(codecogs)；最后 PIL 文本兜底。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig = plt.figure()
        fig.text(0, 0, "$%s$" % tex, fontsize=17 if display else 15)
        fd, path = tempfile.mkstemp(suffix=".png", dir=TMP_DIR)
        os.close(fd)
        fig.savefig(path, dpi=220, transparent=True,
                    bbox_inches="tight", pad_inches=0.04)
        plt.close(fig)
        return path
    except Exception:
        pass
    try:
        q = requests.utils.quote(
            ("\\displaystyle " if display else "") + tex)
        url = "https://latex.codecogs.com/png.image?\\dpi{220}" + q
        r = requests.get(url, timeout=25,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=".png", dir=TMP_DIR)
        with os.fdopen(fd, "wb") as f:
            f.write(r.content)
        return path
    except Exception:
        pass
    try:
        from PIL import Image, ImageDraw, ImageFont
        f = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 18)
        tmp = Image.new("RGB", (10, 10))
        d = ImageDraw.Draw(tmp)
        box = d.textbbox((0, 0), tex, font=f)
        img = Image.new("RGB", (box[2] + 20, box[3] + 14), "#FFFFFF")
        ImageDraw.Draw(img).text((10, 7), tex, font=f, fill="#333333")
        fd, path = tempfile.mkstemp(suffix=".png", dir=TMP_DIR)
        os.close(fd)
        img.save(path)
        return path
    except Exception:
        return None


def _math_img(tex: str, display: bool, as_data_uri: bool) -> str:
    path = render_math_png(tex, display)
    safe_alt = tex.replace('"', "&quot;").replace("<", "&lt;")
    if not path:
        return "<code>%s</code>" % safe_alt
    src = path_to_data_uri(path) if as_data_uri else path
    st = ("display:block;margin:14px auto;max-width:96%;" if display
          else "vertical-align:middle;max-height:1.7em;")
    return '<img src="%s" alt="%s" style="%s"/>' % (src, safe_alt, st)


def _embed_math(html: str, maths: dict, as_data_uri: bool) -> str:
    for tok, (tex, display) in maths.items():
        img = _math_img(tex, display, as_data_uri)
        html = re.sub(r'<p[^>]*>\s*%s\s*</p>' % tok,
                      lambda m: img, html)
        html = html.replace(tok, img)
    return html


def save_data_uri(src: str) -> str:
    """data:image/...;base64 -> 临时文件"""
    header, b64 = src.split(",", 1)
    fmt = header.split("/")[1].split(";")[0]
    fd, path = tempfile.mkstemp(suffix="." + fmt, dir=TMP_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(base64.b64decode(b64))
    return path


# ---------- 表格 -> PNG（三平台统一，编辑器粘贴表格必乱） ----------

def _table_rows(table_html: str):
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.S | re.I):
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', tr, re.S | re.I)
        rows.append([re.sub(r'<[^>]+>', '', c).strip() for c in cells])
    return rows


def render_table_png(table_html: str, font_regular: str, font_bold: str,
                     width: int = 750) -> str:
    """清爽清新风格表格图，返回 PNG 文件路径。"""
    from PIL import Image, ImageDraw, ImageFont
    rows = _table_rows(table_html)
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]

    pad_x, pad_y, line_h = 14, 12, 6
    head_h, row_h_min = 44, 38
    f_head = ImageFont.truetype(font_bold, 16)
    f_cell = ImageFont.truetype(font_regular, 18)
    f_first = ImageFont.truetype(font_bold, 18)

    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)

    def wrap(text, font, maxw):
        lines, cur = [], ""
        for ch in text:
            if ch == "\n":
                lines.append(cur); cur = ""; continue
            w = d.textbbox((0, 0), cur + ch, font=font)[2]
            if w > maxw and cur:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
        return lines or [""]

    # 列宽：按内容均分，第一列稍窄
    inner_w = width - pad_x * 2
    col_w = [inner_w // ncol] * ncol
    col_w[-1] += inner_w - sum(col_w)

    wrapped = []
    heights = []
    for ri, row in enumerate(rows):
        f = f_head if ri == 0 else f_cell
        wrow, hmax = [], row_h_min
        for ci, cell in enumerate(row):
            font = f_head if ri == 0 else (f_first if ci == 0 else f_cell)
            lines = wrap(cell, font, col_w[ci] - 16)
            wrow.append(lines)
            need = len(lines) * (18 + line_h) + pad_y * 2
            hmax = max(hmax, need)
        wrapped.append(wrow)
        heights.append(max(hmax, head_h if ri == 0 else row_h_min))

    H = sum(heights) + pad_y
    img = Image.new("RGB", (width, H), "#FFFFFF")
    dr = ImageDraw.Draw(img)

    y = 0
    for ri, (wrow, rh) in enumerate(zip(wrapped, heights)):
        if ri == 0:
            dr.rounded_rectangle([0, y, width, y + rh], radius=12, fill="#5B8DEF")
        else:
            bg = "#FFFFFF" if ri % 2 else "#F5F9FF"
            dr.rectangle([0, y, width, y + rh], fill=bg)
            dr.line([0, y + rh - 1, width, y + rh - 1], fill="#E8ECF0")
        x = pad_x
        for ci, lines in enumerate(wrow):
            if ri == 0:
                color, font = "#FFFFFF", f_head
            elif ci == 0:
                color, font = "#2D3E50", f_first
            else:
                color, font = "#3A4A5C", f_cell
            ty = y + pad_y
            for ln in lines:
                dr.text((x + 8, ty), ln, font=font, fill=color)
                ty += 18 + line_h
            x += col_w[ci]
        if ri > 0:
            dr.rectangle([pad_x - 8, y + pad_y - 4, pad_x - 4, y + rh - pad_y], fill="#4ECDC4")
        y += rh

    fd, path = tempfile.mkstemp(suffix=".png", dir=TMP_DIR)
    os.close(fd)
    img.save(path)
    return path


def _replace_tables(html: str, font_r: str, font_b: str, as_data_uri: bool):
    def _rep(m):
        p = render_table_png(m.group(0), font_r, font_b)
        if not p:
            return m.group(0)
        src = path_to_data_uri(p) if as_data_uri else p
        return f'<img src="{src}" alt="表格"/>'
    return TABLE_RE.sub(_rep, html)


# ---------- 公众号 HTML（主题化） ----------

_BASE = "font-size:15px;line-height:1.8;color:#000000;"

# 主题：h2 渲染模式 block(整块底色) / bar(左侧粗竖条) / underline(底部粗线)
WECHAT_THEMES = {
    "red": {
        "name": "经典红",
        "h2_mode": "block", "h2_color": "#C43B47",
        "strong": "#C43B47", "link": "#576B95",
        "quote_bar": "#C43B47", "quote_color": "#8E2F38",
        "quote_bg": "#FADCE1", "quote_border": "#F0BCC8",
        "code_bg": "#F5F5F5", "hr": "#EEF2F7",
    },
    "blue": {
        "name": "藏青蓝",
        "h2_mode": "block", "h2_color": "#2B5797",
        "strong": "#2B5797", "link": "#2B5797",
        "quote_bar": "#2B5797", "quote_color": "#2B5797",
        "quote_bg": "#DCE8F5", "quote_border": "#B8CCE6",
        "code_bg": "#F0F4FA", "hr": "#E8EDF5",
    },
    "green": {
        "name": "松绿",
        "h2_mode": "bar", "h2_color": "#3F7E5B",
        "strong": "#3F7E5B", "link": "#3F7E5B",
        "quote_bar": "#3F7E5B", "quote_color": "#2F6147",
        "quote_bg": "#DFF0E6", "quote_border": "#B8D9C6",
        "code_bg": "#F2F7F4", "hr": "#E9F0EB",
    },
    "orange": {
        "name": "暖橙",
        "h2_mode": "underline", "h2_color": "#C96A2B",
        "strong": "#C96A2B", "link": "#576B95",
        "quote_bar": "#C96A2B", "quote_color": "#9A5220",
        "quote_bg": "#F9E7D5", "quote_border": "#EBC9A6",
        "code_bg": "#FBF4EE", "hr": "#F4EDE6",
    },
    "ink": {
        "name": "墨黑",
        "h2_mode": "bar", "h2_color": "#222222",
        "strong": "#111111", "link": "#576B95",
        "quote_bar": "#222222", "quote_color": "#3A3A3C",
        "quote_bg": "#ECECEF", "quote_border": "#D5D5DB",
        "code_bg": "#F5F5F5", "hr": "#ECECEC",
    },
}

DEFAULT_THEME = "red"


def theme_names():
    return {k: v["name"] for k, v in WECHAT_THEMES.items()}


def _h_block(text, color):
    return ('<table style="width:100%;border-collapse:collapse;margin:26px 0 14px;"><tr>'
            f'<td style="padding:7px 14px;background:{color};">'
            f'<p style="margin:0;font-size:17px;font-weight:700;color:#FFFFFF;line-height:1.6;">{text}</p>'
            '</td></tr></table>')


def _h_bar(text, color):
    return ('<table style="width:100%;border-collapse:collapse;margin:26px 0 14px;"><tr>'
            f'<td style="padding:2px 0 2px 12px;border-left:5px solid {color};">'
            f'<p style="margin:0;font-size:17px;font-weight:700;color:#1a1a1a;line-height:1.6;">{text}</p>'
            '</td></tr></table>')


def _h_underline(text, color):
    return ('<table style="width:100%;border-collapse:collapse;margin:26px 0 14px;"><tr>'
            f'<td style="padding:2px 0 8px;border-bottom:3px solid {color};">'
            f'<p style="margin:0;font-size:17px;font-weight:700;color:#1a1a1a;line-height:1.6;">{text}</p>'
            '</td></tr></table>')


_H_MODES = {"block": _h_block, "bar": _h_bar, "underline": _h_underline}


def _wrap_td_li(html: str) -> str:
    """td/li 内裸文字用 <p style="margin:0"> 包裹，防微信加 section。"""
    def wrap(m):
        inner = m.group(2)
        if "<p" in inner or "<img" in inner:
            return m.group(0)
        return f'{m.group(1)}<p style="margin:0;">{inner}</p>{m.group(3)}'
    return re.sub(r'(<(?:td|li)[^>]*>)(.*?)(</(?:td|li)>)', wrap, html, flags=re.S)


def style_for_wechat(md_text: str, base_dir: str, font_r: str, font_b: str,
                     theme: str = DEFAULT_THEME) -> str:
    """markdown 源文 -> 公众号内联样式 HTML（图片/公式转 base64，表格转 PNG）。
    theme ∈ WECHAT_THEMES。"""
    th = WECHAT_THEMES.get(theme) or WECHAT_THEMES[DEFAULT_THEME]
    h_fn = _H_MODES[th["h2_mode"]]

    md_text, maths = extract_math(md_text)
    html = md_to_html(md_text)
    # 1) 表格 -> PNG(base64)
    html = _replace_tables(html, font_r, font_b, as_data_uri=True)

    # 2) 图片：本地->base64；远程下载->base64（微信只收自家素材URL，全走上传）
    def img_rep(m):
        tag, src = m.group(0), m.group(1)
        try:
            if src.startswith("data:"):
                uri = src
            elif is_remote(src):
                uri = path_to_data_uri(download_image(src))
            else:
                uri = path_to_data_uri(local_path_of(src, base_dir))
            alt = re.search(r'alt="([^"]*)"', tag)
            return f'<img src="{uri}" alt="{alt.group(1) if alt else ""}" style="max-width:100%;display:block;margin:8px auto;"/>'
        except Exception:
            return tag
    html = _IMG_RE.sub(img_rep, html)

    # 3) 标题 -> 主题化单格 table
    def h_repl(m):
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        return h_fn(text, th["h2_color"])
    html = re.sub(r'<h([1-4])[^>]*>(.*?)</h\1>', h_repl, html, flags=re.S | re.I)

    # 4) 段落 / 引用 / 列表 / 代码样式
    html = re.sub(r'<p>', f'<p style="margin:16px 0;{_BASE}">', html)

    def _quote_repl(m):
        inner = re.sub(
            r'<p[^>]*>',
            f'<p style="margin:8px 0 0;{_BASE}color:{th["quote_color"]};">',
            m.group(1))
        inner = inner.replace("margin:8px 0 0", "margin:0", 1)  # 首段不加顶距
        return (f'<section style="margin:16px 0;padding:16px 20px;'
                f'background:{th["quote_bg"]};border-radius:14px;'
                f'border:1px solid {th["quote_border"]};">'
                f'{inner}</section>')

    html = re.sub(r'<blockquote>(.*?)</blockquote>', _quote_repl,
                  html, flags=re.S)
    html = re.sub(r'</?blockquote>', '', html)
    html = re.sub(r'<li>', '<li style="' + _BASE + '">', html)
    html = _wrap_td_li(html)
    html = re.sub(r'<strong>', f'<strong style="color:{th["strong"]};">', html)
    html = re.sub(r'<a ', f'<a style="color:{th["link"]};" ', html)
    html = re.sub(r'<code>', f'<code style="background:{th["code_bg"]};padding:2px 6px;border-radius:4px;font-size:14px;">', html)
    html = re.sub(r'<pre>', f'<pre style="background:{th["code_bg"]};padding:12px;border-radius:6px;overflow-x:auto;font-size:14px;line-height:1.6;">', html)
    html = re.sub(r'<hr\s*/?>', f'<p style="margin:24px 0;border-top:1px solid {th["hr"]};"></p>', html)

    # 5) 数学公式 -> PNG(base64)
    html = _embed_math(html, maths, as_data_uri=True)

    # 6) 清理：空段落、注释、多余空行
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    html = re.sub(r'<p[^>]*>\s*</p>', '', html)
    html = re.sub(r'\n{2,}', '\n', html)
    return html.strip()


# ---------- 知乎/头条 段落流 ----------

def style_for_richtext(html: str) -> str:
    """轻度清理，保留语义标签（h2/p/strong/em/li/blockquote/img），编辑器自己解析。"""
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'<h2>\1</h2>', html, flags=re.S | re.I)
    return html.strip()


def richtext_html(md_text: str) -> str:
    """富文本预览/粘贴用 HTML（公式转 base64 图）。"""
    md_text, maths = extract_math(md_text)
    html = md_to_html(md_text)
    html = _embed_math(html, maths, as_data_uri=True)
    return style_for_richtext(html)


def make_segments(md_text: str, base_dir: str, font_r: str, font_b: str):
    """
    -> [ {"type":"html","html":...} , {"type":"image","path":..., "alt":...} ... ]
    所有图片（本地/网络/base64/表格PNG/公式PNG）统一为文件路径，由编辑器上传按钮插入。
    """
    md_text, maths = extract_math(md_text)
    html = md_to_html(md_text)
    html = _replace_tables(html, font_r, font_b, as_data_uri=False)  # 表格->PNG文件
    html = _embed_math(html, maths, as_data_uri=False)             # 公式->PNG文件
    html = style_for_richtext(html)

    segs, pos = [], 0
    for m in _IMG_RE.finditer(html):
        pre = html[pos:m.start()]
        if pre.strip():
            segs.append({"type": "html", "html": pre})
        src, tag = m.group(1), m.group(0)
        alt = re.search(r'alt="([^"]*)"', tag)
        try:
            if src.startswith("data:"):
                path = save_data_uri(src)
            elif is_remote(src):
                path = download_image(src)
            else:
                path = local_path_of(src, base_dir)
            segs.append({"type": "image", "path": path,
                         "alt": alt.group(1) if alt else ""})
        except Exception as e:
            segs.append({"type": "html", "html": f"<p>[图片加载失败: {src} ({e})]</p>"})
        pos = m.end()
    tail = html[pos:]
    if tail.strip():
        segs.append({"type": "html", "html": tail})
    return segs


def md_images(md_text: str):
    """返回 md 中所有图片 src。"""
    return _MD_IMG_RE.findall(md_text or "")
