# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('trackmind_icon.ico', '.'), ('C:\\Users\\lbcya\\AppData\\Local\\Programs\\Python\\Python39\\lib\\site-packages\\mediapipe\\modules', 'mediapipe\\modules'), ('C:\\Users\\lbcya\\AppData\\Local\\Programs\\Python\\Python39\\lib\\site-packages\\mediapipe\\python\\solutions', 'mediapipe\\python\\solutions'), ('C:\\Users\\lbcya\\AppData\\Local\\Programs\\Python\\Python39\\lib\\site-packages\\cv2\\data', 'cv2\\data')]
binaries = []
hiddenimports = ['mediapipe', 'mediapipe.python', 'mediapipe.python.solutions', 'mediapipe.python.solutions.pose', 'cv2', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'numpy']
tmp_ret = collect_all('mediapipe')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['autotrack.py'],
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
    name='Trackmind',
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
    icon=['trackmind_icon.ico'],
)
