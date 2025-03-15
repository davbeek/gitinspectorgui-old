from logging import getLogger
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from gigui._logging import log
from gigui.args_settings import Args
from gigui.constants import AUTO, DYNAMIC_BLAME_HISTORY
from gigui.data import FileStat, IniRepo, Person
from gigui.keys import Keys
from gigui.output.repo_excel import Book
from gigui.output.repo_html import RepoBlameTablesSoup, RepoHTML
from gigui.runner_queues import RunnerQueues
from gigui.typedefs import FileStr, HtmlStr
from gigui.utils import get_outfile_name

# For multicore, logger is set in process_repo_multicore().
logger = getLogger(__name__)


class RepoRunner(RepoBlameTablesSoup, RepoHTML, Book):
    def __init__(
        self,
        ini_repo: IniRepo,
        queues: RunnerQueues,
    ) -> None:
        RepoBlameTablesSoup.__init__(self, ini_repo)
        Book.__init__(self, ini_repo)
        assert ini_repo.args is not None
        self.browser_id: str = ""  # used only for localhost server
        self.queues: RunnerQueues = queues
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
            if self.args.dryrun <= 1:
                log(" " * 8 + "No statistics matching filters found")
            self.queues.task_done.put(self.name)
            if self.args.view == AUTO and self.args.file_formats:
                self.queues.open_file.put((self.name, None))  # type: ignore
            elif self.args.view == AUTO:
                self.queues.html.put((self.name, None))  # type: ignore
            elif self.args.view == DYNAMIC_BLAME_HISTORY:
                self.queues.html.put((self, None))  # type: ignore
        else:
            if self.args.dryrun == 0:
                self.generate_output()

    def generate_output(self) -> None:  # pylint: disable=too-many-locals
        def logfile(fname: FileStr):
            log(" " * 8 + fname)

        if not self.authors_included:
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
            if Keys.html in self.args.file_formats:
                logfile(f"{outfile_name}.html")
                html_code = self.get_html()
                with open(outfilestr + ".html", "w", encoding="utf-8") as f:
                    f.write(html_code)
            self.queues.task_done.put(self.name)

        if self.args.view == AUTO and self.args.file_formats:
            if Keys.excel in self.args.file_formats:
                self.queues.open_file.put((self.name, outfilestr + ".xlsx"))
            if Keys.html in self.args.file_formats:
                self.queues.open_file.put((self.name, outfilestr + ".html"))
        elif self.args.view == AUTO:  # not self.args.file_formats
            self.queues.task_done.put(self.name)
            html_code = self.get_html()
            self.queues.html.put((self.name, html_code))  # type: ignore
        elif self.args.view == DYNAMIC_BLAME_HISTORY:
            self.queues.task_done.put(self.name)
            html_code = self.get_html()
            self.queues.html.put((self, html_code))  # type: ignore
        else:  # self.args.view == NONE
            # Assume that self.args.file_formats is not empty here otherwise this method
            # would not have been called.
            pass
        if (
            self.args.verbosity == 0
            and not self.args.file_formats
            and not self.args.multicore
        ):
            # print new line, because output file with new line was not printed after
            # the dots.
            log("")  # Uncommented logging statement

    def get_html(self) -> HtmlStr:
        # Load the template file.
        module_dir = Path(__file__).resolve().parent
        html_path = module_dir / "output" / "static" / "template.html"
        with open(html_path, "r", encoding="utf-8") as f:
            html_template = f.read()

        if Keys.html in self.args.file_formats:
            # If blame_history_dynamic, create_html_document is called in repo_html_server.py
            html_template = RepoHTML.create_html_document(
                self.args, html_template, RepoHTML.load_css()
            )

        self.global_soup = BeautifulSoup(html_template, "html.parser")
        soup = self.global_soup

        title_tag: Tag = soup.find(name="title")  # type: ignore
        title_tag.string = f"{self.name} viewer"

        authors_tag: Tag = soup.find(id="authors")  # type: ignore
        authors_tag.append(self.get_authors_soup())

        authors_files_tag: Tag = soup.find(id="authors-files")  # type: ignore
        authors_files_tag.append(self.get_authors_files_soup())

        files_authors_tag: Tag = soup.find(id="files-authors")  # type: ignore
        files_authors_tag.append(self.get_files_authors_soup())

        files_tag: Tag = soup.find(id="files")  # type: ignore
        files_tag.append(self.get_files_soup())

        # Add blame output if not skipped.
        if not self.args.blame_skip:
            self.add_blame_tables_soup()

        html: HtmlStr = str(soup)
        html = html.replace("&amp;nbsp;", "&nbsp;")
        html = html.replace("&amp;lt;", "&lt;")
        html = html.replace("&amp;gt;", "&gt;")
        html = html.replace("&amp;quot;", "&quot;")
        return html
