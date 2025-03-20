import platform
from pathlib import Path

import requests

from tools.create_app import create_bundle
from tools.create_mac_dmg import create_dmg
from tools.create_release import GITHUB_API_URL, GITHUB_TOKEN, REPO_NAME, REPO_OWNER
from tools.create_win_setup import create_setup_file


def upload_asset_to_release(file_path: Path, file_name: str):
    if not GITHUB_TOKEN:
        raise EnvironmentError("GITHUB_TOKEN environment variable is not set.")

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Get the latest release
    url = f"{GITHUB_API_URL}/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    print("Fetching the latest GitHub release...")
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    release = response.json()
    upload_url = release["upload_url"].replace("{?name,label}", "")

    # Upload the file
    print(f"Uploading {file_name} to GitHub release...")
    headers.update({"Content-Type": "application/octet-stream"})
    params = {"name": file_name}
    with open(file_path, "rb") as f:
        response = requests.post(upload_url, headers=headers, params=params, data=f)
    response.raise_for_status()
    print(f"Asset uploaded: {response.json()['browser_download_url']}")


def create_mac_asset() -> Path:
    create_bundle("gui")
    return create_dmg()


def create_win_asset() -> Path:
    create_bundle("gui")
    return create_setup_file()


def extend_release():
    system = platform.system().lower()
    arch = platform.machine().lower()

    if system == "darwin" and "intel" in arch:
        print("Detected macOS on Intel hardware. Creating and uploading DMG...")
        dmg_path = create_mac_asset()
        upload_asset_to_release(dmg_path, dmg_path.name)
    elif system == "windows":
        print("Detected Windows. Creating and uploading setup file...")
        setup_file_path = create_win_asset()
        upload_asset_to_release(setup_file_path, setup_file_path.name)
    else:
        print("Unsupported platform or architecture. No action taken.")


if __name__ == "__main__":
    extend_release()
