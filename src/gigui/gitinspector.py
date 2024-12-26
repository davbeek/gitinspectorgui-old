import glob
import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from cProfile import Profile
from pathlib import Path

import PySimpleGUI as sg  # type: ignore

from gigui.args_settings import Args
from gigui.constants import DEFAULT_FILE_BASE, DYNAMIC, HIDE, STATIC
from gigui.data import FileStat, Person
from gigui.keys import Keys
from gigui.output import html, stat_rows
from gigui.output.blame_rows import BlameBaseRows
from gigui.output.excel import Book
from gigui.output.html import (
    BlameBaseTableSoup,
    BlameTablesSoup,
    TableSoup,
    get_repo_html,
)
from gigui.output.server_main import start_werkzeug_server_in_process_with_html
from gigui.output.stat_rows import TableRows
from gigui.repo import RepoGI, get_repos, total_len
from gigui.repo_base import RepoBase
from gigui.repo_blame import RepoBlame, RepoBlameBase, RepoBlameHistory
from gigui.typedefs import FileStr
from gigui.utils import (
    get_outfile_name,
    log,
    log_end_time,
    open_file,
    open_webview,
    out_profile,
)

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = logging.getLogger(__name__)


def main(args: Args, start_time: float, gui_window: sg.Window | None = None) -> None:
    profiler = None
    if args.profile:
        profiler = Profile()
        profiler.enable()

    args.include_files = args.include_files if args.include_files else ["*"]

    logger.info(f"{args = }")
    init_classes(args)
    repo_lists: list[list[RepoGI]] = []

    dir_strs = get_dir_matches(args.input_fstrs)
    dirs_sorted = sorted(dir_strs)
    for dir_str in dirs_sorted:
        repo_lists.extend(get_repos(Path(dir_str), args.depth))

    len_repos = total_len(repo_lists)

    if args.blame_history == STATIC and args.format and args.format != ["html"]:
        logging.warning(
            "Static blame history is supported only for html or no output format.\n"
        )
        return
    if args.blame_history == DYNAMIC and len_repos > 1:
        logging.warning(
            "Dynamic blame history is not supported for multiple repositories.\n"
            "Please select static blame history or a single repository."
        )
        return
    if args.blame_history == DYNAMIC and args.format != []:
        logging.warning(
            "Dynamic blame history is available only when no output formats are selected."
        )
        return
    if not len_repos:
        log("Found no repositories.")
        return
    if len_repos > 1 and args.fix == Keys.nofix:
        log(
            "Multiple repos detected and nofix option selected.\n"
            "Multiple repos need the (default prefix) or postfix option."
        )
        return
    if len_repos > 1 and not args.format:
        log(
            "Multiple repos detected and no output format selected.\n"
            "Please select an output format."
        )
        return
    if not args.view and not args.format:
        log(
            "View option not set and no output format selected.\n"
            "Please set the view option and/or an output format."
        )
        return

    outfile_base = args.outfile_base if args.outfile_base else DEFAULT_FILE_BASE

    # Process a single repository
    if len_repos == 1:
        process_unicore_repo(
            args,
            repo_lists[0][0],
            outfile_base,
            gui_window,
            start_time,
        )
        return

    # Process multiple repositories
    if args.multi_core:
        process_multicore_repos(args, repo_lists, len_repos, outfile_base, start_time)
    else:
        process_unicore_repos(
            args,
            repo_lists,
            len_repos,
            outfile_base,
            start_time,
        )
    out_profile(args, profiler)


