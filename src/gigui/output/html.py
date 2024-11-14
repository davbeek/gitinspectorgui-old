import logging

# Add these imports
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from gigui.constants import DYNAMIC, HIDE, NONE, SHOW, STATIC
from gigui.output.blame_rows import (
    BlameHistoryRows,
    BlameRows,
    header_blames,
    string2truncated,
)
from gigui.output.stat_rows import (
    AuthorsFilesTableRows,
    AuthorsTableRows,
    FilesAuthorsTableRows,
    FilesTableRows,
    header_authors,
    header_authors_files,
    header_files,
    header_files_authors,
)
from gigui.repo import GIRepo
from gigui.typedefs import Author, FileStr, Html, Row, SHALong
from gigui.utils import get_relative_fstr, log

MAX_LENGTH_TAB_NAME = 160

HEADER_CLASS_DICT: dict[str, str] = {
    "ID": "id_col",
    "Author": "author-col",
    "Empty": "empty-col",
    "Email": "email-col",
    "File": "file-col",
    "% Lines": "p-lines-col number-col",
    "% Insertions": "p-insertions-col number-col",
    "% Scaled Lines": "ps-lines-col number-col",
    "% Scaled Insertions": "ps-insertions-col number-col",
    "Lines": "lines-col number-col",
    "Insertions": "insertions-col number-col",
    "Stability": "stability-col number-col",
    "Commits": "commits-col number-col",
    "Deletions": "deletions-col number-col",
    "Age Y:M:D": "age-col number-col",
    "Date": "date-col",
    "Message": "message-col",
    "SHA": "sha-col number-col",
    "Commit number": "commit-number-col number-col",
    "Line": "line-col number-col",
    "Code": "code-col",
}

BG_AUTHOR_COLORS: list[str] = [
    "bg-white",
    "bg-author-light-green",
    "bg-author-light-blue",
    "bg-author-light-red",
    "bg-author-light-yellow",
    "bg-author-light-orange",
    "bg-author-light-purple",
    "bg-author-light-grey",
    "bg-row-light-green",
]

BG_ROW_COLORS: list[str] = ["bg-row-light-green", "bg-white"]

logger = logging.getLogger(__name__)

# Global definition of the current repository. Defined in this module instead of in
# shared_data to prevent circular imports.
current_repo: GIRepo


class TableRootSoup:
    def __init__(self, repo: GIRepo) -> None:
        self.repo: GIRepo = repo

    def _get_color_for_author(self, author: Author) -> str:
        author_nr = self.repo.author_star2nr[author]
        return BG_AUTHOR_COLORS[author_nr % len(BG_AUTHOR_COLORS)]

    def _get_color_for_sha_nr(self, sha_nr: int) -> str:

        sha = self.repo.nr2sha[sha_nr]
        author = self.repo.sha2author[sha]
        color_class = self._get_color_for_author(author)
        return color_class


class TableSoup(TableRootSoup):
    blame_exclusions: str
    empty_lines: bool
    subfolder: FileStr

    def __init__(self, repo: GIRepo) -> None:
        super().__init__(repo)

        self.soup = BeautifulSoup("<div></div>", "html.parser")

        self.author2color_class: dict[Author, str]

    def _add_header_row(self, header_row: list[str], table: Tag) -> None:
        thead: Tag = self.soup.new_tag("thead")
        thead["class"] = "sticky headerRow"
        tr = self.soup.new_tag("tr")
        tr["class"] = "bg-th-green"
        thead.append(tr)
        for column_header in header_row:
            header_class = HEADER_CLASS_DICT[column_header]
            header_string = "" if column_header == "Empty" else column_header
            th = self.soup.new_tag("th")
            th["class"] = header_class
            th.string = header_string
            if column_header == "Code":
                if self.blame_exclusions in {HIDE, SHOW}:
                    exclusions_button = self.soup.new_tag("button")
                    empty_lines_button = self.soup.new_tag("button")
                    if self.blame_exclusions == HIDE:
                        exclusions_button["class"] = "blame-exclusions-button pressed"
                        empty_lines_button["class"] = "blame-empty-lines-button pressed"
                    elif self.blame_exclusions == SHOW:
                        exclusions_button["class"] = "blame-exclusions-button"
                        empty_lines_button["class"] = "blame-empty-lines-button"
                    exclusions_button.string = "Hide blame exclusions"
                    empty_lines_button.string = "Hide empty lines"
                    th.append(exclusions_button)
                    th.append(empty_lines_button)

                button = self.soup.new_tag("button")
                button["class"] = "hide-colors-button"
                button.string = "Hide colors"
                th.append(button)
            thead.append(th)
        table.insert(0, thead)  # ensure thead comes before tbody


