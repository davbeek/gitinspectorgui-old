from pathlib import Path

from bs4 import BeautifulSoup, Tag

from gigui.output.blame_rows import BlameRows, header_blames, string2truncated
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
from gigui.typedefs import Author, FileStr, Html, Row, RowsBools
from gigui.utils import get_relative_fstr, log

MAX_LENGTH_TAB_NAME = 40

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


class TableSoup:
    blame_hide_exclusions: bool
    empty_lines: bool
    subfolder: FileStr

    def __init__(self) -> None:
        self.soup = BeautifulSoup("<table></table>", "html.parser")
        self.table: Tag = self.soup.table  # type: ignore
        self.tbody: Tag = self.soup.new_tag("tbody")

    def _add_header(self, headers: list[str]) -> None:
        self.table.clear()  # remove all rows resulting from previous calls
        thead: Tag = self.soup.new_tag("thead")
        thead["class"] = "sticky headerRow"
        tr = self.soup.new_tag("tr")
        tr["class"] = "bg-th-green"
        thead.append(tr)
        for header in headers:
            header_class = HEADER_CLASS_DICT[header]
            header_string = "" if header == "Empty" else header
            th = self.soup.new_tag("th")
            th["class"] = header_class
            th.string = header_string
            if header == "Code":
                button = self.soup.new_tag("button")
                if self.blame_hide_exclusions:
                    button["class"] = "blame-exclusions-button pressed"
                else:
                    button["class"] = "blame-exclusions-button"
                button.string = "Hide blame exclusions"
                th.append(button)

                button = self.soup.new_tag("button")
                if self.empty_lines:  # include and show empty lines
                    button["class"] = "blame-empty-lines-button"
                else:
                    button["class"] = "blame-empty-lines-button pressed"
                button.string = "Hide empty lines"
                th.append(button)

                button = self.soup.new_tag("button")
                button["class"] = "hide-colors-button"
                button.string = "Hide colors"
                th.append(button)
            thead.append(th)
        self.table.append(thead)
        self.table.append(self.tbody)


class StatTableSoup(TableSoup):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Row]  # to be set by child classes

    def _add_colored_rows_table(self, header: list[str], bg_colors: list[str]) -> None:
        self._add_header(header)
        for row in self.rows:
            tr = self.soup.new_tag("tr")
            tr["class"] = bg_colors[(int(row[0]) % len(bg_colors))]
            self.tbody.append(tr)
            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                td["class"] = HEADER_CLASS_DICT[header[i_col]]
                if header[i_col] == "Empty":
                    td.string = ""
                else:
                    td.string = str(data)
                tr.append(td)


class AuthorsTableSoup(StatTableSoup):
    def get_table(self, repo: GIRepo) -> Tag:
        self.rows: list[Row] = AuthorsTableRows(repo).get_rows()
        self._add_colored_rows_table(
            header_authors(),
            BG_AUTHOR_COLORS,
        )
        return self.table


class AuthorsFilesTableSoup(StatTableSoup):
    def get_table(self, repo: GIRepo) -> Tag:
        self.rows: list[Row] = AuthorsFilesTableRows(repo).get_rows()
        self._add_colored_rows_table(
            header_authors_files(),
            BG_AUTHOR_COLORS,
        )
        return self.table


class FilesAuthorsTableSoup(StatTableSoup):
    def get_table(self, repo: GIRepo) -> Tag:
        row_table = FilesAuthorsTableRows(repo)
        self.rows: list[Row] = row_table.get_rows()
        authors_included: list[Author] = row_table.get_authors_included()

        header: list[str] = header_files_authors()

        # pylint: disable=invalid-name
        ID_COL: int = header.index("ID")  # = 0
        FILE_COL: int = header.index("File")  # = 1
        AUTHOR_COL: int = header.index(
            "Author"
        )  # = 3, because of empty row between File and Author!!

        color_class: str
        author: Author
        author_index: int

        self._add_header(header)

        first_file = True
        row_id = 0
        for row in self.rows:
            if row[ID_COL] != row_id:  # new ID value for new file
                first_file = True
                row_id = row[ID_COL]  # type: ignore

            tr = self.soup.new_tag("tr")
            tr["class"] = BG_ROW_COLORS[(int(row[ID_COL]) % len(BG_ROW_COLORS))]
            self.tbody.append(tr)

            author = row[AUTHOR_COL]  # type: ignore
            author_index = authors_included.index(author)

            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                if i_col == ID_COL:
                    td["class"] = HEADER_CLASS_DICT[header[i_col]]
                    td.string = str(data)
                elif i_col == FILE_COL and first_file:
                    td["class"] = HEADER_CLASS_DICT[header[i_col]]
                    td.string = str(data)
                    first_file = False
                elif i_col == FILE_COL and not first_file or header[i_col] == "Empty":
                    td["class"] = HEADER_CLASS_DICT[header[i_col]]
                    td.string = ""
                else:
                    color_class = BG_AUTHOR_COLORS[author_index % len(BG_AUTHOR_COLORS)]
                    td["class"] = f"{HEADER_CLASS_DICT[header[i_col]]} {color_class}"
                    td.string = str(data)
                tr.append(td)
        return self.table


