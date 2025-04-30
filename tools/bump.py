import argparse
import platform
import re
import subprocess
from pathlib import Path

from git import Repo

DEBUG_UV = False  # If True, use the -v flag for uv sync.


class GIToolError(Exception):
    """Custom exception for errors in the GIBump class, GITool class and subclasses."""

    pass


class GIBump:
    def __init__(self):
        self.root_dpath = Path(__file__).resolve().parent.parent  # repo root dir path
        self.git_repo: Repo = Repo(self.root_dpath)
        self.gigui_path = self.root_dpath / "src" / "gigui"
        self.version_path = self.gigui_path / "version.txt"
        self.toml_path = self.root_dpath / "pyproject.toml"
        self.inno_path = self.root_dpath / "tools" / "static" / "win-setup.iss"
        self.inno_arm_path = self.root_dpath / "tools" / "static" / "win-setup-arm.iss"
        self.uv_lock_path = self.root_dpath / "uv.lock"

        version_paths: list[Path] = [
            self.toml_path,
            self.inno_path,
            self.inno_arm_path,
            self.version_path,
            self.uv_lock_path,
        ]
        self.relative_version_paths: set[Path] = {
            path.relative_to(self.root_dpath) for path in version_paths
        }

        self.version = self.version_path.read_text().strip()
        self.is_win = platform.system() == "Windows"
        self.is_mac = platform.system() == "Darwin"
        self.is_arm = "arm" in platform.machine().lower()
        self.version_commit_message = f"Version {self.version}"

    def main(self, action: str):
        """Perform the specified action: bump version, commit, tag, or all."""
        match action:
            case "all":
                self.bump_version()
                self.commit_version()
                self.add_tag()
                self.push()

            case "version":
                self.bump_version()

            case "commit":
                self.commit_version()

            case "tag":
                self.add_tag()

            case "push":
                self.push()

    def bump_version(self):
        """Update the version in all relevant files."""

        self.uv_sync()  # ensure you are up to date with e.g. updates on another machine
        self.check_version_commit_absence()
        self.check_no_remaining_changed_files()

        print(f"Updating version to {self.version}")
        print("Bumping version in pyproject.toml")
        self.bump_toml_version()
        print("Bumping version in app-setup.iss")
        self.bump_inno_versions()
        print("Syncing and bumping version in uv lock file")
        self.uv_sync()

    def commit_version(self):
        """Commit the version update to the repository."""
        self.check_version_commit_absence()
        self.check_no_remaining_changed_files()

        print(f"Committing version {self.version}")
        for path in self.relative_version_paths:
            self.git_repo.git.add(str(path))
        self.git_repo.git.commit("-m", self.version_commit_message)

    def add_tag(self):
        """Add a Git tag for the new version."""
        self.check_at_bump_commit()

        # Check tag absence
        if self.version in self.git_repo.tags:
            print(f"Tag {self.version} already exists.")
            raise GIToolError()

        print(f"Adding tag {self.version}")
        self.git_repo.create_tag(self.version)

    def push(self):
        """Push the version and tag to the remote repository."""
        self.push_version()
        self.push_tag()

    def uv_sync(self):
        """Sync and update the version in the uv lock file."""
        subprocess.run(
            ["uv", "sync"] + (["-v"] if DEBUG_UV else []),
            check=True,
        )

    def check_version_commit_absence(self) -> None:
        """Check if the version commit already exists in the branch history."""
        for commit in self.git_repo.iter_commits():
            if commit.message.strip() == self.version_commit_message:
                print(f"{self.version_commit_message} commit already exists.")
                raise GIToolError()

    def check_no_remaining_changed_files(self) -> None:
        """Check that there are no changed files other than those due to version
        bumps."""
        # Gather all changed files (both staged and unstaged)
        unstaged_files: set[Path] = {
            Path(item.a_path)
            for item in self.git_repo.index.diff(None)
            if item.a_path is not None
        }
        staged_files: set[Path] = {
            Path(item.a_path)
            for item in self.git_repo.index.diff("HEAD")
            if item.a_path is not None
        }
        changed_files: set[Path] = unstaged_files.union(staged_files)
        remaining_changed_files: set[Path] = changed_files - {
            path for path in self.relative_version_paths
        }
        if remaining_changed_files:
            print("The following changed files should be committed first:")
            for file in remaining_changed_files:
                print(f" - {file}")
            raise GIToolError()

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

    def bump_inno_versions(self):
        """Update the version in the Intel and Arm Inno Setup scripts."""
        self.bump_inno_version_for(self.inno_path)
        self.bump_inno_version_for(self.inno_arm_path)

    def bump_inno_version_for(self, inno_path: Path):
        """Update the version in the Inno Setup script."""
        with inno_path.open("r", encoding="utf-8") as file:
            content = file.read()
        content = re.sub(
            r'^#define MyAppVersion\s*".*"',
            f'#define MyAppVersion "{self.version}"',
            content,
            flags=re.MULTILINE,
        )
        with inno_path.open("w", encoding="utf-8") as file:
            file.write(content)

    def check_at_bump_commit(self) -> None:
        """Check if the HEAD commit has the expected commit message."""
        head_commit_message = self.git_repo.head.commit.message.strip()
        if head_commit_message != self.version_commit_message:
            print(f"HEAD commit is not at Version {self.version}.")
            raise GIToolError()

    def push_version(self):
        """Push the version to the remote repository."""
        self.check_at_bump_commit()

        print("Pushing version")
        self.git_repo.git.push("origin", "main")  # Pushes the main branch

    def push_tag(self):
        """Push the tag to the remote repository."""
        self.check_at_bump_commit()

        # Check that the tag exists
        if self.version not in self.git_repo.tags:
            print(f"Tag {self.version} not found.")
            raise GIToolError()

        print("Pushing tag")
        self.git_repo.git.push("origin", self.version)  # Pushes the version tag

    def get_version(self) -> str:
        """Retrieve the current version from the version file."""
        with self.version_path.open("r", encoding="utf-8") as file:
            return file.read().strip()


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
    except GIToolError:
        print("Exiting")
        exit(1)
    finally:
        # Explicitly clean up the Repo object to avoid subprocess issues
        del gi_bump.git_repo
