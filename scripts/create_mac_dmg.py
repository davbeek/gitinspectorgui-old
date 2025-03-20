from pathlib import Path

import dmgbuild  # Ensure dmgbuild is installed

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "GitinspectorGUI.app"
DMG_NAME = "GitinspectorGUI.dmg"
VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()


def create_dmg():
    app_path = ROOT_DIR / "app" / APP_NAME
    dmg_name_with_version = (
        f"GitinspectorGUI-{VERSION}.dmg"  # Append version to the dmg name
    )
    dmg_path = ROOT_DIR / "app" / dmg_name_with_version

    # Delete the existing .dmg file if it exists
    if dmg_path.exists():
        print(f"Deleting existing .dmg file: {dmg_path}")
        dmg_path.unlink()

    dmgbuild.build_dmg(
        filename=str(dmg_path),
        volume_name="GitinspectorGUI",
        settings={
            "files": [str(app_path)],
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

    print(f"Created .dmg installer at: {dmg_path}")


if __name__ == "__main__":
    create_dmg()
