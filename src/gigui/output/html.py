from pathlib import Path

from bs4 import BeautifulSoup, Tag

from gigui.output.outbase import (
    TableStatsRows,
    header_authors,
    header_authors_files,
    header_blames,
    header_files,
    header_files_authors,
    string2truncated,
)
from gigui.repo import GIRepo
from gigui.typedefs import Author, FileStr, Html, Row
from gigui.utils import get_relative_fstr

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


class HTMLTable:
    hide_blame_exclusions: bool
    empty_lines: bool

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
                if self.hide_blame_exclusions:
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


class HTMLStatTable(HTMLTable):
    def __init__(self, out_rows: TableStatsRows, subfolder: FileStr) -> None:
        super().__init__()
        self.out_rows = out_rows
        self.subfolder = subfolder

    def _add_colored_rows_table(
        self, header: list[str], rows: list[Row], bg_colors: list[str]
    ) -> None:
        self._add_header(header)
        for row in rows:
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


class HTMLAuthorsTable(HTMLStatTable):
    def get_table(self) -> Tag:
        rows: list[Row] = self.out_rows.get_authors_stats_rows()
        self._add_colored_rows_table(
            header_authors(),
            rows,
            BG_AUTHOR_COLORS,
        )
        return self.table


class HTMLAuthorsFilesTable(HTMLStatTable):
    def get_table(self) -> Tag:
        rows: list[Row] = self.out_rows.get_authors_files_stats_rows()
        self._add_colored_rows_table(
            header_authors_files(),
            rows,
            BG_AUTHOR_COLORS,
        )
        return self.table


class HTMLFilesAuthorsTable(HTMLStatTable):
    def get_table(self) -> Tag:
        rows: list[Row] = self.out_rows.get_files_authors_stats_rows()
        self._add_files_authors_table(
            header_files_authors(),
            rows,
            BG_ROW_COLORS,
            BG_AUTHOR_COLORS,
        )
        return self.table

    def _add_files_authors_table(
        self,
        header: list[str],
        rows: list[Row],
        bg_row_colors: list[str],
        bg_author_colors: list[str],
    ) -> None:
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
        for row in rows:
            if row[ID_COL] != row_id:  # new ID value for new file
                first_file = True
                row_id = row[ID_COL]  # type: ignore

            tr = self.soup.new_tag("tr")
            tr["class"] = bg_row_colors[(int(row[ID_COL]) % len(bg_row_colors))]
            self.tbody.append(tr)

            author = row[AUTHOR_COL]  # type: ignore
            author_index = self.out_rows.get_authors_included().index(author)

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
                    color_class = bg_author_colors[author_index % len(bg_author_colors)]
                    td["class"] = f"{HEADER_CLASS_DICT[header[i_col]]} {color_class}"
                    td.string = str(data)
                tr.append(td)


class HTMLFilesTable(HTMLStatTable):
    def get_table(self) -> Tag:
        rows: list[Row] = self.out_rows.get_files_stats_rows()
        self._add_colored_rows_table(header_files(), rows, BG_ROW_COLORS)
        return self.table


class HTMLBlameTable(HTMLTable):
    def __init__(self, out_rows: TableStatsRows, subfolder: FileStr) -> None:
        super().__init__()
        self.out_rows = out_rows
        self.subfolder = subfolder

    def get_table(self, rows_iscomments: tuple[list[Row], list[bool]]) -> Tag:
        col_header = header_blames()
        self._add_header(col_header)

        bg_colors_cnt = len(BG_AUTHOR_COLORS)
        rows, is_comments = rows_iscomments
        for row, is_comment in zip(rows, is_comments):
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


class HTMLBlameTables:
    def __init__(
        self, out_rows: TableStatsRows, subfolder: FileStr, global_soup: BeautifulSoup
    ) -> None:
        self.out_rows = out_rows
        self.subfolder = subfolder
        self.global_soup = global_soup

    def add_tables(self) -> None:
        fstr2rows_iscomments: dict[FileStr, tuple[list[Row], list[bool]]]
        fstr2rows_iscomments = self.out_rows.get_blames(html=True)

        relative_fstrs = [
            get_relative_fstr(fstr, self.subfolder)
            for fstr in fstr2rows_iscomments.keys()
        ]
        relative_fstr2truncated = string2truncated(
            relative_fstrs,
            MAX_LENGTH_TAB_NAME,
        )

        nav_ul: Tag = self.global_soup.find(id="tab-buttons")  # type: ignore
        tab_div: Tag = self.global_soup.find(id="tab-contents")  # type: ignore

        for fstr, rel_fstr in zip(fstr2rows_iscomments.keys(), relative_fstrs):
            rel_fstr_truncated: FileStr = relative_fstr2truncated[rel_fstr]

            blame_table = HTMLBlameTable(self.out_rows, self.subfolder)
            table = blame_table.get_table(fstr2rows_iscomments[fstr])

            nav_ul.append(self._new_nav_tab(rel_fstr_truncated, self.global_soup))
            tab_div.append(
                self._new_tab_content(
                    rel_fstr_truncated,
                    table,
                    self.global_soup,
                )
            )

    def _new_nav_tab(self, rel_fstr: FileStr, soup: BeautifulSoup) -> Tag:
        nav_li = soup.new_tag("li", attrs={"class": "nav-item"})
        nav_bt = soup.new_tag(
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

    def _new_tab_content(self, fstr: FileStr, table: Tag, soup: BeautifulSoup) -> Tag:
        div = soup.new_tag(
            "div",
            attrs={
                "class": "tab-pane fade",
                "id": fstr,
            },
        )
        div.append(table)
        return div


# pylint: disable=too-many-locals
def out_html(
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

    out_rows = TableStatsRows(repo)

    authors_table = HTMLAuthorsTable(out_rows, repo.args.subfolder)
    authors_tag: Tag = soup.find(id="authors")  # type: ignore
    authors_tag.append(authors_table.get_table())

    authors_files_table = HTMLAuthorsFilesTable(out_rows, repo.args.subfolder)
    authors_files_tag: Tag = soup.find(id="authors-files")  # type: ignore
    authors_files_tag.append(authors_files_table.get_table())

    files_authors_table = HTMLFilesAuthorsTable(out_rows, repo.args.subfolder)
    files_authors_tag: Tag = soup.find(id="files-authors")  # type: ignore
    files_authors_tag.append(files_authors_table.get_table())

    files_table = HTMLFilesTable(out_rows, repo.args.subfolder)
    files_tag: Tag = soup.find(id="files")  # type: ignore
    files_tag.append(files_table.get_table())

    # Add blame output if not skipped.
    if not blame_skip:
        HTMLBlameTables(out_rows, repo.args.subfolder, soup).add_tables()

    html: Html = soup.prettify(formatter="html")

    html = html.replace("&amp;nbsp;", "&nbsp;")
    html = html.replace("&amp;lt;", "&lt;")
    html = html.replace("&amp;gt;", "&gt;")
    html = html.replace("&amp;quot;", "&quot;")
    return html
