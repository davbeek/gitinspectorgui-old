import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import PySimpleGUI as sg  # type: ignore[import-untyped]
from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from gigui.constants import DYNAMIC, NONE, STATIC
from gigui.keys import Keys
from gigui.output.repo_excel import Book
from gigui.output.repo_html_server import RepoHTMLServer
from gigui.typedefs import FileStr
from gigui.utils import get_outfile_name, log, log_end_time, open_file, open_webview

logger = logging.getLogger(__name__)


# RepoGI = Repo GitInspector
class RepoGI(RepoHTMLServer, Book):
    outfile_base: str
    fix: str
    formats: list[str]
    view: bool

    def __init__(self, name: str, location: Path):
        super().__init__(name, location)

    def run(
        self,
        thread_executor: ThreadPoolExecutor,
        len_repos: int,  # Total number of repositories being analyzed
        threads: list[threading.Thread] | None = None,
        stop_event: threading.Event | None = None,
        gui_window: sg.Window | None = None,
        start_time: float | None = None,
    ) -> None:
        stats_found = self.run_analysis(thread_executor)
        if stats_found:
            if self.dry_run == 1:
                log("")
            else:  # args.dry_run == 0
                self._generate_output(
                    len_repos,
                    threads,
                    stop_event,
                    gui_window,
                    start_time,
                )
        else:
            log(" " * 8 + "No statistics matching filters found")

    def _generate_output(  # pylint: disable=too-many-locals
        self,
        len_repos: int,  # Total number of repositories being analyzed
        threads: list[threading.Thread] | None = None,
        stop_event: threading.Event | None = None,
        gui_window: sg.Window | None = None,
        start_time: float | None = None,
    ) -> None:
        """
        Generate result file(s) for the analysis of the given repository.

        :return: Files that should be logged
        """

        def logfile(fname: FileStr):
            log(
                ("\n" if self.multicore and self.verbosity == 0 else "")
                + " " * 8
                + fname
            )

        if not self.authors_included:
            return

        outfile_name = get_outfile_name(self.fix, self.outfile_base, self.name)
        outfilestr = str(self.path.parent / outfile_name)

        # Write the excel file if requested.
        if "excel" in self.formats:
            logfile(f"{outfile_name}.xlsx")
            if self.dry_run == 0:
                self.run_excel(outfilestr)

        # Write the HTML file if requested.
        if "html" in self.formats:
            logfile(f"{outfile_name}.html")
            if self.dry_run == 0:
                html_code = self.get_html()
                with open(outfilestr + ".html", "w", encoding="utf-8") as f:
                    f.write(html_code)

        logger.info(" " * 4 + f"Close {self.name}")

        if len_repos == 1:
            log_end_time(start_time)  # type: ignore

        # In dry-run, there is nothing to show.
        if not self.dry_run == 0:
            return

        # If the result files should not be viewed, we're done.
        if not self.view:
            return

        # args.view is True here, so we open the files.
        if "excel" in self.formats:
            open_file(outfilestr + ".xlsx")

        if "html" in self.formats and self.blame_history != DYNAMIC:
            open_file(outfilestr + ".html")
            return

        if self.formats:
            return

        # The following holds: args.view and not args.formats and "no dry run"
        html_code = self.get_html()
        if len_repos == 1 and self.blame_history in {NONE, STATIC}:
            if gui_window:
                gui_window.write_event_value(Keys.open_webview, (html_code, self.name))
            else:  # CLI mode
                open_webview(html_code, self.name)
        else:
            thread = threading.Thread(
                target=self.start_werkzeug_server_in_process_with_html,
                args=(html_code, stop_event),
            )
            thread.start()
            threads.append(thread)  # type: ignore


def get_repos(dir_path: Path, depth: int) -> list[list[RepoGI]]:
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
    repo_lists: list[list[RepoGI]]
    if is_dir_safe(dir_path):
        if is_git_repo(dir_path):
            return [[RepoGI(dir_path.name, dir_path)]]  # independent of depth
        elif depth == 0:
            # For depth == 0, the input itself must be a repo, which is not the case.
            return []
        else:  # depth >= 1:
            subdirs: list[Path] = subdirs_safe(dir_path)
            repos: list[RepoGI] = [
                RepoGI(subdir.name, subdir) for subdir in subdirs if is_git_repo(subdir)
            ]
            repos = sorted(repos, key=lambda x: x.name)
            other_dirs: list[Path] = [
                subdir for subdir in subdirs if not is_git_repo(subdir)
            ]
            other_dirs = sorted(other_dirs)
            repo_lists = [repos] if repos else []
            for other_dir in other_dirs:
                repo_lists.extend(get_repos(other_dir, depth - 1))
            return repo_lists
    else:
        log(f"Path {dir_path} is not a directory")
        return []


def is_dir_safe(path: Path) -> bool:
    try:
        return os.path.isdir(path)
    except PermissionError:
        logger.warning(f"Permission denied for path {str(path)}")
        return False


def is_git_repo(path: Path) -> bool:
    try:
        git_path = path / ".git"
        if git_path.is_symlink():
            git_path = git_path.resolve()
            if not git_path.is_dir():
                return False
        elif not git_path.is_dir():
            return False
    except (PermissionError, TimeoutError):  # git_path.is_symlink() may time out
        return False

    try:
        # The default True value of expand_vars leads to confusing warnings from
        # GitPython for many paths from system folders.
        repo = Repo(path, expand_vars=False)
        return not repo.bare
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False


def subdirs_safe(path: Path) -> list[Path]:
    try:
        if not is_dir_safe(path):
            return []
        subs: list[FileStr] = os.listdir(path)
        sub_paths = [path / sub for sub in subs]
        return [path for path in sub_paths if is_dir_safe(path)]
    # Exception when the os does not allow to list the contents of the path dir:
    except PermissionError:
        logger.warning(f"Permission denied for path {str(path)}")
        return []


def total_len(repo_lists: list[list[RepoGI]]) -> int:
    return sum(len(repo_list) for repo_list in repo_lists)
