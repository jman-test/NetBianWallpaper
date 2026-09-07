# -*- coding: utf-8 -*-
"""
彼岸桌面 (netbian.com) 壁纸浏览器 —— WinUI 3 / Fluent 风格版
功能：浏览/分页/分类/搜索 + 大图预览(拖拽/最大化) + 下载 + 设为壁纸
技术：PySide6 + PySide6-Fluent-Widgets (qfluentwidgets) + requests
"""

# 版本号（单一来源：修改 APP_VERSION 即可，界面显示与 Release tag 均由此派生）
APP_VERSION = "1.0.0"
APP_VERSION_DISPLAY = "V" + APP_VERSION.rsplit(".", 1)[0]  # 如 "V1.0"

import os
import re
import sys
import json
import hashlib
import threading
import random

# 优先使用 curl_cffi 模拟浏览器 TLS/JA3 指纹，降低被 WAF 拦截概率
try:
    from curl_cffi import requests as requests
    _HAS_CURL_CFFI = True
except Exception:
    import requests
    _HAS_CURL_CFFI = False

from PySide6 import QtWidgets
from PySide6.QtCore import (Qt, Signal, QObject, QSize, QPropertyAnimation,
                            QTimer, QEvent, QRect, QRectF, QPoint)
from PySide6.QtGui import (QPixmap, QIcon, QColor, QFont, QDesktopServices,
                           QAction, QImage, QPainter, QCursor)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                               QVBoxLayout, QHBoxLayout, QGridLayout,
                               QScrollArea, QFrame, QPushButton, QDialog,
                               QFileDialog, QStackedWidget, QGraphicsOpacityEffect,
                               QMenu, QSystemTrayIcon, QColorDialog,
                               QSizePolicy, QSpacerItem, QTimeEdit)

from qfluentwidgets import (FluentWindow, MSFluentWindow, NavigationInterface,
                            NavigationItemPosition, FluentIcon, InfoBar,
                            InfoBarPosition, SearchLineEdit, LineEdit, ComboBox,
                            TimeEdit, PushButton, PrimaryPushButton, CardWidget,
                            ScrollArea as FluentScrollArea, CaptionLabel, BodyLabel,
                            TitleLabel, SubtitleLabel, setTheme, Theme, themeColor,
                            setThemeColor, ToolButton, RoundMenu, Action,
                            MenuAnimationType, isDarkTheme, SettingCardGroup,
                            PushSettingCard, SwitchSettingCard, SettingCard,
                            RangeSettingCard, RangeConfigItem, RangeValidator,
                            NavigationWidget)
from qfluentwidgets.components.navigation.navigation_widget import NavigationTreeItem
from qfluentwidgets.components.navigation.navigation_panel import NavigationTreeWidget
from qfluentwidgets.common.icon import drawIcon
from qfluentwidgets.common.color import autoFallbackThemeColor
from qfluentwidgets import FlowLayout

try:
    import shiboken6
except Exception:  # noqa
    shiboken6 = None


def widget_alive(w):
    """判断 Qt 对象是否仍然存活（避免访问已删除的 C++ 对象）"""
    if shiboken6 is None:
        try:
            w.isVisible()
            return True
        except Exception:
            return False
    return shiboken6.isValid(w)


# ---------------------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------------------
BASE_URL = "https://www.netbian.com"
IMG_HOST = "https://img.netbian.com"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": BASE_URL + "/index.htm",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# 分类兜底表（若动态解析失败时使用）
FALLBACK_CATEGORIES = [
    ("全部", ""),
    ("日历", "rili"),
    ("动漫", "dongman"),
    ("美女", "meinv"),
    ("游戏", "youxi"),
    ("风景", "fengjing"),
    ("动物", "dongwu"),
    ("动态", "dongtai"),
    ("节日", "jieri"),
    ("汽车", "qiche"),
    ("剧照", "juzhao"),
    ("唯美", "weimei"),
    ("设计", "sheji"),
    ("可爱", "keai"),
    ("花卉", "huahui"),
    ("人物", "renwu"),
    ("建筑", "jianzhu"),
    ("体育", "tiyu"),
    ("非主流", "feizhuliu"),
    ("打工人", "dagongren"),
]

# 分类 -> Fluent 图标 映射
CATEGORY_ICONS = {
    "": FluentIcon.HOME,
    "rili": FluentIcon.CALENDAR,
    "dongman": FluentIcon.MOVIE,
    "meinv": FluentIcon.HEART,
    "youxi": FluentIcon.GAME,
    "fengjing": FluentIcon.PHOTO,
    "dongwu": FluentIcon.GLOBE,
    "dongtai": FluentIcon.VIDEO,
    "jieri": FluentIcon.FLAG,
    "qiche": FluentIcon.CAR,
    "juzhao": FluentIcon.MEDIA,
    "weimei": FluentIcon.PALETTE,
    "sheji": FluentIcon.BRUSH,
    "keai": FluentIcon.EMOJI_TAB_SYMBOLS,
    "huahui": FluentIcon.LEAF,
    "renwu": FluentIcon.PEOPLE,
    "jianzhu": FluentIcon.TILES,
    "tiyu": FluentIcon.BASKETBALL,
    "feizhuliu": FluentIcon.TAG,
    "dagongren": FluentIcon.BUS,
}


def _app_dir():
    """程序根目录：源码运行取脚本目录，打包后取 exe 所在目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# 本地缓存目录（缩略图 / 预览原图）
CACHE_DIR = os.path.join(_app_dir(), "cache")

# 设置文件（下载目录等）
SETTINGS_FILE = os.path.join(_app_dir(), "settings.json")

# 全局下载目录（可通过设置页修改）
download_dir = os.path.join(os.path.expanduser("~"), "Pictures", "NetBianWallpapers")

import ctypes
from ctypes import wintypes


# 运行期设置（主题 / 定时切换 / 托盘），随 settings.json 持久化
SETTINGS = {
    "theme": "light",                       # light / dark
    "auto_switch": {
        "enabled": False,                    # 是否启用定时切换
        "mode": "random",                    # random 随机 / cate 指定分类
        "category": "",                      # 指定分类 slug（mode=cate 时生效，空=全部）
        "interval_min": 30,                  # 切换间隔（分钟）
    },
    "minimize_to_tray": True,                # 最小化到系统托盘
    # === 新玻璃配置（取代老的 accent_color + glass_skin + auto_color 三个独立字段）===
    # enabled   : 总开关（False 时回 Mica 默认）
    # color     : 主色源，驱动 qfw 强调色（按钮 hover/focus/链接）+ SWCA 客户区渐变色
    # blur_radius : 高斯模糊半径（5~100，控制磨砂颗粒细腻度）
    # opacity   : 不透明度（0.20~1.00，控制颜色蒙版 alpha 通道）
    # color_mode: "fixed" 用户手动色 | "follow_wallpaper" 跟随壁纸自动配色
    # last_manual_color: 关闭跟随壁纸色后回退到的颜色（保留用户上次手动偏好）
    "glass": {
        "enabled": False,
        "color": "#5E91C7",
        "blur_radius": 30,
        "opacity": 0.62,
        "color_mode": "fixed",
        "last_manual_color": "#5E91C7",
    },
    # === 定时切换深色模式 ===
    # enabled  : 总开关
    # mode     : "custom" 自定义时间段 | "sunrise" 跟随日出日落
    # start    : 自定义模式下进入深色的时刻（HH:MM）
    # end      : 自定义模式下退出深色的时刻（HH:MM，支持跨越午夜）
    # lat/lon  : 日出日落模式的经纬度（默认北京）
    "dark_schedule": {
        "enabled": False,
        "mode": "custom",
        "start": "20:00",
        "end": "07:00",
        "lat": 39.9042,
        "lon": 116.4074,
    },
}

# 自动切换可选间隔（分钟）
AUTO_INTERVALS = [5, 10, 15, 30, 60, 120, 240, 720, 1440]

# 玻璃主题预置颜色表。改字段结构为：
#   gradient_color = Windows COLORREF 编码（0xAABBGGRR，R 在最低字节，与 CSS #RRGGBB 反向）
#   blur_radius / opacity 与新版 SETTINGS["glass"] 字段对齐
# 用法：UI 上 4 个"快速预设"按钮，点击 → 把对应字段塞进 SETTINGS["glass"] → 触发 _apply_glass_skin()
# 不再像老版本那样承担"皮肤状态"语义，单纯作为预设色板。
GLASS_PRESETS = {
    "ice_blue": {
        "label": "冰蓝轻雾",
        "color": "#5E91C7",
        "gradient_color": 0x66C7915E,
        "blur_radius": 30,
        "opacity": 0.62,
    },
    "dusk_purple": {
        "label": "暮紫沉浸",
        "color": "#7A4FBF",
        "gradient_color": 0x66BF4F7A,
        "blur_radius": 22,
        "opacity": 0.50,
    },
    "caramel": {
        "label": "焦糖暖意",
        "color": "#A06C3E",
        "gradient_color": 0x663E6CA0,
        "blur_radius": 18,
        "opacity": 0.55,
    },
    "graphite": {
        "label": "极简炭灰",
        "color": "#4B5563",
        "gradient_color": 0x6663554B,
        "blur_radius": 40,
        "opacity": 0.40,
    },
}

# 兼容保留：旧版 GLASS_SKINS / GLASS_LABELS / GLASS_LABEL_TO_ID / GLASS_ID_TO_LABEL
# 仍作为别名指向新表。**仅供**迁移老 settings.json 与 _on_glass_skin_changed 内部
# 兜底使用；新代码应直接引用 GLASS_PRESETS。
GLASS_SKINS = GLASS_PRESETS  # 别名（老 load_settings 兼容读 glass_skin 字段时仍能识别 4 个 id）
GLASS_LABELS = ["冰蓝轻雾", "暮紫沉浸", "焦糖暖意", "极简炭灰"]  # 顺序用于 UI 预设按钮
GLASS_LABEL_TO_ID = {v["label"]: k for k, v in GLASS_PRESETS.items()}
GLASS_ID_TO_LABEL = {k: v["label"] for k, v in GLASS_PRESETS.items()}


def _hex_to_aa_bbggrr(hex_color, opacity):
    """把 #RRGGBB + 0~1 opacity 转 Windows COLORREF (AABBGGRR)。

    返回整数 alpha<<24 | blue<<16 | green<<8 | red。
    """
    s = (hex_color or "").lstrip("#").strip()
    if len(s) != 6:
        s = "5E91C7"   # 兜底默认冰蓝
    try:
        r = int(s[0:2], 16) & 0xFF
        g = int(s[2:4], 16) & 0xFF
        b = int(s[4:6], 16) & 0xFF
    except Exception:
        r, g, b = 0x5E, 0x91, 0xC7
    a = max(0, min(255, int(round(float(opacity) * 255)))) & 0xFF
    return (a << 24) | (b << 16) | (g << 8) | r


def _migrate_glass_legacy(cfg):
    """一次性兼容层：把老 settings.json 中的 accent_color / glass_skin / auto_color
    三个独立字段合并成新的 SETTINGS["glass"] 结构。

    返回 dict（已填默认值，可直接 set 到 SETTINGS["glass"]）。
    触发条件：cfg 不含 "glass" 字段，或 glass 为空。
    """
    old_skin = cfg.get("glass_skin", "off")
    old_accent = cfg.get("accent_color")
    old_auto = bool(cfg.get("auto_color", False))

    if old_skin in GLASS_PRESETS and GLASS_PRESETS[old_skin]:
        preset = GLASS_PRESETS[old_skin]
        color = preset["color"]
        blur = preset["blur_radius"]
        opacity = preset["opacity"]
        source_enabled = True
        source_label = "preset"
    else:
        # 没有玻璃主题启用 → 颜色从 accent_color 拿，若也没有则默认冰蓝
        color = old_accent if (old_accent and isinstance(old_accent, str)
                                and old_accent.startswith("#")) else "#5E91C7"
        blur = 30
        opacity = 0.62
        source_enabled = False
        source_label = "manual" if old_accent else "preset"

    return {
        "enabled": source_enabled,
        "color": color,
        "blur_radius": int(blur),
        "opacity": float(opacity),
        "color_mode": "follow_wallpaper" if old_auto else "fixed",
        "last_manual_color": color,
    }


def load_settings():
    """从 settings.json 加载设置"""
    global download_dir
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return
    try:
        d = cfg.get("download_dir", "")
        if d and os.path.isdir(d):
            download_dir = d
        if cfg.get("theme") in ("light", "dark"):
            SETTINGS["theme"] = cfg["theme"]
        asw = cfg.get("auto_switch")
        if isinstance(asw, dict):
            SETTINGS["auto_switch"].update(asw)
        SETTINGS["minimize_to_tray"] = bool(cfg.get("minimize_to_tray", True))
        # === 新玻璃配置加载 ===
        # 优先级：新结构 → 老字段迁移
        glass_cfg = cfg.get("glass")
        if isinstance(glass_cfg, dict) and glass_cfg:
            # 已经是新结构：补默认值
            for k, v in (
                ("enabled", False),
                ("color", "#5E91C7"),
                ("blur_radius", 30),
                ("opacity", 0.62),
                ("color_mode", "fixed"),
                ("last_manual_color", glass_cfg.get("color", "#5E91C7")),
            ):
                glass_cfg.setdefault(k, v)
            # 字段类型校验
            glass_cfg["enabled"] = bool(glass_cfg["enabled"])
            glass_cfg["color"] = str(glass_cfg["color"])
            try:
                glass_cfg["blur_radius"] = max(5, min(100, int(glass_cfg["blur_radius"])))
            except Exception:
                glass_cfg["blur_radius"] = 30
            try:
                glass_cfg["opacity"] = max(0.20, min(1.00, float(glass_cfg["opacity"])))
            except Exception:
                glass_cfg["opacity"] = 0.62
            if glass_cfg["color_mode"] not in ("fixed", "follow_wallpaper"):
                glass_cfg["color_mode"] = "fixed"
            SETTINGS["glass"] = glass_cfg
        else:
            # 老字段迁移
            SETTINGS["glass"] = _migrate_glass_legacy(cfg)
        # === 深色定时加载（缺字段补默认）===
        ds = cfg.get("dark_schedule")
        if isinstance(ds, dict) and ds:
            for k, v in (
                ("enabled", False),
                ("mode", "custom"),
                ("start", "20:00"),
                ("end", "07:00"),
                ("lat", 39.9042),
                ("lon", 116.4074),
            ):
                ds.setdefault(k, v)
            # 字段校验
            ds["enabled"] = bool(ds["enabled"])
            if ds["mode"] not in ("custom", "sunrise"):
                ds["mode"] = "custom"
            # 时间格式校验（HH:MM）
            import re as _re
            if not _re.match(r"^\d{1,2}:\d{2}$", str(ds["start"])):
                ds["start"] = "20:00"
            if not _re.match(r"^\d{1,2}:\d{2}$", str(ds["end"])):
                ds["end"] = "07:00"
            try:
                ds["lat"] = float(ds["lat"])
                ds["lon"] = float(ds["lon"])
            except Exception:
                ds["lat"] = 39.9042
                ds["lon"] = 116.4074
            SETTINGS["dark_schedule"] = ds
    except Exception:
        pass


def save_settings():
    """保存设置到 settings.json（新 schema：accent_color/glass_skin/auto_color
    三个老字段不再独立写盘，统一写到 SETTINGS["glass"]）。
    """
    cfg = {
        "download_dir": download_dir,
        "theme": SETTINGS["theme"],
        "auto_switch": SETTINGS["auto_switch"],
        "minimize_to_tray": SETTINGS["minimize_to_tray"],
        "glass": SETTINGS["glass"],
        "dark_schedule": SETTINGS.get("dark_schedule", {
            "enabled": False,
            "mode": "custom",
            "start": "20:00",
            "end": "07:00",
            "lat": 39.9042,
            "lon": 116.4074,
        }),
    }
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cache_path(url, suffix=".jpg"):
    name = hashlib.md5(url.encode("utf-8")).hexdigest() + suffix
    return os.path.join(CACHE_DIR, name)


# ---------------------------------------------------------------------------
# 日出日落计算（自实现简化版 NOAA 算法）
# ---------------------------------------------------------------------------
def _sun_times_utc(lat, lon, date):
    """计算指定经纬度 + 本地日期的日出/日落 UTC 时间。

    算法：简化版 NOAA Solar Calculator
      - Julian Day → 太阳几何 → 时角 → sunrise/sunset UTC
    精度：±5 分钟（不含大气折射/海拔修正），对"日落切深色"足够。

    参数：
      lat : 纬度（-90 ~ 90）
      lon : 经度（-180 ~ 180，正=东经）
      date: datetime.date（本地日期；UTC 偏移由调用方决定）

    返回：
      (sunrise_utc, sunset_utc) : 两个带 tzinfo=UTC 的 datetime
      极昼/极夜/异常时返回 (None, None) → 调用方按"全天白天/黑夜"处理
    """
    try:
        import math as _math
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        # ---- 1) Julian Day（参考 J2000.0 = 2000-01-01 12:00 UTC = JD 2451545.0）----
        y = date.year
        m = date.month
        d = date.day
        if m <= 2:
            y -= 1
            m += 12
        A = _math.floor(y / 100)
        B = 2 - A + _math.floor(A / 4)
        jd = _math.floor(365.25 * (y + 4716)) + _math.floor(30.6001 * (m + 1)) + d + B - 1524.5
        n = jd - 2451545.0  # 距 J2000.0 的天数
        # ---- 2) 太阳几何 ----
        L = (280.460 + 0.9856474 * n) % 360            # 平均黄经
        g = _math.radians((357.528 + 0.9856003 * n) % 360)  # 平均近点角
        lam = _math.radians(L + 1.915 * _math.sin(g) + 0.020 * _math.sin(2 * g))  # 真黄经
        eps = _math.radians(23.439 - 0.0000004 * n)    # 黄赤交角
        alpha = _math.atan2(_math.cos(eps) * _math.sin(lam), _math.cos(lam))  # 赤经
        delta = _math.asin(_math.sin(eps) * _math.sin(lam))                   # 赤纬
        # ---- 3) 恒星时 + 地方时角 ----
        gmst = (18.697374558 + 24.06570982441908 * n) % 24   # 格林威治平恒星时（小时）
        lst_h = (gmst + lon / 15.0) % 24                    # 地方恒星时（小时）
        # 太阳时角（度，-180 ~ 180）
        H_deg = ((lst_h * 15) - _math.degrees(alpha) + 540) % 360 - 180
        # ---- 4) 太阳高度角余弦：sin(h) = sin(φ)·sin(δ) + cos(φ)·cos(δ)·cos(H) ----
        # 日出日落时 h = -0.833°（考虑大气折射 + 太阳半径 ~16'）
        lat_r = _math.radians(lat)
        alt0 = _math.radians(-0.833)
        cos_H = (_math.sin(alt0) - _math.sin(lat_r) * _math.sin(delta)) / \
                (_math.cos(lat_r) * _math.cos(delta))
        if cos_H >= 1.0:
            return (None, None)   # 极夜（太阳从不出）
        if cos_H <= -1.0:
            return (None, None)   # 极昼（太阳从不落）
        H0 = _math.acos(cos_H)
        # ---- 5) UTC 时间换算 ----
        # 太阳正午 UTC = 12 - lng/15
        # sunrise_utc = noon_utc - H0/15 (小时)
        # sunset_utc  = noon_utc + H0/15 (小时)
        noon_utc_h = 12.0 - lon / 15.0
        sunrise_h = noon_utc_h - _math.degrees(H0) / 15.0
        sunset_h = noon_utc_h + _math.degrees(H0) / 15.0
        base = _dt(date.year, date.month, date.day, tzinfo=_tz.utc)
        return (base + _td(hours=sunrise_h), base + _td(hours=sunset_h))
    except Exception:
        return (None, None)


def _sun_times_local(lat, lon, date, tz_offset_hours=8):
    """把 _sun_times_utc 结果转成本地时间。
    tz_offset_hours：与 UTC 的小时偏移（中国 +8；西八区 -8；以此类推）"""
    s_utc, e_utc = _sun_times_utc(lat, lon, date)
    if s_utc is None:
        return (None, None)
    from datetime import timedelta as _td
    return (s_utc + _td(hours=tz_offset_hours),
            e_utc + _td(hours=tz_offset_hours))


def _current_tz_offset_hours():
    """取系统当前时区与 UTC 的小时偏移（用本地时间反推）。"""
    try:
        from datetime import datetime as _dt
        # 偷个懒：构造两个 datetime 算 offset
        now = _dt.now()
        utc_now = _dt.utcnow()
        delta = (now - utc_now).total_seconds() / 3600.0
        # 处理半时区（如印度 +5.5）—— 保留 1 位小数
        return round(delta, 1)
    except Exception:
        return 8.0  # 默认中国时间


def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def clean_filename(title):
    title = re.sub(r'[\\/:*?"<>|\r\n\t]', "", title).strip()
    return title if title else "wallpaper"


def _unique_path(path):
    """若文件已存在则自动加序号，避免覆盖"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        new = f"{base}_{i}{ext}"
        if not os.path.exists(new):
            return new
        i += 1


