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


class HTMLTable:
    def _get_header(self, headers: list[str]) -> str:
        table_header = "<tr class='bg-th-green'>\n"
        for col in headers:
            header_class = HEADER_CLASS_DICT[col]
            header_content = "" if col == "Empty" else col
            table_header += f"<th class='{header_class}'>{header_content}</th>\n"
        table_header += "</tr>\n"
        return table_header

    def _get_header_list(self, headers: list[str]) -> list[Html]:
        table_header: list[Html] = ["<tr class='bg-th-green'>\n"]
        for col in headers:
            header_class = HEADER_CLASS_DICT[col]
            header_content = "" if col == "Empty" else col
            table_header.append(f"<th class='{header_class}'>{header_content}</th>\n")
        table_header.append("</tr>\n")
        return table_header


class HTMLStatTable(HTMLTable):
    def __init__(
        self, name: FileStr, out_rows: TableStatsRows, subfolder: FileStr
    ) -> None:
        self.out_rows = out_rows
        self.outfile = name
        self.subfolder = subfolder

    def get_authors_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_authors_stats_rows()
        return self._get_colored_rows_table(
            self._insert_str_at(header_authors(), "Empty", 2),
            self._insert_empties_at(rows, 2),
            BG_AUTHOR_COLORS,
        )

    def get_authors_files_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_authors_files_stats_rows()
        return self._get_colored_rows_table(
            self._insert_str_at(header_authors_files(), "Empty", 2),
            self._insert_empties_at(rows, 2),
            BG_AUTHOR_COLORS,
        )

    def get_files_authors_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_files_authors_stats_rows()
        return self._get_files_authors_table(
            self._insert_str_at(header_files_authors(), "Empty", 2),
            self._insert_empties_at(rows, 2),
            BG_ROW_COLORS,
            BG_AUTHOR_COLORS,
        )

    def get_files_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_files_stats_rows()
        return self._get_colored_rows_table(header_files(), rows, BG_ROW_COLORS)

    def _get_colored_rows_table(
        self, header: list[str], rows: list[Row], bg_colors: list[str]
    ) -> Html:
        table = "<table>\n"
        table += self._get_header(header)

        for row in rows:
            table_row = f"<tr class='{bg_colors[(int(row[0]) % len(bg_colors))]}'>\n"
            for i, data in enumerate(row):
                table_row += f"<td class='{HEADER_CLASS_DICT[header[i]]}'>{data}</td>\n"

            table_row += "</tr>\n"

            table += table_row

        table += "</table>\n"
        return table

    def _get_files_authors_table(
        self,
        header: list[str],
        rows: list[Row],
        bg_row_colors: list[str],
        bg_author_colors: list[str],
    ) -> Html:
        ID_COL: int = header.index("ID")  # = 0
        FILE_COL: int = header.index("File")  # = 1
        AUTHOR_COL: int = header.index(
            "Author"
        )  # = 3, because of empty row between File and Author!!

        # Very confusing term: table_rows is a list of table tags, not rows.
        # Switch to bs4 for better readability!!!!!!!!!!!!!!!
        table_rows: list[Html]
        classes: str
        color_class: str
        author: Author
        author_index: int

        table_rows = ["<table>\n"]
        for header_col in self._get_header_list(header):
            table_rows.append(header_col)

        first_file = True
        row_id = 0
        for row in rows:
            if row[ID_COL] != row_id:  # new ID value for new file
                first_file = True
                row_id = row[ID_COL]  # type: ignore
            table_rows.append(
                f"<tr class='{bg_row_colors[(int(row[ID_COL]) % len(bg_row_colors))]}'>\n"
            )
            author = row[AUTHOR_COL]  # type: ignore
            author_index = self.out_rows.get_authors_included().index(author)

            for i_col, data in enumerate(row):
                if i_col == ID_COL:
                    classes = HEADER_CLASS_DICT[header[i_col]]
                    table_rows.append(f"<td class='{classes}'>{data}</td>\n")
                elif i_col == FILE_COL and first_file:
                    classes = HEADER_CLASS_DICT[header[i_col]]
                    table_rows.append(f"<td class='{classes}'>{data}</td>\n")
                    first_file = False
                elif i_col == FILE_COL and not first_file:
                    classes = HEADER_CLASS_DICT[header[i_col]]
                    table_rows.append(f"<td class='{classes}'></td>\n")
                else:
                    color_class = bg_author_colors[author_index % len(bg_author_colors)]
                    classes = f"{HEADER_CLASS_DICT[header[i_col]]} {color_class}"
                    table_rows.append(f"<td class='{classes}'>{data}</td>\n")

            table_rows.append("</tr>\n")

        table_rows.append("</table>\n")
        table = "".join(table_rows)
        return table

    def _insert_str_at(self, lst: list[str], s: str, i: int) -> list[str]:
        return lst[:i] + [s] + lst[i:]

    def _insert_empties_at(self, rows: list[Row], i: int) -> list[Row]:
        new_rows: list[Row] = []
        for row in rows:
            new_row: Row = self._insert_str_at(row, "", i)  # type: ignore
            new_rows.append(new_row)
        return new_rows


