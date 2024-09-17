import logging
import os
import platform
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from cProfile import Profile
from io import StringIO
from pathlib import Path
from pstats import Stats

import PySimpleGUI as sg
from bs4 import BeautifulSoup

from gigui.args_settings_keys import AUTO, NONE, Args, Keys
from gigui.common import log, open_webview
from gigui.constants import DEFAULT_FILE_BASE, DEFAULT_FORMAT, MAX_BROWSER_TABS
from gigui.data import FileStat, Person
from gigui.html_modifier import HTMLModifier
from gigui.output import outbase
from gigui.output.excel import Book
from gigui.output.htmltable import HTMLTable
from gigui.repo import GIRepo, get_repos, total_len
from gigui.typedefs import FileStr

logger = logging.getLogger(__name__)


def openfiles(fstrs: list[str]):
    if fstrs:
        files = " ".join([f'"{fstr}"' for fstr in fstrs])
        match platform.system():
            case "Darwin":
                os.system(f"open {files}")  # add quotes to handle spaces in path
            case "Linux":
                os.system(f"xdg-open {files}")
            case "Windows":
                if len(fstrs) == 1:
                    # The start command treats the first set of double quotes as the
                    # title for the new command prompt window that is opened. If your
                    # file path contains spaces and you don't provide an empty set of
                    # quotes, start will mistakenly treat the part of the file path up
                    # to the first space as the title, and the rest as the command to
                    # execute or file to open, which will likely result in an error.
                    os.system(f'start "" {fstrs[0]}')
                else:
                    raise RuntimeError(
                        "Illegal attempt to open multiple html files at once on Windows."
                    )
            case _:
                raise RuntimeError(f"Unknown platform {platform.system()}")


def out_html(repo: GIRepo, outfilestr: str, blame_skip: bool) -> str:
    module_parent = Path(__file__).resolve().parent
    html_path = module_parent / "output/files/template.html"
    with open(html_path, "r") as f:
        html_template = f.read()

    htmltable = HTMLTable(outfilestr)
    authors_html = htmltable.add_authors_table(repo.out_authors_stats())
    authors_files_html = htmltable.add_authors_files_table(
        repo.out_authors_files_stats()
    )
    files_authors_html = htmltable.add_files_authors_table(
        repo.out_files_authors_stats()
    )
    files_html = htmltable.add_files_table(repo.out_files_stats())

    html = html_template.replace("__TITLE__", f"{repo.name} viewer")
    html = html.replace("__AUTHORS__", authors_html)
    html = html.replace("__AUTHORS_FILES__", authors_files_html)
    html = html.replace("__FILES_AUTHORS__", files_authors_html)
    html = html.replace("__FILES__", files_html)

    if not blame_skip:
        blames_htmls = htmltable.add_blame_tables(repo.out_blames(), repo.subfolder)
        html_modifier = HTMLModifier(html)
        html = html_modifier.add_blame_tables_to_html(blames_htmls)

    soup = BeautifulSoup(html, "html.parser")
    return soup.prettify(formatter="html")


def log_endtime(start_time: float):
    end_time = time.time()
    log(f"Done in {end_time - start_time:.1f} s")


