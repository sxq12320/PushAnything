# make_icon.py — 生成 PushAnything 应用图标（蓝渐变圆角方块 + 钢笔）
from PIL import Image, ImageDraw
import math, os

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 渐变底（对角线 #4DA3FF -> #0066EE -> #0047C7）
grad = Image.new("RGB", (S, S))
gd = grad.load()
c1 = (77, 163, 255); c2 = (0, 102, 238); c3 = (0, 71, 199)
for y in range(S):
    for x in range(0, S, 4):
        t = (x + y) / (2 * S)
        if t < 0.6:
            tt = t / 0.6
            c = tuple(int(c1[i] + (c2[i] - c1[i]) * tt) for i in range(3))
        else:
            tt = (t - 0.6) / 0.4
            c = tuple(int(c2[i] + (c3[i] - c2[i]) * tt) for i in range(3))
        for dx in range(4):
            if x + dx < S: gd[x + dx, y] = c

# 圆角蒙版（icon 常规 ~22% 圆角）
mask = Image.new("L", (S, S), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([0, 0, S, S], radius=int(S * 0.225), fill=255)
img.paste(grad, (0, 0), mask)

# 顶部内高光
hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
hd = ImageDraw.Draw(hl)
hd.rounded_rectangle([0, 0, S, int(S * 0.5)], radius=int(S * 0.225), fill=(255, 255, 255, 28))
img = Image.alpha_composite(img, hl)
d = ImageDraw.Draw(img)

# 钢笔（把 UI 里的 24x24 SVG 路径映射到画布中央 ~56% 区域，白色粗线）
GS = S * 0.56            # 图案区尺寸
GO = (S - GS) / 2        # 居中偏移
def P(x, y): return (GO + x / 24 * GS, GO + y / 24 * GS)
W = int(GS * 0.14)       # 线宽

def stroke(pts, closed=False, w=None):
    p = [P(*pt) for pt in pts]
    if closed: p.append(p[0])
    d.line(p, fill=(255, 255, 255, 255), width=w or W, joint="curve")

# 笔身轮廓: M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z
stroke([(18, 13), (16.5, 5.5), (2, 2), (5.5, 16.5), (13, 18), (18, 13)], closed=True)
# 笔尖: M12 19l7-7 3 3-7 7-3-3z
stroke([(12, 19), (19, 12), (22, 15), (15, 22), (12, 19)], closed=True, w=int(W * 0.85))
# 中心点
cx, cy = P(11, 11); r = S * 0.032
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 255), width=int(W * 0.8))

os.makedirs("assets", exist_ok=True)
img.save("assets/icon.png")
img.resize((256, 256), Image.LANCZOS).save(
    "assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ok")
