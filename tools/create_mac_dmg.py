import platform
from pathlib import Path

import dmgbuild

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "GitinspectorGUI.app"
APP_PATH = ROOT_DIR / "app" / APP_NAME

VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()
PROCESSOR_TYPE = "AppleSilicon" if "arm" in platform.machine().lower() else "Intel"
DMG_NAME_VERSION = f"GitinspectorGUI-{VERSION}-{PROCESSOR_TYPE}.dmg"
DMG_PATH = ROOT_DIR / "app" / DMG_NAME_VERSION


def create_dmg() -> Path:
    # Delete the existing .dmg file if it exists
    if DMG_PATH.exists():
        print(f"Deleting existing .dmg file: {DMG_PATH}")
        DMG_PATH.unlink()

    dmgbuild.build_dmg(
        filename=str(DMG_PATH),
        volume_name="GitinspectorGUI",
        settings={
            "files": [str(APP_PATH)],
            "symlinks": {"Applications": "/Applications"},
            "icon_locations": {
                APP_NAME: (130, 100),
                "Applications": (510, 100),
            },
            "window": {
                "size": (480, 300),
                "position": (100, 100),
            },
            "background": "builtin-arrow",
            # "background": "rgb(1,0,0)",
            # "background": "goldenrod",
            "icon_size": 128,
        },
    )
    print(f"Created .dmg installer at: {DMG_PATH}")
    return DMG_PATH


if __name__ == "__main__":
    create_dmg()
