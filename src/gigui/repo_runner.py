import threading
from logging import getLogger
from queue import Queue

from gigui import _logging
from gigui.args_settings import Args, MiniRepo
from gigui.constants import DYNAMIC
from gigui.data import FileStat, Person
from gigui.output.repo_excel import Book
from gigui.output.repo_html_server import RepoHTMLServer
from gigui.typedefs import FileStr
from gigui.utils import get_outfile_name, log, log_analysis_end_time, open_file

# For multicore, logger is set in process_repo_multicore().
logger = getLogger(__name__)


class RepoRunner(RepoHTMLServer, Book):
    def __init__(
        self,
        mini_repo: MiniRepo,
        server_started_event: threading.Event,
        server_done_event: threading.Event,
        stop_all_event: threading.Event,
        host_port_queue: Queue,
    ) -> None:
        super().__init__(
            mini_repo,
            server_started_event,
            server_done_event,
            stop_all_event,
            host_port_queue,
        )
        self.init_class_options(mini_repo.args)

    def init_class_options(self, args: Args) -> None:
        Person.show_renames = args.show_renames
        Person.ex_author_patterns = args.ex_authors
        Person.ex_email_patterns = args.ex_emails
        FileStat.show_renames = args.show_renames

    def process_repo_single_core(
        self,
        len_repos: int,  # Total number of repositories being analyzed
        start_time: float | None = None,
    ) -> None:
        stats_found = self.run_analysis()
        if len_repos == 1:
            log_analysis_end_time(start_time)  # type: ignore
        if stats_found:
            if self.args.dry_run == 1:
                log("")
            else:  # args.dry_run == 0
                self._generate_output()
        else:
            self.server_done_event.set()
            log(" " * 8 + "No statistics matching filters found")

    def _generate_output(self) -> None:  # pylint: disable=too-many-locals
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

        # In dry-run, there is nothing to show.
        if not self.args.dry_run == 0:
            return

        outfile_name = get_outfile_name(
            self.args.fix, self.args.outfile_base, self.name
        )
        outfilestr = str(self.path.parent / outfile_name)

        if self.args.formats:
            # Write the excel file if requested.
            if "excel" in self.args.formats:
                logfile(f"{outfile_name}.xlsx")
                if self.args.multithread:
                    threading.Thread(target=self.run_excel, args=(outfilestr,)).start()
                else:
                    self.run_excel(outfilestr)

            # Write the HTML file if requested.
            if "html" in self.args.formats:
                logfile(f"{outfile_name}.html")
                if self.args.multithread:
                    threading.Thread(
                        target=self._write_excel, args=(outfilestr,)
                    ).start()
                else:
                    self._write_excel(outfilestr)

            logger.info(" " * 4 + f"Close {self.name}")

            if self.args.view:
                if "excel" in self.args.formats:
                    open_file(outfilestr + ".xlsx")

                if "html" in self.args.formats and self.args.blame_history != DYNAMIC:
                    open_file(outfilestr + ".html")
                    return

        elif self.args.view:
            html_code = self.get_html()
            log(" " * 4 + f"View {self.name}")
            self.start_werkzeug_server_with_html(html_code)

    def _write_excel(self, outfilestr: FileStr) -> None:
        html_code = self.get_html()
        with open(outfilestr + ".html", "w", encoding="utf-8") as f:
            f.write(html_code)


def process_repo_multicore(
    mini_repo: MiniRepo,
    server_started_event: threading.Event,
    server_done_event: threading.Event,
    stop_all_event: threading.Event,
    host_port_queue: Queue,
) -> bool:
    global logger
    _logging.set_logging_level_from_verbosity(mini_repo.args.verbosity)
    logger = getLogger(__name__)
    try:
        repo = RepoRunner(
            mini_repo,
            server_started_event,
            server_done_event,
            stop_all_event,
            host_port_queue,
        )
        log(" " * 4 + f"Start {mini_repo.name}")
        stats_found: bool = repo.run_analysis()
        if stats_found:
            repo._generate_output()
        elif mini_repo.args.dry_run <= 1:
            server_started_event.set()
            server_done_event.set()
            log(
                " " * 8 + "No statistics matching filters found for "
                f"repository {mini_repo.name}"
            )
    except Exception as e:
        logger.error(f"Error in {mini_repo.name}: {e}")
        return False
    return stats_found
