import platform
import re
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
VERSION = (ROOT_DIR / "src" / "gigui" / "version.txt").read_text().strip()

ARM_ISS_FILE = SCRIPT_DIR / "static" / "win-setup-arm.iss"
INTEL_ISS_FILE = SCRIPT_DIR / "static" / "win-setup.iss"
OUTPUT_DIR = ROOT_DIR / "app" / "pyinstall-setup"
OUTPUT_FILE = OUTPUT_DIR / f"windows-gitinspectorgui-setup-{VERSION}.exe"


def generate_intel_iss():
    """Generate win-setup.iss from win-setup-arm.iss by removing ARM-specific lines."""
    print("Generating win-setup.iss from win-setup-arm.iss")
    with ARM_ISS_FILE.open("r") as arm_file:
        lines = arm_file.readlines()

    with INTEL_ISS_FILE.open("w") as intel_file:
        for line in lines:
            # Skip lines containing "arm64" (case-insensitive) or comments
            if re.search(r"arm64", line, re.IGNORECASE):
                continue
            intel_file.write(line)

    print(f"Generated {INTEL_ISS_FILE}")


def create_setup_file() -> Path:
    arch = platform.machine().lower()
    if "arm" in arch:
        iss_file = ARM_ISS_FILE
        print("Detected ARM architecture. Using win-setup-arm.iss")
    else:
        print("Detected Intel architecture. Regenerating win-setup.iss")
        generate_intel_iss()
        iss_file = INTEL_ISS_FILE

    print("Generating gitinspector setup file")
    subprocess.run(
        [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            f"/O{OUTPUT_DIR}",
            f"/F{OUTPUT_FILE.stem}",
            str(iss_file),
        ],
        check=True,
    )
    print(f"Setup file generated: {OUTPUT_FILE}")
    return OUTPUT_FILE


if __name__ == "__main__":
    create_setup_file()
