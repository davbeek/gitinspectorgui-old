import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def create_bundle(bundle_type: str):
    is_windows: bool = platform.system() == "Windows"

    spec_file = "app-gui-bundle.spec" if bundle_type == "gui" else "app-cli-bundle.spec"
    if bundle_type == "gui":
        app_name = "gitinspectorgui.exe" if is_windows else "GitinspectorGUI.app"
    else:  # cli
        app_name = "gitinspectorcli.exe" if is_windows else "gitinspectorcli executable"
    destination = (
        ROOT_DIR / "app" if bundle_type == "gui" else ROOT_DIR / "app" / "bundle"
    )
    platform_str = "Windows" if is_windows else "macOS"

    print(f"Creating {bundle_type.upper()} app for {platform_str}")
    print("Deleting old app directories")
    shutil.rmtree(ROOT_DIR / "app", ignore_errors=True)
    shutil.rmtree(ROOT_DIR / "build", ignore_errors=True)
    print("Activating virtual environment and running PyInstaller")
    print()

    if is_windows:
        activate_script = ROOT_DIR / ".venv" / "Scripts" / "Activate.ps1"
        if not activate_script.exists():
            raise FileNotFoundError(
                f"Virtual environment activation script not found: {activate_script}"
            )
        command = (
            f"& {activate_script}; "
            f"pyinstaller --distpath={ROOT_DIR / 'app'} {ROOT_DIR / spec_file}"
        )
        result = subprocess.run(
            ["powershell", "-Command", command],
            cwd=ROOT_DIR,
        )
    else:  # macOS or Linux
        activate_script = ROOT_DIR / ".venv" / "bin" / "activate"
        if not activate_script.exists():
            raise FileNotFoundError(
                f"Virtual environment activation script not found: {activate_script}"
            )
        result = subprocess.run(
            [f"source {activate_script} && pyinstaller --distpath=app {spec_file}"],
            cwd=ROOT_DIR,
            shell=True,
            executable="/bin/bash",  # Ensure compatibility with 'source'
        )

    if result.returncode == 0:
        print()
        print(f"Done, created {app_name} in folder {destination}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1].lower() not in {"gui", "cli"}:
        print("Usage: python app-create.py [gui|cli]")
        sys.exit(1)

    bundle_type = sys.argv[1].lower()
    create_bundle(bundle_type)
