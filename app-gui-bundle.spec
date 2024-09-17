# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/gigui/gui/psg.py'],
    pathex=["src"],
    binaries=[],
    datas=
    [
        ('src/gigui/gui/images', 'images'),
        ('src/gigui/output/files', 'gigui/output/files'),
        ('src/gigui/version.txt', 'gigui')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)
pyz = PYZ(
    a.pure, a.zipped_data,
    cipher=block_cipher
)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='gitinspectorgui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='bundle'
)
app = BUNDLE(
    coll,
    name='GitinspectorGUI.app',
    icon='src/gigui/gui/images/icon.icns',  # Optionally set the path to your .icns icon file
)
