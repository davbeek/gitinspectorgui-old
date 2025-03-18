# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "gitpython",
# ]
# ///
import argparse
import re
import subprocess
from pathlib import Path

from git import Repo


def get_version() -> str:
    mydir = Path(__file__).resolve().parent
    version_file = mydir.parent / "src" / "gigui" / "version.txt"
    with open(version_file, "r", encoding="utf-8") as file:
        version = file.read().strip()
    return version


def bump_toml_version(version):
    script_dir = Path(__file__).resolve().parent
    toml_path = script_dir.parent / "pyproject.toml"

    with open(toml_path, "r", encoding="utf-8") as file:
        content = file.read()

    content = re.sub(
        r'^version\s*=\s*".*"',
        f'version = "{version}"',
        content,
        flags=re.MULTILINE,
    )

    with open(toml_path, "w", encoding="utf-8") as file:
        file.write(content)


def bump_inno_version(version):
    script_dir = Path(__file__).resolve().parent
    inno_path = script_dir / "app-setup.iss"

    with open(inno_path, "r", encoding="utf-8") as file:
        content = file.read()

    content = re.sub(
        r'^#define MyAppVersion\s*".*"',
        f'#define MyAppVersion "{version}"',
        content,
        flags=re.MULTILINE,
    )

    with open(inno_path, "w", encoding="utf-8") as file:
        file.write(content)


# This will also update the version in the uv lock file.
def uv_sync():
    subprocess.run(["uv", "sync"], check=True)


def bump_version(version):
    print(f"Update version to {version}")
    print("Bump version in pyproject.toml")
    bump_toml_version(version)
    print("Bump version in scripts/app-setup.iss")
    bump_inno_version(version)
    print("Sync and bump version in uv lock file")
    uv_sync()


def commit_version(version):
    repo_dir = Path(__file__).resolve().parent.parent
    git_repo = Repo(repo_dir)
    print(f"Commit version {version}")
    git_repo.git.add("pyproject.toml")
    git_repo.git.add("app-setup.iss")
    git_repo.git.add("src/gigui/version.txt")
    git_repo.git.commit("-m", f"Version {version}")
    git_repo.git.push("origin", "main")


def add_tag(version):
    repo_dir = Path(__file__).resolve().parent.parent
    repo = Repo(repo_dir)

    if version in repo.tags:
        print(f"Delete old tag {version}")
        repo.delete_tag(version)
        # Delete the old tag remotely
        repo.git.push("origin", f":refs/tags/{version}")

    print(f"Add tag {version}")
    repo.create_tag(version)
    repo.git.push("origin", version)


def confirm_action(message: str) -> bool:
    response = input(f"{message} (y/N): ").strip().lower()
    return response == "y"


def main():
    parser = argparse.ArgumentParser(description="Bump version, commit, tag, or all.")
    parser.add_argument(
        "action",
        choices=["version", "commit", "tag", "all"],
        help="Specify whether to bump version, tag, or all.",
    )
    args = parser.parse_args()

    version = get_version()

    if args.action == "all":
        if not confirm_action(
            "Are you sure you want to bump version, commit, and tag?"
        ):
            return
        bump_version(version)
        print(f"Commit version {version}")
        commit_version(version)
        print(f"Add tag {version}")
        add_tag(version)
        return

    if args.action == "version":
        bump_version(version)

    if args.action == "commit":
        if confirm_action(f"Are you sure you want to commit to version {version}?"):
            commit_version(version)

    if args.action == "tag":
        if confirm_action(f"Are you sure you want to tag version {version}?"):
            add_tag(version)


if __name__ == "__main__":
    main()
