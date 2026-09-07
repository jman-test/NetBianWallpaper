# -*- coding: utf-8 -*-
"""生成壁纸软件候选图标（预览用 PNG，1024 工作尺寸抗锯齿）"""
from PIL import Image, ImageDraw, ImageFont
import os


def load_font(size):
    """尝试加载系统中文字体，回退到默认字体"""
    candidates = [
        os.path.expandvars(r"C:/Windows/Fonts/msyh.ttc"),
        os.path.expandvars(r"C:/Windows/Fonts/msyhbd.ttc"),
        os.path.expandvars(r"C:/Windows/Fonts/simsun.ttc"),
        os.path.expandvars(r"C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

WORK = 1024  # 工作尺寸，最后缩放到预览尺寸
OUT = 256


def vertical_gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def apply_rounded(img, radius):
    mask = rounded_mask(img.size, radius)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def draw_sun(d, cx, cy, r, color, glow_color=None):
    if glow_color:
        for gr in range(int(r * 1.9), int(r * 0.9), -1):
            a = int(80 * (1 - (gr - r * 0.9) / (r * 1.0)))
            d.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=glow_color + (a,))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def draw_mountains(d, w, h, layers):
    """layers: [(color, [峰顶坐标...]), ...] 从左到右绘制重叠山形"""
    for color, peaks in layers:
        pts = [(0, h)]
        for (px, py) in peaks:
            pts.append((px, py))
        pts.append((w, h))
        d.polygon(pts, fill=color)


# ---------------------------------------------------------------------------
# 方案 A：山景壁纸（蓝紫渐变天空 + 太阳 + 山 + 底部任务栏）
# ---------------------------------------------------------------------------
def icon_a():
    w = h = WORK
    img = vertical_gradient(w, h, (58, 108, 214), (122, 82, 205))
    d = ImageDraw.Draw(img, "RGBA")

    draw_sun(d, int(w * 0.72), int(h * 0.30), int(w * 0.085), (255, 216, 130),
             (255, 220, 140))

    # 远山
    draw_mountains(d, w, h, [
        ((86, 110, 168), [(0, int(h * 0.58)), (int(w * 0.22), int(h * 0.34)),
                          (int(w * 0.45), int(h * 0.60)), (int(w * 0.72), int(h * 0.42)),
                          (w, int(h * 0.56))]),
        ((54, 62, 110), [(0, int(h * 0.72)), (int(w * 0.30), int(h * 0.46)),
                         (int(w * 0.56), int(h * 0.72)), (int(w * 0.82), int(h * 0.50)),
                         (w, int(h * 0.70))]),
        ((34, 38, 72), [(0, int(h * 0.88)), (int(w * 0.40), int(h * 0.62)),
                        (int(w * 0.68), int(h * 0.88)), (w, int(h * 0.66))]),
    ])

    # 底部“桌面任务栏”
    bar_h = int(h * 0.16)
    d.rectangle([0, h - bar_h, w, h], fill=(22, 24, 34))
    # 任务栏里的“窗口”小方块
    for i in range(3):
        x = int(w * 0.14) + i * int(w * 0.16)
        y = h - int(bar_h * 0.62)
        s = int(bar_h * 0.42)
        d.rounded_rectangle([x, y, x + s, y + s], radius=int(s * 0.25), fill=(64, 74, 108))

    return apply_rounded(img, int(w * 0.18))


# ---------------------------------------------------------------------------
# 方案 B：画框中的风景（深色底 + 白画框 + 迷你山景）
# ---------------------------------------------------------------------------
def icon_b():
    w = h = WORK
    img = vertical_gradient(w, h, (46, 50, 64), (28, 30, 40))
    d = ImageDraw.Draw(img, "RGBA")

    # 外圈浅色描边装饰
    d.rounded_rectangle([int(w * 0.06), int(h * 0.06), int(w * 0.94), int(h * 0.94)],
                        radius=int(w * 0.16), outline=(90, 100, 128), width=int(w * 0.012))

    # 白色画框
    fx0, fy0 = int(w * 0.20), int(h * 0.16)
    fx1, fy1 = int(w * 0.80), int(h * 0.84)
    d.rounded_rectangle([fx0, fy0, fx1, fy1], radius=int(w * 0.05), fill=(246, 247, 250))

    # 画框内风景
    pad = int(w * 0.03)
    ix0, iy0 = fx0 + pad, fy0 + pad
    ix1, iy1 = fx1 - pad, fy1 - pad
    scene = vertical_gradient(ix1 - ix0, iy1 - iy0, (66, 120, 220), (150, 96, 220))
    sd = ImageDraw.Draw(scene, "RGBA")
    sw, sh = scene.size
    draw_sun(sd, int(sw * 0.72), int(sh * 0.30), int(sw * 0.09), (255, 214, 128))
    draw_mountains(sd, sw, sh, [
        ((80, 104, 168), [(0, int(sh * 0.60)), (int(sw * 0.35), int(sh * 0.36)), (sw, int(sh * 0.58))]),
        ((46, 54, 100), [(0, int(sh * 0.80)), (int(sw * 0.55), int(sh * 0.50)), (sw, int(sh * 0.78))]),
    ])
    # 圆角裁剪画框内景
    smask = rounded_mask(scene.size, int(w * 0.025))
    scene.putalpha(smask)
    img.paste(scene, (ix0, iy0), scene)

    # 画框底部一条细线，暗示“窗口标题栏/分割线”
    bar_y = iy0 + int((iy1 - iy0) * 0.10)
    d.line([(ix0, bar_y), (ix1, bar_y)], fill=(220, 222, 228), width=int(w * 0.01))

    return apply_rounded(img, int(w * 0.18))


# ---------------------------------------------------------------------------
# 方案 C：极简线条山（深藏青底 + 白色线条山峰 + 太阳圆）
# ---------------------------------------------------------------------------
def icon_c():
    w = h = WORK
    img = vertical_gradient(w, h, (32, 42, 64), (20, 24, 38))
    d = ImageDraw.Draw(img, "RGBA")

    # 太阳圆（描边感）
    r = int(w * 0.075)
    cx, cy = int(w * 0.72), int(h * 0.30)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(246, 200, 120))
    d.ellipse([cx - r - int(w * 0.012), cy - r - int(w * 0.012),
               cx + r + int(w * 0.012), cy + r + int(w * 0.012)],
              outline=(255, 230, 170), width=int(w * 0.010))

    lw = int(w * 0.026)
    line1_pts = [(0, int(h * 0.68)), (int(w * 0.28), int(h * 0.40)), (int(w * 0.50), int(h * 0.62)),
                 (int(w * 0.72), int(h * 0.34)), (w, int(h * 0.60))]
    line2_pts = [(0, int(h * 0.86)), (int(w * 0.34), int(h * 0.62)), (int(w * 0.60), int(h * 0.82)),
                 (w, int(h * 0.56))]
    # 山脊折线（带端点圆点，模拟 round cap）
    for pts, color, width in [(line1_pts, (240, 242, 248), lw), (line2_pts, (150, 160, 190), int(lw * 0.8))]:
        d.line(pts, fill=color, width=width, joint="curve")
        for p in (pts[0], pts[-1]):
            d.ellipse([p[0] - width // 2, p[1] - width // 2,
                       p[0] + width // 2, p[1] + width // 2], fill=color)

    return apply_rounded(img, int(w * 0.18))


def preview(icon_fn, out_size=OUT):
    img = icon_fn().convert("RGBA")
    return img.resize((out_size, out_size), Image.LANCZOS)


def main():
    a = preview(icon_a)
    b = preview(icon_b)
    c = preview(icon_c)

    a.save("icon_candidate_A.png")
    b.save("icon_candidate_B.png")
    c.save("icon_candidate_C.png")

    # 拼接对比图
    gap = 32
    label_h = 48
    total_w = OUT * 3 + gap * 4
    total_h = OUT + gap * 2 + label_h
    canvas = Image.new("RGBA", (total_w, total_h), (18, 20, 26, 255))
    cd = ImageDraw.Draw(canvas)
    font = load_font(label_h - 20)
    sub_font = load_font(label_h - 26)
    labels = [("方案 A", "山景壁纸"), ("方案 B", "画框风景"), ("方案 C", "极简线条")]
    for i, ((title, sub), im) in enumerate(zip(labels, [a, b, c])):
        x = gap + i * (OUT + gap)
        y = gap
        canvas.paste(im, (x, y), im)

        def draw_centered(text, fy, fnt):
            bbox = cd.textbbox((0, 0), text, font=fnt)
            tw = bbox[2] - bbox[0]
            cd.text((x + (OUT - tw) // 2, fy), text, font=fnt, fill=(200, 205, 215))

        draw_centered(title, y + OUT + 8, font)
        draw_centered(sub, y + OUT + 34, sub_font)
    canvas.convert("RGB").save("icon_preview_compare.png")
    print("生成完成：icon_candidate_A/B/C.png + icon_preview_compare.png")


if __name__ == "__main__":
    main()
