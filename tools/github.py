import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Add the parent directory to the Python module search path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.bump import GIBump, GIToolError

if platform.system() == "Darwin":
    import dmgbuild  # gives error when imported on Windows


class GITool(GIBump):
    def __init__(self):
        super().__init__()

        self.github_api_url = "https://api.github.com"
        self.repo_owner = "davbeek"
        self.repo_name = "gitinspectorgui"
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.app_name = "GitinspectorGUI.app"
        self.app_path = self.root_dpath / "app" / self.app_name

        if self.is_win:
            self.processor_type = "Arm" if self.is_arm else "Intel"
        else:
            self.processor_type = "AppleSilicon" if self.is_arm else "Intel"

    def create_app(self, app_type: str):
        self.uv_sync
        spec_file = (
            "app-gui-bundle.spec" if app_type == "gui" else "app-cli-bundle.spec"
        )
        if app_type == "gui":
            app_name = "gitinspectorgui.exe" if self.is_win else "GitinspectorGUI.app"
        else:  # cli
            app_name = (
                "gitinspectorcli.exe" if self.is_win else "gitinspectorcli executable"
            )
        destination = (
            self.root_dpath / "app"
            if app_type == "gui"
            else self.root_dpath / "app" / "bundle"
        )
        platform_str = "Windows" if self.is_win else "macOS"

        print(f"Creating {app_type.upper()} app for {platform_str}")
        print("Deleting old app directories")
        shutil.rmtree(self.root_dpath / "app", ignore_errors=True)
        shutil.rmtree(self.root_dpath / "build", ignore_errors=True)
        print("Activating virtual environment and running PyInstaller")
        print()

        if self.is_win:
            command = f"pyinstaller --distpath={self.root_dpath / 'app'} {self.root_dpath / spec_file}"
            result = subprocess.run(
                ["powershell", "-Command", command],
                cwd=self.root_dpath,
            )
        else:  # macOS or Linux
            result = subprocess.run(
                [f"pyinstaller --distpath=app {spec_file}"],
                cwd=self.root_dpath,
                shell=True,
                executable="/bin/bash",  # Ensure compatibility with 'source'
            )
        if result.returncode == 0:
            print()
            if self.is_win:
                print(f"Done, created {app_name} in folder {destination / 'bundle'}")
            else:
                print(f"Done, created {app_name} in folder {destination}")


class GIMacTool(GITool):
    def __init__(self):
        super().__init__()
        dmg_name_version = f"GitinspectorGUI-{self.version}-{self.processor_type}.dmg"
        self.dmg_path = self.root_dpath / "app" / dmg_name_version

    def create_dmg(self):
        # Delete the existing .dmg file if it exists
        if self.dmg_path.exists():
            print(f"Deleting existing .dmg file: {self.dmg_path}")
            self.dmg_path.unlink()

        dmgbuild.build_dmg(  # type: ignore
            filename=str(self.dmg_path),
            volume_name="GitinspectorGUI",
            settings={
                "files": [str(self.app_path)],
                "symlinks": {"Applications": "/Applications"},
                "icon_locations": {
                    self.app_name: (130, 100),
                    "Applications": (510, 100),
                },
                "window": {
                    "size": (480, 300),
                    "position": (100, 100),
                },
                "background": "builtin-arrow",
                "icon_size": 128,
            },
        )
        print(f"Created .dmg installer at: {self.dmg_path}")


class GIWinTool(GITool):
    def __init__(self):
        super().__init__()

        self.iss_dpath = self.root_dpath / "tools" / "static"
        self.win_setup_dpath = self.root_dpath / "app" / "pyinstall-setup"
        self.arm_iss_path = self.iss_dpath / "win-setup-arm.iss"
        self.intel_iss_path = self.iss_dpath / "win-setup.iss"
        setup_name_version = (
            f"win-gitinspectorgui-setup-{self.version}-{self.processor_type}.exe"
        )
        self.win_setup_path = self.win_setup_dpath / setup_name_version

    def create_win_setup_exe(self):
        """Create a Windows setup file using Inno Setup."""
        if self.is_arm:
            iss_file = self.arm_iss_path
            print("Detected ARM architecture. Using win-setup-arm.iss")
        else:
            print("Detected Intel architecture. Regenerating win-setup.iss")
            self.generate_win_setup_iss()
            iss_file = self.intel_iss_path

        print("Generating gitinspector setup file")
        subprocess.run(
            [
                r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                f"/O{self.win_setup_dpath}",
                f"/F{self.win_setup_path.stem}",
                str(iss_file),
            ],
            check=True,
        )
        print(f"Setup file generated: {self.win_setup_path}")

    def generate_win_setup_iss(self):
        """Generate win-setup.iss from win-setup-arm.iss by removing ARM-specific lines."""
        print("Generating win-setup.iss from win-setup-arm.iss")
        with self.arm_iss_path.open("r") as arm_file:
            lines = arm_file.readlines()

        with self.intel_iss_path.open("w") as intel_file:
            for line in lines:
                # Skip lines containing "arm64" (case-insensitive) or comments
                if re.search(r"arm64", line, re.IGNORECASE):
                    continue
                intel_file.write(line)

        print(f"Generated {self.intel_iss_path}")


