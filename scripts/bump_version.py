# pylint: disable=redefined-outer-name

import re
from pathlib import Path


# On Windows:
# from gigui.common import get_version
# from .common import get_version
# both don't work, even though sys.path contains the path to scr/gigui
# On macOS, both work. Therefore, copy get_version() here.
def get_version() -> str:
    mydir = Path(__file__).resolve().parent
    version_file = mydir.parent / "src" / "gigui" / "version.txt"
    with open(version_file, "r", encoding="utf-8") as file:
        version = file.read().strip()
    return version


# Bump version in poetry pyproject.toml
def bump_toml_version(version):
    # Get the path to the directory containing this script
    script_dir = Path(__file__).resolve().parent
    toml_path = script_dir.parent / "pyproject.toml"

    with open(toml_path, "r", encoding="utf-8") as file:
        content = file.read()

    # Regex to match the version line in the [tool.poetry] section
    content = re.sub(
        r'^version\s*=\s*".*"',
        f'version = "{version}"',
        content,
        flags=re.MULTILINE,
    )

    with open(toml_path, "w", encoding="utf-8") as file:
        file.write(content)


# Bump version in gigui-pyinstall.iss inno setup file
def bump_inno_version(version):
    # Get the path to the directory containing this script
    script_dir = Path(__file__).resolve().parent
    inno_path = script_dir / "app-setup.iss"

    with open(inno_path, "r", encoding="utf-8") as file:
        content = file.read()

    # Regex to match the version line in the [tool.poetry] section
    content = re.sub(
        r'^#define MyAppVersion\s*".*"',
        f'#define MyAppVersion "{version}"',
        content,
        flags=re.MULTILINE,
    )

    with open(inno_path, "w", encoding="utf-8") as file:
        file.write(content)


if __name__ == "__main__":
    version = get_version()
    print("Update version to", version)
    print("Bump version in pyproject.toml")
    bump_toml_version(version)
    print("Bump version in scripts/app-setup.iss")
    bump_inno_version(version)
