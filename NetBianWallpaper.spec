# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('qfluentwidgets')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('curl_cffi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# SSL/OpenSSL support
import os, sys
hiddenimports += ['ssl', '_ssl', 'certifi', 'charset_normalizer', 'urllib3']
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# PyInstaller 在执行 spec 时会替换 sys 模块，导致 base_executable 缺失；
# 这里用回退链兼容各种启动方式。
_base_exe = getattr(sys, 'base_executable', None) or getattr(sys, '_base_executable', None) or sys.executable
python_dir = os.path.dirname(_base_exe)
ssl_dlls = ['libssl-3-x64.dll', 'libcrypto-3-x64.dll', 'libssl-3.dll', 'libcrypto-3.dll']
for dll_name in ssl_dlls:
    for search_dir in [python_dir, os.path.join(python_dir, 'DLLs')]:
        dll_path = os.path.join(search_dir, dll_name)
        if os.path.exists(dll_path):
            binaries.append((dll_path, '.'))
            break

a = Analysis(
    ['wallpaper.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NetBianWallpaper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)