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
from gigui.typedefs import FileStr, Html, Row
from gigui.utils import get_relative_fstr, log

MAX_LENGTH_TAB_NAME = 40

header_class_dict: dict[str, str] = {
    "ID": "id_col",
    "Author": "author_col",
    "Empty": "empty_col",
    "Email": "email_col",
    "File": "file_col",
    "% Lines": "p_lines_col number_col",
    "% Insertions": "p_insertions_col number_col",
    "% Scaled Lines": "ps_lines_col number_col",
    "% Scaled Insertions": "ps_insertions_col number_col",
    "Lines": "lines_col number_col",
    "Insertions": "insertions_col number_col",
    "Stability": "stability_col number_col",
    "Commits": "commits_col number_col",
    "Age Y:M:D": "age_col number_col",
    "Date": "date_col",
    "Message": "message_col",
    "SHA": "sha_col number_col",
    "Commit number": "commit_number_col number_col",
    "Line": "line_col number_col",
    "Code": "code_col",
}

bg_author_colors: list[str] = [
    "bg-white",
    "bg-author_light_green",
    "bg-author_light_blue",
    "bg-author_light_red",
    "bg-author_light_yellow",
    "bg-author_light_orange",
    "bg-author_light_purple",
    "bg-author_light_grey",
    "bg-row_light_green",
]
bg_row_colors: list[str] = ["bg-row_light_green", "bg-white"]


class HTMLTable:
    def __init__(
        self, name: FileStr, out_rows: TableStatsRows, subfolder: FileStr
    ) -> None:
        self.out_rows = out_rows
        self.outfile = name
        self.subfolder = subfolder

    def add_conditional_styles_table(
        self, header: list[str], rows: list[Row], bg_colors: list[str]
    ) -> Html:
        bg_colors_cnt = len(bg_colors)

        table = "<table>\n"
        table += self.add_header(header)

        for row in rows:
            table_row = f"<tr class='{bg_colors[(int(row[0]) % bg_colors_cnt)]}'>\n"
            for i, data in enumerate(row):
                table_row += f"<td class='{header_class_dict[header[i]]}'>{data}</td>\n"

            table_row += "</tr>\n"

            table += table_row

        table += "</table>\n"

        return table

    def add_header(self, headers: list[str]) -> str:
        table_header = "<tr class=bg-th-green>\n"
        for col in headers:
            header_class = header_class_dict[col]
            header_content = "" if col == "Empty" else col
            table_header += f"<th class='{header_class}'>{header_content}</th>\n"
        table_header += "</tr>\n"
        return table_header

    def insert_str_at(self, lst: list[str], s: str, i: int) -> list[str]:
        return lst[:i] + [s] + lst[i:]

    def insert_empties_at(self, rows: list[Row], i: int) -> list[Row]:
        new_rows: list[Row] = []
        for row in rows:
            new_row: Row = self.insert_str_at(row, "", i)  # type: ignore
            new_rows.append(new_row)
        return new_rows

    def empty_to_nbsp(self, s: str) -> str:
        return s if s.strip() else "&nbsp;"

    def add_authors_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_authors_stats_rows()
        return self.add_conditional_styles_table(
            self.insert_str_at(header_authors(), "Empty", 2),
            self.insert_empties_at(rows, 2),
            bg_author_colors,
        )

    def add_authors_files_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_authors_files_stats_rows()
        return self.add_conditional_styles_table(
            self.insert_str_at(header_authors_files(), "Empty", 2),
            self.insert_empties_at(rows, 2),
            bg_author_colors,
        )

    def add_files_authors_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_files_authors_stats_rows()
        return self.add_conditional_styles_table(
            self.insert_str_at(header_files_authors(), "Empty", 2),
            self.insert_empties_at(rows, 2),
            bg_author_colors,
        )

    def add_files_table(self) -> Html:
        rows: list[Row] = self.out_rows.get_files_stats_rows()
        return self.add_conditional_styles_table(header_files(), rows, bg_row_colors)

    def add_blame_table(self, rows_iscomments: tuple[list[Row], list[bool]]) -> Html:
        bg_colors_cnt = len(bg_author_colors)
        header = header_blames()

        table = "<table>\n"
        table += self.add_header(header)

        rows, is_comments = rows_iscomments
        for row, is_comment in zip(rows, is_comments):
            table_row = (
                f"<tr class='{bg_author_colors[(int(row[0]) % bg_colors_cnt)]}'>\n"
            )

            if is_comment:
                for i in range(0, len(row) - 1):
                    data = row[i]
                    table_row += (
                        f"<td class='{header_class_dict[header[i]]}'>{data}</td>\n"
                    )
                table_row += f"<td class='comment_col'>{row[-1]}</td>\n"
            else:
                row[7] = (
                    str(row[7])
                    .replace(" ", "&nbsp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                )
                for i, data in enumerate(row):
                    head = header[i]
                    new_data = self.empty_to_nbsp(data) if head == "Code" else data  # type: ignore
                    table_row += (
                        f"<td class='{header_class_dict[head]}'>{new_data}</td>\n"
                    )

            table_row += "</tr>\n"

            table += table_row

        table += "</table>\n"

        return table

    def add_blame_tables(
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
                    self.add_blame_table(fstr2rows_iscomments[fstr]),
                )
            )

        return blame_html_tables


class HTMLModifier:
    def __init__(self, html: Html) -> None:
        self.soup = BeautifulSoup(html, "html.parser")

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

    def add_blame_tables_to_html(
        self, blames_htmls: list[tuple[FileStr, Html]]
    ) -> Html:
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

    # Construct the file in memory and add the authors and files to it.
    out_rows = TableStatsRows(repo)
    html_table = HTMLTable(outfilestr, out_rows, repo.args.subfolder)
    authors_html = html_table.add_authors_table()
    authors_files_html = html_table.add_authors_files_table()
    files_authors_html = html_table.add_files_authors_table()
    files_html = html_table.add_files_table()

    html = html_template.replace("__TITLE__", f"{repo.name} viewer")
    html = html.replace("__AUTHORS__", authors_html)
    html = html.replace("__AUTHORS_FILES__", authors_files_html)
    html = html.replace("__FILES_AUTHORS__", files_authors_html)
    html = html.replace("__FILES__", files_html)

    # Add blame output if not skipped.
    if not blame_skip:
        blames_htmls = html_table.add_blame_tables()
        html_modifier = HTMLModifier(html)
        html = html_modifier.add_blame_tables_to_html(blames_htmls)

    # Convert the table to text and return it.
    soup = BeautifulSoup(html, "html.parser")
    return soup.prettify(formatter="html")
