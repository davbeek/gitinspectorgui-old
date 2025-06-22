# type: ignore
# ruff: noqa: F821  # Do not complain about undefined names

block_cipher = None

a = Analysis(
    ["src/gigui/cli.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/gigui/gui/images", "images"),
        ("src/gigui/output/static", "gigui/output/static"),
        ("src/gigui/version.txt", "gigui"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_private_assemblies=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gitinspectorcli-old",
    debug=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=True,
    disable_windowed_traceback=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="bundle",
)