def get_current_wallpaper_path():
    """抓当前桌面壁纸的物理文件路径。

    Win11：SystemParametersInfoW(SPI_GETDESKWALLPAPER) 直接返回
    %APPDATA%\\Microsoft\\Windows\\Themes\\TranscodedWallpaper 之类
    的实际图片文件路径。注意这不是用户原图，是 DWM 转码后的副本
    （带 EXIF 去除 + 缩放到显示器分辨率），但视觉上与用户壁纸一致，
    完美适合做"玻璃后面"的内容。
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        SPI_GETDESKWALLPAPER = 0x0073
        buf = ctypes.create_unicode_buffer(260)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETDESKWALLPAPER, 260, buf, 0)
        if ok and buf.value and os.path.isfile(buf.value):
            return buf.value
    except Exception:
        pass
    return None


def set_as_wallpaper(path):
    """Windows：将指定图片设为桌面壁纸"""
    if os.name != "nt":
        raise RuntimeError("仅支持 Windows 系统")
    import ctypes
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDWININICHANGE = 0x02
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)
    if not ok:
        raise RuntimeError("设置壁纸失败（SystemParametersInfo 返回 0）")


def extract_dominant_color(image_path):
    """从图片中提取主色调，返回 hex 字符串如 '#ff6b35'，失败返回 None。

    使用 PIL 加载图片（避免打包后 Qt JPEG 插件缺失导致 QImage 加载失败）。
    算法：缩到 100x100 → HSV 色相直方图（12 桶）→
    跳过过暗/过亮/灰白像素 → 取像素最多的色相桶平均值 →
    提升饱和度、钳制亮度，确保作为主题色醒目。
    """
    try:
        from PIL import Image as PILImage
        pil = PILImage.open(image_path).convert("RGB").resize(
            (100, 100), PILImage.LANCZOS)
        pixels = list(pil.getdata())  # [(r,g,b), ...]
    except Exception:
        # 回退到 QImage（开发环境）
        img = QImage(image_path)
        if img.isNull():
            return None
        img = img.scaled(100, 100, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        img = img.convertToFormat(QImage.Format_RGBA8888)
        pixels = []
        for y in range(img.height()):
            for x in range(img.width()):
                c = QColor(img.pixel(x, y))
                pixels.append((c.red(), c.green(), c.blue()))

    hue_bins = {}   # bin -> [count, r_sum, g_sum, b_sum]
    gray_count = 0
    gray_r = gray_g = gray_b = 0

    for r, g, b in pixels:
        c = QColor(r, g, b)
        h = c.hue()
        s = c.saturation()
        v = c.value()
        # 跳过过暗、过亮
        if v < 30 or v > 235:
            continue
        if s < 40:
            # 灰色像素单独统计
            gray_count += 1
            gray_r += r
            gray_g += g
            gray_b += b
        else:
            if h < 0:
                h = 0
            bi = h // 30  # 0-11
            if bi not in hue_bins:
                hue_bins[bi] = [0, 0, 0, 0]
            e = hue_bins[bi]
            e[0] += 1
            e[1] += r
            e[2] += g
            e[3] += b

    if not hue_bins:
        # 几乎全灰：给灰色加蓝调避免太死板
        if gray_count > 0:
            r2, g2, b2 = gray_r // gray_count, gray_g // gray_count, gray_b // gray_count
            c = QColor(r2, g2, b2)
            h = c.hue() if c.hue() >= 0 else 210
            s = max(120, c.saturation())
            v = max(100, min(180, c.value()))
            c.setHsv(h, s, v)
            return c.name()
        return None

    # 像素最多的色相桶
    best = max(hue_bins.values(), key=lambda e: e[0])
    if best[0] == 0:
        return None
    avg = QColor(best[1] // best[0], best[2] // best[0], best[3] // best[0])
    h = avg.hue() if avg.hue() >= 0 else 210
    s = max(160, avg.saturation())     # 提升饱和度
    v = max(80, min(200, avg.value()))  # 钳制亮度
    avg.setHsv(h, s, v)
    return avg.name()


def _is_auto_color():
    """统一判定"自动配色（跟随壁纸色）"是否启用。

    新版字段：SETTINGS["glass"]["color_mode"] == "follow_wallpaper"
    """
    try:
        glass = SETTINGS.get("glass") or {}
        return glass.get("color_mode") == "follow_wallpaper"
    except Exception:
        return False


def notify(parent, kind, title, content, duration=2500):
    """Fluent InfoBar 通知封装"""
    fn = {"success": InfoBar.success,
          "error": InfoBar.error,
          "warning": InfoBar.warning}.get(kind, InfoBar.info)
    fn(title, content, parent=parent, duration=duration)


# ---------------------------------------------------------------------------
# 数据层：抓取与解析
# ---------------------------------------------------------------------------
class NetBian:
    """彼岸桌面数据抓取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._current_search_id = ""

    def get_html(self, url, timeout=20, retry=2, referer=None):
        """
        获取 HTML。
        - referer: 自定义 Referer；默认根据 url 推断（分类页Referer用首页，减少WAF拦截）。
        - retry: 失败后重试次数，带随机延迟。
        """
        import time
        import random

        if referer is None:
            # 分类/详情/搜索页：Referer 用首页，更像正常浏览
            referer = BASE_URL + "/index.htm"

        last = None
        req_headers = {"Referer": referer}
        kwargs = {"timeout": timeout, "headers": req_headers}
        if _HAS_CURL_CFFI:
            kwargs["impersonate"] = "chrome120"

        for i in range(retry + 1):
            try:
                resp = self.session.get(url, **kwargs)
                resp.raise_for_status()
                # 网站为 GBK 编码
                if resp.encoding and resp.encoding.lower() != "gbk":
                    try:
                        return resp.content.decode("gbk")
                    except Exception:
                        return resp.text
                return resp.text
            except Exception as e:  # noqa
                last = e
                if i < retry:
                    time.sleep(random.uniform(0.8, 2.0))
        raise last

    def get_bytes(self, url, timeout=30, referer=BASE_URL + "/index.htm"):
        headers = {"Referer": referer}
        kwargs = {"timeout": timeout, "headers": headers}
        if _HAS_CURL_CFFI:
            kwargs["impersonate"] = "chrome120"
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        return resp.content

    # ---- 分类 ----
    def fetch_categories(self):
        """动态解析首页分类导航，失败回退到内置表"""
        try:
            # 首页 Referer 用站点根目录；分类解析失败可立即 fallback，不重试
            html = self.get_html(BASE_URL + "/index.htm", referer=BASE_URL + "/", retry=0)
            block = re.search(r'<div class="nav cate">(.*?)</div>', html, re.S)
            cats = [("全部", "")]
            if block:
                for m in re.finditer(r'<a href="/([a-z]+)/">([^<]+)</a>', block.group(1)):
                    slug, name = m.group(1), m.group(2).strip()
                    if slug and name and name not in ("车机",):
                        cats.append((name, slug))
            if len(cats) > 1:
                return cats
        except Exception:
            pass
        return FALLBACK_CATEGORIES

    # ---- 列表 ----
    def fetch_list(self, url):
        """
        返回 (items, page, total_pages)
        items: [(title, thumb_url, detail_url), ...]
        """
        html = self.get_html(url)
        items = self._parse_items(html)
        page, total = self._parse_page(html)
        return items, page, total

    def _parse_items(self, html):
        items = []
        for m in re.finditer(
                r'<li><a href="(/desk/\d+\.htm)"[^>]*title="([^"]*)"[^>]*>'
                r'\s*<img src="([^"]+)".*?/>\s*<b>(.*?)</b></a></li>',
                html):
            detail = m.group(1)
            title = self._clean_title(m.group(2)) or self._clean_title(m.group(4))
            thumb = self._abs(m.group(3))
            if thumb and title:
                items.append((title, thumb, detail))
        # 去重（按详情链接）
        seen, uniq = set(), []
        for it in items:
            if it[2] not in seen:
                seen.add(it[2])
                uniq.append(it)
        return uniq

    def _parse_page(self, html):
        m = re.search(r'<div class="page">(.*?)</div>', html, re.S)
        if not m:
            return 1, 1
        block = m.group(1)
        cur = 1
        cur_m = re.search(r'<b>(\d+)</b>', block)
        if cur_m:
            cur = int(cur_m.group(1))

        pages = set()
        # 首页/分类：index_N.htm（第 1 页无后缀）
        for x in re.findall(r'index_(\d+)\.htm', block):
            pages.add(int(x))
        # 搜索：/search/{id}-{n}.html，n 从 0 起，页码 = n + 1
        for x in re.findall(r'/search/\d+-(\d+)\.html', block):
            pages.add(int(x) + 1)
        if not pages:
            pages = set(int(x) for x in re.findall(r'>(\d+)<', block))

        total = max(pages) if pages else 1
        return cur, max(total, cur)

    def _clean_title(self, s):
        """去掉搜索高亮 <font> 标签与「更新时间」后缀"""
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'\s*更新时间[：:]\s*\d{4}-\d{2}-\d{2}.*$', '', s)
        return s.strip()

    def _abs(self, url):
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return BASE_URL + url
        if url.startswith("http"):
            return url
        return ""

    # ---- 搜索 ----
    def search(self, keyword):
        """
        关键词搜索第一页。返回 (search_id, items, page, total_pages)
        后续翻页用 fetch_list 直接 GET /search/{id}-{n}.html
        """
        post_kwargs = {
            "data": {
                "keyboard": keyword.encode("gbk"),
                "tempid": "1",
                "tbname": "bzdb",
                "show": "title",
                "submit": "搜索".encode("gbk"),
            },
            "timeout": 20,
            "allow_redirects": True,
            "headers": {"Referer": BASE_URL + "/index.htm"},
        }
        if _HAS_CURL_CFFI:
            post_kwargs["impersonate"] = "chrome120"

        resp = self.session.post(BASE_URL + "/e/search/index.php", **post_kwargs)
        resp.raise_for_status()
        url = resp.url  # 形如 /search/{id}-0.html

        html = self.get_html(url, referer=BASE_URL + "/index.htm")
        items = self._parse_items(html)
        page, total = self._parse_page(html)

        sid = ""
        m = re.search(r'/search/(\d+)-\d+\.html', url)
        if m:
            sid = m.group(1)
        self._current_search_id = sid
        return sid, items, page, total

    # ---- 详情 ----
    def fetch_detail(self, detail_path, thumb_url):
        """返回 {'title','origin','resolutions', 'res_text','detail_url'}"""
        url = BASE_URL + detail_path if detail_path.startswith("/") else detail_path
        html = self.get_html(url)

        origin = ""
        m = re.search(r'<div class="pic">.*?<img src="([^"]+)"', html, re.S)
        if m:
            origin = self._abs(m.group(1))
        if not origin:
            # 兜底：取第一个非 small 的原图
            for cand in re.findall(r'(?:https?:)?//img\.netbian\.com/file/[^"\'\s]+?\.jpg', html):
                if "/small" not in cand:
                    origin = self._abs(cand)
                    break

        # 分辨率信息
        res = []
        for r in re.findall(r'(\d{3,4}x\d{3,4})', html):
            if r not in res:
                res.append(r)
        return {
            "title": "",
            "origin": origin,
            "resolutions": res,
            "res_text": " / ".join(res) if res else "",
            "detail_url": url,
        }


# ---------------------------------------------------------------------------
# 信号桥（跨线程通信）
# ---------------------------------------------------------------------------
class Bridge(QObject):
    categories_loaded = Signal(list)
    list_loaded = Signal(object)          # (items, page, total)
    list_failed = Signal(str)
    thumb_ready = Signal(int, bytes)      # card_id, image bytes
    detail_ready = Signal(object, object)  # (dlg, detail dict)
    detail_failed = Signal(object, str)
    origin_ready = Signal(object, bytes, str)  # (dlg, bytes, info)
    download_done = Signal(str)
    download_failed = Signal(str)
    # 卡片右键菜单直接下载/设壁纸
    card_download_done = Signal(object, str)      # (parent, path)
    card_download_failed = Signal(object, str)
    card_wallpaper_done = Signal(object, str)     # (parent, title)
    card_wallpaper_failed = Signal(object, str)
    # 定时自动切换壁纸
    auto_switch_done = Signal(str)                 # title
    auto_switch_failed = Signal(str)


bridge = Bridge()


# ---------------------------------------------------------------------------
# 缩略图卡片（Fluent CardWidget）
# ---------------------------------------------------------------------------
_card_seq = 0


