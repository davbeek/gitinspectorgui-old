import logging
import platform
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from cProfile import Profile
from io import StringIO
from pathlib import Path
from pstats import Stats

import PySimpleGUI as sg

from gigui.args_settings_keys import AUTO, NONE, Args, Keys
from gigui.common import log, open_webview
from gigui.constants import DEFAULT_FILE_BASE, DEFAULT_FORMAT, MAX_BROWSER_TABS
from gigui.data import FileStat, Person
from gigui.output import outbase
from gigui.output.excel import Book
from gigui.output.html import out_html
from gigui.output.outbase import TableStatsRows
from gigui.repo import GIRepo, get_repos, total_len
from gigui.typedefs import FileStr, Html

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = logging.getLogger(__name__)


def open_files(fstrs: list[str]):
    """
    Ask the OS to open the given html filenames.

    :param fstrs: The file paths to open.
    """
    if fstrs:
        match platform.system():
            case "Darwin":
                subprocess.run(["open"] + fstrs, check=True)
            case "Linux":
                subprocess.run(["xdg-open"] + fstrs, check=True)
            case "Windows":
                if len(fstrs) != 1:
                    raise RuntimeError(
                        "Illegal attempt to open multiple html files at once on Windows."
                    )

                # First argument "" is the title for the new command prompt window.
                subprocess.run(["start", "", fstrs[0]], check=True)

            case _:
                raise RuntimeError(f"Unknown platform {platform.system()}")


def log_endtime(start_time: float):
    """
    Output a log entry to the log of the currently amount of passed time since 'start_time'.
    """
    end_time = time.time()
    log(f"Done in {end_time - start_time:.1f} s")


def get_outfile_name(fix: str, outfile_base: str, repo_name: str) -> FileStr:
    base_name = Path(outfile_base).name
    if fix == Keys.prefix:
        outfile_name = repo_name + "-" + base_name
    elif fix == Keys.postfix:
        outfile_name = base_name + "-" + repo_name
    else:
        outfile_name = base_name
    return outfile_name


def get_output_file_and_webview_data(
    args: Args, repo: GIRepo, len_repos: int, outfilestr: str, out_format: str
):
    file_to_open: FileStr = ""
    webview_data: tuple[str, str] = "", ""
    if len_repos == 1:
        match out_format:
            case "html":
                file_to_open = outfilestr + ".html"
            case "excel":
                file_to_open = outfilestr + ".xlsx"
            case "auto":
                html_code = out_html(repo, outfilestr, args.blame_skip)
                webview_data = html_code, repo.name
    else:  # multiple repos
        if (
            len_repos <= MAX_BROWSER_TABS
            and out_format in {"auto", "html"}
            and args.viewer == AUTO
        ):
            file_to_open = outfilestr + ".html"
    return file_to_open, webview_data


