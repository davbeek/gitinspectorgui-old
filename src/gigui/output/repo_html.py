# Add these imports
from logging import getLogger
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from gigui._logging import log
from gigui.args_settings import Args
from gigui.constants import HIDE, SHOW
from gigui.data import IniRepo
from gigui.output.repo_blame_rows import RepoBlameRows
from gigui.typedefs import SHA, Author, FileStr, HtmlStr, Row
from gigui.utils import get_relative_fstr

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
    "Origin": "origin-col",
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


# Global variable to store the value of CLI or GUI options
# Set by gitinspector.init_classes
# blame_exclusions_hide is true when --blame_exclusions=hide.
# noqa: F821 (undefined name) is added in the code to suppress the flake8 error
blame_exclusions_hide: bool  # noqa: F821

logger = getLogger(__name__)


class RepoColor(RepoBlameRows):
    def _get_color_for_author(self, author: Author) -> str:
        author_nr = self.author_star2nr[author]
        return BG_AUTHOR_COLORS[author_nr % len(BG_AUTHOR_COLORS)]

    def _get_color_for_sha_nr(self, sha_nr: int) -> str:
        sha = self.nr2sha[sha_nr]
        author = self.sha2author[sha]
        return self._get_color_for_author(author)


class TableSoup(RepoColor):
    def __init__(self, ini_repo: IniRepo) -> None:
        super().__init__(ini_repo)

        self.soup = BeautifulSoup("<div></div>", "html.parser")

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
                if self.args.blame_exclusions in {HIDE, SHOW}:
                    exclusions_button = self.soup.new_tag("button")
                    empty_lines_button = self.soup.new_tag("button")
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
            tr.append(th)
        table.insert(0, thead)  # ensure thead comes before tbody


class RepoStatTableSoup(TableSoup):
    def get_authors_soup(self) -> Tag:
        rows: list[Row] = self.get_author_rows()
        return self._get_colored_rows_table_soup(
            rows,
            self.header_authors(),
            BG_AUTHOR_COLORS,
        )

    def get_authors_files_soup(self) -> Tag:
        rows: list[Row] = self.get_authors_files_rows()
        return self._get_colored_rows_table_soup(
            rows,
            self.header_authors_files(),
            BG_AUTHOR_COLORS,
        )

    def get_files_authors_soup(self) -> Tag:  # pylint: disable=too-many-locals
        table: Tag = self.soup.new_tag("table")
        tbody: Tag = self.soup.new_tag("tbody")

        rows: list[Row] = self.get_files_authors_rows()

        header_row: list[str] = self.header_files_authors()

        # pylint: disable=invalid-name
        ID_COL: int = header_row.index("ID")  # = 0
        FILE_COL: int = header_row.index("File")  # = 1
        AUTHOR_COL: int = header_row.index(
            "Author"
        )  # = 3, because of empty row between File and Author!!

        color_class: str
        author: Author

        self._add_header_row(header_row, table)

        first_file = True
        row_id = 0
        for row in rows:
            if row[ID_COL] != row_id:  # new ID value for new file
                first_file = True
                row_id = row[ID_COL]  # type: ignore

            tr = self.soup.new_tag("tr")
            tr["class"] = BG_ROW_COLORS[(int(row[ID_COL]) % len(BG_ROW_COLORS))]
            tbody.append(tr)

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
        table.append(tbody)
        return table

    def get_files_soup(self) -> Tag:
        rows = self.get_files_rows()
        return self._get_colored_rows_table_soup(
            rows,
            self.header_files(),
            BG_ROW_COLORS,
        )

    def _get_colored_rows_table_soup(
        self, rows, header_row: list[str], bg_colors: list[str]
    ) -> Tag:
        table: Tag = self.soup.new_tag("table")
        tbody: Tag = self.soup.new_tag("tbody")

        self._add_header_row(header_row, table)
        for row in rows:
            tr = self.soup.new_tag("tr")
            tr["class"] = bg_colors[(int(row[0]) % len(bg_colors))]
            tbody.append(tr)
            for i_col, data in enumerate(row):
                td = self.soup.new_tag("td")
                td["class"] = HEADER_CLASS_DICT[header_row[i_col]]
                if header_row[i_col] == "Empty":
                    td.string = ""
                else:
                    td.string = str(data)
                tr.append(td)
        table.append(tbody)
        return table


