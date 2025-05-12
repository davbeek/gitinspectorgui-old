# Add the parent directory to the Python module search path
import sys
from pathlib import Path

# Add the parent directory to the Python module search path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.bump import GIBump

# Add the parent directory to the Python module search path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.github import GitHub, GIToolError

if __name__ == "__main__":
    github = GitHub()
    gi_bump = GIBump()

    try:
        github.check_release_absence()
        gi_bump.main("all")
        github.create_app("gui")
        github.create_asset()
        github.create_release()
        github.upload_asset()
    except GIToolError:
        print("Exiting")
        exit(1)