def init_classes(args: Args):
    RepoGI.blame_history = args.blame_history
    RepoBase.include_files = args.include_files
    RepoBase.n_files = args.n_files
    RepoBase.subfolder = args.subfolder
    RepoBase.extensions = args.extensions
    RepoBase.whitespace = args.whitespace
    RepoBase.multi_thread = args.multi_thread
    RepoBase.since = args.since
    RepoBase.until = args.until
    RepoBase.ex_files = args.ex_files
    RepoBase.ex_revs = set(args.ex_revisions)
    RepoBase.ex_messages = args.ex_messages
    RepoBlameBase.copy_move = args.copy_move
    RepoBlameBase.since = args.since
    RepoBlameBase.whitespace = args.whitespace
    RepoBlame.multi_thread = args.multi_thread
    RepoBlame.comments = args.comments
    RepoBlame.empty_lines = args.empty_lines
    RepoBlameHistory.blame_history = args.blame_history
    FileStat.show_renames = args.show_renames
    TableRows.deletions = args.deletions
    TableRows.subfolder = args.subfolder
    BlameBaseRows.comments = args.comments
    BlameBaseRows.empty_lines = args.empty_lines
    BlameBaseRows.ex_authors = args.ex_authors
    BlameBaseRows.blame_exclusions = args.blame_exclusions
    BlameBaseTableSoup.blame_history = args.blame_history
    TableSoup.blame_exclusions = args.blame_exclusions
    TableSoup.empty_lines = args.empty_lines
    TableSoup.subfolder = args.subfolder
    BlameTablesSoup.subfolder = args.subfolder
    BlameTablesSoup.blame_history = args.blame_history
    Book.subfolder = args.subfolder
    Book.blame_skip = args.blame_skip
    Book.blame_history = args.blame_history
    Person.show_renames = args.show_renames
    Person.ex_author_patterns = args.ex_authors
    Person.ex_email_patterns = args.ex_emails
    stat_rows.deletions = args.deletions
    stat_rows.scaled_percentages = args.scaled_percentages
    html.blame_exclusions_hide = args.blame_exclusions == HIDE
    html.blame_history = args.blame_history


# Normally, the input paths have already been expanded by the shell, but in case the
# wildcard were protected in quotes, we expand them here.
def get_dir_matches(input_fstrs: list[FileStr]) -> list[FileStr]:
    matching_fstrs: list[FileStr] = []
    for pattern in input_fstrs:
        matches = glob.glob(pattern)
        if not matches:
            logger.warning(
                f'No repositories found for input folder pattern "{pattern}"'
            )
        for match in matches:
            if os.path.isdir(match) and match not in matching_fstrs:
                matching_fstrs.append(match)
    return matching_fstrs


def process_unicore_repo(
    args: Args,
    repo: RepoGI,
    outfile_base: str,
    gui_window: sg.Window | None,
    start_time: float,
) -> None:
    # Process a single repository in case len(repos) == 1 which also means on a single core.

    args.multi_core = False
    log("Output in folder " + str(repo.path.parent))
    log(f"    {repo.name} repository ({1} of {1}) ")
    with ThreadPoolExecutor(max_workers=6) as thread_executor:
        # repo.set_thread_executor(thread_executor)
        if args.dry_run <= 1:
            stats_found = repo.run(thread_executor)
            if stats_found:
                if args.dry_run == 1:
                    log("")
                else:  # args.dry_run == 0
                    log("        ", end="")
                    _ = process_repo_output(
                        args, repo, 1, outfile_base, gui_window, start_time
                    )
            else:
                log("No statistics matching filters found")


def process_repo_output(  # pylint: disable=too-many-locals
    args: Args,
    repo: RepoGI,
    len_repos: int,  # Total number of repositories being analyzed
    outfile_base: str,
    gui_window: sg.Window | None = None,
    start_time: float | None = None,
) -> list[FileStr]:  # Files to log
    """
    Generate result file(s) for the analysis of the given repository.

    :return: Files that should be logged
    """

    # Setup logging.
    def logfile(fname: FileStr):
        if args.multi_core:
            # Logging is postponed in multi-core.
            files_to_log.append(fname)
        else:
            # Single core.
            log(fname, end=" ")  # Append space as more filenames may be logged.

    files_to_log: list[FileStr] = []
    formats = args.format

    if not repo.authors_included:
        return []

    outfile_name = get_outfile_name(args.fix, outfile_base, repo.name)
    outfilestr = str(repo.path.parent / outfile_name)

    # Write the excel file if requested.
    if "excel" in formats:
        logfile(f"{outfile_name}.xlsx")
        if args.dry_run == 0:
            Book(outfilestr, repo)

    # Write the HTML file if requested.
    if "html" in formats:
        logfile(f"{outfile_name}.html")
        if args.dry_run == 0:
            html_code = get_repo_html(repo, args.blame_skip)
            with open(outfilestr + ".html", "w", encoding="utf-8") as f:
                f.write(html_code)

    # All formats done, end the log line in the single core case.
    if not args.multi_core:
        log("")

    # In dry-run, there is nothing to show.
    if args.dry_run != 0:
        return files_to_log

    if len_repos == 1:
        log_end_time(start_time)  # type: ignore

    # If the result files should not be viewed, we're done.
    if not args.view:
        return files_to_log

    # args.view is True here, so we open the files.
    if "excel" in formats:
        open_file(outfilestr + ".xlsx")

    if "html" in formats and args.blame_history != DYNAMIC:
        open_file(outfilestr + ".html")
        return []

    if len_repos == 1 and not args.format:
        html_code = get_repo_html(repo, args.blame_skip)
        if gui_window:
            gui_window.write_event_value(Keys.open_webview, (html_code, repo.name))
        elif args.blame_history != DYNAMIC:  # CLI mode, dynamic or no blame history
            open_webview(html_code, repo.name)
        else:  # CLI mode, dynamic blame history
            try:
                start_werkzeug_server_in_process_with_html(html_code)
            except KeyboardInterrupt:
                os._exit(0)
    return []


