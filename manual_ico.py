# -*- coding: utf-8 -*-
"""从方案 A 生成图标资源（一键生成）：
1. app.ico —— BMP(DIB) 格式多尺寸 ICO，供 PyInstaller --icon 使用
2. app_icon_256.png —— 256 预览图
3. app_icon.py —— 内嵌 PNG 的窗口图标模块
"""
import base64
import struct
from PIL import Image
from generate_icons import icon_a

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build_bmp_icon(size):
    img = icon_a().resize((size, size), Image.LANCZOS).convert("RGBA")
    w = h = size
    px = img.load()

    # XOR mask：bottom-up，BGRA 顺序
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = px[x, y]
            xor += bytes([b, g, r, a])

    # AND mask：1bpp，bottom-up，每行 padding 到 4 字节；全 0（不透明，透明度由 alpha 通道决定）
    and_rows = bytearray()
    row_byte_len = ((w + 31) // 32) * 4
    for _ in range(h):
        and_rows += bytes(row_byte_len)

    # BITMAPINFOHEADER（40 字节），biHeight = 2*h（XOR + AND）
    biHeight = h * 2
    biSizeImage = len(xor) + len(and_rows)
    header = struct.pack("<IiiHHIIiiII", 40, w, biHeight, 1, 32, 0,
                         biSizeImage, 0, 0, 0, 0)
    return header + bytes(xor) + bytes(and_rows)


def build_ico():
    entries = []
    blobs = []
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        s = size[0]
        data = build_bmp_icon(s)
        blobs.append(data)
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        entries.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset))
        offset += len(data)

    header = struct.pack("<HHH", 0, 1, len(SIZES))
    ico = header + b"".join(entries) + b"".join(blobs)
    with open("app.ico", "wb") as f:
        f.write(ico)
    print("生成 BMP 格式 app.ico，大小", len(ico), "字节")


def build_png():
    img = icon_a().resize((256, 256), Image.LANCZOS).convert("RGBA")
    img.save("app_icon_256.png")
    print("生成 app_icon_256.png")


def build_py():
    with open("app_icon_256.png", "rb") as f:
        png = f.read()
    b64 = base64.b64encode(png).decode("ascii")
    lines = [b64[i:i + 100] for i in range(0, len(b64), 100)]
    body = "\n".join('    "' + l + '"' for l in lines)
    code = '''# -*- coding: utf-8 -*-
"""应用图标（内嵌 PNG，窗口左上角图标用，无需外部文件）"""
import base64
from PySide6.QtGui import QIcon, QPixmap

_ICO_B64 = (
%s
)

_icon = None


def get_app_icon():
    global _icon
    if _icon is None:
        data = base64.b64decode(_ICO_B64)
        pm = QPixmap()
        pm.loadFromData(data)
        _icon = QIcon(pm)
    return _icon
''' % body
    with open("app_icon.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("生成 app_icon.py")


if __name__ == "__main__":
    build_ico()
    build_png()
    build_py()