class GitHub(GIMacTool, GIWinTool):
    def __init__(self):
        super().__init__()
        self.release_name = f"GitinspectorGUI-{self.version}"

    def check_release_absence(self):
        """Check if a GitHub release for the current version already exists."""
        if not self.github_token:
            print("GITHUB_TOKEN environment variable is not set.")
            raise GIToolError()

        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases/tags/v{self.version}"
        headers = {"Authorization": f"token {self.github_token}"}

        response = requests.get(url, headers=headers)
        if response.status_code != 404:
            response.raise_for_status()
            print(f"Release for version {self.version} already exists.")
            raise GIToolError()

    def create_asset(self):
        if self.is_mac:
            self.create_dmg()
        elif self.is_win:
            self.create_win_setup_exe()

    def create_release(self):
        """Create a new GitHub release and store the upload URL."""
        if not self.github_token:
            print("GITHUB_TOKEN environment variable is not set.")
            raise GIToolError()

        self.check_release_absence()

        # Determine if this is a prerelease based on VERSION
        is_prerelease = "rc" in self.version

        # Create a new release
        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases"
        headers = {"Authorization": f"token {self.github_token}"}
        data = {
            "tag_name": f"{self.version}",
            "name": f"{self.version}",
            "body": f"Release version {self.version}",
            "draft": False,
            "prerelease": is_prerelease,
        }

        print(
            f"Creating GitHub {'pre-' if is_prerelease else ''}release for version {self.version}"
        )
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        release = response.json()
        print(f"Release created: {release['html_url']}")

    def upload_asset(self):
        """Upload the stored asset to the GitHub release."""
        asset_path: Path = self.dmg_path if self.is_mac else self.win_setup_path
        if not asset_path or not asset_path.exists():
            print(f"Asset file not found: {asset_path}")
            raise GIToolError()

        upload_url = self.get_upload_url()
        release_id = self.get_release_id()

        # Check and delete existing asset if it exists
        self.delete_existing_asset(release_id, asset_path.name)

        print(f"Uploading {asset_path.name} to GitHub release")

        # Configure retries for the session
        session = requests.Session()
        retries = Retry(
            total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504]
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))

        headers = {
            "Authorization": f"token {self.github_token}",
            "Content-Type": "application/octet-stream",
        }
        params = {"name": asset_path.name}

        try:
            with asset_path.open("rb") as f:
                response = session.post(
                    upload_url,
                    headers=headers,
                    params=params,
                    data=f,
                    verify=True,  # Set to False if SSL issues persist
                )
            response.raise_for_status()
            print(f"Asset uploaded: {response.json()['browser_download_url']}")
        except requests.exceptions.SSLError as e:
            print("SSL error occurred. Please check your SSL configuration.")
            raise GIToolError() from e
        except requests.exceptions.RequestException as e:
            print("Failed to upload asset.")
            raise GIToolError() from e

    def delete_existing_asset(self, release_id, asset_name):
        """Delete an existing asset from the GitHub release."""
        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases/{release_id}/assets"
        headers = {"Authorization": f"token {self.github_token}"}

        print(f"Checking for existing asset: {asset_name}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        assets = response.json()

        for asset in assets:
            if asset["name"] == asset_name:
                delete_url = asset["url"]
                print(f"Deleting existing asset: {asset_name}")
                delete_response = requests.delete(delete_url, headers=headers)
                delete_response.raise_for_status()
                print(f"Deleted existing asset: {asset_name}")
                break

    def get_release_id(self):
        """Get the release ID for the current version."""
        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases/tags/{self.version}"
        headers = {"Authorization": f"token {self.github_token}"}

        print(f"Fetching release ID for version {self.version}")
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            print(f"No release found for version {self.version}.")
            raise GIToolError()
        response.raise_for_status()
        release = response.json()
        return release["id"]

    def get_upload_url(self):
        """Get the upload URL for the GitHub release."""
        if not self.github_token:
            print("GITHUB_TOKEN environment variable is not set.")
            raise GIToolError()

        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases/tags/{self.version}"
        headers = {"Authorization": f"token {self.github_token}"}

        print(f"Fetching upload URL for release version {self.version}")
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            print(f"No release found for version {self.version}.")
            raise GIToolError()
        response.raise_for_status()
        release = response.json()
        return release["upload_url"].replace("{?name,label}", "")
