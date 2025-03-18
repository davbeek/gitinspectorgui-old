import platform
import re
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()


def generate_intel_iss():
    """Generate win-setup.iss from win-setup-arm.iss by removing ARM-specific lines."""
    arm_iss_file = SCRIPT_DIR / "static" / "win-setup-arm.iss"
    intel_iss_file = SCRIPT_DIR / "static" / "win-setup.iss"

    print("Generating win-setup.iss from win-setup-arm.iss")
    with arm_iss_file.open("r") as arm_file:
        lines = arm_file.readlines()

    with intel_iss_file.open("w") as intel_file:
        for line in lines:
            # Skip lines containing "arm64" (case-insensitive) or comments
            if re.search(r"arm64", line, re.IGNORECASE):
                continue
            intel_file.write(line)

    print(f"Generated {intel_iss_file}")
    return intel_iss_file


def create_setup_file():
    arch = platform.machine().lower()
    if "arm" in arch:
        iss_file = SCRIPT_DIR / "static" / "win-setup-arm.iss"
        print("Detected ARM architecture. Using win-setup-arm.iss")
    else:
        print("Detected Intel architecture. Regenerating win-setup.iss")
        iss_file = generate_intel_iss()

    output_dir = ROOT_DIR / "app" / "pyinstall-setup"
    output_file = output_dir / f"windows-gitinspectorgui-setup-{VERSION}.exe"

    print("Generating gitinspector setup file")
    subprocess.run(
        [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            f"/O{output_dir}",
            f"/F{output_file.stem}",
            str(iss_file),
        ],
        check=True,
    )
    print(f"Setup file generated: {output_file}")


if __name__ == "__main__":
    create_setup_file()
