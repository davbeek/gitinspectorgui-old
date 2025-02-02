from logging import getLogger

from gigui._logging import log
from gigui.args_settings import Args
from gigui.constants import AUTO, NONE
from gigui.data import FileStat, IniRepo, Person, RunnerQueues
from gigui.keys import Keys
from gigui.output.repo_excel import Book
from gigui.output.repo_html_server import RepoHTMLServer
from gigui.typedefs import FileStr
from gigui.utils import get_outfile_name, open_file

# For multicore, logger is set in process_repo_multicore().
logger = getLogger(__name__)


class RepoRunner(RepoHTMLServer, Book):
    def __init__(
        self,
        ini_repo: IniRepo,
        queues: RunnerQueues,
    ) -> None:
        super().__init__(
            ini_repo,
            queues,
        )
        assert ini_repo.args is not None
        self.init_class_options(ini_repo.args)

    def init_class_options(self, args: Args) -> None:
        Person.show_renames = args.show_renames
        Person.ex_author_patterns = args.ex_authors
        Person.ex_email_patterns = args.ex_emails
        FileStat.show_renames = args.show_renames

    def process_repo(self) -> None:
        log(" " * 4 + f"{self.name}" + (": start" if self.args.multicore else ""))
        stats_found = self.run_analysis()
        if not stats_found:
            if self.args.dry_run <= 1:
                log(" " * 8 + "No statistics matching filters found")
            self.queues.task_done.put(self.name)
            self.queues.repo_done.put(self.name)
        else:
            if self.args.dry_run == 0:
                self.generate_output()

    def generate_output(self) -> None:  # pylint: disable=too-many-locals
        """
        Generate result file(s) for the analysis of the given repository.

        :return: Files that should be logged
        """

        def logfile(fname: FileStr):
            log(" " * 8 + fname)

        if not self.authors_included:
            return

        # In dry-run, there is nothing to show.
        if not self.args.dry_run == 0:
            return

        outfile_name = get_outfile_name(
            self.args.fix, self.args.outfile_base, self.name
        )
        outfilestr = str(self.path.parent / outfile_name)
        if self.args.file_formats:
            # Write the excel file if requested.
            if Keys.excel in self.args.file_formats:
                logfile(f"{outfile_name}.xlsx")
                self.run_excel(outfilestr)
            # Write the HTML file if requested.
            if (
                Keys.html in self.args.file_formats
                or Keys.html_blame_history in self.args.file_formats
            ):
                logfile(f"{outfile_name}.html")
                html_code = self.get_html()
                with open(outfilestr + ".html", "w", encoding="utf-8") as f:
                    f.write(html_code)
            self.queues.task_done.put(self.name)

        if self.args.view == AUTO and self.args.file_formats:
            if Keys.excel in self.args.file_formats:
                open_file(outfilestr + ".xlsx")
            if (
                Keys.html in self.args.file_formats
                or Keys.html_blame_history in self.args.file_formats
            ):
                open_file(outfilestr + ".html")
            self.queues.repo_done.put(self.name)
        elif not self.args.view == NONE:
            html_code = self.get_html()
            self.start_werkzeug_server_with_html(html_code)
        else:
            self.queues.repo_done.put(self.name)

    def join_threads(self) -> None:
        # server thread is joined in monitor_events()
        if self.monitor_thread is not None:
            self.monitor_thread.join()
