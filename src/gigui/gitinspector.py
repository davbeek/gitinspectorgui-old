import glob
import logging
import os
import platform
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from cProfile import Profile
from pathlib import Path

import PySimpleGUI as sg  # type: ignore

from gigui.args_settings import Args
from gigui.blame_reader import BlameBaseReader, BlameHistoryReader, BlameReader
from gigui.constants import (
    AUTO,
    DEFAULT_FILE_BASE,
    DEFAULT_FORMAT,
    DYNAMIC,
    MAX_BROWSER_TABS,
    NONE,
    STATIC,
)
from gigui.data import FileStat, Person
from gigui.keys import Keys
from gigui.output import stat_rows
from gigui.output.blame_rows import BlameBaseRows
from gigui.output.excel import Book
from gigui.output.html import (
    BlameBaseTableSoup,
    BlameTablesSoup,
    TableSoup,
    get_repo_html,
    load_css,
)
from gigui.output.server_main import start_werkzeug_server_in_process_with_html
from gigui.output.stat_rows import TableRows
from gigui.repo import GIRepo, get_repos, total_len
from gigui.repo_reader import RepoReader
from gigui.typedefs import FileStr, Html
from gigui.utils import (
    get_outfile_name,
    log,
    log_end_time,
    open_files,
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

    logger.info(f"{args = }")
    init_classes(args)
    repo_lists: list[list[GIRepo]] = []

    dir_strs = get_dir_matches(args.input_fstrs)
    for dir_str in dir_strs:
        repo_lists.extend(get_repos(Path(dir_str), args.depth))

    len_repos = total_len(repo_lists)

    if args.blame_history != NONE and "excel" in args.format:
        logging.warning(
            "Blame history is not not supported and will be ignored for excel output."
        )
    if args.blame_history == DYNAMIC and len_repos > 1:
        logging.warning(
            "Dynamic blame history is not supported for multiple repositories, exiting."
        )
        return
    if args.blame_history == DYNAMIC and args.format != ["auto"]:
        logging.warning(
            "Dynamic blame history is not supported for formats other than auto, exiting."
        )
        return
    if not len_repos:
        log("Found no repositories")
        return
    if len_repos > 1 and args.fix == Keys.nofix:
        log(
            "Multiple repos detected and nofix option selected."
            "Multiple repos need the (default prefix) or postfix option."
        )
        return

    outfile_base = args.outfile_base if args.outfile_base else DEFAULT_FILE_BASE
    if not args.format:
        args.format = [DEFAULT_FORMAT]

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
    GIRepo.blame_history = args.blame_history
    RepoReader.include_files = args.include_files
    RepoReader.n_files = args.n_files
    RepoReader.subfolder = args.subfolder
    RepoReader.extensions = args.extensions
    RepoReader.whitespace = args.whitespace
    RepoReader.multi_thread = args.multi_thread
    RepoReader.since = args.since
    RepoReader.until = args.until
    RepoReader.ex_files = args.ex_files
    RepoReader.ex_revs = set(args.ex_revisions)
    RepoReader.ex_messages = args.ex_messages
    BlameBaseReader.copy_move = args.copy_move
    BlameBaseReader.since = args.since
    BlameBaseReader.whitespace = args.whitespace
    BlameReader.multi_thread = args.multi_thread
    BlameReader.comments = args.comments
    BlameReader.empty_lines = args.comments
    BlameHistoryReader.blame_history = args.blame_history
    FileStat.show_renames = args.show_renames
    BlameBaseRows.args = args
    TableRows.deletions = args.deletions
    TableRows.subfolder = args.subfolder
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
    repo: GIRepo,
    outfile_base: str,
    gui_window: sg.Window | None,
    start_time: float,
) -> None:
    # Process a single repository in case len(repos) == 1 which also means on a single core.

    args.multi_core = False
    file_to_open = ""
    html_code = ""
    repo_name = ""

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
                    _, file_to_open, (html_code, repo_name) = process_repo_output(
                        args,
                        repo,
                        1,
                        outfile_base,
                    )
            else:
                log("No statistics matching filters found")
    log_end_time(start_time)
    if file_to_open:  # format must be "html" or "excel"
        open_files([file_to_open])
    elif html_code and not gui_window:  # format must be "auto"
        if args.blame_history in {STATIC, NONE}:
            open_webview(html_code, repo_name)
        else:  # args.blame_history == DYNAMIC
            try:
                start_werkzeug_server_in_process_with_html(html_code, load_css())
                # server_process.join()  # Wait for the server process to finish
            except KeyboardInterrupt:
                os._exit(0)
    elif html_code and gui_window:  # format must be "auto"
        if args.blame_history in {STATIC, NONE}:
            gui_window.write_event_value(Keys.open_webview, (html_code, repo.name))
        else:  # args.blame_history == DYNAMIC
            logger.error("Dynamic blame history is not supported in GUI mode.")
    else:
        log("No html code to show")


