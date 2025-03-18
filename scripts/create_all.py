import platform
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import the relevant modules
from create_app import create_bundle

from scripts.create_mac_dmg import create_dmg
from scripts.create_win_setup import create_setup_file

SCRIPT_DIR = Path(__file__).resolve().parent


def run_all():
    try:
        # Run the create_app function with "gui" as an argument
        create_bundle("gui")
        print()

        if platform.system() == "Windows":
            # Call the function to generate the Windows setup file
            create_setup_file()
        elif platform.system() == "Darwin":  # macOS
            # Call the function to create the macOS DMG
            create_dmg()
        else:
            print("Unsupported platform. Only Windows and macOS are supported.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    run_all()
