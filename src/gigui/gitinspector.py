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

import PySimpleGUI as sg  # type: ignore

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
    HIDE,
    MAX_BROWSER_TABS,
    MAX_THREAD_WORKERS,
    STATIC,
)
from gigui.data import FileStat, Person
from gigui.keys import Keys
from gigui.output import repo_html
from gigui.output.repo_blame_rows import RepoBlameRows
from gigui.output.repo_excel import Book
from gigui.output.repo_html import RepoBlameTableSoup, TableSoup
from gigui.output.repo_stat_rows import RepoRows, RepoStatRows
from gigui.repo import RepoGI, get_repos, total_len
from gigui.repo_base import RepoBase
from gigui.repo_blame import RepoBlame, RepoBlameBase
from gigui.repo_data import RepoData
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


def run(args: Args, start_time: float, gui_window: sg.Window | None = None) -> None:
    profiler: Profile | None = None
    repo_lists: list[list[RepoGI]] = []
    len_repos: int = 0
    dir_strs: list[FileStr]
    dirs_sorted: list[FileStr]

    if args.profile:
        profiler = Profile()
        profiler.enable()

    if args.dry_run == 1:
        args.copy_move = 0

    args.include_files = args.include_files if args.include_files else ["*"]
    args.outfile_base = args.outfile_base if args.outfile_base else DEFAULT_FILE_BASE

    args.input_fstrs = to_posix_fstrs(args.input_fstrs)
    args.outfile_base = to_posix_fstr(args.outfile_base)
    args.subfolder = to_posix_fstr(args.subfolder)
    args.include_files = to_posix_fstrs(args.include_files)
    args.ex_files = to_posix_fstrs(args.ex_files)

    set_logging_level_from_verbosity(args.verbosity)
    logger.verbose(f"{args = }")  # type: ignore

    init_classes(args)

    dir_strs = get_dir_matches(args.input_fstrs)
    dirs_sorted = sorted(dir_strs)

    for dir_str in dirs_sorted:
        repo_lists.extend(get_repos(Path(dir_str), args.depth))

    len_repos = total_len(repo_lists)

    if args.blame_history == STATIC and args.formats and args.formats != ["html"]:
        logger.warning(
            "Static blame history is supported only for html or no output formats.\n"
        )
        return
    if args.blame_history == DYNAMIC and args.formats != []:
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
    if len_repos > 1 and args.fix == Keys.nofix:
        log(
            "Multiple repos detected and nofix option selected.\n"
            "Multiple repos need the (default prefix) or postfix option."
        )
        return
    if not args.formats and args.view and len_repos > 1 and args.dry_run == 0:
        if args.multicore:
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
    if len_repos > 1 and args.fix == Keys.nofix and args.formats:
        log(
            "Multiple repos detected and nofix option selected for file output.\n"
            "Multiple repos with file output need the (default prefix) or postfix option."
        )
        return
    if not args.view and not args.formats and args.dry_run == 0:
        log(
            "View option not set and no output formats selected.\n"
            "Set the view option and/or an output format."
        )
        return

    if non_hex := non_hex_chars_in_list(args.ex_revisions):
        log(
            f"Non-hex characters {" ". join(non_hex)} not allowed in exclude "
            f"revisions option {", ". join(args.ex_revisions)}."
        )
        return

    if len_repos == 1:
        # Process a single repository
        process_unicore_repo(
            args,
            repo_lists[0][0],
            gui_window,
            start_time,
        )
    elif args.multicore:
        # Process multiple repositories on multiple cores
        process_multicore_repos(
            args,
            repo_lists,
            len_repos,
            start_time,
        )
    else:  # not args.multicore, len(repos) > 1
        # Process multiple repositories on a single core
        process_unicore_repos(
            args,
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

    out_profile(profiler, args.profile)


def init_classes(args: Args):
    RepoBase.subfolder = args.subfolder
    RepoBase.n_files = args.n_files
    RepoBase.include_files = args.include_files
    RepoData.blame_history = args.blame_history
    RepoBase.whitespace = args.whitespace
    RepoBase.since = args.since
    RepoBase.until = args.until
    RepoBase.verbosity = args.verbosity
    RepoData.dry_run = args.dry_run
    RepoBase.extensions = args.extensions
    RepoBase.multithread = args.multithread
    RepoBase.multicore = args.multicore
    RepoBase.ex_files = args.ex_files
    RepoBase.ex_revisions = set(args.ex_revisions)
    RepoBase.ex_messages = args.ex_messages
    RepoBlameBase.blame_skip = args.blame_skip
    RepoBlameBase.copy_move = args.copy_move
    RepoBlame.comments = args.comments
    RepoBlame.empty_lines = args.empty_lines
    FileStat.show_renames = args.show_renames
    RepoRows.deletions = args.deletions
    RepoRows.scaled_percentages = args.scaled_percentages
    RepoStatRows.deletions = args.deletions
    RepoStatRows.scaled_percentages = args.scaled_percentages
    RepoBlameRows.ex_authors = args.ex_authors
    RepoBlameRows.blame_exclusions = args.blame_exclusions
    TableSoup.blame_exclusions = args.blame_exclusions
    RepoBlameTableSoup.blame_history = args.blame_history
    RepoGI.formats = args.formats
    RepoGI.outfile_base = args.outfile_base
    RepoGI.fix = args.fix
    RepoGI.view = args.view
    Book.subfolder = args.subfolder
    Book.blame_skip = args.blame_skip
    Book.blame_history = args.blame_history
    Person.show_renames = args.show_renames
    Person.ex_author_patterns = args.ex_authors
    Person.ex_email_patterns = args.ex_emails
    repo_html.blame_exclusions_hide = args.blame_exclusions == HIDE
    repo_html.blame_history = args.blame_history


def process_unicore_repo(
    args: Args,
    repo: RepoGI,
    gui_window: sg.Window | None,
    start_time: float,
) -> None:
    # Process a single repository in case len(repos) == 1 which also means on a single core.
    args.multicore = False
    if args.formats:
        log("Output in folder " + str(repo.path.parent))
        log(" " * 4 + f"{repo.name} repository ({1} of {1}) ")
    else:
        log(f"Repository {repo.path}")
    with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
        repo.run(
            thread_executor,
            1,
            threads,
            stop_event,
            gui_window,
            start_time,
        )


def process_unicore_repos(
    args: Args,
    repo_lists: list[list[RepoGI]],
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
            prefix: str = "Output in folder" if args.formats else "Folder"
            log(prefix + str(repos[0].path.parent))
            for repo in repos:
                log(" " * 4 + f"{repo.name} repository ({count} of {len_repos})")
                repo.run(
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
    args: Args,
    repo_lists: list[list[RepoGI]],
    len_repos: int,
    start_time: float,
) -> None:
    queue: multiprocessing.Queue = multiprocessing.Queue(-1)
    listener = start_logging_listener(queue)
    with ProcessPoolExecutor(
        initializer=configure_logging_for_multiprocessing,
        initargs=(queue, args.verbosity),
    ) as process_executor:
        for repos in repo_lists:
            len_repos = len(repos)
            repo_parent_str = str(Path(repos[0].path).parent)
            log("Output in folder " + repo_parent_str)
            future_to_repo = {
                process_executor.submit(
                    process_multicore_repo,
                    args,
                    repo,
                    len_repos,
                ): repo
                for repo in repos
            }
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                stats_found = future.result()
                if args.dry_run <= 1 and not stats_found:
                    log(
                        " " * 8 + "No statistics matching filters found for "
                        f"repository {repo.name}"
                    )
        log_end_time(start_time)
    listener.stop()


def process_multicore_repo(
    args: Args,
    repo: RepoGI,
    len_repos: int,
) -> bool:
    init_classes(args)
    with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
        log(" " * 4 + f"Start {repo.name}")
        stats_found = repo.run_analysis(thread_executor)
        if stats_found:
            repo._generate_output(
                len_repos,
            )
    return stats_found
