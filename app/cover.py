# -*- coding: utf-8 -*-
"""cover.py — 公众号封面图自动生成（深蓝对角渐变模板，900x383）。"""
import os
from datetime import datetime

import paths

W, H = 900, 383

FONT_REGULAR = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"


def _fit_font(draw, text, font_path, max_w, start=40, low=20):
    from PIL import ImageFont
    for size in range(start, low - 1, -1):
        f = ImageFont.truetype(font_path, size)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_w:
            return f
    return ImageFont.truetype(font_path, low)


def gen_cover(title: str, subtitle: str = "", out_path: str = None,
              tag: str = "深度观察", source: str = "") -> str:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), (10, 37, 64))
    draw = ImageDraw.Draw(img)

    # 对角线渐变：左上深蓝 -> 蓝 -> 右下淡紫
    c1, c2, c3 = (10, 37, 64), (22, 104, 220), (139, 125, 196)
    for y in range(H):
        for x in range(0, W, 2):
            ratio = (x / W) * 0.55 + (y / H) * 0.45
            if ratio < 0.5:
                t = ratio / 0.5
                rgb = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            else:
                t = (ratio - 0.5) / 0.5
                rgb = tuple(int(c2[i] + (c3[i] - c2[i]) * t) for i in range(3))
            draw.line([(x, y), (x + 1, y)], fill=rgb)

    fb = FONT_BOLD if os.path.exists(FONT_BOLD) else FONT_REGULAR
    tag_font = ImageFont.truetype(fb, 18)
    small_font = ImageFont.truetype(fb, 14)
    title_font = _fit_font(draw, title, fb, W * 0.80)

    draw.text((50, 28), tag, font=tag_font, fill=(255, 255, 255))
    date_s = datetime.now().strftime("%Y年%m月")
    dw = draw.textbbox((0, 0), date_s, font=tag_font)[2]
    draw.text((W - 50 - dw, 28), date_s, font=tag_font, fill=(255, 255, 255))
    draw.text((50, 150), title, font=title_font, fill=(255, 255, 255))
    if subtitle:
        draw.text((50, 220), subtitle, font=tag_font, fill=(255, 255, 255))
    if source:
        sw = draw.textbbox((0, 0), source, font=small_font)[2]
        draw.text((W - 30 - sw, 345), source, font=small_font, fill=(220, 220, 235))

    if not out_path:
        out_path = os.path.join(paths.ASSETS_DIR, "cover.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path)
    return out_path