class HTMLBlameTable(HTMLTable):
    def __init__(
        self, name: FileStr, out_rows: TableStatsRows, subfolder: FileStr
    ) -> None:
        self.out_rows = out_rows
        self.outfile = name
        self.subfolder = subfolder

    def get_blame_tables(
        self,
    ) -> list[tuple[FileStr, Html]]:
        fstr2rows_iscomments: dict[FileStr, tuple[list[Row], list[bool]]]
        fstr2rows_iscomments = self.out_rows.get_blames()
        blame_html_tables: list[tuple[FileStr, Html]] = []

        relative_fstrs = [
            get_relative_fstr(fstr, self.subfolder)
            for fstr in fstr2rows_iscomments.keys()
        ]
        relative_fstr2truncated = string2truncated(
            relative_fstrs,
            MAX_LENGTH_TAB_NAME,
        )

        for fstr, rel_fstr in zip(fstr2rows_iscomments.keys(), relative_fstrs):
            blame_html_tables.append(
                (
                    relative_fstr2truncated[rel_fstr],
                    self.get_blame_table(fstr2rows_iscomments[fstr]),
                )
            )

        return blame_html_tables

    def get_blame_table(self, rows_iscomments: tuple[list[Row], list[bool]]) -> Html:
        bg_colors_cnt = len(BG_AUTHOR_COLORS)
        header = header_blames()

        table = "<table>\n"
        table += self._get_header(header)

        rows, is_comments = rows_iscomments
        for row, is_comment in zip(rows, is_comments):
            table_row = (
                f"<tr class='{BG_AUTHOR_COLORS[(int(row[0]) % bg_colors_cnt)]}'>\n"
            )
            for i, data in enumerate(row):
                head = header[i]
                if head != "Code":
                    table_row += (
                        f"<td class='{HEADER_CLASS_DICT[header[i]]}'>{data}</td>\n"
                    )
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
                        table_row += f"<td class='comment-col'>{data}</td>\n"
                    else:
                        table_row += (
                            f"<td class='{HEADER_CLASS_DICT[head]}'>{data}</td>\n"
                        )
            table_row += "</tr>\n"

            table += table_row

        table += "</table>\n"

        return table


class HTMLModifier:
    def __init__(self, html: Html) -> None:
        self.soup = BeautifulSoup(html, "html5lib")

    def blame_tables_to_html(self, blames_htmls: list[tuple[FileStr, Html]]) -> Html:
        nav_ul = self.soup.find("ul", {"id": "stats-tabs"})
        tab_div = self.soup.find("div", {"class": "tab-content"})
        if nav_ul and tab_div:
            for blame in blames_htmls:
                file_name, _ = blame
                nav_ul.append(self.new_nav_tab(file_name))
                tab_div.append(self.new_tab_content(file_name))

            html = str(self.soup)
            for blame in blames_htmls:
                file_name, content = blame
                html = html.replace("__" + file_name + "__", content)

            return html
        else:
            if nav_ul is None:
                log(
                    "Cannot find the component with id = 'stats-tabs'", text_color="red"
                )

            if tab_div is None:
                log(
                    "Cannot find the component with class = 'tab-content'",
                    text_color="red",
                )

        return str(self.soup)

    def new_nav_tab(self, name: str) -> Tag:
        nav_li = self.soup.new_tag("li", attrs={"class": "nav-item"})
        nav_bt = self.soup.new_tag(
            "button",
            attrs={
                "class": "nav-link",
                "id": name + "-tab",
                "data-bs-toggle": "tab",
                "data-bs-target": "#" + name,
            },
        )
        nav_bt.string = name
        nav_li.append(nav_bt)
        return nav_li

    def new_tab_content(self, name: str) -> Tag:
        div = self.soup.new_tag(
            "div",
            attrs={
                "class": "tab-pane fade",
                "id": name,
            },
        )
        div.string = "__" + name + "__"
        return div


# pylint: disable=too-many-locals
def out_html(
    repo: GIRepo,
    outfilestr: FileStr,  # Path to write the result file.
    blame_skip: bool,
) -> Html:
    """
    Generate an html file with analysis result of the provided repository.
    """

    # Load the template file.
    module_dir = Path(__file__).resolve().parent
    html_path = module_dir / "files" / "template.html"
    with open(html_path, "r", encoding="utf-8") as f:
        html_template = f.read()

    html_table: HTMLStatTable
    html_blame_table: HTMLBlameTable

    # Construct the file in memory and add the authors and files to it.
    out_rows = TableStatsRows(repo)
    html_table = HTMLStatTable(outfilestr, out_rows, repo.args.subfolder)
    authors_html = html_table.get_authors_table()
    authors_files_html = html_table.get_authors_files_table()
    files_authors_html = html_table.get_files_authors_table()
    files_html = html_table.get_files_table()

    html = html_template.replace("__TITLE__", f"{repo.name} viewer")
    html = html.replace("__AUTHORS__", authors_html)
    html = html.replace("__AUTHORS_FILES__", authors_files_html)
    html = html.replace("__FILES_AUTHORS__", files_authors_html)
    html = html.replace("__FILES__", files_html)

    # Add blame output if not skipped.
    if not blame_skip:
        html_blame_table = HTMLBlameTable(outfilestr, out_rows, repo.args.subfolder)
        blames_htmls = html_blame_table.get_blame_tables()
        html_modifier = HTMLModifier(html)
        html = html_modifier.blame_tables_to_html(blames_htmls)

    # Convert the table to text and return it.
    soup = BeautifulSoup(html, "html.parser")
    return soup.prettify(formatter="html")