def process_unicore_repos(
    args: Args,
    repo_lists: list[list[RepoGI]],
    len_repos: int,
    outfile_base: FileStr,
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
    while repo_lists:
        # output a batch of repos from the same folder in a single run
        repos = repo_lists.pop(0)
        count = process_unicore_repo_batch(
            args,
            repos,
            len_repos,
            outfile_base,
            count,
        )
        runs += 1
    log_end_time(start_time)


# Process multiple repos on a single core.
def process_unicore_repo_batch(
    args: Args,
    repos: list[RepoGI],
    len_repos: int,
    outfile_base: str,
    count: int,
) -> int:
    log("Output in folder " + str(repos[0].path.parent))
    with ThreadPoolExecutor(max_workers=5) as thread_executor:
        for repo in repos:
            dry_run = args.dry_run
            log(f"    {repo.name} repository ({count} of {len_repos})")
            if dry_run == 2:
                continue

            # dry_run == 0 or dry_run == 1
            stats_found = repo.run(thread_executor)
            log("        ", end="")
            if not stats_found:
                log("No statistics matching filters found")
            else:  # stats found
                if dry_run == 1:
                    log("")
                else:  # dry_run == 0
                    _ = process_repo_output(
                        args,
                        repo,
                        len_repos,
                        outfile_base,
                    )
            count += 1
    return count


# Process multiple repositories in case len(repos) > 1 on multiple cores.
def process_multicore_repos(
    args: Args,
    repo_lists: list[list[RepoGI]],
    len_repos: int,
    outfile_base: FileStr,
    start_time: float,
) -> None:
    with ProcessPoolExecutor() as process_executor:
        future_to_repo = {
            process_executor.submit(
                process_multicore_repo,
                args,
                repo,
                len_repos,
                outfile_base,
            ): repo
            for repos in repo_lists
            for repo in repos
        }
        count = 1
        last_parent = None
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            stats_found, files_to_log = future.result()
            repo_parent = Path(repo.path).parent
            if not last_parent or repo_parent != last_parent:
                last_parent = repo_parent
                log("Output in folder " + str(repo.path.parent))
            log(f"    {repo.name} repository ({count} of {len_repos}) ")
            if stats_found:
                log(f"        {" ".join(files_to_log)}")
            elif args.dry_run <= 1:
                log(
                    "        "
                    "No statistics matching filters found for "
                    f"repository {repo.name}"
                )
            count += 1
        log_end_time(start_time)


def process_multicore_repo(
    args: Args,
    repo: RepoGI,
    len_repos: int,
    outfile_base: str,
) -> tuple[bool, list[FileStr]]:
    init_classes(args)
    with ThreadPoolExecutor(max_workers=5) as thread_executor:
        dry_run = args.dry_run
        stats_found = False
        files_to_log: list[FileStr] = []
        if dry_run <= 1:
            stats_found = repo.run(thread_executor)
        if dry_run == 0 and stats_found:
            files_to_log = process_repo_output(
                args,
                repo,
                len_repos,
                outfile_base,
            )
    return stats_found, files_to_log
