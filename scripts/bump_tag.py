from pathlib import Path

from bump_version import get_version
from git import Repo


def add_tag(version):
    repo_dir = Path(__file__).resolve().parent.parent
    repo = Repo(repo_dir)

    # Check if the tag exists
    if version in repo.tags:
        # Delete the old tag locally
        print(f"Delete old tag {version}")
        repo.delete_tag(version)
        # Delete the old tag remotely
        repo.git.push("origin", f":refs/tags/{version}")

    print(f"Add new tag {version}")
    repo.create_tag(version)
    repo.git.push("origin", version)


if __name__ == "__main__":
    version = get_version()
    add_tag(version)
