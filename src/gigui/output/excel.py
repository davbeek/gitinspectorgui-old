import sys
from pathlib import Path

from xlsxwriter import Workbook
from xlsxwriter.chart import Chart
from xlsxwriter.workbook import Format as ExcelFormat
from xlsxwriter.worksheet import Worksheet

from gigui.common import get_relative_fstr
from gigui.output.outbase import (
    header_authors,
    header_authors_files,
    header_blames,
    header_files,
    header_files_authors,
    string2truncated,
)
from gigui.typedefs import FileStr, Row

type FormatSpec = dict[str, str | int | float]

# Same for row and blame colors
# Note that not specifying a color is equivalent to specifying white
WHITE = "#FFFFFF"

# Author background colors
AUTHORLIGHTGREEN = "#E6FFE6"
AUTHORLIGHTBLUE = "#ADD8E6"
AUTHORLIGHTRED = "#FFCCCB"
AUTHORLIGHTYELLOW = "#FFFFBF"
AUTHORLIGHTORANGE = "#FFD7B5"
AUTHORLIGHTPURPLE = "#CBC3E3"
AUTHORLIGHTGREY = "#D3D3D3"

# Row background and border colors
ROWWHITE_BORDER = "#D8E4BC"

ROWLIGHTGREEN = "#EBF1DE"
ROWLIGHTGREEN_BORDER = "C4D79B"

# Worksheet zoom level for macOS is 120, for other platforms 100
ZOOMLEVEL = 120 if sys.platform == "darwin" else 100


class Sheet:
    def __init__(
        self,
        worksheet: Worksheet,
        book: "Book",
    ):
        self.worksheet: Worksheet = worksheet
        self.book: "Book" = book
        self.formats: dict[str, ExcelFormat] = book.formats

        self.row: int = 0
        self.col: int = 0
        self.maxrow: int = 0
        self.maxcol: int = 0

        worksheet.set_zoom(ZOOMLEVEL)

    def set_pos(self, row: int, col: int):
        self.row = row
        self.col = col

    def inc_row(self):
        self.row += 1

    def inc_col(self):
        self.col += 1

    def reset_col(self):
        self.col = 0

    def next_row(self):
        self.inc_row()
        self.reset_col()

    def update_max(self, row: int, col: int):
        self.maxrow = max(self.maxrow, row)
        self.maxcol = max(self.maxcol, col)

    def write(self, data, format: ExcelFormat | None = None):
        self.worksheet.write(self.row, self.col, data, format)
        self.update_max(self.row, self.col)
        self.inc_col()

    def write_number(self, n: int):
        self.worksheet.write_number(self.row, self.col, n)
        self.update_max(self.row, self.col)
        self.inc_col()

    def write_string(self, s: str):
        self.worksheet.write_string(self.row, self.col, s)
        self.update_max(self.row, self.col)
        self.inc_col()

    def write_row(self, datalist: list, format: ExcelFormat | None = None):
        datalist = [data for data in datalist if data is not None]
        if datalist:
            self.worksheet.write_row(self.row, self.col, datalist, format)
            newcol = self.col + len(datalist) - 1
            self.update_max(self.row, newcol)
            self.set_pos(self.row, newcol + 1)

    def number_to_letter(self, n: int) -> str:
        return chr(ord("A") + n)


