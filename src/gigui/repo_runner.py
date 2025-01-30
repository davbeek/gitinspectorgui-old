from logging import getLogger

from gigui._logging import log
from gigui.args_settings import Args
from gigui.constants import DYNAMIC
from gigui.data import FileStat, IniRepo, Person, RunnerQueues
from gigui.output.repo_excel import Book
from gigui.output.repo_html_server import RepoHTMLServer
from gigui.typedefs import FileStr
from gigui.utils import get_outfile_name, log_analysis_end_time, open_file

# For multicore, logger is set in process_repo_multicore().
logger = getLogger(__name__)


class RepoRunner(RepoHTMLServer, Book):
    def __init__(
        self,
        ini_repo: IniRepo,
        queues: RunnerQueues,
        len_repos: int,
    ) -> None:
        super().__init__(
            ini_repo,
            queues,
            len_repos,
        )
        assert ini_repo.args is not None
        self.init_class_options(ini_repo.args)

    def init_class_options(self, args: Args) -> None:
        Person.show_renames = args.show_renames
        Person.ex_author_patterns = args.ex_authors
        Person.ex_email_patterns = args.ex_emails
        FileStat.show_renames = args.show_renames

    def process_repo(
        self,
        len_repos: int,  # Total number of repositories being analyzed
        start_time: float | None = None,
    ) -> None:
        task_done_nr: int

        log(" " * 4 + f"{self.name}")
        stats_found = self.run_analysis()
        task_done_nr = self.get_task_done_nr()
        if not stats_found:
            self.get_repo_done_nr()
            if self.args.dry_run <= 1:
                log(" " * 8 + "No statistics matching filters found")
        if task_done_nr == len_repos:  # All repositories have been analyzed
            log_analysis_end_time(start_time)  # type: ignore
        if stats_found:
            if self.args.dry_run == 0:
                self.generate_output()
        log(
            f"    {self.name}:"
            + (f" {task_done_nr} of {len_repos}" if len_repos > 1 else "")
        )

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
        if self.args.formats:
            # Write the excel file if requested.
            if "excel" in self.args.formats:
                logfile(f"{outfile_name}.xlsx")
                self.run_excel(outfilestr)
            # Write the HTML file if requested.
            if "html" in self.args.formats:
                logfile(f"{outfile_name}.html")
                html_code = self.get_html()
                with open(outfilestr + ".html", "w", encoding="utf-8") as f:
                    f.write(html_code)

            if self.args.view:
                if "excel" in self.args.formats:
                    open_file(outfilestr + ".xlsx")
                if "html" in self.args.formats and self.args.blame_history != DYNAMIC:
                    open_file(outfilestr + ".html")

        elif self.args.view:
            html_code = self.get_html()
            self.start_werkzeug_server_with_html(html_code)
