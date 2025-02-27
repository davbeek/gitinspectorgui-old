# type: ignore
# ruff: noqa: F821  # Do not complain about undefined names

block_cipher = None

a = Analysis(
    ['src/gigui/gui/psg.py'],
    pathex=[],
    binaries=[],
    datas=
    [ ('src/gigui/gui/images', 'images'), ('src/gigui/output/files', 'gigui/output/files')],
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
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='gitinspectorgui',
    debug=False,    # Set to True to debug the GUI when started via app/mac/gitinspectorgui
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)

app = BUNDLE(
    exe,
    name='GitinspectorGUI.app',
    icon=None,
    bundle_identifier=None
 )