class TableSheet(Sheet):
    def __init__(
        self,
        header_items: list[str],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.header_items: list[str] = header_items

        self.head2col: dict[str, int] = {}
        self.head2formatname: dict[str, str] = {}
        self.head2width: dict[str, int] = {}

        self.worksheet.set_zoom(ZOOMLEVEL)
        self.head2width |= {
            "ID": 4,
        }
        self.head2formatname["ID"] = "align_left"

    def create_header(self) -> list[dict[str, str]]:
        headlist = self.header_items
        header = [({"header": head}) for head in headlist]
        for col, head in enumerate(headlist):
            self.head2col[head] = col
        return header

    def head_to_letter(self, head: str) -> str:
        col = self.head2col[head]
        return self.number_to_letter(col)

    def set_excel_column_formats(self):
        for head in self.header_items:
            col = self.head2col[head]
            width = self.head2width.get(head)
            formatname = self.head2formatname.get(head)
            excel_format = self.formats.get(formatname)  # type: ignore
            self.worksheet.set_column(col, col, width, excel_format)

    def add_table(self, header: list[dict[str, str]]):
        self.worksheet.add_table(
            0,
            0,
            self.maxrow,
            self.maxcol,
            {
                "columns": header,
                "style": "Table Style Light 11",
            },
        )
        self.worksheet.freeze_panes(1, 0)  # freeze top row

    def set_conditional_author_formats(self):
        author_color_formats: list[ExcelFormat] = self.book.author_color_formats
        # Add conditional formats for author colors
        total_formats_1 = len(author_color_formats) - 1
        for i, color_format in enumerate(author_color_formats):
            if i < total_formats_1:
                critical = "$A2=" + str(i + 1)
            else:
                # If the number of authors equals or surpasses the number of colors, the
                # last color is used for all authors with a number greater or equal to
                # the number of colors
                critical = "$A2>=" + str(i + 1)

            # Add a conditional format for each color
            # The conditional format will match the author number in the first column
            # with the corresponding color format
            self.worksheet.conditional_format(
                1,
                0,
                self.maxrow,
                self.maxcol,
                {
                    "type": "formula",
                    "criteria": critical,
                    "format": color_format,
                },
            )


class StatsSheet(TableSheet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.head2width |= {
            "Author": 20,
            "File": 20,
        }
        self.head2formatname |= {
            "% Lines": "num_format",
            "% Insertions": "num_format",
            "% Scaled Lines": "num_format",
            "% Scaled Insertions": "num_format",
            "Stability": "num_format",
            "Age Y:M:D": "align_right",
        }

    def set_conditional_file_formats(self):
        self.worksheet.conditional_format(
            1,
            0,
            self.maxrow,
            self.maxcol,
            {
                "type": "formula",
                "criteria": "MOD($A2,2)=1",
                "format": self.formats["row_white"],
            },
        )
        self.worksheet.conditional_format(
            1,
            0,
            self.maxrow,
            self.maxcol,
            {
                "type": "formula",
                "criteria": "MOD($A2,2)=0",
                "format": self.formats["row_lightgreen"],
            },
        )


class AuthorsSheet(StatsSheet):
    def __init__(self, rows: list[Row], chart: Chart, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.head2width |= {
            "Email": 20,
        }

        header = self.create_header()
        self.next_row()
        for row in rows:
            self.write_row(row)
            self.next_row()
        self.add_table(header)
        self.set_excel_column_formats()
        self.set_conditional_author_formats()

        points = []
        for c in self.book.author_colors:
            points.append({"fill": {"color": c}})
        author_letter = self.head_to_letter("Author")
        lines_letter = self.head_to_letter("% Lines")
        end_row = self.maxrow + 1
        chart.add_series(
            {
                "categories": f"=Authors!${author_letter}$3:${author_letter}${end_row}",
                "values": f"=Authors!${lines_letter}$3:${lines_letter}${end_row}",
                "points": points,
            }
        )
        chart.set_legend({"none": True})
        self.worksheet.insert_chart(self.row + 1, 1, chart, {"x_scale": 0.6})


class AuthorsFilesSheet(StatsSheet):
    def __init__(self, rows: list[Row], *args, **kwargs):
        super().__init__(*args, **kwargs)

        header = self.create_header()
        self.next_row()
        for row in rows:
            self.write_row(row)
            self.next_row()
        self.add_table(header)
        self.set_excel_column_formats()
        self.set_conditional_author_formats()


class FilesAuthorsSheet(StatsSheet):
    def __init__(self, rows: list[Row], *args, **kwargs):
        super().__init__(*args, **kwargs)

        header = self.create_header()
        self.next_row()
        for row in rows:
            self.write_row(row)
            self.next_row()
        self.add_table(header)
        self.set_excel_column_formats()
        self.set_conditional_file_formats()


class FilesSheet(StatsSheet):
    def __init__(self, rows: list[Row], *args, **kwargs):
        super().__init__(*args, **kwargs)

        header = self.create_header()
        self.next_row()
        for row in rows:
            self.write_row(row)
            self.next_row()
        self.add_table(header)
        self.set_excel_column_formats()
        self.set_conditional_file_formats()


class BlameSheet(TableSheet):
    def __init__(
        self,
        rows_iscomments: tuple[list[Row], list[bool]],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        header = self.create_header()
        rows, is_comments = rows_iscomments
        for row, is_comment in zip(rows, is_comments):
            self.next_row()
            code_col: int = self.head2col["Code"]
            if is_comment:
                self.write_row(row[:code_col])
                self.write(row[code_col], self.formats["italic"])
            else:
                self.write_row(row)

        self.head2formatname |= {
            "Date": "date_format",
            "SHA": "SHA_format",
            "Code": "code_format",
        }
        self.head2width |= {
            "Author": 12,
            "Date": 10,
            "Message": 20,
            "Commit number": 6,
            "Line": 6,
            "Code": 120,
        }
        self.add_table(header)
        self.set_excel_column_formats()
        self.set_conditional_author_formats()

        # Override right alignment of SHA column with left alignment for header
        col = self.head2col["SHA"]
        self.worksheet.write(0, col, "SHA", self.formats["align_left"])


class Book:
    def __init__(self, name: str):
        self.name: str = name

        self.outfile: str = self.name + ".xlsx"
        self.workbook = Workbook(self.name + ".xlsx")
        self.formats: dict[str, ExcelFormat] = {}
        self.author_color_formats: list[ExcelFormat] = []
        self.author_colors = [
            AUTHORLIGHTGREEN,
            AUTHORLIGHTBLUE,
            AUTHORLIGHTRED,
            AUTHORLIGHTYELLOW,
            AUTHORLIGHTORANGE,
            AUTHORLIGHTPURPLE,
            AUTHORLIGHTGREY,
        ]

        self.add_format("align_left", {"align": "left"})
        self.add_format("align_right", {"align": "right"})

        self.add_format(
            "row_white",
            {"bg_color": WHITE, "border": 1, "border_color": ROWWHITE_BORDER},
        )
        self.add_format(
            "row_lightgreen",
            {
                "bg_color": ROWLIGHTGREEN,
                "border": 1,
                "border_color": ROWLIGHTGREEN_BORDER,
            },
        )
        self.add_format(
            "num_format",
            {"num_format": "0"},
        )
        self.add_format(
            "SHA_format", {"align": "right", "font_name": "Menlo", "font_size": "9.5"}
        )
        self.add_format(
            "code_format", {"font_name": "Menlo", "font_size": "9.5", "indent": 1}
        )
        self.add_format("date_format", {"num_format": 14})
        self.add_format("italic", {"italic": True})

        for c in self.author_colors:
            self.author_color_formats.append(
                self.workbook.add_format(
                    {"bg_color": c, "border": 1, "border_color": "#D8E4BC"}
                )
            )

        Path(self.outfile).unlink(missing_ok=True)

    def add_format(self, format_name: str, formatspec: FormatSpec):
        excel_format = self.workbook.add_format(formatspec)
        self.formats[format_name] = excel_format

    def add_authors_sheet(self, rows: list[Row]):
        AuthorsSheet(
            rows,
            self.workbook.add_chart({"type": "pie"}),  # type: ignore
            header_authors(),
            self.workbook.add_worksheet("Authors"),
            self,
        )

    def add_authors_files_sheet(self, rows: list[Row]):
        AuthorsFilesSheet(
            rows,
            header_authors_files(),
            self.workbook.add_worksheet("Authors-Files"),
            self,
        )

    def add_files_authors_sheet(self, rows: list[Row]):
        FilesAuthorsSheet(
            rows,
            header_files_authors(),
            self.workbook.add_worksheet("Files-Authors"),
            self,
        )

    def add_files_sheet(self, rows: list[Row]):
        FilesSheet(
            rows,
            header_files(),
            self.workbook.add_worksheet("Files"),
            self,
        )

    def add_blame_sheet(
        self,
        name,
        rows_iscomments: tuple[list[Row], list[bool]],
    ):
        if rows_iscomments:
            sheetname = name.replace("/", ">")
            BlameSheet(
                rows_iscomments,
                header_blames(),
                self.workbook.add_worksheet(sheetname),
                self,
            )

    def add_blame_sheets(
        self,
        fstr2rows_iscomments: dict[FileStr, tuple[list[Row], list[bool]]],
        subfolder: str,
    ):
        relative_fstrs = [
            get_relative_fstr(fstr, subfolder) for fstr in fstr2rows_iscomments.keys()
        ]
        relativefstr2truncated = string2truncated(relative_fstrs, 31)
        for fstr, relfstr in zip(fstr2rows_iscomments.keys(), relative_fstrs):
            self.add_blame_sheet(
                relativefstr2truncated[relfstr],
                fstr2rows_iscomments[fstr],
            )

    def close(self):
        self.workbook.close()
