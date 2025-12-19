# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('config.yml', '.'), ('moyu.ico', '.'), ('moyu.png', '.')]
datas += collect_data_files('mediapipe')

# 添加所有模块目录
hiddenimports = [
    'core',
    'core.constants',
    'core.deps',
    'core.paths',
    'core.config_loader',
    'core.detector',
    'services',
    'services.snapshot',
    'services.work_app',
    'ui',
    'ui.tray',
    'ui.ui_app',
    'ui.headless',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
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
    name='moyu',
    icon='moyu.ico',
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
)
