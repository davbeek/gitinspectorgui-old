import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import PySimpleGUI as sg  # type: ignore[import-untyped]

from gigui.args_settings import Args
from gigui.constants import DYNAMIC, NONE, STATIC
from gigui.data import FileStat, Person
from gigui.keys import Keys
from gigui.output.repo_excel import Book
from gigui.output.repo_html_server import RepoHTMLServer
from gigui.typedefs import FileStr
from gigui.utils import get_outfile_name, log, log_end_time, open_file, open_webview

logger = logging.getLogger(__name__)


# RepoGI = Repo GitInspector
class RepoGIGUI(RepoHTMLServer, Book):
    def __init__(self, name: str, location: Path, args: Args) -> None:
        super().__init__(name, location, args)
        self._init_class_options()

    def run_repo(
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
            if self.args.dry_run == 1:
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

    def _init_class_options(self) -> None:
        Person.show_renames = self.args.show_renames
        Person.ex_author_patterns = self.args.ex_authors
        Person.ex_email_patterns = self.args.ex_emails
        FileStat.show_renames = self.args.show_renames

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
                ("\n" if self.args.multicore and self.args.verbosity == 0 else "")
                + " " * 8
                + fname
            )

        if not self.authors_included:
            return

        outfile_name = get_outfile_name(
            self.args.fix, self.args.outfile_base, self.name
        )
        outfilestr = str(self.path.parent / outfile_name)

        # Write the excel file if requested.
        if "excel" in self.args.formats:
            logfile(f"{outfile_name}.xlsx")
            if self.args.dry_run == 0:
                self.run_excel(outfilestr)

        # Write the HTML file if requested.
        if "html" in self.args.formats:
            logfile(f"{outfile_name}.html")
            if self.args.dry_run == 0:
                html_code = self.get_html()
                with open(outfilestr + ".html", "w", encoding="utf-8") as f:
                    f.write(html_code)

        logger.info(" " * 4 + f"Close {self.name}")

        if len_repos == 1:
            log_end_time(start_time)  # type: ignore

        # In dry-run, there is nothing to show.
        if not self.args.dry_run == 0:
            return

        # If the result files should not be viewed, we're done.
        if not self.args.view:
            return

        # args.view is True here, so we open the files.
        if "excel" in self.args.formats:
            open_file(outfilestr + ".xlsx")

        if "html" in self.args.formats and self.args.blame_history != DYNAMIC:
            open_file(outfilestr + ".html")
            return

        if self.args.formats:
            return

        # The following holds: args.view and not args.formats and "no dry run"
        html_code = self.get_html()
        if len_repos == 1 and self.args.blame_history in {NONE, STATIC}:
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