class StatTableSoup(TableSoup):
    def __init__(self, repo: GIRepo) -> None:
        super().__init__(repo)

        self.table: Tag = self.soup.new_tag("table")
        self.tbody: Tag = self.soup.new_tag("tbody")

        self.rows: list[Row]  # to be set by child classes

    def _add_colored_rows_table(
        self, header_row: list[str], bg_colors: list[str]
    ) -> None:
        self._add_header_row(header_row, self.table)
        for row in self.rows:
            tr = self.soup.new_tag("tr")
            tr["class"] = bg_colors[(int(row[0]) % len(bg_colors))]
            self.tbody.append(tr)
            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                td["class"] = HEADER_CLASS_DICT[header_row[i_col]]
                if header_row[i_col] == "Empty":
                    td.string = ""
                else:
                    td.string = str(data)
                tr.append(td)
        self.table.append(self.tbody)


class AuthorsTableSoup(StatTableSoup):
    def get_table(self) -> Tag:
        self.rows: list[Row] = AuthorsTableRows(self.repo).get_rows()
        self._add_colored_rows_table(
            header_authors(),
            BG_AUTHOR_COLORS,
        )
        return self.table


class AuthorsFilesTableSoup(StatTableSoup):
    def get_table(self) -> Tag:
        self.rows: list[Row] = AuthorsFilesTableRows(self.repo).get_rows()
        self._add_colored_rows_table(
            header_authors_files(),
            BG_AUTHOR_COLORS,
        )
        return self.table


class FilesAuthorsTableSoup(StatTableSoup):
    def get_table(self) -> Tag:  # pylint: disable=too-many-locals
        row_table = FilesAuthorsTableRows(self.repo)
        rows: list[Row] = row_table.get_rows()

        header_row: list[str] = header_files_authors()

        # pylint: disable=invalid-name
        ID_COL: int = header_row.index("ID")  # = 0
        FILE_COL: int = header_row.index("File")  # = 1
        AUTHOR_COL: int = header_row.index(
            "Author"
        )  # = 3, because of empty row between File and Author!!

        color_class: str
        author: Author

        self._add_header_row(header_row, self.table)

        first_file = True
        row_id = 0
        for row in rows:
            if row[ID_COL] != row_id:  # new ID value for new file
                first_file = True
                row_id = row[ID_COL]  # type: ignore

            tr = self.soup.new_tag("tr")
            tr["class"] = BG_ROW_COLORS[(int(row[ID_COL]) % len(BG_ROW_COLORS))]
            self.tbody.append(tr)

            author = row[AUTHOR_COL]  # type: ignore

            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                if i_col == ID_COL:
                    td["class"] = HEADER_CLASS_DICT[header_row[i_col]]
                    td.string = str(data)
                elif i_col == FILE_COL and first_file:
                    td["class"] = HEADER_CLASS_DICT[header_row[i_col]]
                    td.string = str(data)
                    first_file = False
                elif (
                    i_col == FILE_COL and not first_file or header_row[i_col] == "Empty"
                ):
                    td["class"] = HEADER_CLASS_DICT[header_row[i_col]]
                    td.string = ""
                else:
                    color_class = self._get_color_for_author(author)
                    td["class"] = (
                        f"{HEADER_CLASS_DICT[header_row[i_col]]} {color_class}"
                    )
                    td.string = str(data)
                tr.append(td)
        self.table.append(self.tbody)
        return self.table


class FilesTableSoup(StatTableSoup):
    def get_table(self) -> Tag:
        self.rows: list[Row] = FilesTableRows(self.repo).get_rows()
        self._add_colored_rows_table(header_files(), BG_ROW_COLORS)
        return self.table