class FilesTableSoup(StatTableSoup):
    def get_table(self, repo: GIRepo) -> Tag:
        self.rows: list[Row] = FilesTableRows(repo).get_rows()
        self._add_colored_rows_table(header_files(), BG_ROW_COLORS)
        return self.table


class BlameTableSoup(TableSoup):
    def get_table(self, fstr: FileStr, repo: GIRepo) -> Tag | None:
        rows: list[Row]
        iscomments: list[bool]

        rows, iscomments = BlameRows(repo).get_blame_rows(fstr, html=True)
        if not rows:
            log(f"No blame output matching filters found for file {fstr}")
            return None

        col_header = header_blames()
        self._add_header(col_header)

        bg_colors_cnt = len(BG_AUTHOR_COLORS)
        for row, is_comment in zip(rows, iscomments):
            tr = self.soup.new_tag("tr")
            tr["class"] = BG_AUTHOR_COLORS[(int(row[0]) % bg_colors_cnt)]
            self.tbody.append(tr)
            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                head = col_header[i_col]
                if head != "Code":
                    td["class"] = HEADER_CLASS_DICT[col_header[i_col]]
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
        return self.table


class BlameTablesSoup:
    subfolder: FileStr

    def __init__(self, repo: GIRepo, global_soup: BeautifulSoup) -> None:
        self.repo: GIRepo = repo
        self.global_soup = global_soup

    def add_tables(self) -> None:
        fstr2table: dict[FileStr, Tag] = {}
        nav_ul: Tag = self.global_soup.find(id="tab-buttons")  # type: ignore
        tab_div: Tag = self.global_soup.find(id="tab-contents")  # type: ignore

        for fstr in self.repo.fstrs:
            table = BlameTableSoup().get_table(fstr, self.repo)
            if table:
                fstr2table[fstr] = table

        relative_fstrs = [
            get_relative_fstr(fstr, self.subfolder) for fstr in fstr2table
        ]
        relative_fstr2truncated = string2truncated(
            relative_fstrs,
            MAX_LENGTH_TAB_NAME,
        )

        for fstr, rel_fstr in zip(fstr2table, relative_fstrs):
            rel_fstr_truncated: FileStr = relative_fstr2truncated[rel_fstr]
            nav_ul.append(self._new_nav_tab(rel_fstr_truncated))
            tab_div.append(
                self._new_tab_content(
                    rel_fstr_truncated,
                    fstr2table[fstr],
                )
            )

    def _new_nav_tab(self, rel_fstr: FileStr) -> Tag:
        nav_li = self.global_soup.new_tag("li", attrs={"class": "nav-item"})
        nav_bt = self.global_soup.new_tag(
            "button",
            attrs={
                "class": "nav-link",
                "id": rel_fstr + "-tab",
                "data-bs-toggle": "tab",
                "data-bs-target": "#" + rel_fstr,
            },
        )
        nav_bt.string = rel_fstr
        nav_li.append(nav_bt)
        return nav_li

    def _new_tab_content(self, fstr: FileStr, table: Tag) -> Tag:
        div = self.global_soup.new_tag(
            "div",
            attrs={
                "class": "tab-pane fade",
                "id": fstr,
            },
        )
        div.append(table)
        return div


# pylint: disable=too-many-locals
def get_repo_html(
    repo: GIRepo,
    blame_skip: bool,
) -> Html:
    """
    Generate html with complete analysis results of the provided repository.
    """

    # Load the template file.
    module_dir = Path(__file__).resolve().parent
    html_path = module_dir / "files" / "template.html"
    with open(html_path, "r", encoding="utf-8") as f:
        html_template = f.read()

    soup = BeautifulSoup(html_template, "html.parser")

    title_tag: Tag = soup.find(name="title")  # type: ignore
    title_tag.string = f"{repo.name} viewer"

    if not repo.args.blame_history:
        authors_tag: Tag = soup.find(id="authors")  # type: ignore
        authors_tag.append(AuthorsTableSoup().get_table(repo))

        authors_files_tag: Tag = soup.find(id="authors-files")  # type: ignore
        authors_files_tag.append(AuthorsFilesTableSoup().get_table(repo))

        files_authors_tag: Tag = soup.find(id="files-authors")  # type: ignore
        files_authors_tag.append(FilesAuthorsTableSoup().get_table(repo))

        files_tag: Tag = soup.find(id="files")  # type: ignore
        files_tag.append(FilesTableSoup().get_table(repo))

    # Add blame output if not skipped.
    if not blame_skip:
        BlameTablesSoup(repo, soup).add_tables()

    html: Html = soup.prettify(formatter="html")

    html = html.replace("&amp;nbsp;", "&nbsp;")
    html = html.replace("&amp;lt;", "&lt;")
    html = html.replace("&amp;gt;", "&gt;")
    html = html.replace("&amp;quot;", "&quot;")
    return html