def write_repo_output(
    args: Args,
    repo: GIRepo,
    len_repos: int,
    outfile_base: str,
    gui_window: sg.Window | None = None,
) -> tuple[list[FileStr], FileStr, tuple[str, str]]:

    def logfile(fname: FileStr):
        nonlocal files_to_log
        if args.multi_core:
            if not files_to_log:
                files_to_log = [fname]
            else:
                files_to_log.append(fname)
        else:  # single-core
            log(fname, end=" ")

    # For not args.multi_core, log the filename and end with a space, because more formats may
    # be selected by the "-F" option, these output files are printed on the same line
    # separated by a space. At the end of all outputs, a newline is printed by log("")

    # For multi-core, logging is not be done immediately, but all output files are saved
    # in the (non-local) output string filestr.
    files_to_log: list[FileStr] = []
    file_to_open: FileStr = ""
    webview_htmlcode_name: tuple[str, str] = "", ""
    formats = args.format
    if repo.authors_included and len(formats):
        base_name = Path(outfile_base).name
        if args.fix == Keys.prefix:
            outfile_name = repo.name + "-" + base_name
        elif args.fix == Keys.postfix:
            outfile_name = base_name + "-" + repo.name
        else:
            outfile_name = base_name
        repo_parent = Path(repo.gitrepo.working_dir).parent
        outfile = repo_parent / outfile_name
        outfilestr = str(outfile)
        if "excel" in formats:
            logfile(f"{outfile_name}.xlsx")
            if args.dry_run == 0:
                book = Book(outfilestr)
                book.add_authors_sheet(repo.out_authors_stats())
                book.add_authors_files_sheet(repo.out_authors_files_stats())
                book.add_files_authors_sheet(repo.out_files_authors_stats())
                book.add_files_sheet(repo.out_files_stats())
                if not args.blame_skip:
                    book.add_blame_sheets(repo.out_blames(), repo.subfolder)
                book.close()
        if "html" in formats or (
            formats == ["auto"]
            and (len_repos > 1 or len_repos == 1 and args.viewer == NONE)
        ):
            logfile(f"{outfile_name}.html")
            if args.dry_run == 0:
                html_code = out_html(repo, outfilestr, args.blame_skip)
                with open(outfilestr + ".html", "w") as f:
                    f.write(html_code)
        if not args.multi_core:
            log("")
        assert len(formats) > 0
        if len(formats) == 1 and not args.profile and not args.viewer == NONE:
            format = formats[0]
            if len_repos == 1 and args.dry_run == 0:
                match format:
                    case "html":
                        file_to_open = outfilestr + ".html"
                    case "excel":
                        file_to_open = outfilestr + ".xlsx"
                    case "auto":
                        html_code = out_html(repo, outfilestr, args.blame_skip)
                        if gui_window:
                            gui_window.write_event_value(
                                Keys.open_webview, (html_code, repo.name)
                            )
                        else:
                            webview_htmlcode_name = html_code, repo.name
            else:  # multiple repos
                if (
                    len_repos <= MAX_BROWSER_TABS
                    and (format == "auto" or format == "html")
                    and args.viewer == AUTO
                    and args.dry_run == 0
                ):
                    file_to_open = outfilestr + ".html"
    return files_to_log, file_to_open, webview_htmlcode_name


def init_classes(args: Args):
    GIRepo.set_args(args)
    FileStat.show_renames = args.show_renames
    Person.show_renames = args.show_renames
    Person.ex_author_patterns = args.ex_authors
    Person.ex_email_patterns = args.ex_emails
    outbase.deletions = args.deletions
    outbase.scaled_percentages = args.scaled_percentages


def process_repos_on_main_thread(
    args: Args,
    repo_lists: list[list[GIRepo]],
    len_repos: int,
    outfile_base: FileStr,
    gui_window: sg.Window | None,
    start_time: float,
):

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
        html = ""
        name = ""

        log("Output in folder " + str(repo.path.parent))
        log(f"    {repo.name} repository ({1} of {1}) ")
        with ThreadPoolExecutor(max_workers=6) as thread_executor:
            # repo.set_thread_executor(thread_executor)
            if args.dry_run <= 1:
                stats_found = repo.calculate_stats(thread_executor)
                if stats_found:
                    if args.dry_run == 1:
                        log("")
                    else:  # args.dry_run == 0
                        log("        ", end="")
                        _, file_to_open, (html, name) = write_repo_output(
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
            openfiles([file_to_open])
        elif html:
            open_webview(html, name)

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
                else:  # dryrun == 0 or dryrun == 1
                    stats_found = repo.calculate_stats(thread_executor)
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
                                    openfiles([file_to_open])
                                else:
                                    files_to_open.append(file_to_open)
                count += 1
        return count, files_to_open

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
            openfiles(files_to_open)


def process_repo_in_process_pool(
    args: Args,
    repo: GIRepo,
    len_repos: int,
    outfile_base: str,
    gui_window: sg.Window | None,
) -> tuple[bool, list[str]]:
    init_classes(args)
    files_to_log = ""
    with ThreadPoolExecutor(max_workers=5) as thread_executor:
        dryrun = repo.args.dry_run
        stats_found = False
        files_to_log = []
        if dryrun <= 1:
            stats_found = repo.calculate_stats(thread_executor)
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
