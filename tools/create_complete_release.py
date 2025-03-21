# Add the parent directory to the Python module search path
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.github import GitHub, GIToolError

if __name__ == "__main__":
    github = GitHub()

    try:
        github.check_release_absence()
        github.create_asset()
        github.create_release()
        github.upload_asset()
    except GIToolError:
        print("Exiting")
        exit(1)