class WallpaperCard(CardWidget):
    clicked = Signal(object)              # 左键点击
    download_requested = Signal(object)   # 右键菜单：下载到本地
    wallpaper_requested = Signal(object)  # 右键菜单：设为壁纸

    def __init__(self, title, thumb_url, detail_url, parent=None):
        super().__init__(parent)
        global _card_seq
        _card_seq += 1
        self.card_id = _card_seq
        self.title = title
        self.thumb_url = thumb_url
        self.detail_url = detail_url

        self.setFixedSize(238, 198)
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.img_label = QLabel("加载中…")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setObjectName("cardImg")
        self.img_label.setFixedSize(222, 128)
        # 背景跟随 Fluent 卡片主题，文字颜色由主题 palette 决定
        self.img_label.setStyleSheet(
            "background:transparent; border-radius:6px; font-size:12px;")

        self.title_label = QLabel(self._ellipsis(title))
        self.title_label.setObjectName("cardTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setToolTip(title)
        # 根据主题设置黑/白文字，确保浅色/深色下都有足够对比度
        self._update_text_color()

        lay.addWidget(self.img_label, 0, Qt.AlignHCenter)
        lay.addWidget(self.title_label)

    def _update_text_color(self):
        """同步标题颜色到当前 Fluent 主题"""
        color = "#f5f5f5" if isDarkTheme() else "#1a1a1a"
        self.title_label.setStyleSheet(
            f"font-size:12px; background:transparent; border:none; color:{color};")

    def _ellipsis(self, s, n=20):
        return s if len(s) <= n else s[:n] + "…"

    def set_thumb(self, data: bytes):
        pm = QPixmap()
        if pm.loadFromData(data):
            scaled = pm.scaled(
                self.img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(scaled)
        else:
            self.img_label.setText("加载失败")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Fluent 右键菜单：设为壁纸 / 下载到本地"""
        menu = RoundMenu(parent=self)
        a_wallpaper = Action(FluentIcon.PHOTO, "设为壁纸", self)
        a_wallpaper.triggered.connect(lambda: self.wallpaper_requested.emit(self))
        menu.addAction(a_wallpaper)
        menu.addSeparator()
        a_download = Action(FluentIcon.DOWNLOAD, "下载到本地", self)
        a_download.triggered.connect(lambda: self.download_requested.emit(self))
        menu.addAction(a_download)
        menu.exec(event.globalPos(), aniType=MenuAnimationType.FADE_IN_DROP_DOWN)


# ---------------------------------------------------------------------------
# 可拖拽查看的大图标签
# ---------------------------------------------------------------------------
class DraggableImageLabel(QLabel):
    """支持鼠标拖拽滚动浏览的大图标签"""

    def __init__(self, scroll_area: QScrollArea, parent=None):
        super().__init__(parent)
        self._scroll = scroll_area
        self._dragging = False
        self._last_pos = None
        self.setCursor(Qt.OpenHandCursor)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._last_pos is not None:
            cur = event.globalPosition().toPoint()
            delta = cur - self._last_pos
            self._last_pos = cur
            hbar = self._scroll.horizontalScrollBar()
            vbar = self._scroll.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._last_pos = None
            self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# 可缩放滚动区（滚轮缩放）
# ---------------------------------------------------------------------------
class ZoomScrollArea(FluentScrollArea):
    """滚轮触发缩放信号：向上放大、向下缩小

    继承 qfw 的 FluentScrollArea 而非原生 QScrollArea，目的是让滚动条样式
    跟随主程序主题（亮/暗）。其余 API（viewport/setWidgetResizable/
    setAlignment）与 QScrollArea 完全兼容。
    """

    zoom_signal = Signal(int)   # >0 放大, <0 缩小

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta != 0:
            self.zoom_signal.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)


# ---------------------------------------------------------------------------
# 大图预览窗口
# ---------------------------------------------------------------------------
class PreviewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("壁纸预览")
        self.resize(920, 640)
        # 支持最大化、最小化、自由缩放
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint)
        self._origin_url = ""
        self._origin_bytes = None
        self._title = "wallpaper"
        self._pixmap = None          # 原始分辨率 QPixmap
        self._fit_mode = True        # 默认适应窗口
        self._zoom = 1.0             # 相对原始尺寸的缩放倍率
        self._fit_ratio = 1.0        # 适应窗口时的实际缩放比例

        # 主题感知配色（随主窗口主题变化）
        from qfluentwidgets import isDarkTheme
        self._dark = isDarkTheme()
        self._init_theme_colors()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 顶部缩放工具条（跟随主题）
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet(f"background:{self._c_bg}; border:none;")
        top = QHBoxLayout(self.top_bar)
        top.setContentsMargins(12, 6, 12, 6)
        top.setSpacing(6)
        self.btn_zoom_in = self._zoom_btn(FluentIcon.ZOOM_IN, "放大")
        self.btn_zoom_out = self._zoom_btn(FluentIcon.ZOOM_OUT, "缩小")
        self.btn_fit = self._zoom_btn(FluentIcon.FIT_PAGE, "适应窗口")
        self.btn_actual = self._zoom_btn(FluentIcon.ZOOM, "实际大小")
        self.zoom_label = QLabel("适应窗口")
        self.zoom_label.setStyleSheet(f"color:{self._c_text}; background:transparent; font-size:12px;")
        top.addWidget(self.btn_zoom_in)
        top.addWidget(self.btn_zoom_out)
        top.addWidget(self.btn_fit)
        top.addWidget(self.btn_actual)
        top.addSpacing(10)
        top.addWidget(self.zoom_label)
        top.addStretch(1)
        lay.addWidget(self.top_bar)

        self.scroll = ZoomScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(f"background:{self._c_viewport}; border:none;")
        self.img_label = DraggableImageLabel(self.scroll)
        self.img_label.setText("正在加载原图…")
        self.img_label.setMinimumSize(600, 400)
        self.scroll.setWidget(self.img_label)
        lay.addWidget(self.scroll, 1)

        self._bottom_bar = QWidget()
        self._bottom_bar.setStyleSheet(f"background:{self._c_bg}; border:none;")
        bar = QHBoxLayout(self._bottom_bar)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(8)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color:{self._c_info}; background:transparent;")
        self.btn_wallpaper = PrimaryPushButton(FluentIcon.VIEW, "设为壁纸")
        self.btn_download = PrimaryPushButton(FluentIcon.DOWNLOAD, "下载到本地")
        self.btn_close = PushButton("关闭")
        bar.addWidget(self.info_label, 1)
        bar.addWidget(self.btn_wallpaper)
        bar.addWidget(self.btn_download)
        bar.addWidget(self.btn_close)
        lay.addWidget(self._bottom_bar)

        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_fit.clicked.connect(self._fit)
        self.btn_actual.clicked.connect(self._actual)
        self.scroll.zoom_signal.connect(self._on_wheel_zoom)
        self.btn_wallpaper.clicked.connect(self._on_set_wallpaper)
        self.btn_download.clicked.connect(self._on_download)
        self.btn_close.clicked.connect(self.accept)

        # 监听主程序主题变化：用户切主题时同步刷新顶/底条配色
        # 解绑在 closeEvent 里做，避免 dialog 关闭后信号回调已死对象
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChanged.connect(self._on_theme_changed)
        except Exception:
            pass

    # ---------- 主题色（构造时 + themeChanged 回调都用）----------
    def _init_theme_colors(self):
        """构造时一次性算出主题色（自用，避免与 _on_theme_changed 重复代码）"""
        # 浅色用微软 Fluent 浅灰背景，深色用 Mica 暗色背景
        if self._dark:
            self._c_bg = "#1f1f1f"
            self._c_viewport = "#2a2a2a"
            self._c_text = "#ffffff"
            self._c_info = "#999999"
        else:
            self._c_bg = "#f5f5f5"
            self._c_viewport = "#ffffff"
            self._c_text = "#333333"
            self._c_info = "#666666"

    def _on_theme_changed(self):
        """主程序主题切换时同步刷新弹窗顶/底条配色"""
        from qfluentwidgets import isDarkTheme
        self._dark = isDarkTheme()
        self._init_theme_colors()
        # 顶/底条背景
        if hasattr(self, "top_bar") and self.top_bar is not None:
            self.top_bar.setStyleSheet(
                f"background:{self._c_bg}; border:none;")
        if hasattr(self, "_bottom_bar") and self._bottom_bar is not None:
            self._bottom_bar.setStyleSheet(
                f"background:{self._c_bg}; border:none;")
        # viewport 背景
        if hasattr(self, "scroll") and self.scroll is not None:
            self.scroll.setStyleSheet(
                f"background:{self._c_viewport}; border:none;")
        # 文字色
        if hasattr(self, "zoom_label") and self.zoom_label is not None:
            self.zoom_label.setStyleSheet(
                f"color:{self._c_text}; background:transparent; font-size:12px;")
            self.zoom_label.repaint()
        if hasattr(self, "info_label") and self.info_label is not None:
            self.info_label.setStyleSheet(
                f"color:{self._c_info}; background:transparent;")
            self.info_label.repaint()

    def closeEvent(self, event):
        # 解绑主题信号，避免 dialog 已销毁后被 Qt 回调炸掉
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChanged.disconnect(self._on_theme_changed)
        except Exception:
            pass
        super().closeEvent(event)

    def _zoom_btn(self, icon, tooltip):
        b = ToolButton(self)
        b.setIcon(icon.icon())
        b.setIconSize(QSize(18, 18))
        b.setFixedSize(34, 30)
        b.setToolTip(tooltip)
        return b

    # ---------- 缩放 ----------
    def _effective_scale(self):
        return self._fit_ratio if self._fit_mode else self._zoom

    def _on_wheel_zoom(self, direction):
        if direction > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _zoom_in(self):
        if self._pixmap is None:
            return
        self._fit_mode = False
        self._zoom = min(self._effective_scale() * 1.25, 8.0)
        self._render()

    def _zoom_out(self):
        if self._pixmap is None:
            return
        self._fit_mode = False
        self._zoom = max(self._effective_scale() * 0.8, 0.05)
        self._render()

    def _fit(self):
        self._fit_mode = True
        self._render()

    def _actual(self):
        self._fit_mode = False
        self._zoom = 1.0
        self._render()

    def _render(self):
        if self._pixmap is None or self._pixmap.isNull():
            return
        orig = self._pixmap.size()
        if self._fit_mode:
            vp = self.scroll.viewport().size()
            target = QSize(max(10, vp.width() - 8), max(10, vp.height() - 8))
            scaled = self._pixmap.scaled(
                target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._fit_ratio = scaled.width() / max(1, orig.width())
        else:
            w = max(1, int(orig.width() * self._zoom))
            h = max(1, int(orig.height() * self._zoom))
            scaled = self._pixmap.scaled(
                QSize(w, h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(scaled)
        self.img_label.setMinimumSize(scaled.size())
        if self._fit_mode:
            self.zoom_label.setText(f"适应窗口（{int(self._fit_ratio * 100)}%）")
        else:
            self.zoom_label.setText(f"{int(self._zoom * 100)}%")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._pixmap is not None:
            QTimer.singleShot(0, self._render)

    def show_loading(self, title):
        self._title = clean_filename(title)
        self.setWindowTitle("壁纸预览 - " + title)
        self.info_label.setText("正在加载…")
        self.img_label.setText("正在加载原图…")
        self.img_label.setMinimumSize(600, 400)
        self._origin_bytes = None
        self._pixmap = None
        self._fit_mode = True
        self._zoom = 1.0
        self._fit_ratio = 1.0
        self.zoom_label.setText("适应窗口")

    def set_image(self, data: bytes, info=""):
        self._origin_bytes = data
        pm = QPixmap()
        if pm.loadFromData(data):
            self._pixmap = pm
            self.info_label.setText(info or f"分辨率：{pm.width()}×{pm.height()}")
            self._fit_mode = True
            self._render()
        else:
            self.img_label.setText("无法显示该图片")

    def set_origin_url(self, url):
        self._origin_url = url

    def _on_set_wallpaper(self):
        data = self._origin_bytes
        if not data:
            notify(self, "warning", "尚未加载完成", "图片仍在加载中，请稍候", 2000)
            return
        try:
            ensure_cache_dir()
            tmp = os.path.join(CACHE_DIR, "_current_wallpaper.jpg")
            with open(tmp, "wb") as f:
                f.write(data)
            set_as_wallpaper(tmp)
            notify(self, "success", "设置成功", "桌面壁纸已更新", 2500)
            # 自动配色：从预览设的壁纸提取主色调
            if _is_auto_color():
                app = QApplication.instance()
                mw = None
                for ww in app.topLevelWidgets():
                    if ww.isVisible() and hasattr(ww, "_extract_and_apply_color") and isinstance(ww, QMainWindow):
                        mw = ww
                        break
                if mw:
                    mw._extract_and_apply_color(tmp)
        except Exception as e:  # noqa
            notify(self, "error", "设置失败", str(e), 4000)

    def _on_download(self):
        data = self._origin_bytes
        if not data:
            notify(self, "warning", "尚未加载完成", "图片仍在加载中，请稍候", 2000)
            return
        default = os.path.join(os.path.expanduser("~"), "Pictures",
                               self._title + ".jpg")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存壁纸", default, "JPEG 图片 (*.jpg);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(data)
            notify(self, "success", "下载成功", f"已保存到：{path}", 4500)
        except Exception as e:  # noqa
            notify(self, "error", "下载失败", str(e), 4000)


# ---------------------------------------------------------------------------
# 内容页（工具栏 + 壁纸网格）
# ---------------------------------------------------------------------------
class WallpaperPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("wallpaperPage")
        # 壁纸展示区底色跟主窗口纯色背景保持一致：page / scroll / grid_host 全透明
        self.setStyleSheet("WallpaperPage { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索壁纸关键词…")
        self.search_edit.setFixedWidth(260)
        self.btn_reset = PushButton(FluentIcon.HOME, "全部")

        toolbar.addWidget(self.search_edit)
        toolbar.addWidget(self.btn_reset)
        toolbar.addSpacing(8)
        toolbar.addStretch(1)

        # 分页区
        self.btn_prev = PushButton(FluentIcon.PAGE_LEFT, "上一页")
        self.page_edit = LineEdit()
        self.page_edit.setPlaceholderText("页码")
        self.page_edit.setFixedWidth(72)
        self.page_edit.setClearButtonEnabled(True)
        self.btn_next = PushButton(FluentIcon.PAGE_RIGHT, "下一页")
        self.btn_goto = PrimaryPushButton("跳转")
        self.page_info = CaptionLabel("共 0 页")

        toolbar.addWidget(self.btn_prev)
        toolbar.addWidget(self.page_edit)
        toolbar.addWidget(self.btn_next)
        toolbar.addWidget(self.btn_goto)
        toolbar.addWidget(self.page_info)

        root.addLayout(toolbar)

        # ---- 网格滚动区 ----
        self.scroll = FluentScrollArea()
        self.scroll.setWidgetResizable(True)
        # scroll + viewport + grid_host 全透明，底色由主窗口纯色背景决定
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.grid_host = QWidget()
        self.grid_host.setObjectName("gridHost")
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        # 监听 grid_host 自身的尺寸变化（scroll 内部 resize 时不会触发 page.resizeEvent）
        self.grid_host.installEventFilter(self)
        # 首次进入页面时延后重排一次，保证拿到正确的 viewport 宽度
        QTimer.singleShot(0, self._relayout)

    # ---------- 自适应布局 ----------
    def _relayout(self):
        """根据当前可用宽度重排 grid 列数（建议通过 QTimer.singleShot 延迟调用）"""
        if self.grid.count() == 0:
            return
        cards = []
        for i in range(self.grid.count()):
            it = self.grid.itemAt(i)
            if it is None:
                continue
            w = it.widget()
            if isinstance(w, WallpaperCard):
                cards.append(w)
        if not cards:
            return
        # 用 scroll viewport 的宽度，比 grid_host.width() 更准确（不含滚动条边距）
        viewport_w = max(1, self.scroll.viewport().width())
        spacing = self.grid.spacing()
        card_w = 238  # WallpaperCard 固定宽度
        cols = max(1, (viewport_w + spacing) // (card_w + spacing))
        # 清空再按新列数放回
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(cards):
            r, c = divmod(i, cols)
            self.grid.addWidget(card, r, c)

    def eventFilter(self, obj, event):
        """grid_host Resize 时延后重排（scroll 内部 resize 不会触发 page.resizeEvent）"""
        if obj is self.grid_host and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._relayout)
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 延后一帧再读 viewport 宽度，避免布局未传播读到旧值
        QTimer.singleShot(0, self._relayout)

    def showEvent(self, event):
        super().showEvent(event)
        # 在 showEvent 中重新应用 DWM 暗色模式（winId 此时确保有效）
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof
            hwnd = int(self.winId())
            val = c_int(1 if self._dark else 0)
            for attr in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, byref(val), sizeof(val))
                except Exception:
                    pass
        except Exception:
            pass
        QTimer.singleShot(0, self._relayout)


# ---------------------------------------------------------------------------
# 设置页
# ---------------------------------------------------------------------------
class ComboSettingCard(SettingCard):
    """带下拉框的设置卡片（不依赖 qconfig）"""

    def __init__(self, icon, title, content=None, texts=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.comboBox.setFixedWidth(170)
        if texts:
            self.comboBox.addItems(texts)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class TimeSettingCard(SettingCard):
    """带主题化 QTimeEdit 的设置卡片（用于深色定时 start/end）

    用 qfw 的 TimeEdit（继承自 QTimeEdit），自动跟随当前主题的
    文字色 / 背景色，避免浅色主题下原生控件看不清楚。
    """

    def __init__(self, icon, title, content=None, initial="08:00", parent=None):
        super().__init__(icon, title, content, parent)
        from PySide6.QtCore import QTime
        self.timeEdit = TimeEdit(self)
        self.timeEdit.setDisplayFormat("HH:mm")
        # 120 太窄：qfw TimeEdit 自带上下箭头 + 时/分两段，会截断显示不全。
        # 放宽到 170，保证 HH:mm 完整展示。
        self.timeEdit.setFixedWidth(170)
        h, m = (int(x) for x in str(initial).split(":")[:2])
        self.timeEdit.setTime(QTime(max(0, min(23, h)), max(0, min(59, m))))
        self.hBoxLayout.addWidget(self.timeEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class LineEditSettingCard(SettingCard):
    """带主题化 LineEdit 的设置卡片（用于深色定时 经度/纬度）

    用 qfw 的 LineEdit（继承自 QLineEdit），自动跟随当前主题的
    文字色，浅色主题下依然清晰。
    """

    def __init__(self, icon, title, content=None, initial="", placeholder="", parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setFixedWidth(170)
        self.lineEdit.setText(str(initial) if initial is not None else "")
        if placeholder:
            self.lineEdit.setPlaceholderText(placeholder)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)




def _get_cache_size_str():
    """返回 cache 目录的可读大小字符串"""
    try:
        total = 0
        if os.path.isdir(CACHE_DIR):
            for dirpath, _, filenames in os.walk(CACHE_DIR):
                for fn in filenames:
                    fp = os.path.join(dirpath, fn)
                    try:
                        total += os.path.getsize(fp)
                    except Exception:
                        pass
        if total < 1024:
            return f"{total} B"
        elif total < 1024 * 1024:
            return f"{total / 1024:.1f} KB"
        else:
            return f"{total / (1024 * 1024):.1f} MB"
    except Exception:
        return "未知"


def _clear_cache():
    """清理 cache 目录中所有文件（保留当前壁纸和自动取色文件）"""
    import shutil
    keep = {"_current_wallpaper.jpg", "_auto_wallpaper.jpg"}
    removed = 0
    if os.path.isdir(CACHE_DIR):
        for fn in os.listdir(CACHE_DIR):
            if fn in keep:
                continue
            fp = os.path.join(CACHE_DIR, fn)
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
                    removed += 1
                elif os.path.isdir(fp):
                    shutil.rmtree(fp, ignore_errors=True)
                    removed += 1
            except Exception:
                pass
    return removed


# ---------------------------------------------------------------------------
# 关于软件 - 自绘小组件
# 圆底图标徽标 / 版本胶囊。画色在 paintEvent 里实时取 themeColor() 与
# isDarkTheme()；qfw 切换主题会触发全窗口重绘，因此深/浅主题都会自动刷新，
# 无需额外信号，稳定且两种主题下都清晰。
# ---------------------------------------------------------------------------
class _AboutBadge(QWidget):
    """圆形应用图标徽标：主题主色渐变圆底 + 白色图标。"""

    def __init__(self, icon, size=64, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor, QLinearGradient, QBrush
        from PySide6.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.SmoothPixmapTransform)
        painter.setPen(Qt.NoPen)
        base = themeColor()
        s = self._size
        grad = QLinearGradient(0, 0, s, s)
        grad.setColorAt(0.0, base.lighter(120))
        grad.setColorAt(1.0, base.darker(108))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QRectF(0, 0, s, s))
        # 顶部细高光，增加圆润感
        painter.setBrush(QColor(255, 255, 255, 36))
        painter.drawEllipse(QRectF(s * 0.16, s * 0.06, s * 0.68, s * 0.40))
        # 白色图标（居中）
        iw = int(s * 0.54)
        pix = self._icon.icon(QColor("#ffffff")).pixmap(iw, iw)
        painter.drawPixmap(int((s - iw) / 2), int((s - iw) / 2), pix)
        painter.end()


class _AboutPill(QWidget):
    """版本胶囊：主题主色淡底 + 主色文字，圆角。"""

    def __init__(self, text=APP_VERSION_DISPLAY, parent=None):
        super().__init__(parent)
        self._text = text
        f = self.font()
        f.setPointSizeF(max(9.5, f.pointSizeF()))
        self.setFont(f)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.TextAntialiasing)
        painter.setPen(Qt.NoPen)
        base = themeColor()
        bg = QColor(base)
        bg.setAlpha(42)
        painter.setBrush(bg)
        painter.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)
        painter.setPen(base)
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
        painter.end()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._text) + 28, 24)


class SettingPage(FluentScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingPage")
        self._categories = list(FALLBACK_CATEGORIES)  # [(name, slug)]
        self._init_ui()
        self.refresh()

    @staticmethod
    def _fmt_interval(m):
        if m < 60:
            return f"{m} 分钟"
        if m % 60 == 0:
            return f"{m // 60} 小时"
        return f"{m // 60} 小时 {m % 60} 分钟"

    def _init_ui(self):
        # 使用滚动区域：创建容器 widget，内容超出时可滚动查看
        self.container = QWidget(self)
        self.container.setObjectName("settingContainer")
        root = QVBoxLayout(self.container)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignTop)
        # 滚动区域 + viewport + 容器 全透明，底色由主窗口纯色背景决定（适配深浅主题）
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }")
        self.viewport().setStyleSheet("background: transparent;")
        self.container.setStyleSheet("background: transparent;")
        # 滚动区域配置
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setWidget(self.container)

        title = SubtitleLabel("设置")
        root.addWidget(title)

        # ---- 下载设置 ----
        self.group_dl = SettingCardGroup("下载设置", self)
        self.card_download = PushSettingCard(
            "修改", FluentIcon.DOWNLOAD, "下载目录",
            f"当前：{download_dir}", self)
        # 长路径用省略号显示，避免撑破卡片布局
        self.card_download.contentLabel.setWordWrap(False)
        self.card_download.clicked.connect(self._choose_download_dir)
        self.group_dl.addSettingCard(self.card_download)
        root.addWidget(self.group_dl)

        # ---- 外观 ----
        self.group_ui = SettingCardGroup("外观", self)
        self.card_theme = SwitchSettingCard(
            FluentIcon.BRIGHTNESS, "深色主题",
            "开启后使用深色主题，退出后仍生效", None, self)
        self.card_theme.checkedChanged.connect(self._on_theme_changed)
        self.group_ui.addSettingCard(self.card_theme)

        # === 新版窗口半透明风格（合并"自定义主题色"+"磨砂玻璃"+"自动配色"）===

        # 总开关：启用磨砂玻璃
        self.card_glass_enabled = SwitchSettingCard(
            FluentIcon.VIDEO, "启用磨砂玻璃",
            "开启后主窗口呈半透明效果；关闭时回 Mica 默认", None, self)
        self.card_glass_enabled.checkedChanged.connect(self._on_glass_enabled_changed)
        self.group_ui.addSettingCard(self.card_glass_enabled)

        # 跟随壁纸自动配色（取代老的 auto_color）
        self.card_glass_color_mode = SwitchSettingCard(
            FluentIcon.PALETTE, "跟随壁纸自动配色",
            "设置壁纸后自动提取主色调，驱动窗口半透明色与 qfw 强调色",
            None, self)
        self.card_glass_color_mode.checkedChanged.connect(
            self._on_glass_color_mode_changed)
        self.group_ui.addSettingCard(self.card_glass_color_mode)

        # 窗口半透明色（取代老的"自定义主题色"卡片，颜色字段已合并到 glass.color）
        glass_color = (SETTINGS.get("glass") or {}).get("color") or "#5E91C7"
        self.card_glass_color = PushSettingCard(
            "选择", FluentIcon.BRUSH, "窗口半透明色",
            f"当前：{glass_color}", self)
        self.card_glass_color.clicked.connect(self._choose_glass_color)
        self.group_ui.addSettingCard(self.card_glass_color)

        # 模糊强度（5~100）
        blur_value = int((SETTINGS.get("glass") or {}).get("blur_radius", 30))
        blur_cfg = RangeConfigItem("glass", "blur_radius", blur_value,
                                    RangeValidator(5, 100), self)
        self.card_glass_blur = RangeSettingCard(
            blur_cfg, FluentIcon.EDIT, "模糊强度",
            "数值越大磨砂颗粒越细腻（5 颗粒感强，100 接近全雾）", self)
        self.card_glass_blur.valueChanged.connect(
            self._on_glass_blur_changed)
        self.group_ui.addSettingCard(self.card_glass_blur)

        # 不透明度（20~100%，对应 0.20~1.00，滑块用整数百分比更直观）
        opacity_pct = int(round((SETTINGS.get("glass") or {}).get("opacity", 0.62)
                                 * 100))
        opacity_cfg = RangeConfigItem("glass", "opacity_pct", opacity_pct,
                                       RangeValidator(20, 100), self)
        self.card_glass_opacity = RangeSettingCard(
            opacity_cfg, FluentIcon.TRANSPARENT, "不透明度",
            "数值越大窗口颜色越不透明（20% 透感强，100% 完全不透）", self)
        self.card_glass_opacity.valueChanged.connect(
            self._on_glass_opacity_changed)
        self.group_ui.addSettingCard(self.card_glass_opacity)

        # 4 个预置颜色按钮组（快速应用）
        # 用 QHBoxLayout + 等宽均分：4 个按钮横向排成一行，宽度均分占满容器，
        # 即使容器偏窄也保持一行（每个按钮拉伸均分宽度）而不是竖向堆叠。
        # 关键点：① 按钮均分（addWidget(..., 1)）保证一行放得下 ② 移除
        # SettingCard.hBoxLayout 末尾的 stretch(1)，让按钮占中段而不是挤到右
        # ③ 保留小 stretch 兜底，避免按钮贴死卡片右边
        self.group_ui_presets = SettingCardGroup("快速预设", self)
        preset_card = SettingCard(
            FluentIcon.HEART, "颜色预设",
            "点击预设按钮，立即应用对应颜色/模糊/不透明度组合", self)
        from PySide6.QtWidgets import QHBoxLayout
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(12, 0, 12, 0)
        preset_row.setSpacing(8)
        self._preset_buttons = {}
        for pid in ("ice_blue", "dusk_purple", "caramel", "graphite"):
            preset = GLASS_PRESETS[pid]
            btn = PushButton(preset["label"], preset_card)
            btn.setToolTip(f"{preset['color']} · blur={preset['blur_radius']} · "
                            f"opacity={preset['opacity']}")
            btn.clicked.connect(lambda _checked=False, k=pid: self._apply_glass_preset(k))
            # 每个按钮等宽拉伸，保证横向一行占满容器
            preset_row.addWidget(btn, 1)
            self._preset_buttons[pid] = btn
        # SettingCard.hBoxLayout 末尾默认有一个 stretch(1)，它会把按钮推到最右；
        # 这里 takeAt 掉末尾 stretch，让按钮紧跟标题容器、占中段
        last_idx = preset_card.hBoxLayout.count() - 1
        last_item = preset_card.hBoxLayout.itemAt(last_idx)
        if last_item is not None and last_item.spacerItem() is not None:
            preset_card.hBoxLayout.takeAt(last_idx)
        preset_card.hBoxLayout.addLayout(preset_row)
        # 加一个极小的 stretch 保底，避免按钮贴死卡片右边
        preset_card.hBoxLayout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.group_ui_presets.addSettingCard(preset_card)

        # 把预设组合并到外观组之后追加（视觉上仍属于外观区）
        root.addWidget(self.group_ui)
        root.addWidget(self.group_ui_presets)

        # 初始同步所有玻璃卡片（blockSignals 避免触发 _on_*）
        self._sync_glass_ui()

        # ---- 定时切换壁纸 ----
        self.group_auto = SettingCardGroup("定时切换壁纸", self)
        self.card_auto_enabled = SwitchSettingCard(
            FluentIcon.SYNC, "自动切换壁纸",
            "开启后按设定间隔自动更换桌面壁纸", None, self)
        self.card_auto_enabled.checkedChanged.connect(self._on_auto_enabled)
        self.group_auto.addSettingCard(self.card_auto_enabled)

        self.card_auto_mode = ComboSettingCard(
            FluentIcon.PALETTE, "切换方式", "随机或指定分类",
            ["随机切换", "指定分类"], self)
        self.card_auto_mode.comboBox.currentIndexChanged.connect(self._on_auto_mode)
        self.group_auto.addSettingCard(self.card_auto_mode)

        self.card_auto_cate = ComboSettingCard(
            FluentIcon.PHOTO, "指定分类", "仅“指定分类”方式下生效",
            [], self)
        self.card_auto_cate.comboBox.currentIndexChanged.connect(self._on_auto_cate)
        self.group_auto.addSettingCard(self.card_auto_cate)

        self.card_auto_interval = ComboSettingCard(
            FluentIcon.HISTORY, "切换间隔", "每隔多久自动切换一次",
            [self._fmt_interval(m) for m in AUTO_INTERVALS], self)
        self.card_auto_interval.comboBox.currentIndexChanged.connect(self._on_auto_interval)
        self.group_auto.addSettingCard(self.card_auto_interval)
        root.addWidget(self.group_auto)

        # ---- 定时切换主题（深色模式）----
        self.group_dark_sch = SettingCardGroup("定时切换主题", self)
        # 总开关
        self.card_ds_enabled = SwitchSettingCard(
            FluentIcon.ROTATE, "定时切换深色模式",
            "开启后按设定时间或日出日落自动在深色/浅色之间切换",
            None, self)
        self.card_ds_enabled.checkedChanged.connect(self._on_ds_enabled_changed)
        self.group_dark_sch.addSettingCard(self.card_ds_enabled)
        # 模式
        self.card_ds_mode = ComboSettingCard(
            FluentIcon.MENU, "切换方式",
            "自定义时间：按你设的起止时刻切换深色；跟随日出日落：按当地经纬度计算",
            ["自定义时间", "跟随日出日落"], self)
        self.card_ds_mode.comboBox.currentIndexChanged.connect(self._on_ds_mode_changed)
        self.group_dark_sch.addSettingCard(self.card_ds_mode)
        # 自定义：起止时刻
        self.card_ds_start = TimeSettingCard(
            FluentIcon.PLAY, "进入深色时刻",
            "到达该时刻后切换到深色模式（支持跨越 00:00）",
            SETTINGS["dark_schedule"].get("start", "20:00"), self)
        self.card_ds_start.timeEdit.timeChanged.connect(self._on_ds_start_changed)
        self.group_dark_sch.addSettingCard(self.card_ds_start)
        self.card_ds_end = TimeSettingCard(
            FluentIcon.PAUSE, "退出深色时刻",
            "到达该时刻后切换回浅色模式（支持跨越 00:00）",
            SETTINGS["dark_schedule"].get("end", "07:00"), self)
        self.card_ds_end.timeEdit.timeChanged.connect(self._on_ds_end_changed)
        self.group_dark_sch.addSettingCard(self.card_ds_end)
        # 日出日落：经纬度
        self.card_ds_lat = LineEditSettingCard(
            FluentIcon.GLOBE, "纬度",
            "北纬为正、南纬为负（如北京 39.9）",
            str(SETTINGS["dark_schedule"].get("lat", 39.9042)),
            "39.9042", self)
        self.card_ds_lat.lineEdit.editingFinished.connect(self._on_ds_lat_changed)
        self.group_dark_sch.addSettingCard(self.card_ds_lat)
        self.card_ds_lon = LineEditSettingCard(
            FluentIcon.PIN, "经度",
            "东经为正、西经为负（如北京 116.4）",
            str(SETTINGS["dark_schedule"].get("lon", 116.4074)),
            "116.4074", self)
        self.card_ds_lon.lineEdit.editingFinished.connect(self._on_ds_lon_changed)
        self.group_dark_sch.addSettingCard(self.card_ds_lon)
        # 一次性添加组
        root.addWidget(self.group_dark_sch)

        # ---- 系统 ----
        self.group_sys = SettingCardGroup("系统", self)
        self.card_tray = SwitchSettingCard(
            FluentIcon.MINIMIZE, "最小化到托盘",
            "关闭/最小化时隐藏到系统托盘，而非退出", None, self)
        self.card_tray.checkedChanged.connect(self._on_tray_changed)
        self.group_sys.addSettingCard(self.card_tray)

        self.card_cache_size = PushSettingCard(
            "刷新", FluentIcon.FOLDER, "缓存占用",
            f"当前：{_get_cache_size_str()}", self)
        self.card_cache_size.clicked.connect(self._refresh_cache_size)
        self.group_sys.addSettingCard(self.card_cache_size)

        self.card_clear_cache = PushSettingCard(
            "清理", FluentIcon.DELETE, "一键清理缓存",
            "删除所有缩略图和预览图缓存，不影响当前壁纸", self)
        self.card_clear_cache.clicked.connect(self._on_clear_cache)
        self.group_sys.addSettingCard(self.card_clear_cache)
        root.addWidget(self.group_sys)

        # ---- 关于软件 ----
        self.group_about = SettingCardGroup("关于软件", self)
        about_card = CardWidget(self)
        about_lay = QVBoxLayout(about_card)
        about_lay.setContentsMargins(20, 22, 20, 22)
        about_lay.setSpacing(6)
        about_lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        # 圆底应用图标徽标（居中）
        badge = _AboutBadge(FluentIcon.PHOTO, 68, about_card)
        about_lay.addWidget(badge, 0, Qt.AlignHCenter)

        # 软件名（居中标题）
        app_title = TitleLabel("壁纸助手 NetBianWallpaper", about_card)
        app_title.setAlignment(Qt.AlignHCenter)
        about_lay.addWidget(app_title, 0, Qt.AlignHCenter)

        # 版本徽标（居中胶囊）
        pill = _AboutPill(APP_VERSION_DISPLAY, about_card)
        pill_row = QHBoxLayout()
        pill_row.setSpacing(4)
        pill_row.addStretch(1)
        pill_row.addWidget(pill)
        pill_row.addStretch(1)
        about_lay.addLayout(pill_row)

        # 作者 · 日期（正文居中）
        info = BodyLabel("作者：你的大大大魔头　·　2026 年 09 月", about_card)
        info.setAlignment(Qt.AlignHCenter)
        about_lay.addWidget(info, 0, Qt.AlignHCenter)

        # 数据来源鸣谢（弱化居中）
        credit = CaptionLabel("数据来源：彼岸图网（鸣谢）", about_card)
        credit.setAlignment(Qt.AlignHCenter)
        about_lay.addWidget(credit, 0, Qt.AlignHCenter)

        # SettingCardGroup 内部用 ExpandLayout，只保留卡片当前 height()，不会按
        # 内容自动伸缩。这里激活布局后按内容展开并固定最小高度，否则内容会被压成
        # 0 高（表现为"关于软件"整块空白、只有徽标悬在底部）。见离屏诊断验证。
        about_lay.activate()
        about_card.adjustSize()
        about_card.setMinimumHeight(about_card.height())

        self.group_about.addSettingCard(about_card)
        root.addWidget(self.group_about)

        root.addStretch(1)

    # ---------- 分类数据 ----------
    def set_categories(self, cats):
        self._categories = list(cats) if cats else list(FALLBACK_CATEGORIES)
        self._rebuild_cate_combo()

    def _rebuild_cate_combo(self):
        cb = self.card_auto_cate.comboBox
        cb.blockSignals(True)
        cb.clear()
        cur = SETTINGS["auto_switch"].get("category", "")
        target = 0
        for i, (name, slug) in enumerate(self._categories):
            cb.addItem(name, slug)
            if slug == cur:
                target = i
        cb.setCurrentIndex(target)
        cb.blockSignals(False)

    # ---------- 状态同步 ----------
    def refresh(self):
        self.card_download.setContent(f"当前：{download_dir}")
        self.card_theme.blockSignals(True)
        self.card_theme.setChecked(SETTINGS["theme"] == "dark")
        self.card_theme.blockSignals(False)
        # 玻璃配置卡片同步（新版统一入口）
        self._sync_glass_ui()
        self.card_tray.blockSignals(True)
        self.card_tray.setChecked(SETTINGS["minimize_to_tray"])
        self.card_tray.blockSignals(False)
        asw = SETTINGS["auto_switch"]
        self.card_auto_enabled.blockSignals(True)
        self.card_auto_enabled.setChecked(asw["enabled"])
        self.card_auto_enabled.blockSignals(False)
        self.card_auto_mode.comboBox.blockSignals(True)
        self.card_auto_mode.comboBox.setCurrentIndex(0 if asw["mode"] == "random" else 1)
        self.card_auto_mode.comboBox.blockSignals(False)
        self._rebuild_cate_combo()
        try:
            idx = AUTO_INTERVALS.index(int(asw.get("interval_min", 30)))
        except ValueError:
            idx = 3
        self.card_auto_interval.comboBox.blockSignals(True)
        self.card_auto_interval.comboBox.setCurrentIndex(idx)
        self.card_auto_interval.comboBox.blockSignals(False)
        # 玻璃配置同步（新版统一入口 _sync_glass_ui）
        # 刷新缓存大小显示
        if hasattr(self, "card_cache_size"):
            self.card_cache_size.setContent(f"当前：{_get_cache_size_str()}")
        self._update_auto_visibility()
        # 定时切换主题 UI 同步
        if hasattr(self, "_sync_dark_schedule_ui"):
            self._sync_dark_schedule_ui()

    def _update_auto_visibility(self):
        asw = SETTINGS["auto_switch"]
        enabled = bool(asw.get("enabled", False))
        for card in (self.card_auto_mode, self.card_auto_cate, self.card_auto_interval):
            card.setEnabled(enabled)
        self.card_auto_cate.setEnabled(enabled and asw.get("mode") == "cate")

    def _sync_dark_schedule_ui(self):
        """同步"定时切换主题"组所有卡片的值/可用性"""
        ds = SETTINGS.get("dark_schedule") or {}
        enabled = bool(ds.get("enabled", False))
        mode = ds.get("mode", "custom")
        # 总开关
        self.card_ds_enabled.blockSignals(True)
        self.card_ds_enabled.setChecked(enabled)
        self.card_ds_enabled.blockSignals(False)
        # 模式
        idx = 0 if mode == "custom" else 1
        self.card_ds_mode.comboBox.blockSignals(True)
        self.card_ds_mode.comboBox.setCurrentIndex(idx)
        self.card_ds_mode.comboBox.blockSignals(False)
        # 时间（custom 模式才有意义，但仍保留值便于切换查看）
        from PySide6.QtCore import QTime
        for card, key in ((self.card_ds_start, "start"), (self.card_ds_end, "end")):
            try:
                h, m = (int(x) for x in str(ds.get(key, "20:00")).split(":")[:2])
                card.timeEdit.blockSignals(True)
                card.timeEdit.setTime(QTime(max(0, min(23, h)), max(0, min(59, m))))
                card.timeEdit.blockSignals(False)
            except Exception:
                pass
        # 经纬度（sunrise 模式才有意义）
        self.card_ds_lat.lineEdit.blockSignals(True)
        self.card_ds_lat.lineEdit.setText(str(ds.get("lat", 39.9042)))
        self.card_ds_lat.lineEdit.blockSignals(False)
        self.card_ds_lon.lineEdit.blockSignals(True)
        self.card_ds_lon.lineEdit.setText(str(ds.get("lon", 116.4074)))
        self.card_ds_lon.lineEdit.blockSignals(False)
        # --- 启用/禁用逻辑 ---
        # 总开关 OFF：所有子项禁用
        # 总开关 ON + custom：start/end 可用，lat/lon 禁用
        # 总开关 ON + sunrise：lat/lon 可用，start/end 禁用
        for card in (self.card_ds_mode, self.card_ds_start, self.card_ds_end,
                     self.card_ds_lat, self.card_ds_lon):
            card.setEnabled(enabled)
        if enabled and mode == "custom":
            self.card_ds_start.setEnabled(True)
            self.card_ds_end.setEnabled(True)
            self.card_ds_lat.setEnabled(False)
            self.card_ds_lon.setEnabled(False)
        elif enabled and mode == "sunrise":
            self.card_ds_start.setEnabled(False)
            self.card_ds_end.setEnabled(False)
            self.card_ds_lat.setEnabled(True)
            self.card_ds_lon.setEnabled(True)

    def _on_ds_enabled_changed(self, checked):
        SETTINGS["dark_schedule"]["enabled"] = bool(checked)
        save_settings()
        self._sync_dark_schedule_ui()
        # 启停 MainWindow 的定时器
        w = self.window()
        if hasattr(w, "_apply_dark_schedule"):
            w._apply_dark_schedule()

    def _on_ds_mode_changed(self, index):
        SETTINGS["dark_schedule"]["mode"] = "custom" if int(index) == 0 else "sunrise"
        save_settings()
        self._sync_dark_schedule_ui()
        # 立即触发一次检查（避免用户等 60s 才看到效果）
        w = self.window()
        if hasattr(w, "_on_dark_schedule_tick"):
            w._on_dark_schedule_tick()

    def _on_ds_start_changed(self, t):
        SETTINGS["dark_schedule"]["start"] = t.toString("HH:mm")
        save_settings()
        w = self.window()
        if hasattr(w, "_on_dark_schedule_tick"):
            w._on_dark_schedule_tick()

    def _on_ds_end_changed(self, t):
        SETTINGS["dark_schedule"]["end"] = t.toString("HH:mm")
        save_settings()
        w = self.window()
        if hasattr(w, "_on_dark_schedule_tick"):
            w._on_dark_schedule_tick()

    def _on_ds_lat_changed(self):
        try:
            v = float(self.card_ds_lat.lineEdit.text())
            SETTINGS["dark_schedule"]["lat"] = v
            save_settings()
            w = self.window()
            if hasattr(w, "_on_dark_schedule_tick"):
                w._on_dark_schedule_tick()
        except Exception:
            pass

    def _on_ds_lon_changed(self):
        try:
            v = float(self.card_ds_lon.lineEdit.text())
            SETTINGS["dark_schedule"]["lon"] = v
            save_settings()
            w = self.window()
            if hasattr(w, "_on_dark_schedule_tick"):
                w._on_dark_schedule_tick()
        except Exception:
            pass

    # ---------- 事件处理 ----------
    def _refresh_cache_size(self):
        """刷新缓存大小显示"""
        size_str = _get_cache_size_str()
        self.card_cache_size.setContent(f"当前：{size_str}")

    def _on_clear_cache(self):
        """一键清理缓存"""
        from qfluentwidgets import MessageBox
        w = MessageBox(
            "清理缓存",
            f"将删除所有缩略图和预览图缓存（当前 {_get_cache_size_str()}），\n"
            "不影响当前壁纸和自动取色功能。\n\n确定要清理吗？",
            self)
        if not w.exec():
            return
        removed = _clear_cache()
        new_size = _get_cache_size_str()
        self.card_cache_size.setContent(f"当前：{new_size}")
        from qfluentwidgets import InfoBar, InfoBarPosition
        try:
            parent = self.window()
            InfoBar.success(
                "清理完成",
                f"已清理 {removed} 个文件，剩余 {new_size}",
                duration=3000, parent=parent,
                position=InfoBarPosition.TOP)
        except Exception:
            pass

    def _choose_download_dir(self):
        global download_dir
        d = QFileDialog.getExistingDirectory(
            self, "选择下载目录", download_dir,
            QFileDialog.ShowDirsOnly)
        if not d:
            return
        download_dir = d
        self.card_download.setContent(f"当前：{download_dir}")
        save_settings()
        notify(self.window(), "success", "已更新", f"下载目录：{download_dir}", 3000)

    def _on_theme_changed(self, checked):
        SETTINGS["theme"] = "dark" if checked else "light"
        save_settings()
        w = self.window()
        if hasattr(w, "_set_dark"):
            w._set_dark(bool(checked))

    # ====== 新版玻璃配置（合并 accent_color + glass_skin + auto_color）======
    def _sync_glass_ui(self):
        """把 SETTINGS["glass"] 同步到全部玻璃卡片（blockSignals 避免触发 _on_*）。"""
        if not hasattr(self, "card_glass_enabled"):
            return
        glass = SETTINGS.get("glass") or {}
        # 总开关
        self.card_glass_enabled.blockSignals(True)
        self.card_glass_enabled.setChecked(bool(glass.get("enabled", False)))
        self.card_glass_enabled.blockSignals(False)
        # color_mode
        self.card_glass_color_mode.blockSignals(True)
        self.card_glass_color_mode.setChecked(
            glass.get("color_mode", "fixed") == "follow_wallpaper")
        self.card_glass_color_mode.blockSignals(False)
        # 颜色
        color = glass.get("color") or "#5E91C7"
        self.card_glass_color.setContent(f"当前：{color}")
        self.card_glass_color.setEnabled(
            glass.get("color_mode", "fixed") != "follow_wallpaper")
        # 模糊
        blur_val = int(glass.get("blur_radius", 30))
        self.card_glass_blur.slider.blockSignals(True)
        self.card_glass_blur.setValue(blur_val)
        self.card_glass_blur.slider.blockSignals(False)
        # 不透明度（百分比）
        opacity_pct = int(round(float(glass.get("opacity", 0.62)) * 100))
        self.card_glass_opacity.slider.blockSignals(True)
        self.card_glass_opacity.setValue(opacity_pct)
        self.card_glass_opacity.slider.blockSignals(False)

    def _on_glass_enabled_changed(self, checked):
        """总开关变更：写 SETTINGS + 立即调 _apply_glass_skin（启用/禁用）。"""
        SETTINGS["glass"]["enabled"] = bool(checked)
        save_settings()
        w = self.window()
        if hasattr(w, "_apply_glass_skin"):
            w._apply_glass_skin()

    def _on_glass_color_mode_changed(self, checked):
        """跟随壁纸色开关：写 SETTINGS["glass"]["color_mode"] + 切换时刷新色源。

        开启 → 立即从当前壁纸取色（行为同老的 auto_color=True）
        关闭 → 回退到 last_manual_color
        """
        SETTINGS["glass"]["color_mode"] = (
            "follow_wallpaper" if checked else "fixed")
        save_settings()
        w = self.window()
        # 同步 UI 联动：color_mode=follow_wallpaper 时禁用色盘卡片
        if hasattr(self, "card_glass_color"):
            self.card_glass_color.setEnabled(not checked)
        if checked:
            # 开启自动：从当前壁纸立即提取
            if hasattr(w, "_extract_current_wallpaper_color"):
                w._extract_current_wallpaper_color()
        else:
            # 关闭自动：回退到 last_manual_color
            last = SETTINGS["glass"].get("last_manual_color") or "#5E91C7"
            SETTINGS["glass"]["color"] = last
            save_settings()
            if hasattr(self, "card_glass_color"):
                self.card_glass_color.setContent(f"当前：{last}")
            # 实时同步：刷 qfw 强调色 + 刷玻璃（仅在 enabled 时有可见效果）
            if hasattr(w, "_apply_accent_color"):
                w._apply_accent_color()
            if hasattr(w, "_apply_glass_skin"):
                w._apply_glass_skin()

    def _choose_glass_color(self):
        """点 "窗口半透明色" 卡片：开色盘，写 SETTINGS["glass"]["color"]
        + 同步 last_manual_color + 实时刷 qfw 强调色 + 实时刷玻璃。"""
        glass = SETTINGS.get("glass") or {}
        current = glass.get("color") or "#0078d4"
        color = QColorDialog.getColor(QColor(current), self, "选择窗口半透明色")
        if not color.isValid():
            return
        hex_color = color.name()
        SETTINGS["glass"]["color"] = hex_color
        SETTINGS["glass"]["last_manual_color"] = hex_color
        save_settings()
        self.card_glass_color.setContent(f"当前：{hex_color}")
        w = self.window()
        if hasattr(w, "_apply_accent_color"):
            w._apply_accent_color()
        if hasattr(w, "_apply_glass_skin"):
            w._apply_glass_skin()

    def _on_glass_blur_changed(self, value):
        """模糊强度滑块变更：把新半径写进 SETTINGS + 失效缓存
        让 paintEvent 重抓+重模糊（debounce 200ms 避免拖动时连续重抓）。"""
        SETTINGS["glass"]["blur_radius"] = int(value)
        self._schedule_glass_apply(blur_changed=True)

    def _on_glass_opacity_changed(self, value):
        """不透明度滑块变更：写 SETTINGS + 只触发重绘（无需重抓壁纸）。
        节流 30ms：opacity 走 alpha 蒙版不需要重算，但拖动过快会触发密集
        paintEvent + QPainter.fillRect 撕裂，节流降低视觉抖动。"""
        SETTINGS["glass"]["opacity"] = float(value) / 100.0
        self._schedule_glass_apply(blur_changed=False)

    def _schedule_glass_apply(self, blur_changed=False):
        """debounce + 节流：
          - blur 改变：debounce 200ms（避免 PIL GaussianBlur 在主线程被反复触发）
          - opacity 改变：debounce 30ms（仅 paintEvent 重绘，很快）
        blur 改变期间 paintEvent 用 _glass_render_pending 标志显示 fallback，
        避免"上一次的 pixmap + 新 alpha 蒙版"叠加产生色块。"""
        if blur_changed:
            self._glass_render_pending = True
            interval = 200
            timer_attr = "_glass_blur_timer"
        else:
            interval = 30
            timer_attr = "_glass_opacity_timer"
        t = getattr(self, timer_attr, None)
        if t is None:
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(interval)
            t.timeout.connect(self._flush_glass_apply)
            setattr(self, timer_attr, t)
        try:
            t.start()
        except Exception:
            self._flush_glass_apply()

    def _flush_glass_apply(self):
        """debounce 到点：保存 + 实时刷玻璃。"""
        try:
            save_settings()
        except Exception:
            pass
        w = self.window()
        if hasattr(w, "_apply_glass_skin"):
            w._apply_glass_skin()

    def _apply_glass_preset(self, preset_id):
        """点 4 个预设按钮之一：把对应字段塞进 SETTINGS["glass"] + 实时刷。"""
        preset = GLASS_PRESETS.get(preset_id)
        if not preset:
            return
        glass = SETTINGS.get("glass") or {}
        # 预设应用：覆盖 color / blur / opacity，但不强制开 enabled（用户偏好）
        glass["color"] = preset["color"]
        glass["blur_radius"] = int(preset["blur_radius"])
        glass["opacity"] = float(preset["opacity"])
        glass["last_manual_color"] = preset["color"]
        save_settings()
        # 同步 UI（不触发 _on_*）
        self._sync_glass_ui()
        # 实时刷 qfw 强调色 + 玻璃
        w = self.window()
        if hasattr(w, "_apply_accent_color"):
            w._apply_accent_color()
        if hasattr(w, "_apply_glass_skin"):
            w._apply_glass_skin()

    def _on_tray_changed(self, checked):
        SETTINGS["minimize_to_tray"] = bool(checked)
        save_settings()

    def _on_auto_enabled(self, checked):
        SETTINGS["auto_switch"]["enabled"] = bool(checked)
        save_settings()
        self._update_auto_visibility()
        w = self.window()
        if hasattr(w, "_apply_auto_switch"):
            w._apply_auto_switch()

    def _on_auto_mode(self, idx):
        SETTINGS["auto_switch"]["mode"] = "random" if idx == 0 else "cate"
        save_settings()
        self._update_auto_visibility()

    def _on_auto_cate(self, idx):
        slug = self.card_auto_cate.comboBox.itemData(idx) or ""
        SETTINGS["auto_switch"]["category"] = slug
        save_settings()

    def _on_auto_interval(self, idx):
        if 0 <= idx < len(AUTO_INTERVALS):
            SETTINGS["auto_switch"]["interval_min"] = AUTO_INTERVALS[idx]
            save_settings()
        w = self.window()
        if hasattr(w, "_apply_auto_switch"):
            w._apply_auto_switch()


# ---------------------------------------------------------------------------
# 主窗口（Fluent 窗口 + 左侧导航）
# ---------------------------------------------------------------------------
class NavItemVertical(NavigationTreeItem):
    """左侧导航项：图标在上、文字在下（垂直堆叠），取代默认的"图标左/文字右"。

    复用 qfluentwidgets 的选中/悬停/背景绘制逻辑（与 NavigationPushButton 一致），
    仅调整图标与文字的绘制位置：图标绘制在项上部居中，文字绘制在图标正下方居
    中。展开态项高 54px（比默认 36px 高，才能容纳上下两行）。
    """

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.TextAntialiasing |
                               QPainter.SmoothPixmapTransform)
        painter.setPen(Qt.NoPen)

        if self.isPressed:
            painter.setOpacity(0.7)
        if not self.isEnabled():
            painter.setOpacity(0.4)

        # 背景 / 选中指示条 / 悬停高亮
        c = 255 if isDarkTheme() else 0
        m = self._margins()
        pl, pr = m.left(), m.right()
        globalRect = QRect(self.mapToGlobal(QPoint()), self.size())

        if self._canDrawIndicator():
            painter.setBrush(QColor(c, c, c, 6 if self.isEnter else 10))
            painter.drawRoundedRect(self.rect(), 5, 5)
            painter.setBrush(autoFallbackThemeColor(self.lightIndicatorColor,
                                                    self.darkIndicatorColor))
            painter.drawRoundedRect(self.indicatorRect(), 1.5, 1.5)
        elif ((self.isEnter and globalRect.contains(QCursor.pos()))
              or self.isAboutSelected) and self.isEnabled():
            painter.setBrush(QColor(c, c, c, 6 if self.isAboutSelected else 10))
            painter.drawRoundedRect(self.rect(), 5, 5)

        # 图标：上部居中
        icon = self.icon()
        if not icon.isNull():
            iw = 20
            ix = (self.width() - iw) / 2
            iy = 8
            drawIcon(self._icon, painter, QRectF(ix, iy, iw, iw))

        # 文字：图标正下方；收起态（仅图标条）不画文字
        if self.isCompacted:
            return
        painter.setFont(self.font())
        painter.setPen(self.textColor())
        if icon.isNull():
            ty = 10
        else:
            ty = 32
        painter.drawText(QRectF(pl, ty, self.width() - pl - pr, self.height() - ty),
                         Qt.AlignTop | Qt.AlignHCenter, self.text())

    def setCompacted(self, isCompacted):
        """展开态需要更高（纵向两行），收起态保持 40x36 图标条"""
        if isCompacted == self.isCompacted:
            return
        self.isCompacted = isCompacted
        if isCompacted:
            self.setFixedSize(40, 36)
        else:
            self.setFixedSize(self.EXPAND_WIDTH, 54)
        self.update()

    def _drawDropDownArrow(self):
        # 叶子分类项无需下拉箭头
        pass


class NavTreeWidgetVertical(NavigationTreeWidget):
    """配合 NavItemVertical：让导航"容器"项在展开态也升高到 54px。

    qfluentwidgets 默认 NavigationTreeWidget.setCompacted 把容器固定为
    (EXPAND_WIDTH, 36)，会裁掉内部竖排 item 的下半部分（文字）。这里将其改为
    54px，容器与内部 NavItemVertical 同为 54px，图标在上、文字在下完整显示。
    """

    def setCompacted(self, isCompacted):
        if isCompacted == self.isCompacted:
            return
        self.isCompacted = isCompacted
        # 必须把展开/收起状态传给内部 item（原版 setCompacted 会传播，
        # 否则 item 停留在 40x36 初始收起态，竖排文字会被 isCompacted 分支跳过）
        self.itemWidget.setCompacted(isCompacted)
        if isCompacted:
            self.setFixedSize(40, 36)
        else:
            self.setFixedSize(self.EXPAND_WIDTH, 54)
        self.update()


class MainWindow(FluentWindow):
    _color_extracted = Signal(str)  # 后台线程提取完颜色后发射
    def __init__(self):
        load_settings()  # 加载 settings.json（下载目录、主题、定时切换、托盘等）
        super().__init__()
        self.setWindowTitle("彼岸桌面 · 壁纸浏览器")
        # 隐藏 FluentTitleBar 的标题文字：qfluentwidgets 的 FluentWindow 在透明玻璃背景 +
        # DWM 合成层下，titleBar.titleLabel 会被错位渲染到内容区中部，形成用户看到的
        # "残留的窗口标题内容"（已实测：隐藏它后残留消失，grab/Qt层本就干净）。frameless
        # + 玻璃窗口的标题文字非必需，隐藏最稳妥。
        self.titleBar.titleLabel.hide()
        self.resize(1280, 840)
        self.setMinimumSize(960, 680)
        # 启动时窗口居中
        try:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.availableGeometry()
                self.move(sg.center().x() - self.width() // 2,
                          sg.center().y() - self.height() // 2)
        except Exception:
            pass
        # 用官方 API 收窄导航：展开宽度 120px，默认展开（点汉堡可收起为窄图标条）
        # 之前 setFixedWidth(120)+NavigationWidget.EXPAND_WIDTH hack 会被 panel 宽度
        # (eventFilter) 覆盖，导致收起48px/展开312px——正是"展开太宽"的根因。
        self.navigationInterface.setExpandWidth(120)
        self.navigationInterface.expand(False)

        self.net = NetBian()
        self.categories = []
        self.mode = "home"        # home / cate / search / settings
        self.cur_cate = ""        # slug，空 = 全部
        self.search_id = ""
        self.search_kw = ""
        self.cur_page = 1
        self.total_pages = 1
        self.loading = False
        self._previews = set()   # 保持预览对话框引用，防止被 GC
        self._dark = (SETTINGS["theme"] == "dark")
        self._really_quit = False
        self._auto_switching = False
        self._tray_tip_shown = False
        self._current_accent = None  # 自动提取的主题色缓存
        self.tray = None

        # ---- 玻璃效果（壁纸抓取 + Pillow 模糊 + 颜色蒙版）----
        # 取代旧的 SWCA ACCENT 注入方案：SWCA 的模糊半径 Windows 强制固定，
        # 且效果被 qfw 不透明 widget 完全遮挡。两个滑块都看不出效果。
        # 新方案：抓当前桌面壁纸 → Pillow GaussianBlur(radius=blur_radius)
        # → 在 MainWindow.paintEvent 客户区最底层画 → 上叠 alpha 颜色蒙版
        # → 真正的"整个窗体磨砂玻璃"。
        self._glass_wallpaper_path = None   # 缓存当前加载的壁纸路径
        self._glass_pixmap = None           # 缓存模糊后的 QPixmap
        self._glass_reload_timer = None     # 80ms debounce
        self._glass_size_hash = None        # 记录上次绘制的窗口尺寸，resize 时重抓

        # 连接颜色提取信号到主线程槽
        self._color_extracted.connect(self._on_color_extracted)

        # 单实例信号文件检测定时器
        self._show_signal_timer = QTimer(self)
        self._show_signal_timer.timeout.connect(self._check_show_signal)
        self._show_signal_timer.start(500)  # 每 500ms 检测

        # 应用主题色：自动配色从壁纸提取，否则用手动自定义色
        if _is_auto_color():
            self._extract_current_wallpaper_color()
        else:
            self._apply_accent_color()

        # 让左侧导航项显示为"图标在上、文字在下"。qfluentwidgets 的
        # NavigationTreeWidget 在构造内部 item 时引用模块全局 NavigationTreeItem，
        # NavigationPanel.setExpanded 会调用 findChildren(NavigationWidget) 触发
        # _setWidgetCompacted → setCompacted，因此也要把"容器"类替换掉，否则容器
        # 仍按默认 36px 固定高度，会把文字裁掉。两者必须同时 monkeypatch。
        try:
            from qfluentwidgets.components.navigation import navigation_widget as _nav_widget
            _nav_widget.NavigationTreeItem = NavItemVertical
            from qfluentwidgets.components.navigation import navigation_panel as _nav_panel
            _nav_panel.NavigationTreeWidget = NavTreeWidgetVertical
        except Exception:
            pass

        self._build_ui()
        self._bind()

        # 定时切换壁纸定时器
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._auto_switch_tick)

        # 系统托盘
        self._setup_tray()

        # 应用持久化设置
        self._apply_auto_switch()
        self._apply_dark_schedule()

        # 启动后串行加载分类 + 首页，避免并发请求首页触发 WAF 频率限制
        def _init_load():
            self._load_categories()
            if self.mode == "home":
                self._load_page(1)
        threading.Thread(target=_init_load, daemon=True).start()

    # ---------- UI ----------
    def _build_ui(self):
        # 内容页
        self.page = WallpaperPage(self)
        self.stackedWidget.addWidget(self.page)

        # 设置页
        self.setting_page = SettingPage(self)
        self.stackedWidget.addWidget(self.setting_page)

        self.stackedWidget.setCurrentWidget(self.page)

        # ---- 玻璃背景穿透：让 paintEvent 画的模糊壁纸在卡片之间的空隙可见 ----
        # 关键：stackedWidget 必须设成透明背景，否则它会盖住我们画在
        # MainWindow.paintEvent 最底层的玻璃层。每个 page 自己的卡片/列表
        # 仍保持 qfw 默认不透明（卡片本身看得清，玻璃只透出"空隙"）。
        # 注：navigationInterface（左侧导航）和 titleBar（顶部）保持不透明，
        # 它们是 qfw 自身样式，强制透明会破坏 hover 态和选中态视觉。
        self.stackedWidget.setStyleSheet("background: transparent;")
        # 整窗设置 WA_StyledBackground 让 stylesheet 真正生效（PySide6 需要）
        self.stackedWidget.setAttribute(Qt.WA_StyledBackground, True)

        # 左侧导航：分类（初始只放「全部」，分类解析完成后填充）
        self.navigationInterface.addItem(
            routeKey="home", icon=FluentIcon.HOME, text="全部壁纸",
            onClick=lambda _: self._nav_clicked("", "全部"),
            selectable=True, position=NavigationItemPosition.TOP)

        # 设置（底部）
        self.navigationInterface.addItem(
            routeKey="settings", icon=FluentIcon.SETTING, text="设置",
            onClick=self._open_settings, selectable=True,
            position=NavigationItemPosition.BOTTOM)

        # 主题切换（底部）▸ 已隐藏：主题在「设置 → 外观」里切换，不再占用左侧导航
        # 如需恢复，取消下面 5 行注释即可。
        # self.navigationInterface.addItem(
        #     routeKey="theme", icon=FluentIcon.BRIGHTNESS, text="切换主题",
        #     onClick=self._toggle_theme, selectable=False,
        #     position=NavigationItemPosition.BOTTOM)

        self.navigationInterface.setCurrentItem("home")

    def _add_category_items(self, cats):
        """把分类填充到左侧导航滚动区"""
        for name, slug in cats:
            if slug == "":  # 「全部」已在 TOP 区
                continue
            icon = CATEGORY_ICONS.get(slug, FluentIcon.PHOTO)
            self.navigationInterface.addItem(
                routeKey=slug, icon=icon, text=name,
                onClick=lambda _, s=slug, n=name: self._nav_clicked(s, n),
                selectable=True, position=NavigationItemPosition.SCROLL)

    def _bind(self):
        bridge.categories_loaded.connect(self._on_categories)
        bridge.list_loaded.connect(self._on_list)
        bridge.list_failed.connect(self._on_list_failed)
        bridge.thumb_ready.connect(self._on_thumb)
        bridge.detail_ready.connect(self._on_detail)
        bridge.detail_failed.connect(self._on_detail_failed)
        bridge.origin_ready.connect(self._on_origin)
        bridge.download_done.connect(self._on_download_done)
        bridge.download_failed.connect(self._on_download_failed)
        bridge.card_download_done.connect(self._on_card_download_done)
        bridge.card_download_failed.connect(self._on_card_download_failed)
        bridge.card_wallpaper_done.connect(self._on_card_wallpaper_done)
        bridge.card_wallpaper_failed.connect(self._on_card_wallpaper_failed)
        bridge.auto_switch_done.connect(self._on_auto_switch_done)
        bridge.auto_switch_failed.connect(self._on_auto_switch_failed)

        p = self.page
        p.search_edit.searchSignal.connect(self._do_search)
        p.search_edit.returnPressed.connect(self._do_search)   # 支持回车搜索
        p.btn_reset.clicked.connect(self._do_reset)
        p.btn_prev.clicked.connect(lambda: self._load_page(self.cur_page - 1))
        p.btn_next.clicked.connect(lambda: self._load_page(self.cur_page + 1))
        p.btn_goto.clicked.connect(self._on_goto_page)
        p.page_edit.returnPressed.connect(self._on_goto_page)  # 回车跳转页码

    def _set_dark(self, dark):
        """设置主题并持久化"""
        self._dark = bool(dark)
        setTheme(Theme.DARK if self._dark else Theme.LIGHT)
        SETTINGS["theme"] = "dark" if self._dark else "light"
        save_settings()
        # 同步更新所有卡片标题颜色，确保深浅主题下都清晰可读
        for i in range(self.page.grid.count()):
            w = self.page.grid.itemAt(i).widget()
            if isinstance(w, WallpaperCard):
                w._update_text_color()
        # 同步设置页主题开关（不触发回调）
        if hasattr(self, "setting_page"):
            self.setting_page.card_theme.blockSignals(True)
            self.setting_page.card_theme.setChecked(self._dark)
            self.setting_page.card_theme.blockSignals(False)
    def _toggle_theme(self, _=None):
        self._set_dark(not self._dark)

    # ---------- 导航 ----------
    def _nav_clicked(self, slug, name):
        # 从设置页切回壁纸页
        self.stackedWidget.setCurrentWidget(self.page)
        if self.mode == "settings":
            self.mode = "home" if slug == "" else "cate"
            self.cur_cate = slug
            self.search_id = ""
            self.search_kw = ""
            self.page.search_edit.clear()
            self._load_page(1)
            return

        if self.mode == ("cate" if slug else "home") and self.cur_cate == slug:
            return
        self.mode = "cate" if slug else "home"
        self.cur_cate = slug
        self.search_id = ""
        self.search_kw = ""
        self.page.search_edit.clear()
        self._load_page(1)

    def _open_settings(self, _=None):
        self.mode = "settings"
        self.setting_page.refresh()
        self.stackedWidget.setCurrentWidget(self.setting_page, popOut=False)

    # ---------- 分页 ----------
    def _on_goto_page(self):
        if self.loading:
            return
        txt = self.page.page_edit.text().strip()
        if not txt:
            return
        try:
            page = int(txt)
        except ValueError:
            notify(self, "warning", "页码无效", "请输入数字页码", 2000)
            return
        if page < 1 or page > self.total_pages:
            notify(self, "warning", "页码超出范围",
                   f"页码范围 1 ~ {self.total_pages}", 2500)
            return
        if page != self.cur_page:
            self._load_page(page)

    # ---------- 分类 ----------
    def _load_categories(self):
        try:
            cats = self.net.fetch_categories()
            bridge.categories_loaded.emit(cats)
        except Exception:  # noqa
            bridge.categories_loaded.emit(FALLBACK_CATEGORIES)

    def _on_categories(self, cats):
        self.categories = cats
        self._add_category_items(cats)
        self.setting_page.set_categories(cats)

    # ---------- 搜索 ----------
    def _do_search(self):
        kw = self.page.search_edit.text().strip()
        if not kw:
            self._do_reset()
            return
        if self.loading:
            return
        self.loading = True
        self.mode = "search"
        self.search_kw = kw
        self.page.page_info.setText(f"正在搜索「{kw}」…")
        threading.Thread(target=self._search_worker, args=(kw,), daemon=True).start()

    def _search_worker(self, kw):
        try:
            sid, items, page, total = self.net.search(kw)
            self.search_id = sid  # 先记录，供翻页使用
            bridge.list_loaded.emit((items, 1, total))
        except Exception as e:  # noqa
            bridge.list_failed.emit(str(e))

    def _do_reset(self):
        self.mode = "home"
        self.cur_cate = ""
        self.search_id = ""
        self.search_kw = ""
        self.page.search_edit.clear()
        self.navigationInterface.setCurrentItem("home")
        self._load_page(1)

    # ---------- 列表 ----------
    @staticmethod
    def _cate_list_url(slug, page):
        """分类/首页的列表 URL（第 1 页统一用 index.htm，避免目录根路径被 WAF 拦截）"""
        if slug:
            if page <= 1:
                return f"{BASE_URL}/{slug}/index.htm"
            return f"{BASE_URL}/{slug}/index_{page}.htm"
        if page <= 1:
            return BASE_URL + "/index.htm"
        return f"{BASE_URL}/index_{page}.htm"

    def _make_list_url(self, page):
        if self.mode == "search":
            return f"{BASE_URL}/search/{self.search_id}-{page - 1}.html"
        return self._cate_list_url(self.cur_cate, page)

    def _load_page(self, page):
        if self.loading:
            return
        page = max(1, page)
        if page > self.total_pages:
            page = self.total_pages
        self.cur_page = page
        self.loading = True
        self.page.page_info.setText(f"正在加载第 {page} 页…")
        url = self._make_list_url(page)
        threading.Thread(target=self._fetch_list_worker, args=(url, page),
                         daemon=True).start()

    def _fetch_list_worker(self, url, page):
        try:
            items, p, total = self.net.fetch_list(url)
            bridge.list_loaded.emit((items, page, total))
        except Exception as e:  # noqa
            bridge.list_failed.emit(str(e))

    def _on_list(self, result):
        self.loading = False
        items, page, total = result
        self.cur_page = page
        self.total_pages = max(total, 1)

        p = self.page
        p.page_info.setText(f"共 {self.total_pages} 页 · 本页 {len(items)} 张")
        p.page_edit.setText(str(page))

        # 重建网格
        self._clear_grid()
        cols = max(1, p.grid_host.width() // 250)
        for i, (title, thumb, detail) in enumerate(items):
            card = WallpaperCard(title, thumb, detail)
            card.clicked.connect(self._open_preview)
            card.download_requested.connect(self._download_card)
            card.wallpaper_requested.connect(self._set_wallpaper_card)
            r, c = divmod(i, cols)
            p.grid.addWidget(card, r, c)
            # 异步加载缩略图
            threading.Thread(target=self._thumb_worker,
                             args=(card.card_id, thumb), daemon=True).start()
        p.scroll.verticalScrollBar().setValue(0)

    def _on_list_failed(self, msg):
        self.loading = False
        self.page.page_info.setText("加载失败")
        notify(self, "error", "加载失败", msg, 5000)

    def _clear_grid(self):
        p = self.page
        while p.grid.count():
            item = p.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 缩略图 ----------
    def _thumb_worker(self, card_id, thumb_url):
        try:
            cpath = cache_path(thumb_url)
            if os.path.exists(cpath):
                data = open(cpath, "rb").read()
            else:
                data = self.net.get_bytes(thumb_url)
                ensure_cache_dir()
                try:
                    with open(cpath, "wb") as f:
                        f.write(data)
                except Exception:
                    pass
            bridge.thumb_ready.emit(card_id, data)
        except Exception:
            pass  # 缩略图失败静默忽略

    def _on_thumb(self, card_id, data):
        card = self._find_card(card_id)
        if card:
            card.set_thumb(data)

    def _find_card(self, card_id):
        p = self.page
        for i in range(p.grid.count()):
            w = p.grid.itemAt(i).widget()
            if isinstance(w, WallpaperCard) and w.card_id == card_id:
                return w
        return None

    # ---------- 预览 ----------
    def _open_preview(self, card):
        dlg = PreviewDialog(self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.show_loading(card.title)
        dlg.show()
        self._previews.add(dlg)
        dlg.destroyed.connect(lambda _=None, d=dlg: self._previews.discard(d))
        threading.Thread(target=self._detail_worker, args=(card, dlg),
                         daemon=True).start()

    def _detail_worker(self, card, dlg):
        try:
            detail = self.net.fetch_detail(card.detail_url, card.thumb_url)
            bridge.detail_ready.emit(dlg, detail)
        except Exception as e:  # noqa
            bridge.detail_failed.emit(dlg, str(e))

    def _on_detail(self, dlg, detail):
        if not widget_alive(dlg):
            return
        origin = detail.get("origin")
        if not origin:
            dlg.img_label.setText("未找到原图链接")
            return
        dlg.set_origin_url(origin)
        threading.Thread(target=self._origin_worker, args=(dlg, origin, detail),
                         daemon=True).start()

    def _origin_worker(self, dlg, origin, detail):
        try:
            cpath = cache_path(origin)
            if os.path.exists(cpath):
                data = open(cpath, "rb").read()
            else:
                data = self.net.get_bytes(origin, referer=detail.get("detail_url", BASE_URL + "/index.htm"))
                ensure_cache_dir()
                try:
                    with open(cpath, "wb") as f:
                        f.write(data)
                except Exception:
                    pass
            bridge.origin_ready.emit(dlg, data, detail.get("res_text", ""))
        except Exception as e:  # noqa
            bridge.detail_failed.emit(dlg, str(e))

    def _on_origin(self, dlg, data, info):
        if not widget_alive(dlg):
            return
        try:
            dlg.set_image(data, info)
        except Exception:
            pass

    def _on_detail_failed(self, dlg, msg):
        if not widget_alive(dlg):
            return
        try:
            dlg.img_label.setText("加载失败：" + msg)
        except Exception:
            pass

    # ---------- 下载 ----------
    def _on_download_done(self, path):
        notify(self, "success", "下载成功", f"已保存到：{path}", 4500)

    def _on_download_failed(self, msg):
        notify(self, "error", "下载失败", msg, 4000)

    # ---------- 卡片右键菜单：直接下载 / 设为壁纸 ----------
    def _download_card(self, card):
        self._status_hint(f"正在下载「{card.title}」…")
        threading.Thread(target=self._download_card_worker,
                         args=(card, self), daemon=True).start()

    def _download_card_worker(self, card, parent):
        try:
            detail = self.net.fetch_detail(card.detail_url, card.thumb_url)
            origin = detail.get("origin")
            if not origin:
                raise RuntimeError("未找到原图链接")
            cpath = cache_path(origin)
            if os.path.exists(cpath):
                data = open(cpath, "rb").read()
            else:
                detail_url = BASE_URL + card.detail_url
                data = self.net.get_bytes(origin, referer=detail_url)
                ensure_cache_dir()
                with open(cpath, "wb") as f:
                    f.write(data)
            title = clean_filename(card.title)
            os.makedirs(download_dir, exist_ok=True)
            path = os.path.join(download_dir, title + ".jpg")
            path = _unique_path(path)
            with open(path, "wb") as f:
                f.write(data)
            bridge.card_download_done.emit(parent, path)
        except Exception as e:  # noqa
            bridge.card_download_failed.emit(parent, str(e))

    def _set_wallpaper_card(self, card):
        self._status_hint(f"正在设置「{card.title}」为壁纸…")
        threading.Thread(target=self._set_wallpaper_card_worker,
                         args=(card, self), daemon=True).start()

    def _set_wallpaper_card_worker(self, card, parent):
        try:
            detail = self.net.fetch_detail(card.detail_url, card.thumb_url)
            origin = detail.get("origin")
            if not origin:
                raise RuntimeError("未找到原图链接")
            cpath = cache_path(origin)
            if os.path.exists(cpath):
                data = open(cpath, "rb").read()
            else:
                detail_url = BASE_URL + card.detail_url
                data = self.net.get_bytes(origin, referer=detail_url)
                ensure_cache_dir()
                with open(cpath, "wb") as f:
                    f.write(data)
            tmp = os.path.join(CACHE_DIR, "_current_wallpaper.jpg")
            with open(tmp, "wb") as f:
                f.write(data)
            set_as_wallpaper(tmp)
            # 壁纸刚换 → 立即让 paintEvent 重抓新壁纸
            if hasattr(self, "_glass_pixmap"):
                self._glass_pixmap = None
                self._glass_wallpaper_path = None
                self._glass_size_hash = None
                self.update()
            bridge.card_wallpaper_done.emit(parent, card.title)
        except Exception as e:  # noqa
            bridge.card_wallpaper_failed.emit(parent, str(e))

    def _on_card_download_done(self, parent, path):
        self._status_hint("下载完成")
        notify(parent, "success", "下载成功", f"已保存到：{path}", 4500)

    def _on_card_download_failed(self, parent, msg):
        self._status_hint("下载失败")
        notify(parent, "error", "下载失败", msg, 4000)

    def _on_card_wallpaper_done(self, parent, title):
        self._status_hint("壁纸已更新")
        notify(parent, "success", "设为壁纸成功", f"「{title}」已设为桌面壁纸", 2500)
        # 自动配色：从刚设的壁纸提取主色调
        if _is_auto_color():
            wp_path = os.path.join(CACHE_DIR, "_current_wallpaper.jpg")
            if os.path.exists(wp_path):
                self._extract_and_apply_color(wp_path)

    def _on_card_wallpaper_failed(self, parent, msg):
        self._status_hint("设置壁纸失败")
        notify(parent, "error", "设为壁纸失败", msg, 4000)



    # ---------- 状态提示 ----------
    def _status_hint(self, msg):
        """临时状态提示（托盘气泡或静默）"""
        if self.tray:
            self.tray.showMessage("彼岸桌面", msg,
                                  QSystemTrayIcon.Information, 2000)

    # ---------- 主题色 ----------
    def _apply_accent_color(self):
        """应用当前主题色设置。

        新版统一从 SETTINGS["glass"]["color"] 读取（玻璃色 = 主色源）。
        glass.enabled=False 时仍同步（让用户即使关闭玻璃也能保留主题色偏好），
        只有 glass 完全缺失时才回退默认 Fluent 蓝。
        """
        try:
            glass = SETTINGS.get("glass") or {}
            color = glass.get("color")
            if color and isinstance(color, str) and color.startswith("#"):
                setThemeColor(color)
            else:
                setThemeColor("#0078D4")  # WinUI 3 强调蓝（默认）
        except Exception:
            setThemeColor("#0078D4")

    def _extract_and_apply_color(self, image_path):
        """直接在主线程提取颜色并应用（避免线程/信号问题）"""
        try:
            color = extract_dominant_color(image_path)
        except Exception as e:
            color = None
        if not color:
            return
        self._on_color_extracted(color)

    def _on_color_extracted(self, color):
        """应用提取到的颜色并实时刷新 UI（新版：从壁纸自动取色后，
        写入 SETTINGS["glass"]["color"] 主色源 + 实时刷玻璃）

        行为矩阵：
          color_mode == "follow_wallpaper" 且 glass.enabled == True
              → 写 SETTINGS["glass"]["color"] = color
              → 调 _apply_glass_skin() 实时刷新客户区渐变色
              → setThemeColor + setTheme 切换刷 qfw 强调色
          color_mode == "follow_wallpaper" 且 glass.enabled == False
              → 写 SETTINGS["glass"]["color"] = color（用户后续启用玻璃时颜色已在）
              → setThemeColor + setTheme 切换刷 qfw 强调色
          color_mode == "fixed"
              → 仅 setThemeColor（用户偏好固定色，不动）
        """
        self._current_accent = color
        # 取一次玻璃色源（避免重复读字典）
        glass = SETTINGS.get("glass") or {}
        mode = glass.get("color_mode", "fixed")
        enabled = bool(glass.get("enabled", False))
        if mode == "follow_wallpaper":
            # 1. 写主色源
            SETTINGS["glass"]["color"] = color
            try:
                save_settings()
            except Exception:
                pass
            # 2. 实时刷新玻璃层（仅在 enabled 时才有可见效果；disabled 时
            #    下次启用会用这个新色）
            if enabled and hasattr(self, "_apply_glass_skin"):
                self._apply_glass_skin()
            # 3. 同步 qfw 强调色
            setThemeColor(color)
            # 4. 强制刷新 QSS：切换到反色再切回，确保所有控件更新
            from qfluentwidgets import Theme as _Theme, setTheme as _setTheme, isDarkTheme as _isDark
            cur_theme = _Theme.DARK if _isDark() else _Theme.LIGHT
            opp_theme = _Theme.LIGHT if _isDark() else _Theme.DARK
            _setTheme(opp_theme)
            _setTheme(cur_theme)
            # 5. 再次设置主题色（setTheme 可能覆盖，需重新应用）
            setThemeColor(color)
            # 6. 更新设置页显示
            if hasattr(self, "setting_page") and widget_alive(self.setting_page):
                sp = self.setting_page
                if hasattr(sp, "card_glass_color"):
                    sp.card_glass_color.setContent(f"当前：{color}（自动）")
            # 7. 自动取色成功不弹提示（用户要求静默生效）
        else:
            # fixed 模式：不写主色源（用户偏好固定色），仅刷一次强调色
            setThemeColor(color)
            from qfluentwidgets import Theme as _Theme, setTheme as _setTheme, isDarkTheme as _isDark
            cur_theme = _Theme.DARK if _isDark() else _Theme.LIGHT
            opp_theme = _Theme.LIGHT if _isDark() else _Theme.DARK
            _setTheme(opp_theme)
            _setTheme(cur_theme)
            setThemeColor(color)

    def _extract_current_wallpaper_color(self):
        """从当前已设壁纸提取颜色（供设置页切换自动配色时立即调用）"""
        wp_path = os.path.join(CACHE_DIR, "_current_wallpaper.jpg")
        if not os.path.exists(wp_path):
            wp_path = os.path.join(CACHE_DIR, "_auto_wallpaper.jpg")
        if os.path.exists(wp_path):
            self._extract_and_apply_color(wp_path)
        else:
            # 没有壁纸缓存文件，回退到手动色
            self._apply_accent_color()

    # ---------- 系统托盘 ----------
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        icon = self.windowIcon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("彼岸桌面 · 壁纸浏览器")
        menu = QMenu()
        act_show = menu.addAction("显示主界面")
        act_show.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.show()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        self._really_quit = True
        save_settings()
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def _hide_to_tray(self):
        self.hide()
        if self.tray and not self._tray_tip_shown:
            self._tray_tip_shown = True
            self.tray.showMessage(
                "彼岸桌面", "已最小化到托盘，双击图标恢复；右键可退出",
                QSystemTrayIcon.Information, 3000)

    def closeEvent(self, e):
        if not self._really_quit and SETTINGS.get("minimize_to_tray", True):
            e.ignore()
            self._hide_to_tray()
            return
        save_settings()
        if self.tray:
            self.tray.hide()
        super().closeEvent(e)

    def _check_show_signal(self):
        """检测第二实例发出的显示信号文件，自行激活窗口"""
        flag = os.path.join(CACHE_DIR, "_show_signal.flag")
        if os.path.exists(flag):
            try:
                os.remove(flag)
            except Exception:
                pass
            # 从自身事件循环激活窗口，不涉及跨进程操作
            self.showNormal()
            self.raise_()
            self.activateWindow()
            # 如果在托盘，也要恢复
            if hasattr(self, "tray") and self.tray:
                self.tray.show()

    # ---------- 原生事件（绕过 DWM HitTest 拦截，修复窗口拉伸） ----------
    def nativeEvent(self, event_type, message):
        """重写 nativeEvent，在 WA_TranslucentBackground 模式下强制处理 WM_NCHITTEST。

        根因（诊断确认）：
          WA_TranslucentBackground=True 时，DWM 会"代为处理"
          鼠标 HitTest 并把所有客户区返回 HTCLIENT，导致 qframelesswindow 自带的
          nativeEvent 收不到 WM_NCHITTEST、无法命中 HTLEFT/HTRIGHT/HTTOP 等拉伸区，
          表现就是"窗口边缘 5px 无法拉伸"。
        修复：在 nativeEvent 里自己解 MSG，对 WM_NCHITTEST 直接算鼠标相对客户区坐标，
          命中扩展的 8px 边缘就返回拉伸 hit-test 码。其余消息交给 super()。
        收益：
          ① 8px 拉伸边界，比 qfw 默认 5px 更友好、不容易错过；
          ② 不依赖 super() 是否处理，DWM 拦截也无效；
          ③ 保留 qfw 对 WM_NCCALCSIZE / 最大化按钮区域的处理（通过 super 转发）。
        """
        try:
            # PySide6: event_type = b"windows_generic_MSG" 或 QByteArray；message = sip.voidptr
            et = bytes(event_type) if isinstance(event_type, (bytes, bytearray)) else event_type
            if et in (b"windows_generic_MSG", "windows_generic_MSG", b"windows_generic", "windows_generic"):
                # 用标准 MSG 结构解 message 指针（64-bit Win 下 MSG = 48 bytes）
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", ctypes.c_void_p),
                        ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_void_p),
                        ("lParam", ctypes.c_void_p),
                        ("time", ctypes.c_uint32),
                        ("pt", POINT),
                        ("lPrivate", ctypes.c_uint32),
                    ]
                msg = MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    lparam = int(msg.lParam) if hasattr(msg, "lParam") else 0
                    # 屏幕坐标（lParam = MAKELPARAM(x, y)，x 是 LOWORD, y 是 HIWORD）
                    x = lparam & 0xFFFF
                    y = (lparam >> 16) & 0xFFFF
                    # 转为客户区坐标：frameGeometry 给出的是带边框的窗口外框位置
                    frame = self.frameGeometry()
                    rx = x - frame.x()
                    ry = y - frame.y()
                    w, h = frame.width(), frame.height()
                    # 排除：最大化/全屏时不拉伸（保持 qfw 默认行为）
                    if self.isMaximized() or self.isFullScreen():
                        return super().nativeEvent(event_type, message)
                    # 8px 拉伸边界
                    bw = 8
                    lx = rx < bw
                    rx_hit = rx > w - bw
                    ty = ry < bw
                    by = ry > h - bw
                    # 角
                    if lx and ty:     return True, 13   # HTTOPLEFT
                    if rx_hit and ty: return True, 14   # HTTOPRIGHT
                    if lx and by:     return True, 16   # HTBOTTOMLEFT
                    if rx_hit and by: return True, 17   # HTBOTTOMRIGHT
                    # 边
                    if ty:      return True, 12         # HTTOP
                    if by:      return True, 15         # HTBOTTOM
                    if lx:      return True, 10         # HTLEFT
                    if rx_hit:  return True, 11         # HTRIGHT
                    # 客户区交给 super() 处理（titleBar 拖动、最大化按钮等）
                    return super().nativeEvent(event_type, message)
        except Exception:
            pass
        # 其余消息完全交给 qframelesswindow / qfluentwidgets 处理
        return super().nativeEvent(event_type, message)

    def _fix_titlebar_native(self):
        """修复 qframelesswindow titleBar 原生子窗口被 DWM 错位合成的问题。

        现象：内容区第一行壁纸卡片上方出现一条"遮盖的黑色横条"。
        根因：qframelesswindow 的 titleBar widget 几何本身是正确的（在顶部 46,0，
        最小化/最大化/关闭按钮也正常渲染在右上角），但其“原生子窗口句柄”被 DWM
        合成到了错误位置（例如内容区中部 rel y≈150），于是在内容区叠出一条深色横带
        （顶层窗口底色 32,32,32 透过该错位子窗口显露，而该处卡片内容未被合成）。
        本项目之前"隐藏 titleBar.titleLabel"只能去掉标题文字残留，无法移除这条横带。

        修复：把 titleBar 的原生子窗口句柄强制 SetWindowPos 回与 widget 几何一致的
        客户区位置（46,0），横带即消失，且 titleBar 子对象（min/max/close 按钮）仍
        正常留在右上角（实测：对齐后 y=150 亮度 40→61、y=185 亮度 35→85，按钮可见）。
        需要在窗口真正显示后调用（初始 winId 可能为 0）。
        """
        try:
            user32 = ctypes.windll.user32
            tb = int(self.titleBar.winId())
            if not tb:
                return
            x, y = self.titleBar.x(), self.titleBar.y()
            # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
            flags = 0x0001 | 0x0004 | 0x0010 | 0x0020
            user32.SetWindowPos(tb, None, x, y, 0, 0, flags)
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)
        # 显示后再对齐 titleBar 原生子窗口，消除"遮盖的黑色横条"
        QTimer.singleShot(150, self._fix_titlebar_native)
        # 显式启用拉伸（qframelesswindow 默认 True，但显式声明更稳）
        try:
            self.setResizeEnabled(True)
        except Exception:
            pass
        # 安装 WndProc 并递归把所有子 HWND 设为"全透"，让 WM_NCHITTEST 能
        # 穿透滚动条/视图等所有截断点，回到主窗口 WndProc 处理四角四边拉伸。
        # 注意：这里**不再调用 _strip_dwm_backdrop_for_resize**——
        # 它会把 qfw 设置的 Mica/DWM 主题背景一并清掉，导致首启动主题显示异常
        # （qconfig.themeChangedFinished 信号在 MainWindow 构造前就 emit 过一次，
        # 重新应用 Mica 需要等到 MainWindow 完成构造并 showEvent 后才能正确触发）。
        # 不 strip DWM 反而是更稳的方案：Mica 由 qfw 的 _onThemeChangedFinished
        # 在 _install_resize_wnd_proc 之后再次强制刷新，自然就修好首启动主题。
        QTimer.singleShot(250, self._install_resize_wnd_proc)
        # 每隔 500ms 校准一次几何（应对 winId 切换/多显示器场景）
        self._resize_geom_timer = QTimer(self)
        self._resize_geom_timer.setInterval(500)
        self._resize_geom_timer.timeout.connect(self._refresh_resize_geometry)
        self._resize_geom_timer.start()
        # 强制重应用一次 Mica —— 修复"首次启动主题显示需切一次才正常"的 bug。
        # 根因：main() 里 setTheme() 时 qconfig.themeChangedFinished 信号 emit，
        # 但此时 MainWindow 还没构造，无人监听；构造里 setMicaEffectEnabled(True)
        # 单独跑一次 Mica，DWM 视觉首帧可能未及时合成。延迟 350ms 重新 setMicaEffect
        # 可让 Win11 DWM 在窗口完全 ready 后再合成一次，颜色立刻正确。
        QTimer.singleShot(350, self._force_reapply_mica)
        # 初始应用磨砂玻璃主题（读 SETTINGS['glass'] 完整 dict，实时构建 cfg）
        # delay=700ms 让 WndProc 和 Mica reapply 都先完成，再叠 ACCENT 玻璃层
        QTimer.singleShot(700, self._apply_glass_skin)
        # 安装滚动钩子（700ms 后），实时感知滚动暂停模糊
        QTimer.singleShot(800, self._wire_scroll_hooks)

    def _force_reapply_mica(self):
        """修复"首启动主题显示异常"的 Mica 强制重应用。

        根因：
          main() 里 setTheme() 时 qconfig.themeChangedFinished 信号 emit，但此时
          MainWindow 还没构造，无人监听。MainWindow.__init__ 里 super().__init__()
          走 FluentWidget.__init__ → setMicaEffectEnabled(True) → setMicaEffect()，
          第一次 setup Mica 时 DWM 视觉首帧可能来不及合成（Win11 已知现象），
          用户看到的是 "未生效的主题"。切换主题时 themeChangedFinished 再次触发
          _onThemeChangedFinished → setMicaEffect() 重应用，立刻恢复正常。

        修复：
          showEvent 350ms 后（窗口已 show 完、客户区已绘制、paintEvent 已触发），
          再次调一次完整的 setTheme()：qfw.setTheme 会跑
          ① qconfig.themeMode 重设（保持原值）
          ② updateStyleSheet() —— 遍历所有已注册 widget 重新拉 stylesheet
          ③ emit themeChangedFinished → MainWindow._onThemeChangedFinished 跑
             setMicaEffect(winId, isDarkTheme) —— DWM 重新合成 Mica 首帧
        让 Win11 DWM 在窗口完全 ready 后再合成一次 Mica 首帧，颜色立刻正确。
        """
        try:
            import sys as _sys
            if _sys.platform != "win32":
                return
            if _sys.getwindowsversion().build < 22000:  # 不是 Win11，无 Mica
                return
            hwnd = int(self.winId())
            if not hwnd:
                return
            # 完整重应用：复用 qfw 的 setTheme 流程
            from qfluentwidgets import setTheme, Theme as _QfwTheme
            setTheme(_QfwTheme.DARK if self._dark else _QfwTheme.LIGHT)
        except Exception:
            pass

    # ---------- 磨砂玻璃主题（壁纸抓取 + Pillow 模糊 + paintEvent 绘制） ----------
    def _load_wallpaper_for_glass(self, force=False):
        """加载当前桌面壁纸，按用户模糊半径做 GaussianBlur，返回 QPixmap。

        缓存策略：
          - 用 (path, blur_radius) 做 key 命中缓存（窗口内多 paintEvent 不会反复重抓）
          - 路径变了（用户换了系统壁纸）或 blur 变了 → 失效重抓
          - 任何异常 → 返回 None（paintEvent 会回退到纯色背景，不崩）
        """
        try:
            from PIL import Image as PILImage, ImageFilter
        except Exception:
            return None
        try:
            glass = SETTINGS.get("glass") or {}
            blur = int(glass.get("blur_radius", 30))
            path = get_current_wallpaper_path()
            if not path:
                return None
            # 缓存命中：路径 + 模糊半径都未变
            if not force and self._glass_pixmap is not None \
                    and self._glass_wallpaper_path == path \
                    and getattr(self, "_glass_cached_blur", None) == blur:
                return self._glass_pixmap
            # 加载
            pil = PILImage.open(path)
            # 处理 EXIF orientation（避免手机拍的图旋转 90°）
            try:
                from PIL import ImageOps
                pil = ImageOps.exif_transpose(pil)
            except Exception:
                pass
            pil = pil.convert("RGB")
            # 大图降采样：模糊本来就是降细节，先缩到目标尺寸让 Pillow 模糊快很多。
            # blur 越大视觉上越糊，等效分辨率可以更低，避免 blur=100 时 PIL
            # 在 1920px 图上跑 300ms+ 导致 paintEvent 卡住 + 色块。
            #  - blur <= 30：1920（精细模糊需原图分辨率）
            #  - blur 31~60：1600
            #  - blur > 60：1280（强模糊时 1280 跟 1920 视觉几乎一致，但快 ~2x）
            if blur <= 30:
                max_dim = 1920
            elif blur <= 60:
                max_dim = 1600
            else:
                max_dim = 1280
            if max(pil.size) > max_dim:
                pil.thumbnail((max_dim, max_dim), PILImage.LANCZOS)
            # Pillow GaussianBlur：radius 越大越糊。半径>0 才有效果，0 走原图
            if blur > 0:
                pil = pil.filter(ImageFilter.GaussianBlur(radius=blur))
            # PIL → QImage（必须 .copy() 把内存从 PIL 那边切走，避免 Pillow 释放后 use-after-free）
            w, h = pil.size
            data = pil.tobytes("raw", "RGB")
            qimg = QImage(data, w, h, w * 3, QImage.Format_RGB888).copy()
            from PySide6.QtGui import QPixmap
            self._glass_pixmap = QPixmap.fromImage(qimg)
            self._glass_wallpaper_path = path
            self._glass_cached_blur = blur
            self._glass_size_hash = None  # 让 paintEvent 知道需要重算缩放
            self._glass_render_pending = False  # blur 缓存就绪，清 pending
            return self._glass_pixmap
        except Exception:
            return None

    def paintEvent(self, e):
        """窗体最底层先画"玻璃背景"（模糊壁纸 + 颜色蒙版），再让 qfw
        在上面正常画所有子 widget。卡片/按钮保持 qfw 默认不透明 → 玻璃
        只在卡片之间的空隙透出，正是"整个窗体磨砂但内容不糊"的视觉。

        注意：本方法只画"底部一层"，完全不动 SWCA / DWM 属性 →
        ① 不影响 resize WndProc ② 不影响首启动 Mica ③ 不会引起滚动闪烁
        """
        try:
            glass = SETTINGS.get("glass") or {}
            if not glass.get("enabled", False):
                # 玻璃关闭 → 让 qfw 正常画（Mica + 主题背景就够）
                super().paintEvent(e)
                return
            from PySide6.QtGui import QPainter
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QColor
            painter = QPainter(self)
            try:
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                # ---- 防色块 A 方案：blur pending 期间不画旧 pixmap ----
                # blur 滑块改变时 _glass_render_pending 被置 True，
                # 此时 _load_wallpaper_for_glass 会同步重算（耗时 100~400ms），
                # paintEvent 不应该拿"上次的 pixmap + 新的 alpha 蒙版"叠加，
                # 改为画纯 fallback 色 + 等待用户视觉上不会感知到撕裂。
                # opacity 滑块只改蒙版颜色，不走这条分支。
                render_pending = getattr(self, "_glass_render_pending", False)
                if not render_pending:
                    pix = self._load_wallpaper_for_glass()
                else:
                    pix = None  # 强制走 fallback，避免新旧叠加
                if pix is not None and not pix.isNull():
                    # 按窗口尺寸缩放并居中（KeepAspectRatioByExpanding 保证填满）
                    target_size = (self.width(), self.height())
                    size_hash = (target_size, id(pix))
                    if self._glass_size_hash != size_hash:
                        self._glass_scaled = pix.scaled(
                            target_size[0], target_size[1],
                            Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation)
                        self._glass_size_hash = size_hash
                    # 居中裁切
                    sw, sh = self._glass_scaled.width(), self._glass_scaled.height()
                    x = (self.width() - sw) // 2
                    y = (self.height() - sh) // 2
                    painter.drawPixmap(x, y, self._glass_scaled)
                else:
                    # fallback：抓不到壁纸 或 blur 计算中
                    # 用玻璃色 + 不透明度 画一层纯色，避免突然变黑
                    color_hex = glass.get("color") or "#5E91C7"
                    fallback_alpha = 0.35 if render_pending else 1.0
                    fallback = QColor(color_hex)
                    fallback.setAlphaF(max(0.0, min(1.0, fallback_alpha)))
                    painter.fillRect(self.rect(), fallback)
                # 颜色蒙版（opacity 滑块控制）：pending 期间不叠，避免色块
                if not render_pending:
                    color_hex = glass.get("color") or "#5E91C7"
                    opacity = float(glass.get("opacity", 0.62))
                    overlay = QColor(color_hex)
                    overlay.setAlphaF(max(0.0, min(1.0, opacity)))
                    painter.fillRect(self.rect(), overlay)
            finally:
                painter.end()
        except Exception:
            pass
        # 不论上面成功失败，最后都让 qfw 正常画所有子 widget
        super().paintEvent(e)

    def _apply_glass_skin(self):
        """应用当前磨砂玻璃配置（从 SETTINGS["glass"] 读取，无参数）。

        新版字段结构：
          enabled        总开关（False → 回 Mica 默认）
          color          主色源（#RRGGBB），驱动 SWCA 渐变色 + qfw 强调色
          blur_radius    模糊半径（5~100，PIL GaussianBlur 半径）
          opacity        不透明度（0.20~1.00）→ 颜色蒙版 alpha 通道
          color_mode     fixed / follow_wallpaper（决定颜色是否随壁纸自动提取）

        实现路径：
          Win11 Mica（DWMWA_SYSTEMBACKDROP_TYPE=2）由 qfw 维护，不动。
          在 Mica 之上额外叠一层 ACCENT_ENABLE_ACRYLICBLURBEHIND(4) +
          GradientColor(实时从 glass.color + glass.opacity 算 AABBGGRR)
          → 客户区呈主题色磨砂玻璃。

        不影响：
          ① _install_resize_wnd_proc（四角四边拉伸）
          ② _force_reapply_mica（首启动主题）
          ③ _fix_titlebar_native（黑条）
          ④ 滚动闪烁修复（不引 SetWindowPos / DwmSetWindowAttribute）

        旧版说明（已弃用）：以前用 SWCA ACCENT_ENABLE_ACRYLICBLURBEHIND
        + GradientColor，但有两个根本问题：
          a) Win11 不允许运行时调模糊半径（系统固定值），blur 滑块无效
          b) qfw 卡片/按钮全部不透明，把 SWCA 渐变完全遮挡，调透明度也看不见
        新版见 paintEvent：直接抓桌面壁纸 → Pillow 模糊 → 画在最底层 →
        qfw 控件照常画在上面 → 玻璃透出在卡片之间的空隙，两个滑块都真生效。
        """
        try:
            # 强制失效 wallpaper cache（颜色变了/切了主题/用户点了预设按钮）
            # → 下次 paintEvent 会重新抓 + 重新模糊
            self._glass_pixmap = None
            self._glass_size_hash = None
            # 触发重绘（不开玻璃时 paintEvent 直接走 super，什么都不画）
            if self.isVisible():
                self.update()
        except Exception:
            pass

    def _enable_frosted_glass(self, hwnd, cfg):
        """打开磨砂玻璃层：ACCENT_POLICY = ACCENT_ENABLE_ACRYLICBLURBEHIND(4)
        + GradientColor = cfg['gradient_color'] (AABBGGRR)。

        SetWindowCompositionAttribute 静态/动态 GetProcAddress 双重兜底
        （pyinstaller 打包可能丢静态链接）。

        重要：此函数**不**做任何会触发 DWM 全窗重合成的操作（例如
        SetWindowPos(SWP_FRAMECHANGED) 或 DwmSetWindowAttribute(Mica)）。
        原因：滚动期间若调用这些函数，DWM 会强制重算整张客户区 →
        可见闪烁。Win11 上 OS 合成器对 ACCENT_POLICY 的切换会自动平滑
        过渡，**不需要**手动合成重置。
        """
        try:
            _SWCA = self._get_swca()
            if _SWCA is None:
                return
            # 构建 AccentPolicy
            class _AP(ctypes.Structure):
                _fields_ = [
                    ("nAccentState", ctypes.c_int),
                    ("nFlags", ctypes.c_int),
                    ("nColor", ctypes.c_int),
                    ("nAnimationId", ctypes.c_int),
                ]
            class _WCD(ctypes.Structure):
                _fields_ = [
                    ("nAttribute", ctypes.c_int),
                    ("pData", ctypes.POINTER(_AP)),
                    ("ulDataSize", ctypes.c_ulong),
                ]
            accent = _AP()
            accent.nAccentState = 4   # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.nFlags = 2          # 2 = 渐变颜色
            accent.nColor = int(cfg["gradient_color"])
            accent.nAnimationId = 0
            data = _WCD()
            data.nAttribute = 19  # WCA_ACCENT_POLICY
            data.pData = ctypes.pointer(accent)
            data.ulDataSize = ctypes.sizeof(accent)
            _SWCA(hwnd, ctypes.byref(data))
            # 同步 qfw 强调色到玻璃色：让按钮 hover / 链接 / focus 状态
            # 与玻璃主色保持一致。新版玻璃色是唯一色源，**总是同步**（不再
            # 有"用户手动设过就跳过"的守卫，因为现在只有一套色源）。
            # 失败不影响已成功的 SWCA 设置（独立 try/except）。
            try:
                _accent = cfg.get("color")
                if _accent:
                    setThemeColor(_accent)
            except Exception:
                pass
        except Exception:
            pass

    def _disable_frosted_glass(self, hwnd):
        """关闭磨砂玻璃层（回 Mica-only）。

        同 _enable_frosted_glass：只切 ACCENT_POLICY = 0，不主动触发
        DWM 重合成（DwmSetWindowAttribute(Mica=2) 已由 _force_reapply_mica
        维护，此处不重复）。

        强调色策略：用户没手动设过强调色时才改回默认蓝，与启动时
        `setThemeColor("#0078D4")` 一致；若用户手动设过则保留其偏好。
        """
        try:
            _SWCA = self._get_swca()
            if _SWCA is None:
                return
            class _AP(ctypes.Structure):
                _fields_ = [
                    ("nAccentState", ctypes.c_int),
                    ("nFlags", ctypes.c_int),
                    ("nColor", ctypes.c_int),
                    ("nAnimationId", ctypes.c_int),
                ]
            class _WCD(ctypes.Structure):
                _fields_ = [
                    ("nAttribute", ctypes.c_int),
                    ("pData", ctypes.POINTER(_AP)),
                    ("ulDataSize", ctypes.c_ulong),
                ]
            accent = _AP()
            accent.nAccentState = 0   # ACCENT_DISABLED
            data = _WCD()
            data.nAttribute = 19
            data.pData = ctypes.pointer(accent)
            data.ulDataSize = ctypes.sizeof(accent)
            _SWCA(hwnd, ctypes.byref(data))
            # 强调色策略：玻璃关闭时同步回退到默认蓝（WinUI 3 #0078D4）。
            # 新版玻璃色是唯一色源 → 关闭 = 强调色回默认（不再有"用户手动设过
            # 就跳过"的守卫，老守卫依赖已废弃的 SETTINGS['accent_color'] 字段）。
            try:
                setThemeColor("#0078D4")  # WinUI 3 强调蓝（默认值）
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def _get_swca():
        """获取 SetWindowCompositionAttribute 函数指针（兜底 GetProcAddress）"""
        try:
            SWCA = ctypes.windll.user32.SetWindowCompositionAttribute
            SWCA.argtypes = [wintypes.HWND, ctypes.c_void_p]
            SWCA.restype = ctypes.c_int
            return SWCA
        except AttributeError:
            pass
        try:
            ux = ctypes.windll.uxtheme
            # 通过 ordinal 拿（SetWindowCompositionAttribute 是 uxtheme 下 序号 #21）
            proc = ctypes.windll.kernel32.GetProcAddress(
                ctypes.windll.kernel32.LoadLibraryW("uxtheme.dll"),
                b"SetWindowCompositionAttribute")
            if proc:
                SWCA = ctypes.WINFUNCTYPE(
                    ctypes.c_int, wintypes.HWND, ctypes.c_void_p)(proc)
                return SWCA
        except Exception:
            pass
        try:
            ux = ctypes.windll.uxtheme
            SWCA = ux.SetWindowCompositionAttribute
            SWCA.argtypes = [wintypes.HWND, ctypes.c_void_p]
            SWCA.restype = ctypes.c_int
            return SWCA
        except Exception:
            return None

    def _wire_scroll_hooks(self):
        """钩所有 QScrollArea.valueChanged —— 当前为**占位实现**。

        历史背景：早期版本里，滚动时调用 `_disable_frosted_glass_quiet`
        暂时关掉 ACCENT_POLICY，120ms 后再 `_enable_frosted_glass` 恢复
        以抑制 GPU 拖影。但恢复路径里的 `SetWindowPos(SWP_FRAMECHANGED)`
        会强制 DWM 全窗重合成，在客户区上呈现可见闪烁（背景明暗瞬变）。

        现在的方案：**滚动期间不触碰 SWCA**，完全由 OS 合成器自动平滑
        客户区内容。本函数保留只是为了：① 防止未来破坏调用链；② 若
        日后有真正"必须做"的滚动期响应（比如轻量级 opacity 调整），
        已在对应位置预留 callback 接口。

        注册逻辑**仍然完整**：所有滚动条信号都连到 `_on_scroll_value_changed`，
        但回调本身是 no-op。
        """
        try:
            from PySide6.QtWidgets import QScrollArea
            seen = set()
            if hasattr(self, "stackedWidget"):
                for sa in self.stackedWidget.findChildren(QScrollArea):
                    key = id(sa)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        sa.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)
                    except Exception:
                        pass
                    try:
                        sa.horizontalScrollBar().valueChanged.connect(self._on_scroll_value_changed)
                    except Exception:
                        pass
            for attr_name in ("settingPage", "setting_page"):
                if hasattr(self, attr_name):
                    sp = getattr(self, attr_name)
                    if isinstance(sp, QScrollArea) and id(sp) not in seen:
                        seen.add(id(sp))
                        try:
                            sp.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)
                        except Exception:
                            pass
            if not hasattr(self, "_glass_scroll_timer"):
                # 占位：保留一个 QTimer 实例，便于将来需要做"滚动停止 N ms 后"
                # 类优化时直接复用，不必再改 showEvent 的 singleShot 顺序。
                self._glass_scroll_timer = QTimer(self)
                self._glass_scroll_timer.setSingleShot(True)
                self._glass_scroll_timer.setInterval(120)
                self._glass_scroll_timer.timeout.connect(self._restore_glass_after_scroll)
                self._glass_paused = False
        except Exception:
            pass

    def _on_scroll_value_changed(self, *_):
        """滚动回调 —— 当前为 no-op。

        历史：曾在此函数内关闭 ACCENT_POLICY + 120ms 后调用
        `_enable_frosted_glass` 重新开启。`_enable_frosted_glass` 内
        的 `SetWindowPos(SWP_FRAMECHANGED)` 会在滚动停止瞬间强制
        DWM 重合成整个客户区 → 可见闪烁。

        现在滚动期间**完全不**操作 SWCA / SWP / DWM 属性，OS 合成器
        会自然平滑采样壁纸做 blur，**无**闪烁。若后续要做一个不会闪烁
        的轻量级调整（如降低透明度），请改 `_on_scroll_value_changed`
        内部实现，但**禁止**调用任何 `_enable_frosted_glass` /
        `_disable_frosted_glass` / SetWindowPos(SWP_FRAMECHANGED)
        / DwmSetWindowAttribute(Mica)。
        """
        # Intentionally empty. SWCA is set once at theme switch and never
        # touched again on scroll. See _enable_frosted_glass docstring.
        return

    def _restore_glass_after_scroll(self):
        """滚动停止回调 —— 当前为 no-op。

        历史配套：在 `_on_scroll_value_changed` 关掉 ACCENT 后由 120 ms
        定时器触发恢复。如今不再在滚动期间关闭 ACCENT，自然无需要"恢复"。
        保留为 no-op，避免 `QTimer.timeout` 连接目标丢失产生警告。
        """
        self._glass_paused = False

    # ---------- 定时切换深色模式 ----------
    def _apply_dark_schedule(self):
        """根据 SETTINGS["dark_schedule"] 启停后台 QTimer。
        60 秒轮询一次精度足够（用户不会在意 ±1 分钟的切换偏差）。"""
        if not hasattr(self, "_dark_schedule_timer") or self._dark_schedule_timer is None:
            self._dark_schedule_timer = QTimer(self)
            self._dark_schedule_timer.setInterval(60 * 1000)
            self._dark_schedule_timer.timeout.connect(self._on_dark_schedule_tick)
        ds = SETTINGS.get("dark_schedule") or {}
        if ds.get("enabled", False):
            if not self._dark_schedule_timer.isActive():
                self._dark_schedule_timer.start()
            # 启动时立刻跑一次，避免等 60 秒
            self._on_dark_schedule_tick()
        else:
            self._dark_schedule_timer.stop()

    def _on_dark_schedule_tick(self):
        """60 秒一次：判断当前是否应切深色，状态不一致就切。"""
        try:
            should_dark = self._should_dark_now()
            if should_dark is None:
                return  # 计算失败（极昼极夜等），不动
            if bool(should_dark) != bool(self._dark):
                # 状态切换
                self._set_dark(bool(should_dark))
        except Exception:
            pass

    def _should_dark_now(self):
        """根据当前时间 + SETTINGS["dark_schedule"] 判断是否应进入深色模式。

        custom 模式：start~end 区间内为深色（支持跨越 00:00）
        sunrise 模式：本地时间 sunset ~ 次日 sunrise 为深色
        返回 None 表示无法判断（如极昼极夜），调用方应跳过。"""
        ds = SETTINGS.get("dark_schedule") or {}
        mode = ds.get("mode", "custom")
        from datetime import datetime as _dt
        now = _dt.now()
        try:
            if mode == "custom":
                sh, sm = (int(x) for x in str(ds.get("start", "20:00")).split(":")[:2])
                eh, em = (int(x) for x in str(ds.get("end", "07:00")).split(":")[:2])
                cur = now.hour * 60 + now.minute
                s = sh * 60 + sm
                e = eh * 60 + em
                if s == e:
                    return None  # 起止相同视为未配置
                if s < e:
                    # 不跨午夜：s <= cur < e
                    return s <= cur < e
                else:
                    # 跨午夜：cur >= s 或 cur < e
                    return cur >= s or cur < e
            else:
                # sunrise 模式：sunset ~ next sunrise 为深色
                lat = float(ds.get("lat", 39.9042))
                lon = float(ds.get("lon", 116.4074))
                tz_off = _current_tz_offset_hours()
                s_utc, e_utc = _sun_times_utc(lat, lon, now.date())
                if s_utc is None:
                    return None
                # 转换成本地时间
                from datetime import timedelta as _td
                s_local = s_utc + _td(hours=tz_off)
                e_local = e_utc + _td(hours=tz_off)
                # 深色 = sunset <= now < next sunrise
                # 如果 now < s_local：还在白天（now 早于今天的 sunset）
                # 如果 now >= s_local：进入深色（要看是否已过第二天 sunrise）
                #   next sunrise = s_local + 1 day（如果不是同一天）
                if now < s_local:
                    return False  # 还在白天（今天 sunset 之前）
                # 已过今天 sunset，下次 sunrise 是明天
                next_sunrise = s_local + _td(days=1)
                if now < next_sunrise:
                    return True
                # 已过明天 sunrise，回到白天
                return False
        except Exception:
            return None
        # Intentionally empty. SWCA already set; do not touch during/after scroll.
        return

    def _disable_frosted_glass_quiet(self, hwnd):  # noqa: ARG002  (保持签名兼容)
        """历史占位：曾是滚动期间的"轻量级暂停"开关。

        现已不再被调用。保留方法以兼容潜在的反射型引用；调用不会改变
        SWCA / Mica / 窗口位置。
        """
        # Intentionally empty: scroll-time SWCA toggle removed to fix flicker.
        return

    # ---------- 真正的 WndProc 注入（解决"只有左侧能拉伸"） ----------
    def _install_resize_wnd_proc(self):
        """用 SetWindowLongPtrW 注入原生 WndProc，强制处理 WM_NCHITTEST。

        背景：
          之前我们用 PySide6 的 nativeEvent 覆写 WM_NCHITTEST，理论上应该四角四边
          都返回拉伸码。但实测只有左/上能用（右边/下边的滚动条、视图等子 HWND 截
          断了 WM_NCHITTEST 路由）。

          更稳妥的做法：**直接在 Win32 层用 SetWindowLongPtrW(GWLP_WNDPROC)
          替换主窗口的 WndProc**，我们的 WndProc 先于 Qt 看到 WM_NCHITTEST，并
          直接处理四角四边（8px 边界，HITTEST_CODES 完全自己控制）。
          其余消息用 CallWindowProcW 转给原 WndProc，不破坏 Qt 事件链。

        同时**递归**遍历主窗口的所有子 HWND（任意层级），把它们的 WndProc 也
        替换成"WM_NCHITTEST 始终返回 HTTRANSPARENT"。这样无论鼠标停在滚动条、
        视图、还是卡片上，WM_NCHITTEST 都会穿透回到主窗口 → 我们主窗口 WndProc
        决定这是边缘拉伸码还是客户区（HTCLIENT）。

        Qt 自己的事件分发（WM_LBUTTONDOWN → QMouseEvent → 按 cursor 位置派发到
        具体 QWidget）跟 Win32 命中测试码无关，所以关闭/最大化/最小化按钮、
        滚动条拖动等都能正常工作，只是光标外观可能略有差异（功能完全保留）。
        """
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            user32 = ctypes.windll.user32

            # ------ 原生 WndProc 函数（必须保持全局引用，ctypes 才能正确回收） ------
            if not hasattr(self, "_orig_wndproc") or self._orig_wndproc is None:
                GWLP_WNDPROC = -4
                SetWindowLongPtrW = user32.SetWindowLongPtrW
                SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                SetWindowLongPtrW.restype = ctypes.c_void_p
                GetWindowLongPtrW = user32.GetWindowLongPtrW
                GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
                GetWindowLongPtrW.restype = ctypes.c_void_p

                CallWindowProcW = user32.CallWindowProcW
                CallWindowProcW.argtypes = [
                    ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                    wintypes.WPARAM, wintypes.LPARAM,
                ]
                CallWindowProcW.restype = ctypes.c_long

                # 保存原 WndProc
                orig_proc = GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
                self._orig_wndproc = orig_proc
                self._resize_hwnd = hwnd

                # WM_NCHITTEST / SetWindowPos 用到的常量
                WM_NCHITTEST = 0x0084
                WM_SIZE = 0x0005
                WM_MOVE = 0x0003
                HTLEFT = 10
                HTRIGHT = 11
                HTTOP = 12
                HTTOPLEFT = 13
                HTTOPRIGHT = 14
                HTBOTTOM = 15
                HTBOTTOMLEFT = 16
                HTBOTTOMRIGHT = 17
                HTTRANSPARENT = -1

                # 边界宽度（与 nativeEvent 一致：8px 更友好）
                BORDER_W = 8

                # 缓存主窗口矩形
                import threading
                self._resize_lock = threading.Lock()
                self._resize_state = {
                    "x": 0, "y": 0, "w": 0, "h": 0,
                    "maximized": False, "fullscreen": False,
                }
                self._refresh_resize_geometry()

                WM_ENTERSIZEMOVE = 0x0231
                WM_EXITSIZEMOVE = 0x0232

                # ----- 真正的 WndProc -----
                WndProcType = ctypes.WINFUNCTYPE(
                    ctypes.c_long,
                    wintypes.HWND, wintypes.UINT,
                    wintypes.WPARAM, wintypes.LPARAM,
                )

                main_ref = self

                def _wnd_proc(h, msg, wp, lp):
                    try:
                        if h == main_ref._resize_hwnd and msg == WM_NCHITTEST:
                            with main_ref._resize_lock:
                                st = main_ref._resize_state
                            if st["maximized"] or st["fullscreen"]:
                                return CallWindowProcW(
                                    main_ref._orig_wndproc, h, msg, wp, lp)
                            x = lp & 0xFFFF
                            y = (lp >> 16) & 0xFFFF
                            with main_ref._resize_lock:
                                rx = x - st["x"]
                                ry = y - st["y"]
                                w = st["w"]
                                h2 = st["h"]
                            lx = rx < BORDER_W
                            rxr = rx > w - BORDER_W
                            ty = ry < BORDER_W
                            by = ry > h2 - BORDER_W
                            if lx and ty:   return HTTOPLEFT
                            if rxr and ty:  return HTTOPRIGHT
                            if lx and by:   return HTBOTTOMLEFT
                            if rxr and by:  return HTBOTTOMRIGHT
                            if ty:          return HTTOP
                            if by:          return HTBOTTOM
                            if lx:          return HTLEFT
                            if rxr:         return HTRIGHT
                            return CallWindowProcW(
                                main_ref._orig_wndproc, h, msg, wp, lp)

                        if h == main_ref._resize_hwnd and msg in (WM_MOVE, WM_SIZE,
                                                                 WM_ENTERSIZEMOVE,
                                                                 WM_EXITSIZEMOVE):
                            main_ref._refresh_resize_geometry()
                    except Exception:
                        pass
                    return CallWindowProcW(
                        main_ref._orig_wndproc, h, msg, wp, lp)

                # 装到主窗口
                new_proc = WndProcType(_wnd_proc)
                self._resize_wnd_proc = new_proc
                SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                                  ctypes.cast(new_proc, ctypes.c_void_p).value)

                # ----- 递归给所有子 HWND 装"WM_NCHITTEST→HTTRANSPARENT" WndProc -----
                # 不再用白名单法（只 patch 4 个已知子窗口），而是把所有孙子 HWND
                # 一并 patch，让命中测试**穿透**到主窗口处理。Qt 事件分发通过
                # QMouseEvent 按 cursor 位置派发，跟 WM_NCHITTEST 返回值无关，
                # 所以按钮点击、滚动条拖动、卡片交互全部保留。
                if not hasattr(self, "_child_transparent_procs"):
                    self._child_transparent_procs = []

                WNDENUMPROC = ctypes.WINFUNCTYPE(
                    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

                def _enum_recursive(parent_hwnd):
                    """深度优先枚举所有子 HWND（含任意层级嵌套）"""
                    result = []
                    children_holding = []

                    def _cb(hwnd, lparam):
                        children_holding.append(hwnd)
                        return True

                    user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(_cb), 0)
                    for ch in children_holding:
                        result.append(ch)
                        result.extend(_enum_recursive(ch))
                    return result

                all_descendants = _enum_recursive(hwnd)
                patched = 0
                for ch_hwnd in all_descendants:
                    try:
                        orig = GetWindowLongPtrW(ch_hwnd, GWLP_WNDPROC)
                        if not orig:
                            continue
                        # 已经被 patch 过的跳过（避免重复包装）
                        if any(p and ctypes.cast(p, ctypes.c_void_p).value == orig
                               for p in self._child_transparent_procs):
                            continue

                        def _make_transparent_proc(_orig_ptr):
                            def _proc(h, msg, wp, lp):
                                try:
                                    if msg == WM_NCHITTEST:
                                        return HTTRANSPARENT
                                except Exception:
                                    pass
                                return CallWindowProcW(_orig_ptr, h, msg, wp, lp)
                            return _proc

                        proc_func = _make_transparent_proc(orig)
                        new_child_proc = WndProcType(proc_func)
                        self._child_transparent_procs.append(new_child_proc)
                        SetWindowLongPtrW(
                            ch_hwnd, GWLP_WNDPROC,
                            ctypes.cast(new_child_proc, ctypes.c_void_p).value)
                        patched += 1
                    except Exception:
                        continue
                # 调试时可解开看 patch 了多少
                # print(f"[WndProc] patched {patched} descendants of main window")

        except Exception:
            pass

    def _refresh_resize_geometry(self):
        """读取主窗口的当前屏幕矩形 + 最大化状态，供 WndProc 命中计算用。"""
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            class RECT(ctypes.Structure):
                _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                            ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            # 最大化/全屏：用 GetWindowPlacement 判
            WPF_RESTORETOMAXIMIZED = 0x0002
            class WINDOWPLACEMENT(ctypes.Structure):
                _fields_ = [
                    ('length', ctypes.c_uint),
                    ('flags', ctypes.c_uint),
                    ('showCmd', ctypes.c_uint),
                    ('ptMinPosition', ctypes.c_long * 2),
                    ('ptMaxPosition', ctypes.c_long * 2),
                    ('rcNormalPosition', RECT),
                    ('rcDevice', RECT),
                ]
            wp = WINDOWPLACEMENT()
            wp.length = ctypes.sizeof(wp)
            user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
            is_max = bool(wp.flags & WPF_RESTORETOMAXIMIZED) or wp.showCmd == 3  # SW_SHOWMAXIMIZED
            is_full = bool(self.isFullScreen())
            with self._resize_lock:
                self._resize_state["x"] = r.left
                self._resize_state["y"] = r.top
                self._resize_state["w"] = r.right - r.left
                self._resize_state["h"] = r.bottom - r.top
                self._resize_state["maximized"] = is_max
                self._resize_state["fullscreen"] = is_full
        except Exception:
            pass

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:
            if self.isMinimized() and SETTINGS.get("minimize_to_tray", True):
                QTimer.singleShot(0, self._hide_to_tray)

    # ---------- 定时自动切换壁纸 ----------
    def _apply_auto_switch(self):
        asw = SETTINGS["auto_switch"]
        if asw.get("enabled", False):
            interval_min = int(asw.get("interval_min", 30))
            self.auto_timer.start(interval_min * 60 * 1000)
        else:
            self.auto_timer.stop()

    def _auto_switch_tick(self):
        if self._auto_switching:
            return
        self._auto_switching = True
        threading.Thread(target=self._auto_switch_worker, daemon=True).start()

    def _random_cate_slug(self):
        cats = self.categories or FALLBACK_CATEGORIES
        return random.choice([s for _, s in cats])

    def _pick_random_item(self, cate):
        """从指定分类（slug 空=全部）随机取一张壁纸，返回 (title, detail)"""
        url1 = self._cate_list_url(cate, 1)
        items, _p, total = self.net.fetch_list(url1)
        if total > 1:
            page = random.randint(1, min(total, 300))
            if page != 1:
                items, _p, total = self.net.fetch_list(self._cate_list_url(cate, page))
        if not items:
            raise RuntimeError("没有可用的壁纸")
        title, thumb, detail_url = random.choice(items)
        detail = self.net.fetch_detail(detail_url, thumb)
        return title, detail

    def _auto_switch_worker(self):
        try:
            cfg = SETTINGS["auto_switch"]
            mode = cfg.get("mode", "random")
            cate = cfg.get("category", "") if mode == "cate" else self._random_cate_slug()
            title, detail = self._pick_random_item(cate)
            origin = detail.get("origin")
            if not origin:
                raise RuntimeError("未找到原图链接")
            data = self.net.get_bytes(origin, referer=detail.get("detail_url", BASE_URL + "/index.htm"))
            ensure_cache_dir()
            tmp = os.path.join(CACHE_DIR, "_auto_wallpaper.jpg")
            with open(tmp, "wb") as f:
                f.write(data)
            set_as_wallpaper(tmp)
            bridge.auto_switch_done.emit(title)
        except Exception as e:  # noqa
            bridge.auto_switch_failed.emit(str(e))
        finally:
            self._auto_switching = False

    def _on_auto_switch_done(self, title):
        if self.tray:
            self.tray.showMessage("已切换壁纸", f"「{title}」已设为桌面壁纸",
                                  QSystemTrayIcon.Information, 2500)
        else:
            notify(self, "success", "已切换壁纸", f"「{title}」已设为桌面壁纸", 2500)
        # 自动配色：从定时切换的壁纸提取主色调
        if _is_auto_color():
            wp_path = os.path.join(CACHE_DIR, "_auto_wallpaper.jpg")
            if os.path.exists(wp_path):
                self._extract_and_apply_color(wp_path)

    def _on_auto_switch_failed(self, msg):
        if self.tray:
            self.tray.showMessage("切换壁纸失败", msg, QSystemTrayIcon.Warning, 3000)
        else:
            notify(self, "error", "切换壁纸失败", msg, 4000)

    def resizeEvent(self, event):
        # 主窗口 resize 不再主动重排 grid——WallpaperPage.eventFilter/resizeEvent
        # 会监听 grid_host 自身 Resize 并通过 singleShot 防抖延后重排。
        super().resizeEvent(event)
        # 缩放后 titleBar 原生子窗口可能再次被 DWM 错位合成，重新对齐
        QTimer.singleShot(0, self._fix_titlebar_native)
        # 缩放后 _glass_scaled 尺寸缓存失效，让 paintEvent 重算缩放（不重抓不重模糊，只换张）
        self._glass_size_hash = None



def _ensure_single_instance():
    """确保只运行一个实例。如已有实例则激活其窗口并退出。

    使用 Windows 命名互斥锁，可靠且无副作用。
    """
    import ctypes
    from ctypes import wintypes

    mutex_name = r"Local\NetBianWallpaper_SingleInstance_Mutex"
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    # 创建命名互斥锁
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    last_error = kernel32.GetLastError()

    if last_error == 183:  # ERROR_ALREADY_EXISTS — 已有实例
        # 文件 IPC：写入信号文件，由已有实例的定时器检测并自行激活窗口
        # 不做任何跨进程窗口操作，彻底避免死锁/卡死
        try:
            flag = os.path.join(CACHE_DIR, "_show_signal.flag")
            with open(flag, "w") as f:
                f.write("show")
        except Exception:
            pass
        kernel32.CloseHandle(mutex)
        os._exit(0)

    return mutex  # 保持引用防止被 GC 回收


def main():
    # 单实例限制：如有已有实例则激活并退出
    _instance_mutex = _ensure_single_instance()
    ensure_cache_dir()
    load_settings()
    app = QApplication(sys.argv)
    setTheme(Theme.DARK if SETTINGS["theme"] == "dark" else Theme.LIGHT)
    setThemeColor("#0078D4")  # WinUI 3 强调蓝

    app.setApplicationName("彼岸桌面壁纸浏览器")
    try:
        from app_icon import get_app_icon
        app.setWindowIcon(get_app_icon())
    except Exception:
        pass
    win = MainWindow()
    win.show()
    # 命令行参数 --settings 直接跳转到设置页
    if "--settings" in sys.argv:
        win._open_settings()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
