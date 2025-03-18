import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "GitinspectorGUI.app"
DMG_NAME = "GitinspectorGUI.dmg"
VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()


def create_dmg():
    app_path = ROOT_DIR / "app" / APP_NAME
    dmg_path = ROOT_DIR / "app" / DMG_NAME

    # Create a temporary directory to prepare the .dmg contents
    temp_dmg_dir = ROOT_DIR / "temp_dmg_dir"
    temp_dmg_dir.mkdir(parents=True, exist_ok=True)

    # Copy the .app bundle into the temporary directory
    shutil.copytree(app_path, temp_dmg_dir / APP_NAME, dirs_exist_ok=True)

    # Delete the existing .dmg file if it exists
    if dmg_path.exists():
        print(f"Deleting existing .dmg file: {dmg_path}")
        dmg_path.unlink()

    # Use create-dmg to create the .dmg file
    create_dmg_command = [
        "create-dmg",
        "--volname",
        "GitinspectorGUI",
        "--window-size",
        "450",
        "300",
        "--icon-size",
        "128",
        "--icon",
        APP_NAME,
        "300",
        "100",
        "--icon",
        "Applications",
        "100",
        "100",
        "--hide-extension",
        APP_NAME,
        "--app-drop-link",
        "100",
        "100",
        str(dmg_path),
        str(temp_dmg_dir),
    ]
    print(" ".join(create_dmg_command))
    subprocess.run(create_dmg_command, check=True)

    # Clean up the temporary directory
    shutil.rmtree(temp_dmg_dir)

    print(f"Created .dmg installer at: {dmg_path}")


if __name__ == "__main__":
    create_dmg()
