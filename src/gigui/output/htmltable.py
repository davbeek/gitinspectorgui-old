from gigui.common import get_relative_fstr
from gigui.output.outbase import (
    header_authors,
    header_authors_files,
    header_blames,
    header_files,
    header_files_authors,
    string2truncated,
)
from gigui.typedefs import HTML, FileStr, Row

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

bg_author_colros: list[str] = [
    "bg-white",
    "bg-authorlightgreen",
    "bg-authorlightblue",
    "bg-authorlightred",
    "bg-authorlightyellow",
    "bg-authorlightorange",
    "bg-authorlightpurple",
    "bg-authorlightgrey",
    "bg-rowlightgreen",
]
bg_row_colors: list[str] = ["bg-rowlightgreen", "bg-white"]


class HTMLTable:
    def __init__(self, name: str):
        self.outfile: str = name

    def add_conditional_styles_table(
        self, header: list[str], rows: list[Row], bg_colors: list[str]
    ) -> str:
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
            table_header += f"<th class='{header_class_dict[col]}'>{"" if col == "Empty" else col}</th>\n"
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

    def add_authors_table(self, rows: list[Row]) -> str:
        return self.add_conditional_styles_table(
            self.insert_str_at(header_authors(), "Empty", 2),
            self.insert_empties_at(rows, 2),
            bg_author_colros,
        )

    def add_authors_files_table(self, rows: list[Row]) -> str:
        return self.add_conditional_styles_table(
            self.insert_str_at(header_authors_files(), "Empty", 2),
            self.insert_empties_at(rows, 2),
            bg_author_colros,
        )

    def add_files_authors_table(self, rows: list[Row]) -> str:
        return self.add_conditional_styles_table(
            self.insert_str_at(header_files_authors(), "Empty", 2),
            self.insert_empties_at(rows, 2),
            bg_author_colros,
        )

    def add_files_table(self, rows: list[Row]) -> str:
        return self.add_conditional_styles_table(header_files(), rows, bg_row_colors)

    def add_blame_table(self, rows_iscomments: tuple[list[Row], list[bool]]) -> str:
        bg_colors_cnt = len(bg_author_colros)
        header = header_blames()

        table = "<table>\n"
        table += self.add_header(header)

        rows, is_comments = rows_iscomments
        for row, is_comment in zip(rows, is_comments):
            table_row = (
                f"<tr class='{bg_author_colros[(int(row[0]) % bg_colors_cnt)]}'>\n"
            )

            if is_comment:
                for i in range(0, len(row) - 1):
                    data = row[i]
                    table_row += (
                        f"<td class='{header_class_dict[header[i]]}'>{data}</td>\n"
                    )
                table_row += f"<td class='comment_col'>{row[-1]}</td>\n"
            else:
                row[7] = str(row[7]).replace(" ", "&nbsp;")
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
        fstr2rows_iscomments: dict[FileStr, tuple[list[Row], list[bool]]],
        subfolder: str,
    ) -> list[tuple[FileStr, HTML]]:
        blame_html_tables: list[tuple[str, str]] = []
        relative_fstrs = [
            get_relative_fstr(fstr, subfolder) for fstr in fstr2rows_iscomments.keys()
        ]
        relativefstr2truncated = string2truncated(relative_fstrs, 31)

        for fstr, relfstr in zip(fstr2rows_iscomments.keys(), relative_fstrs):
            blame_html_tables.append(
                (
                    relativefstr2truncated[relfstr],
                    self.add_blame_table(fstr2rows_iscomments[fstr]),
                )
            )

        return blame_html_tables
