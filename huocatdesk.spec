# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把 huocatdesk 打成单文件可执行程序。

构建：python build.py（或 pyinstaller huocatdesk.spec）
产物：dist/huocatdesk.exe（Windows）/ dist/huocatdesk（macOS/Linux）
"""
import os

from PyInstaller.utils.hooks import collect_all

# tkinter / PIL 的运行时数据（tcl/tk 库、_tkinter.pyd、PIL 插件）必须显式收集，
# 否则冻结后的 GUI 找不到 init.tcl 而启动失败。
tk_d, tk_b, tk_h = collect_all('tkinter')
pil_d, pil_b, pil_h = collect_all('PIL')

block_cipher = None

a = Analysis(
    ['src/huocatdesk/__main__.py'],
    pathex=['src'],
    binaries=tk_b + pil_b,
    datas=tk_d + pil_d,
    hiddenimports=tk_h + pil_h + ['PIL.ImageTk', 'PIL.Image', 'PIL.ImageGrab'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['cv2', 'numpy', 'pandas', 'PySide6', 'PyQt6'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='huocatdesk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='huocatdesk',
)