def write_repo_output(  # pylint: disable=too-many-locals
    args: Args,
    repo: GIRepo,
    len_repos: int,  # Total number of repositories being analyzed
    outfile_base: str,
    gui_window: sg.Window | None = None,
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
            out_rows = TableStatsRows(repo)
            book = Book(outfilestr, out_rows, repo.args.subfolder)
            book.add_authors_sheet()
            book.add_authors_files_sheet()
            book.add_files_authors_sheet()
            book.add_files_sheet()
            if not args.blame_skip:
                book.add_blame_sheets()
            book.close()

    # Write the HTML file if requested.
    if "html" in formats or (
        formats == ["auto"]
        and (len_repos > 1 or len_repos == 1 and args.viewer == NONE)
    ):
        logfile(f"{outfile_name}.html")
        if args.dry_run == 0:
            html_code = out_html(repo, outfilestr, args.blame_skip)
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

    if len_repos == 1 and out_format == "auto" and gui_window:
        html_code = out_html(repo, outfilestr, args.blame_skip)
        gui_window.write_event_value(Keys.open_webview, (html_code, repo.name))
        return [], "", ("", "")

    file_to_open, webview_data = get_output_file_and_webview_data(
        args, repo, len_repos, outfilestr, out_format
    )

    return files_to_log, file_to_open, webview_data


def init_classes(args: Args):
    GIRepo.set_args(args)
    FileStat.show_renames = args.show_renames
    Person.show_renames = args.show_renames
    Person.ex_author_patterns = args.ex_authors
    Person.ex_email_patterns = args.ex_emails
    outbase.deletions = args.deletions
    outbase.scaled_percentages = args.scaled_percentages
    outbase.subfolder = args.subfolder


# Process multiple repos in single core mode.
def handle_repos(
    repos: list[GIRepo],
    len_repos: int,
    outfile_base: str,
    count: int,
    gui_window: sg.Window | None,
) -> tuple[int, list[FileStr]]:
    log("Output in folder " + str(repos[0].path.parent))
    with ThreadPoolExecutor(max_workers=5) as thread_executor:
        files_to_open = []
        for repo in repos:
            dryrun = repo.args.dry_run
            log(f"    {repo.name} repository ({count} of {len_repos})")
            if dryrun == 2:
                continue

            # dryrun == 0 or dryrun == 1
            stats_found = repo.run(thread_executor)
            log("        ", end="")
            if not stats_found:
                log("No statistics matching filters found")
            else:  # stats found
                if dryrun == 1:
                    log("")
                else:  # dryrun == 0
                    _, file_to_open, _ = write_repo_output(
                        repo.args,
                        repo,
                        len_repos,
                        outfile_base,
                        gui_window,
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


# Process a single repository in case len(repos) == 1 which also means that
# args.multi_core is False.
def process_len1_repo(
    args: Args,
    repo: GIRepo,
    outfile_base: str,
    gui_window: sg.Window | None,
    start_time: float,
):
    args.multi_core = False
    file_to_open = ""
    html_code = ""
    name = ""

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
                    _, file_to_open, (html_code, name) = write_repo_output(
                        args,
                        repo,
                        1,
                        outfile_base,
                        gui_window,
                    )
            else:
                log("No statistics matching filters found")
    log_endtime(start_time)
    if file_to_open:
        open_files([file_to_open])
    elif html_code:
        open_webview(html_code, name)


def process_repos_on_main_thread(
    args: Args,
    repo_lists: list[list[GIRepo]],
    len_repos: int,
    outfile_base: FileStr,
    gui_window: sg.Window | None,
    start_time: float,
):
    if len_repos == 1:
        process_len1_repo(
            args,
            repo_lists[0][0],
            outfile_base,
            gui_window,
            start_time,
        )
    elif len_repos > 1:
        count = 1
        runs = 0
        while repo_lists:
            repos = repo_lists.pop(0)
            count, files_to_open = handle_repos(
                repos,
                len_repos,
                outfile_base,
                count,
                gui_window,
            )
            runs += 1
        log_endtime(start_time)
        if runs == 1 and files_to_open:  # type: ignore
            open_files(files_to_open)


def process_repo_in_process_pool(
    args: Args,
    repo: GIRepo,
    len_repos: int,
    outfile_base: str,
    gui_window: sg.Window | None,
) -> tuple[bool, list[str]]:
    init_classes(args)
    with ThreadPoolExecutor(max_workers=5) as thread_executor:
        dryrun = repo.args.dry_run
        stats_found = False
        files_to_log = []
        if dryrun <= 1:
            stats_found = repo.run(thread_executor)
        if dryrun == 0 and stats_found:
            files_to_log, _, _ = write_repo_output(
                repo.args,
                repo,
                len_repos,
                outfile_base,
                gui_window,
            )
    return stats_found, files_to_log


# Process multiple repositories in case len(repos) > 1 on multiple cores.
def process_multi_repos_multi_core(
    args: Args,
    repo_lists: list[list[GIRepo]],
    len_repos: int,
    outfile_base: FileStr,
    gui_window: sg.Window | None,
    start_time: float,
):
    with ProcessPoolExecutor() as process_executor:
        future_to_repo = {
            process_executor.submit(
                process_repo_in_process_pool,
                args,
                repo,
                len_repos,
                outfile_base,
                gui_window,
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
        log_endtime(start_time)


def main(args: Args, start_time: float, gui_window: sg.Window | None = None):
    profiler = None
    if args.profile:
        profiler = Profile()
        profiler.enable()

    logger.info(f"{args = }")
    init_classes(args)
    repo_lists: list[list[GIRepo]] = []

    for fstr in args.input_fstrs:
        repo_lists.extend(get_repos(fstr, args.depth))
    len_repos = total_len(repo_lists)
    fix_ok = not (len_repos == 1 and args.fix == Keys.nofix)

    if repo_lists and fix_ok:
        outfile_base = args.outfile_base if args.outfile_base else DEFAULT_FILE_BASE
        if not args.format:
            args.format = [DEFAULT_FORMAT]

        if not args.multi_core or len_repos == 1:  # Process on main_thread
            process_repos_on_main_thread(
                args, repo_lists, len_repos, outfile_base, gui_window, start_time
            )
        else:
            # Process multiple repos on multi cores
            # gui_window is not passed as argument to process_multi_repos_multi_core
            # because gui_window.write_event_value only works on the main thread.
            process_multi_repos_multi_core(
                args, repo_lists, len_repos, outfile_base, gui_window, start_time
            )

        out_profile(args, profiler)
    elif not fix_ok:
        log(
            "Multiple repos detected and nofix option selected."
            "Multiple repos need the (default prefix) or postfix option."
        )
    else:  # repos is empty
        log("Found no repositories")


def out_profile(args, profiler):
    def log_profile(profile: Profile, sort: str):
        iostream = StringIO()
        stats = Stats(profile, stream=iostream).strip_dirs()
        stats.sort_stats(sort).print_stats(args.profile)
        s = iostream.getvalue()
        log(s)

    if args.profile:
        assert profiler is not None
        log("Profiling results:")
        profiler.disable()
        if 0 < args.profile < 100:
            log_profile(profiler, "cumulative")
            log_profile(profiler, "time")
        else:
            stats = Stats(profiler).strip_dirs()
            log("printing to: gigui.prof")
            stats.dump_stats("gigui.prof")
