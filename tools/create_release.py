import os
from pathlib import Path

import requests

from tools.create_app import create_bundle
from tools.create_mac_dmg import create_dmg

ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()

GITHUB_API_URL = "https://api.github.com"
REPO_OWNER = "davbeek"  # Replace with the GitHub username or organization
REPO_NAME = "gitinspectorgui"  # Replace with the repository name
GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN"
)  # Ensure the GitHub token is set in the environment


def create_github_release():
    if not GITHUB_TOKEN:
        raise EnvironmentError("GITHUB_TOKEN environment variable is not set.")

    # Determine if this is a prerelease based on VERSION
    is_prerelease = "rc" in VERSION

    # Create a new release
    url = f"{GITHUB_API_URL}/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "tag_name": f"v{VERSION}",
        "name": f"v{VERSION}",
        "body": f"Release version {VERSION}",
        "draft": False,
        "prerelease": is_prerelease,  # Set prerelease flag dynamically
    }

    print(f"Creating GitHub release for version {VERSION} ({is_prerelease=})...")
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    release = response.json()
    print(f"Release created: {release['html_url']}")

    return release["upload_url"].replace("{?name,label}", "")


def create_asset() -> Path:
    create_bundle("gui")
    return create_dmg()


def upload_asset(upload_url):
    dmg_path = create_asset()
    dmg_name = dmg_path.name
    if not dmg_path.exists():
        raise FileNotFoundError(f"DMG file not found: {dmg_path}")

    print(f"Uploading {dmg_name} to GitHub release...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/octet-stream",
    }
    params = {"name": dmg_name}
    with open(dmg_path, "rb") as f:
        response = requests.post(upload_url, headers=headers, params=params, data=f)
    response.raise_for_status()
    print(f"Asset uploaded: {response.json()['browser_download_url']}")


if __name__ == "__main__":
    upload_url = create_github_release()
    upload_asset(upload_url)
