import os
from cProfile import Profile
from logging import getLogger
from pathlib import Path

from gigui._logging import log, set_logging_level_from_verbosity
from gigui.args_settings import Args
from gigui.constants import (
    DEFAULT_FILE_BASE,
    DEFAULT_VERBOSITY,
    MAX_BROWSER_TABS,
    NONE,
)
from gigui.data import IniRepo
from gigui.gui.psg_base import is_git_repo
from gigui.keys import Keys
from gigui.typedefs import FileStr
from gigui.utils import non_hex_chars_in_list, to_posix_fstr, to_posix_fstrs

logger = getLogger(__name__)


class GiRunnerBase:
    def __init__(self, args: Args) -> None:
        self.args: Args = args

    def _check_options(self, len_repos: int) -> bool:
        if not len_repos:
            log(
                "Missing search path. Specify a valid relative or absolute search "
                "path. E.g. '.' for the current directory."
            )
            return False
        if len_repos > 1 and self.args.fix == Keys.nofix:
            log(
                "Multiple repos detected and nofix option selected.\n"
                "Multiple repos need the (default prefix) or postfix option."
            )
            return False
        if (
            not self.args.file_formats
            and not self.args.view == NONE
            and len_repos > 1
            and self.args.dry_run == 0
        ):
            if len_repos > MAX_BROWSER_TABS:
                logger.warning(
                    f"No file formats selected and number of {len_repos} repositories "
                    f"exceeds the maximum number of {MAX_BROWSER_TABS} browser tabs.\n"
                    "Select an output format or set dry run."
                )
                return False
        if len_repos > 1 and self.args.fix == Keys.nofix and self.args.file_formats:
            log(
                "Multiple repos detected and nofix option selected for file output.\n"
                "Multiple repos with file output need the (default prefix) or postfix option."
            )
            return False
        if (
            self.args.view == NONE
            and not self.args.file_formats
            and self.args.dry_run == 0
        ):
            log(
                "View option not set and no file formats selected.\n"
                "Set the view option and/or an output format."
            )
            return False
        if non_hex := non_hex_chars_in_list(self.args.ex_revisions):
            log(
                f"Non-hex characters {' '.join(non_hex)} not allowed in exclude "
                f"revisions option {', '.join(self.args.ex_revisions)}."
            )
            return False
        return True

    def _set_options(self) -> None:
        if self.args.profile:
            profiler = Profile()
            profiler.enable()
        if self.args.dry_run == 1:
            self.args.copy_move = 0
        self.args.include_files = (
            self.args.include_files if self.args.include_files else ["*"]
        )
        self.args.outfile_base = (
            self.args.outfile_base if self.args.outfile_base else DEFAULT_FILE_BASE
        )

        self.args.input_fstrs = to_posix_fstrs(self.args.input_fstrs)
        self.args.outfile_base = to_posix_fstr(self.args.outfile_base)
        self.args.subfolder = to_posix_fstr(self.args.subfolder)
        self.args.include_files = to_posix_fstrs(self.args.include_files)
        self.args.ex_files = to_posix_fstrs(self.args.ex_files)

        if self.args.verbosity is None:
            self.args.verbosity = DEFAULT_VERBOSITY
        set_logging_level_from_verbosity(self.args.verbosity)
        logger.debug(f"{self.args = }")  # type: ignore

    def get_repos(self, dir_path: Path, depth: int) -> list[list[IniRepo]]:
        """
        Recursively retrieves a list of repositories from a given directory path up to a
        specified depth.

        Args:
            - dir_path (Path): The directory path to search for repositories.
            - depth (int): The depth of recursion to search for repositories. A depth of 0
            means only the given directory is checked.

        Returns:
            list[list[RepoGI]]: A list of lists, where each inner list contains repositories
            found in the same directory.

        Notes:
            - If the given path is not a directory, an empty list is returned.
            - If the given path is a Git repository, a list containing a single list with
            one RepoGI object is returned.
            - If the depth is greater than 0, the function will recursively search
            subdirectories for Git repositories.
        """
        repo_lists: list[list[IniRepo]]
        if self.is_dir_safe(dir_path):
            if is_git_repo(dir_path):
                return [
                    [IniRepo(dir_path.name, dir_path, self.args)]
                ]  # independent of depth
            elif depth == 0:
                # For depth == 0, the input itself must be a repo, which is not the case.
                return []
            else:  # depth >= 1:
                subdirs: list[Path] = self.subdirs_safe(dir_path)
                repos: list[IniRepo] = [
                    IniRepo(subdir.name, subdir, self.args)
                    for subdir in subdirs
                    if is_git_repo(subdir)
                ]
                repos = sorted(repos, key=lambda x: x.name)
                other_dirs: list[Path] = [
                    subdir for subdir in subdirs if not is_git_repo(subdir)
                ]
                other_dirs = sorted(other_dirs)
                repo_lists = [repos] if repos else []
                for other_dir in other_dirs:
                    repo_lists.extend(self.get_repos(other_dir, depth - 1))
                return repo_lists
        else:
            log(f"Path {dir_path} is not a directory")
            return []

    def is_dir_safe(self, path: Path) -> bool:
        try:
            return os.path.isdir(path)
        except PermissionError:
            logger.warning(f"Permission denied for path {str(path)}")
            return False

    def subdirs_safe(self, path: Path) -> list[Path]:
        try:
            if not self.is_dir_safe(path):
                return []
            subs: list[FileStr] = os.listdir(path)
            sub_paths = [path / sub for sub in subs]
            return [path for path in sub_paths if self.is_dir_safe(path)]
        # Exception when the os does not allow to list the contents of the path dir:
        except PermissionError:
            logger.warning(f"Permission denied for path {str(path)}")
            return []
