# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

_dnd_datas, _dnd_binaries, _dnd_hiddenimports = collect_all('tkinterdnd2')
_fit_datas, _fit_binaries, _fit_hiddenimports = collect_all('fitz')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_dnd_binaries + _fit_binaries,
    datas=_dnd_datas + _fit_datas + [
        ('catalog.py', '.'),
        ('config.py', '.'),
        ('msi_ops.py', '.'),
        ('logo_assets.py', '.'),
        ('assets', 'assets'),
    ],
    hiddenimports=_dnd_hiddenimports + _fit_hiddenimports,
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
    name='Rexdesk Version Manager',
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
    uac_admin=False,
)
