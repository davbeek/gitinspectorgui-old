import argparse
import platform
import re
import subprocess
from pathlib import Path

from git import Repo

DEBUG_UV = False  # If True, use the -v flag for uv sync.


class GIBump:
    def __init__(self):
        self.root_dpath = Path(__file__).resolve().parent.parent
        self.git_repo: Repo = Repo(self.root_dpath)
        self.gigui_path = self.root_dpath / "src" / "gigui"
        self.version_path = self.gigui_path / "version.txt"
        self.version = self.version_path.read_text().strip()
        self.is_win = platform.system() == "Windows"
        self.is_mac = platform.system() == "Darwin"
        self.is_arm = "arm" in platform.machine().lower()
        self.toml_path = self.root_dpath / "pyproject.toml"
        self.inno_path = self.root_dpath / "tools" / "static" / "win-setup.iss"

    def get_version(self) -> str:
        """Retrieve the current version from the version file."""
        with self.version_path.open("r", encoding="utf-8") as file:
            return file.read().strip()

    def bump_toml_version(self):
        """Update the version in the pyproject.toml file."""
        with self.toml_path.open("r", encoding="utf-8") as file:
            content = file.read()
        content = re.sub(
            r'^version\s*=\s*".*"',
            f'version = "{self.version}"',
            content,
            flags=re.MULTILINE,
        )
        with self.toml_path.open("w", encoding="utf-8") as file:
            file.write(content)

    def bump_inno_version(self):
        """Update the version in the Inno Setup script."""
        with self.inno_path.open("r", encoding="utf-8") as file:
            content = file.read()
        content = re.sub(
            r'^#define MyAppVersion\s*".*"',
            f'#define MyAppVersion "{self.version}"',
            content,
            flags=re.MULTILINE,
        )
        with self.inno_path.open("w", encoding="utf-8") as file:
            file.write(content)

    def uv_sync(self):
        """Sync and update the version in the uv lock file."""
        subprocess.run(
            ["uv", "sync"] + (["-v"] if DEBUG_UV else []),
            check=True,
        )

    def bump_version(self):
        """Update the version in all relevant files."""
        print(f"Updating version to {self.version}")
        print("Bumping version in pyproject.toml")
        self.bump_toml_version()
        print("Bumping version in app-setup.iss")
        self.bump_inno_version()
        print("Syncing and bumping version in uv lock file")
        self.uv_sync()

    def commit_version(self):
        """Commit the version update to the repository."""
        version_paths: list[Path] = [
            self.toml_path,
            self.inno_path,
            self.version_path,
            self.root_dpath / "uv.lock",
        ]
        version_rel_paths_str = {
            str(path.relative_to(self.root_dpath)) for path in version_paths
        }

        # Gather all changed files (both staged and unstaged)
        unstaged_files: set[str] = {
            item.a_path
            for item in self.git_repo.index.diff(None)
            if item.a_path is not None
        }
        staged_files: set[str] = {
            item.a_path
            for item in self.git_repo.index.diff("HEAD")
            if item.a_path is not None
        }
        changed_files: set[str] = unstaged_files.union(staged_files)

        # Check if all changed files are in version_paths
        if changed_files.issubset(version_rel_paths_str):
            print(f"Committing version {self.version}")
            for fstr in version_rel_paths_str:
                self.git_repo.git.add(fstr)
            self.git_repo.git.commit("-m", f"Version {self.version}")
        else:
            # Print files not in version_paths
            unexpected_files = changed_files - version_rel_paths_str
            print("The following changed files should be committed first:")
            for file in unexpected_files:
                print(f" - {file}")
            raise ValueError("Unexpected files in the commit")

    def add_tag(self):
        """Add a Git tag for the new version."""
        if self.version in self.git_repo.tags:
            print(f"Deleting old tag {self.version}")
            self.git_repo.delete_tag()
        print(f"Adding tag {self.version}")
        self.git_repo.create_tag(self.version)

    def push_version(self):
        """Push the version and tag to the remote repository."""
        self.git_repo.git.push("origin", "main")  # Pushes the main branch
        self.git_repo.git.push("origin", self.version)  # Pushes the version tag

    def confirm_action(self, message: str) -> bool:
        """Prompt the user for confirmation."""
        response = input(f"{message} (y/N): ").strip().lower()
        return response == "y"

    def main(self, action: str):
        """Perform the specified action: bump version, commit, tag, or all."""
        match action:
            case "all":
                if not self.confirm_action(
                    "Do you want to bump the version, commit, add tag, and push?"
                ):
                    return
                self.bump_version()
                self.commit_version()
                self.add_tag()
                self.push_version()

            case "version":
                self.bump_version()

            case "commit":
                self.commit_version()

            case "tag":
                self.add_tag()

            case "push":
                if self.confirm_action("Do you want to push the version and tag?"):
                    self.push_version()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["version", "commit", "tag", "push", "all"],
        nargs="?",  # Makes the argument optional
        help="Specify whether to bump version, commit, add tag, push, or all.",
    )
    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        exit(0)

    gi_bump = GIBump()
    try:
        gi_bump.main(args.action)
    except ValueError:
        print("Exiting")
        exit(1)