class RepoBlameTableSoup(RepoStatTableSoup):
    def get_blame_table_soup(self, fstr: FileStr) -> Tag | None:
        rows: list[Row]
        iscomments: list[bool]
        table: Tag | None

        rows, iscomments = self.get_fstr_blame_rows(fstr)
        if not rows:
            log(f"No blame output matching filters found for file {fstr}")
            return None

        table = self._get_blame_table_from_rows(rows, iscomments)
        return table

    def _get_blame_table_from_rows(
        self,
        rows: list[Row],
        iscomments: list[bool],
        fstr_nr: int = 0,
        sha_nr: int = 0,
    ) -> Tag:
        table: Tag = self.soup.new_tag("table")
        tbody: Tag = self.soup.new_tag("tbody")
        table.append(tbody)

        if self.dynamic_blame_history_selected():
            table["id"] = f"file-{fstr_nr}-sha-{sha_nr}"

        header_row = self.header_blames(self.args)
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
                        if is_comment:
                            td["class"] = "comment-col"
                        else:
                            td["class"] = HEADER_CLASS_DICT[head]
                    else:
                        # empty line of code
                        data = "&nbsp;"
                        td["class"] = HEADER_CLASS_DICT[head]
                td.string = str(data)
                tr.append(td)
        return table


class RepoBlameTablesSoup(RepoBlameTableSoup):
    def __init__(self, ini_repo: IniRepo) -> None:
        super().__init__(ini_repo)

        # Is set when get_html() from superclass RepoHTML is called.
        self.global_soup: BeautifulSoup

    def add_blame_tables_soup(self) -> None:
        table: Tag | None
        fstr2table: dict[FileStr, Tag] = {}
        fstr2tables: dict[FileStr, list[Tag]] = {}
        fstrs: list[FileStr] = []
        sha2nr: dict[SHA, int] = self.sha2nr
        nav_ul: Tag = self.global_soup.find(id="tab-buttons")  # type: ignore
        tab_div: Tag = self.global_soup.find(id="tab-contents")  # type: ignore

        blame_tab_index = 0
        for fstr in self.fstrs:
            if self.dynamic_blame_history_selected():
                fstr2tables[fstr] = []
                fstrs.append(fstr)
            else:
                table = self.get_blame_table_soup(fstr)
                if table:
                    fstr2table[fstr] = table
                    fstrs.append(fstr)
            blame_tab_index += 1

        relative_fstrs = [
            get_relative_fstr(fstr, self.args.subfolder) for fstr in fstrs
        ]
        relative_fstr2truncated = self.string2truncated(
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

            if self.dynamic_blame_history_selected():
                self._add_radio_buttons(
                    self.get_blame_shas_for_fstr(fstr),
                    sha2nr,
                    blame_container,
                    blame_tab_index,
                )
                for table in fstr2tables[fstr]:
                    table_container.append(table)
            else:  # self.args.blame_history == NONE
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
        shas: list[SHA],
        sha2nr: dict[SHA, int],
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


class RepoHTML:
    @staticmethod
    def load_css() -> str:
        css_file = Path(__file__).parent / "static" / "styles.css"
        with open(css_file, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def create_html_document(
        args: Args, html_code: HtmlStr, css_code: str, browser_id: str | None = None
    ) -> HtmlStr:
        # Insert CSS code
        html_code = html_code.replace(
            "</head>",
            f"<style>{css_code}</style></head>",
        )

        # Read and insert JavaScript files
        if browser_id:  # dynamic blame history
            js_files = [
                "browser-id.js",
                "globals.js",
                "tab-radio-button-activation.js",
                "shutdown.js",
                "truncate-tab-names.js",
                "update-table-on-button-click.js",
            ]
        else:  # static blame history
            js_files = [
                # "adjust-header-row-pos.js",
                "globals.js",
                "tab-radio-button-activation.js",
                "truncate-tab-names.js",
                "update-table-on-button-click.js",
            ]
        html_js_code: HtmlStr = ""
        js_code: str
        for js_file in js_files:
            js_path = Path(__file__).parent / "static" / "js" / js_file
            with open(js_path, "r", encoding="utf-8") as f:
                js_code = f.read()

            match js_file:
                case "globals.js":
                    # Insert the value of --blame-exclusions=hide in the js code
                    js_code = js_code.replace(
                        '"<%= blame_exclusions_hide %>"',
                        ("true" if args.blame_exclusions == HIDE else "false"),  # noqa: F821
                    )
                case "browser-id.js":
                    # Insert the browser ID option in the js code
                    js_code = js_code.replace("<%= browser_id %>", browser_id)  # type: ignore

            html_js_code += f"\n<script>\n{js_code}</script>\n"

        html_code = html_code.replace("</body>", f"{html_js_code}</body>")
        return html_code
