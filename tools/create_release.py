# Add the parent directory to the Python module search path
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.github import GitHub

if __name__ == "__main__":
    github = GitHub()

    if github.release_exists():
        print(f"Release for version {github.version} already exists. Exiting.")
        exit(0)

    github.create_app("gui")
    github.create_asset()
    github.create_release()
    github.upload_asset()