def process_repo_output(  # pylint: disable=too-many-locals
    args: Args,
    repo: GIRepo,
    len_repos: int,  # Total number of repositories being analyzed
    outfile_base: str,
) -> tuple[
    list[FileStr],  # Files to log
    FileStr,  # File to open
    tuple[Html, str],  # (HTML code, name of repository), empty if no webview generated.
]:
    """
    Generate result file(s) for the analysis of the given repository.

    :return: Files that should be logged, files that should be opened, and
            the (viewed HTML file text and name of repository) pair.
            The latter is empty if viewing is not requested.
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

    if not repo.authors_included or not formats:
        return [], "", ("", "")

    outfile_name = get_outfile_name(args.fix, outfile_base, repo.name)
    outfilestr = str(repo.path.parent / outfile_name)

    # Write the excel file if requested.
    if "excel" in formats:
        logfile(f"{outfile_name}.xlsx")
        if args.dry_run == 0:
            Book(outfilestr, repo)

    # Write the HTML file if requested.
    if "html" in formats or (
        formats == ["auto"]
        and (len_repos > 1 or len_repos == 1 and args.viewer == NONE)
    ):
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
        return [], "", ("", "")

    # If the result files should not be opened, we're done.
    if len(formats) > 1 or args.profile or args.viewer == NONE:
        return [], "", ("", "")

    # not len(formats) > 1 and not len(formats) == 0, because in those cases a return
    # statement has already been executed.
    out_format = formats[0]

    # Determine the file to open and webview data based on the output format and number
    # of repositories.
    file_to_open, webview_data = get_output_file_and_webview_data(
        args, repo, len_repos, outfilestr, out_format
    )
    return files_to_log, file_to_open, webview_data


def process_unicore_repos(
    args: Args,
    repo_lists: list[list[GIRepo]],
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
        count, files_to_open = process_unicore_repo_batch(
            args,
            repos,
            len_repos,
            outfile_base,
            count,
        )
        runs += 1
    log_end_time(start_time)
    if runs == 1 and files_to_open:  # type: ignore
        open_files(files_to_open)


def get_output_file_and_webview_data(
    args: Args, repo: GIRepo, len_repos: int, outfilestr: str, out_format: str
) -> tuple[FileStr, tuple[Html, str]]:
    file_to_open: FileStr = ""
    webview_data: tuple[str, str] = "", ""
    if len_repos == 1:
        match out_format:
            case "html":
                file_to_open = outfilestr + ".html"
            case "excel":
                file_to_open = outfilestr + ".xlsx"
            case "auto":
                html_code = get_repo_html(repo, args.blame_skip)
                webview_data = html_code, repo.name
    else:  # multiple repos
        if (
            len_repos <= MAX_BROWSER_TABS
            and out_format in {"auto", "html"}
            and args.viewer == AUTO
        ):
            file_to_open = outfilestr + ".html"
    return file_to_open, webview_data


# Process multiple repos on a single core.
def process_unicore_repo_batch(
    args: Args,
    repos: list[GIRepo],
    len_repos: int,
    outfile_base: str,
    count: int,
) -> tuple[int, list[FileStr]]:
    log("Output in folder " + str(repos[0].path.parent))
    with ThreadPoolExecutor(max_workers=5) as thread_executor:
        files_to_open = []
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
                    _, file_to_open, _ = process_repo_output(
                        args,
                        repo,
                        len_repos,
                        outfile_base,
                    )
                    if file_to_open:
                        if platform.system() == "Windows":
                            # Windows cannot open multiple files at once in a
                            # browser, so files are opened one by one.
                            open_files([file_to_open])
                        else:
                            files_to_open.append(file_to_open)
            count += 1
    return count, files_to_open


# Process multiple repositories in case len(repos) > 1 on multiple cores.
def process_multicore_repos(
    args: Args,
    repo_lists: list[list[GIRepo]],
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
    repo: GIRepo,
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
            files_to_log, _, _ = process_repo_output(
                args,
                repo,
                len_repos,
                outfile_base,
            )
    return stats_found, files_to_log