class BlameBaseTableSoup(TableSoup):
    blame_history: str

    def get_table(
        self,
        rows: list[Row],
        iscomments: list[bool],
        fstr_nr: int = 0,
        sha_nr: int = 0,
    ) -> Tag:
        table: Tag = self.soup.new_tag("table")
        tbody: Tag = self.soup.new_tag("tbody")
        table.append(tbody)

        if self.blame_history == DYNAMIC:
            table["id"] = f"file-{fstr_nr}-sha-{sha_nr}"

        header_row = header_blames()
        self._add_header_row(header_row, table)

        bg_colors_cnt = len(BG_AUTHOR_COLORS)
        for row, is_comment in zip(rows, iscomments):
            tr = self.soup.new_tag("tr")
            tr["class"] = BG_AUTHOR_COLORS[(int(row[0]) % bg_colors_cnt)]
            tbody.append(tr)
            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                head = header_row[i_col]
                if head != "Code":
                    td["class"] = HEADER_CLASS_DICT[header_row[i_col]]
                else:  # head == "Code"
                    if data:
                        data = (
                            str(data)
                            .replace(" ", "&nbsp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace('"', "&quot;")
                        )
                    else:
                        # empty line of code
                        data = "&nbsp;"
                    if is_comment:
                        td["class"] = "comment-col"
                    else:
                        td["class"] = HEADER_CLASS_DICT[head]
                td.string = str(data)
                tr.append(td)
        return table


class BlameTableSoup(BlameBaseTableSoup):
    def get_fstr_table(self, fstr: FileStr) -> Tag | None:
        rows: list[Row]
        iscomments: list[bool]
        table: Tag | None

        rows, iscomments = BlameRows(self.repo).get_fstr_blame_rows(fstr)
        if not rows:
            log(f"No blame output matching filters found for file {fstr}")
            return None

        table = self.get_table(rows, iscomments)
        return table


class BlameHistoryStaticTableSoup(BlameBaseTableSoup):
    def __init__(self, repo: GIRepo) -> None:
        super().__init__(repo)
        self.fstr2shas: dict[FileStr, list[SHALong]] = self.repo.fstr2shas

    def get_fstr_tables(
        self, fstr: FileStr, sha2nr: dict[SHALong, int], blame_tab_index: int
    ) -> list[Tag]:
        tables: list[Tag] = []
        if fstr not in self.fstr2shas:
            return []

        for sha in self.fstr2shas[fstr]:
            rows, iscomments = BlameHistoryRows(self.repo).get_fstr_sha_blame_rows(
                fstr, sha
            )
            if not rows:
                continue

            nr = sha2nr[sha]
            table = self.get_table(rows, iscomments)
            table["id"] = f"file-{blame_tab_index}-sha-{nr}"
            tables.append(table)
        return tables


class BlameTablesSoup(TableRootSoup):
    subfolder: FileStr
    blame_history: str

    def __init__(self, repo: GIRepo, global_soup: BeautifulSoup) -> None:
        super().__init__(repo)
        self.global_soup = global_soup

    def add_tables(self) -> None:
        table: Tag | None
        tables: list[Tag]
        fstr2table: dict[FileStr, Tag] = {}
        fstr2tables: dict[FileStr, list[Tag]] = {}
        fstrs: list[FileStr] = []
        sha2nr: dict[SHALong, int] = self.repo.blame_reader.sha2nr
        nav_ul: Tag = self.global_soup.find(id="tab-buttons")  # type: ignore
        tab_div: Tag = self.global_soup.find(id="tab-contents")  # type: ignore

        blame_tab_index = 0
        for fstr in self.repo.fstrs:
            if self.blame_history == STATIC:
                tables = BlameHistoryStaticTableSoup(self.repo).get_fstr_tables(
                    fstr, sha2nr, blame_tab_index
                )
                if tables:
                    fstr2tables[fstr] = tables
                    fstrs.append(fstr)
            elif self.blame_history == DYNAMIC:
                fstr2tables[fstr] = []
                fstrs.append(fstr)
            elif self.blame_history == NONE:
                table = BlameTableSoup(self.repo).get_fstr_table(fstr)
                if table:
                    fstr2table[fstr] = table
                    fstrs.append(fstr)
            blame_tab_index += 1

        relative_fstrs = [get_relative_fstr(fstr, self.subfolder) for fstr in fstrs]
        relative_fstr2truncated = string2truncated(
            relative_fstrs,
            MAX_LENGTH_TAB_NAME,
        )

        blame_tab_index = 0
        for fstr, rel_fstr in zip(fstrs, relative_fstrs):
            rel_fstr_truncated: FileStr = relative_fstr2truncated[rel_fstr]

            nav_ul.append(self._new_nav_tab(rel_fstr_truncated))
            tab_pane_div = self._new_tab_pane(rel_fstr_truncated)

            blame_container = self.global_soup.new_tag(
                "div", attrs={"class": "blame-container"}
            )
            tab_pane_div.append(blame_container)

            table_container = self.global_soup.new_tag(
                "div", attrs={"class": "table-container"}
            )

            if self.blame_history in {STATIC, DYNAMIC}:
                self._add_radio_buttons(
                    self.repo.fstr2shas[fstr],
                    sha2nr,
                    blame_container,
                    blame_tab_index,
                )
                for table in fstr2tables[fstr]:
                    table_container.append(table)
            else:  # self.blame_history == NONE
                table_container.append(fstr2table[fstr])

            blame_container.append(table_container)
            tab_pane_div.append(blame_container)
            tab_div.append(tab_pane_div)
            blame_tab_index += 1

    def _new_nav_tab(self, rel_fstr: FileStr) -> Tag:
        safe_rel_fstr = rel_fstr.replace(".", "_").replace("/", "_")
        nav_li = self.global_soup.new_tag("li", attrs={"class": "nav-item"})
        nav_bt = self.global_soup.new_tag(
            "button",
            attrs={
                "class": "nav-link",
                "id": f"{safe_rel_fstr}-tab",
                "data-bs-toggle": "tab",
                "data-bs-target": f"#{safe_rel_fstr}",
            },
        )
        nav_bt.string = rel_fstr
        nav_li.append(nav_bt)
        return nav_li

    def _new_tab_pane(self, fstr: FileStr) -> Tag:
        div = self.global_soup.new_tag(
            "div",
            attrs={
                "class": "tab-pane fade",
                "id": fstr.replace(".", "_").replace("/", "_"),
            },
        )
        return div

    def _add_radio_buttons(
        self,
        shas: list[SHALong],
        sha2nr: dict[SHALong, int],
        parent: Tag,
        blame_tab_index: int,
    ) -> None:
        # Create a container for the radio buttons
        container = self.global_soup.new_tag(
            "div", attrs={"class": "radio-container sticky"}
        )

        for sha in shas:
            sha_nr = sha2nr[sha]
            button_id = f"button-file-{blame_tab_index}-sha-{sha_nr}"
            color_class = self._get_color_for_sha_nr(sha_nr)
            radio_button = self.global_soup.new_tag(
                "input",
                attrs={
                    "class": f"radio-button {color_class}",
                    "type": "radio",
                    "name": f"radio-group-{blame_tab_index}",
                    "value": f"{sha_nr}",
                    "id": button_id,
                },
            )
            label = self.global_soup.new_tag(
                "label",
                attrs={
                    "class": f"radio-label {color_class}",
                    # This causes the label to be displayed on the radio button.
                    # The for value must match the id of the button.
                    "for": button_id,
                },
            )
            label.string = str(sha_nr)

            container.append(radio_button)
            container.append(label)
        parent.append(container)


# pylint: disable=too-many-locals
def get_repo_html(
    repo: GIRepo,
    blame_skip: bool,
) -> Html:
    """
    Generate html with complete analysis results of the provided repository.
    """

    global current_repo
    current_repo = repo

    # Load the template file.
    module_dir = Path(__file__).resolve().parent
    if repo.blame_history == DYNAMIC:
        html_path = module_dir / "static" / "server-template.html"
    else:
        html_path = module_dir / "static" / "template.html"
    with open(html_path, "r", encoding="utf-8") as f:
        html_template = f.read()

    soup = BeautifulSoup(html_template, "html.parser")

    title_tag: Tag = soup.find(name="title")  # type: ignore
    title_tag.string = f"{repo.name} viewer"

    authors_tag: Tag = soup.find(id="authors")  # type: ignore
    authors_tag.append(AuthorsTableSoup(repo).get_table())

    authors_files_tag: Tag = soup.find(id="authors-files")  # type: ignore
    authors_files_tag.append(AuthorsFilesTableSoup(repo).get_table())

    files_authors_tag: Tag = soup.find(id="files-authors")  # type: ignore
    files_authors_tag.append(FilesAuthorsTableSoup(repo).get_table())

    files_tag: Tag = soup.find(id="files")  # type: ignore
    files_tag.append(FilesTableSoup(repo).get_table())

    # Add blame output if not skipped.
    if not blame_skip:
        BlameTablesSoup(repo, soup).add_tables()

    html: Html = str(soup)
    html = html.replace("&amp;nbsp;", "&nbsp;")
    html = html.replace("&amp;lt;", "&lt;")
    html = html.replace("&amp;gt;", "&gt;")
    html = html.replace("&amp;quot;", "&quot;")
    return html


# Is called by gitinspector module
def load_css() -> str:
    css_file = Path(__file__).parent / "static" / "styles.css"
    with open(css_file, "r", encoding="utf-8") as f:
        return f.read()
