# Disadvantage: running the generated .pkg file requires a password.

import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "GitinspectorGUI.app"
PKG_NAME = "GitinspectorGUI.pkg"
VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()
PKG_IDENTIFIER = "com.example.gitinspectorgui"
COMPONENT_PLIST = (
    ROOT_DIR / "scripts" / "static" / "component.plist"
)  # Updated path to the component plist


def create_pkg():
    app_path = ROOT_DIR / "app" / APP_NAME
    pkg_path = ROOT_DIR / "app" / PKG_NAME

    # Create a temporary directory to serve as the root for the package
    temp_root = ROOT_DIR / "temp_pkg_root"
    temp_root.mkdir(parents=True, exist_ok=True)

    # Copy the .app bundle into the temporary root directory
    shutil.copytree(app_path, temp_root / APP_NAME, dirs_exist_ok=True)

    # Delete the existing .pkg file if it exists
    if pkg_path.exists():
        print(f"Deleting existing .pkg file: {pkg_path}")
        pkg_path.unlink()

    # Run pkgbuild to create the .pkg installer
    pkgbuild_command = [
        "pkgbuild",
        "--root",
        str(temp_root),
        "--identifier",
        PKG_IDENTIFIER,
        "--version",
        VERSION,
        "--install-location",
        "Applications",
        "--component-plist",
        str(COMPONENT_PLIST),
        str(pkg_path),
    ]
    print(" ".join(pkgbuild_command))
    subprocess.run(pkgbuild_command, check=True)

    # Clean up the temporary directory
    shutil.rmtree(temp_root)

    print(f"Created .pkg installer at: {pkg_path}")


if __name__ == "__main__":
    create_pkg()
