import logging
import multiprocessing
import os
import select
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from cProfile import Profile
from pathlib import Path

import PySimpleGUI as sg

from gigui import shared
from gigui._logging import (
    configure_logging_for_multiprocessing,
    set_logging_level_from_verbosity,
    start_logging_listener,
)
from gigui.args_settings import Args
from gigui.constants import (
    DEFAULT_FILE_BASE,
    DYNAMIC,
    MAX_BROWSER_TABS,
    MAX_THREAD_WORKERS,
    STATIC,
)
from gigui.gui.psg_support import is_git_repo
from gigui.keys import Keys
from gigui.repo import RepoGIGUI
from gigui.typedefs import FileStr
from gigui.utils import (
    get_dir_matches,
    log,
    log_end_time,
    non_hex_chars_in_list,
    out_profile,
    to_posix_fstr,
    to_posix_fstrs,
)

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = logging.getLogger(__name__)


threads: list[threading.Thread] = []
stop_event = threading.Event()


class ReposGIGUI(RepoGIGUI):
    def __init__(self, name: str, location: Path, args: Args) -> None:
        super().__init__(name, location, args)

        self._init_class_options()

    def run_repos(self, start_time: float, gui_window: sg.Window | None = None) -> None:
        profiler: Profile | None = None
        repo_lists: list[list[RepoGIGUI]] = []
        len_repos: int = 0
        dir_strs: list[FileStr]
        dirs_sorted: list[FileStr]

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

        set_logging_level_from_verbosity(self.args.verbosity)
        logger.verbose(f"{self.args = }")  # type: ignore

        dir_strs = get_dir_matches(self.args.input_fstrs)
        dirs_sorted = sorted(dir_strs)

        for dir_str in dirs_sorted:
            repo_lists.extend(self.get_repos(Path(dir_str), self.args.depth))

        len_repos = self.total_len(repo_lists)

        if (
            self.args.blame_history == STATIC
            and self.args.formats
            and self.args.formats != ["html"]
        ):
            logger.warning(
                "Static blame history is supported only for html or no output formats.\n"
            )
            return
        if self.args.blame_history == DYNAMIC and self.args.formats != []:
            logger.warning(
                "Dynamic blame history is available only when no output formats are "
                "selected, because it is generated on the fly and the output cannot be "
                "stored in a file."
            )
            return
        if not len_repos:
            log(
                "Missing search path. Specify a valid relative or absolute search "
                "path. E.g. '.' for the current directory."
            )
            return
        if len_repos > 1 and self.args.fix == Keys.nofix:
            log(
                "Multiple repos detected and nofix option selected.\n"
                "Multiple repos need the (default prefix) or postfix option."
            )
            return
        if (
            not self.args.formats
            and self.args.view
            and len_repos > 1
            and self.args.dry_run == 0
        ):
            if self.args.multicore:
                log(
                    "Multiple repos detected and no output formats selected for multicore.\n"
                    "Select an output format or disable multi-core or set dry run. "
                    + ("E.g. -F html or --no-multicore.")
                )
                return
            if len_repos > MAX_BROWSER_TABS:
                logger.warning(
                    f"No output formats selected and number of {len_repos} repositories "
                    f"exceeds the maximum number of {MAX_BROWSER_TABS} browser tabs.\n"
                    "Select an output format or set dry run."
                )
                return
            if shared.gui:
                log(
                    "Multiple repos detected and no output formats selected.\n"
                    "Select an output format or switch to the command line."
                )
                return
        if len_repos > 1 and self.args.fix == Keys.nofix and self.args.formats:
            log(
                "Multiple repos detected and nofix option selected for file output.\n"
                "Multiple repos with file output need the (default prefix) or postfix option."
            )
            return
        if not self.args.view and not self.args.formats and self.args.dry_run == 0:
            log(
                "View option not set and no output formats selected.\n"
                "Set the view option and/or an output format."
            )
            return

        if non_hex := non_hex_chars_in_list(self.args.ex_revisions):
            log(
                f"Non-hex characters {" ". join(non_hex)} not allowed in exclude "
                f"revisions option {", ". join(self.args.ex_revisions)}."
            )
            return

        if len_repos == 1:
            # Process a single repository
            self.process_unicore_repo(
                repo_lists[0][0],
                gui_window,
                start_time,
            )
        elif self.args.multicore:
            # Process multiple repositories on multiple cores
            self.process_multicore_repos(
                repo_lists,
                len_repos,
                start_time,
            )
        else:  # not self.args.multicore, len(repos) > 1
            # Process multiple repositories on a single core
            self.process_unicore_repos(
                repo_lists,
                len_repos,
                start_time,
            )

        if threads:
            try:
                log("Close all browser tabs or press q followed by Enter to quit.")
                while True:
                    if select.select([sys.stdin], [], [], 0.1)[
                        0
                    ]:  # Check if there is input
                        if input().lower() == "q":
                            stop_event.set()
                            time.sleep(
                                0.1
                            )  # Wait for the server to handle the shutdown request
                            break
                    threads_finished = True
                    for thread in threads:
                        thread.join(timeout=0.1)
                        if thread.is_alive():
                            threads_finished = False
                            continue
                    if threads_finished:
                        break
            except KeyboardInterrupt:
                logger.info("GI: keyboard interrupt received")
            finally:
                for thread in threads:
                    if thread.is_alive():
                        thread.join()
                time.sleep(0.1)  # Wait for the threads to finish and cleanup
                os._exit(0)

        out_profile(profiler, self.args.profile)

    def process_unicore_repo(
        self,
        repo: RepoGIGUI,
        gui_window: sg.Window | None,
        start_time: float,
    ) -> None:
        # Process a single repository in case len(repos) == 1 which also means on a single core.
        self.args.multicore = False
        if self.args.formats:
            log("Output in folder " + str(repo.path.parent))
            log(" " * 4 + f"{repo.name} repository ({1} of {1}) ")
        else:
            log(f"Repository {repo.path}")
        with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
            repo.run_repo(
                thread_executor,
                1,
                threads,
                stop_event,
                gui_window,
                start_time,
            )

    def process_unicore_repos(
        self,
        repo_lists: list[list[RepoGIGUI]],
        len_repos: int,
        start_time: float,
    ) -> None:
        """Processes repositories on a single core.

        Outputs repositories in batches, where each batch contains repositories
        from a single folder.

        Args:
            args: Command-line arguments.
            repo_lists: List of lists of repositories to process.
            len_repos: Total number of repositories.
            outfile_base: Base name for output files.
            gui_window: GUI window instance, if any.
            start_time: Start time of the process.
            shared_data: Shared data dictionary for inter-process communication.
        """

        count = 1
        runs = 0
        with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
            while repo_lists:
                # output a batch of repos from the same folder in a single run
                repos = repo_lists.pop(0)
                prefix: str = "Output in folder" if self.args.formats else "Folder"
                log(prefix + str(repos[0].path.parent))
                for repo in repos:
                    log(" " * 4 + f"{repo.name} repository ({count} of {len_repos})")
                    repo.run_repo(
                        thread_executor,
                        len_repos,
                        threads,
                        stop_event,
                    )
                    count += 1
                runs += 1
        log_end_time(start_time)

    # Process multiple repositories in case len(repos) > 1 on multiple cores.
    def process_multicore_repos(
        self,
        repo_lists: list[list[RepoGIGUI]],
        len_repos: int,
        start_time: float,
    ) -> None:
        queue: multiprocessing.Queue = multiprocessing.Queue(-1)
        listener = start_logging_listener(queue)
        with ProcessPoolExecutor(
            initializer=configure_logging_for_multiprocessing,
            initargs=(queue, self.args.verbosity),
        ) as process_executor:
            for repos in repo_lists:
                len_repos = len(repos)
                repo_parent_str = str(Path(repos[0].path).parent)
                log("Output in folder " + repo_parent_str)
                future_to_repo = {
                    process_executor.submit(
                        self.process_multicore_repo,
                        repo,
                        len_repos,
                    ): repo
                    for repo in repos
                }
                for future in as_completed(future_to_repo):
                    repo = future_to_repo[future]
                    stats_found = future.result()
                    if self.args.dry_run <= 1 and not stats_found:
                        log(
                            " " * 8 + "No statistics matching filters found for "
                            f"repository {repo.name}"
                        )
            log_end_time(start_time)
        listener.stop()

    def process_multicore_repo(
        self,
        repo: RepoGIGUI,
        len_repos: int,
    ) -> bool:
        with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
            log(" " * 4 + f"Start {repo.name}")
            stats_found = repo.run_analysis(thread_executor)
            if stats_found:
                repo._generate_output(
                    len_repos,
                )
        return stats_found

    def get_repos(self, dir_path: Path, depth: int) -> list[list[RepoGIGUI]]:
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
        repo_lists: list[list[RepoGIGUI]]
        if self.is_dir_safe(dir_path):
            if is_git_repo(dir_path):
                return [
                    [RepoGIGUI(dir_path.name, dir_path, self.args)]
                ]  # independent of depth
            elif depth == 0:
                # For depth == 0, the input itself must be a repo, which is not the case.
                return []
            else:  # depth >= 1:
                subdirs: list[Path] = self.subdirs_safe(dir_path)
                repos: list[RepoGIGUI] = [
                    RepoGIGUI(subdir.name, subdir, self.args)
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

    @staticmethod
    def total_len(repo_lists: list[list[RepoGIGUI]]) -> int:
        return sum(len(repo_list) for repo_list in repo_lists)


def run_repos(
    args: Args, start_time: float, gui_window: sg.Window | None = None
) -> None:
    repos_gigui = ReposGIGUI(
        "gigui", Path(), args
    )  # First two arguments are don't care
    repos_gigui.run_repos(start_time, gui_window)
