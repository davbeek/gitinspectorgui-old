import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import dmgbuild
import requests

# Add the parent directory to the Python module search path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.bump import GIBump


class GITool(GIBump):
    def __init__(self):
        super().__init__()

        self.github_api_url = "https://api.github.com"
        self.repo_owner = "davbeek"
        self.repo_name = "gitinspectorgui"
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.app_name = "GitinspectorGUI.app"
        self.app_path = self.root_dpath / "app" / self.app_name
        self.processor_type = "AppleSilicon" if self.is_arm else "Intel"

        # Set by subclasses to path of asset to upload to GitHub: either dmg file for
        # macOS or setup file for Windows.
        self.asset_path: Path

    def create_app(self, app_type: str):
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
            activate_script = self.root_dpath / ".venv" / "Scripts" / "Activate.ps1"
            if not activate_script.exists():
                raise FileNotFoundError(
                    f"Virtual environment activation script not found: {activate_script}"
                )
            command = (
                f"& {activate_script}; "
                f"pyinstaller --distpath={self.root_dpath / 'app'} {self.root_dpath / spec_file}"
            )
            result = subprocess.run(
                ["powershell", "-Command", command],
                cwd=self.root_dpath,
            )
        else:  # macOS or Linux
            activate_script = self.root_dpath / ".venv" / "bin" / "activate"
            if not activate_script.exists():
                raise FileNotFoundError(
                    f"Virtual environment activation script not found: {activate_script}"
                )
            result = subprocess.run(
                [f"source {activate_script} && pyinstaller --distpath=app {spec_file}"],
                cwd=self.root_dpath,
                shell=True,
                executable="/bin/bash",  # Ensure compatibility with 'source'
            )
        if result.returncode == 0:
            print()
            print(f"Done, created {app_name} in folder {destination}")


class GIMacTool(GITool):
    def __init__(self):
        super().__init__()
        self.dmg_name_version = (
            f"GitinspectorGUI-{self.version}-{self.processor_type}.dmg"
        )
        self.dmg_path = self.root_dpath / "app" / self.dmg_name_version

    def create_dmg(self):
        # Delete the existing .dmg file if it exists
        if self.dmg_path.exists():
            print(f"Deleting existing .dmg file: {self.dmg_path}")
            self.dmg_path.unlink()

        dmgbuild.build_dmg(
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
        self.asset_path = self.dmg_path


class GIWinTool(GITool):
    def __init__(self):
        super().__init__()

        self.iss_dpath = self.root_dpath / "tools" / "static"
        self.win_setup_dpath = self.root_dpath / "app" / "pyinstall-setup"
        self.arm_iss_path = self.iss_dpath / "static" / "win-setup-arm.iss"
        self.intel_iss_path = self.iss_dpath / "static" / "win-setup.iss"
        self.win_setup_path = (
            self.win_setup_dpath / f"windows-gitinspectorgui-setup-{self.version}.exe"
        )

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
        self.asset_path = self.win_setup_path


class GitHub(GIMacTool, GIWinTool):
    def __init__(self):
        super().__init__()
        self.release_name = f"GitinspectorGUI-{self.version}"
        self.upload_url = None

    def create_release(self):
        if self.is_win:
            # Release must be created on macOS.
            raise EnvironmentError("Creating releases on Windows is not supported.")

        """Create a new GitHub release and store the upload URL."""
        if not self.github_token:
            raise EnvironmentError("GITHUB_TOKEN environment variable is not set.")

        # Determine if this is a prerelease based on VERSION
        is_prerelease = "rc" in self.version

        # Create a new release
        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases"
        headers = {"Authorization": f"token {self.github_token}"}
        data = {
            "tag_name": f"v{self.version}",
            "name": f"v{self.version}",
            "body": f"Release version {self.version}",
            "draft": False,
            "prerelease": is_prerelease,
        }

        print(
            f"Creating GitHub release for version {self.version} ({is_prerelease=})..."
        )
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        release = response.json()
        self.upload_url = release["upload_url"].replace("{?name,label}", "")
        print(f"Release created: {release['html_url']}")

    def create_asset(self):
        if self.is_mac:
            self.create_dmg()
        elif self.is_win:
            self.create_win_setup_exe()

    def upload_asset(self):
        """Upload the stored asset to the GitHub release."""
        if not self.asset_path or not self.asset_path.exists():
            raise FileNotFoundError(f"Asset file not found: {self.asset_path}")

        print(f"Uploading {self.asset_path.name} to GitHub release...")
        headers = {
            "Authorization": f"token {self.github_token}",
            "Content-Type": "application/octet-stream",
        }
        params = {"name": self.asset_path.name}
        with self.asset_path.open("rb") as f:
            response = requests.post(
                self.upload_url,  # type: ignore
                headers=headers,
                params=params,
                data=f,
            )
        response.raise_for_status()
        print(f"Asset uploaded: {response.json()['browser_download_url']}")

    def extend_release(self):
        """Extend the release by creating and uploading platform-specific assets."""

        if self.is_mac:
            print("Detected macOS on Intel hardware. Creating and uploading DMG...")
            self.create_app("gui")
            self.create_dmg()
        elif self.is_win:
            print("Detected Windows. Creating and uploading setup file...")
            self.create_app("gui")
            self.create_win_setup_exe()
        else:
            print("Unsupported platform or architecture. No action taken.")
            return

        self.upload_asset()

    def release_exists(self) -> bool:
        """Check if a GitHub release for the current version already exists."""
        if not self.github_token:
            raise EnvironmentError("GITHUB_TOKEN environment variable is not set.")

        url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases/tags/v{self.version}"
        headers = {"Authorization": f"token {self.github_token}"}

        print(f"Checking if release for version {self.version} exists...")
        response = requests.get(url, headers=headers)

        if response.status_code == 404:
            print(f"No release found for version {self.version}.")
            return False

        response.raise_for_status()
        print(f"Release for version {self.version} already exists.")
        return True
