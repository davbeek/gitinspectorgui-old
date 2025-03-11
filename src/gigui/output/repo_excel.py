import platform
import sys
from pathlib import Path

from xlsxwriter import Workbook  # type: ignore[import-untyped]
from xlsxwriter.workbook import Format as ExcelFormat  # type: ignore[import-untyped]

from gigui.output.excel_sheet import (
    AuthorsFilesSheet,
    AuthorsSheet,
    BlameSheet,
    FilesAuthorsSheet,
    FilesSheet,
)
from gigui.output.repo_blame_rows import RepoBlameRows
from gigui.typedefs import FileStr, Row
from gigui.utils import get_relative_fstr

type FormatSpec = dict[str, str | int | float]  # type: ignore

MAX_LENGTH_SHEET_NAME = 31  # hard coded in Excel

# Same for row and blame colors
# Note that not specifying a color is equivalent to specifying white
WHITE = "#FFFFFF"

# Author background colors
AUTHOR_LIGHT_GREEN = "#E6FFE6"
AUTHOR_LIGHT_BLUE = "#ADD8E6"
AUTHOR_LIGHT_RED = "#FFCCCB"
AUTHOR_LIGHT_YELLOW = "#FFFFBF"
AUTHOR_LIGHT_ORANGE = "#FFD7B5"
AUTHOR_LIGHT_PURPLE = "#CBC3E3"
AUTHOR_LIGHT_GRAY = "#D3D3D3"

# Row background and border colors
ROW_WHITE_BORDER = "#D8E4BC"

ROW_LIGHT_GREEN = "#EBF1DE"
ROW_LIGHT_GREEN_BORDER = "C4D79B"

# Worksheet zoom level for macOS is 120, for other platforms 100
ZOOM_LEVEL = 120 if sys.platform == "darwin" else 100


class Book(RepoBlameRows):
    def run_excel(self, outfile: FileStr) -> None:
        self.outfile: str = outfile + ".xlsx"
        self.workbook = Workbook(self.outfile)
        self.formatstr2excelformat: dict[str, ExcelFormat] = {}
        self.author_color_formats: list[ExcelFormat] = []
        self.author_colors = [
            AUTHOR_LIGHT_GREEN,
            AUTHOR_LIGHT_BLUE,
            AUTHOR_LIGHT_RED,
            AUTHOR_LIGHT_YELLOW,
            AUTHOR_LIGHT_ORANGE,
            AUTHOR_LIGHT_PURPLE,
            AUTHOR_LIGHT_GRAY,
        ]

        # Remove all formatting, so that the default format is used.
        self.add_format("clear", {})

        self.add_format("align_left", {"align": "left"})
        self.add_format("align_right", {"align": "right"})

        self.add_format(
            "row_white",
            {"bg_color": WHITE, "border": 1, "border_color": ROW_WHITE_BORDER},
        )
        self.add_format(
            "row_light_green",
            {
                "bg_color": ROW_LIGHT_GREEN,
                "border": 1,
                "border_color": ROW_LIGHT_GREEN_BORDER,
            },
        )
        self.add_format(
            "num_format",
            {"num_format": "0"},
        )

        fixed_width_font: dict[str, str | int | float]
        match platform.system():
            case "Windows":
                fixed_width_font = {
                    "font_name": "Consolas",
                    "font_size": 10,
                }
            case "Darwin":
                fixed_width_font = {
                    "font_name": "Menlo",
                    "font_size": 9.5,
                }
            case _:
                fixed_width_font = {
                    "font_name": "Liberation Mono, 'DejaVu Sans Mono', 'Ubuntu Mono', Courier New",
                    "font_size": 9.5,
                }

        sha_format_spec = {**fixed_width_font, "align": "right"}
        self.add_format("SHA_format", sha_format_spec)

        code_format_spec = {**fixed_width_font, "indent": 1}
        self.add_format("code_format", code_format_spec)
        self.add_format(
            "code_italic_format", {**fixed_width_font, "indent": 1, "italic": True}
        )

        self.add_format("date_format", {"num_format": 14})

        for c in self.author_colors:
            self.author_color_formats.append(
                self.workbook.add_format(
                    {"bg_color": c, "border": 1, "border_color": "#D8E4BC"}
                )
            )

        Path(self.outfile).unlink(missing_ok=True)

        self.add_authors_sheet()
        self.add_authors_files_sheet()
        self.add_files_authors_sheet()
        self.add_files_sheet()
        if not self.args.blame_skip:
            self.add_blame_sheets()
        self.close()

    def add_format(self, format_name: str, format_spec: FormatSpec) -> None:
        excel_format = self.workbook.add_format(format_spec)
        self.formatstr2excelformat[format_name] = excel_format

    def add_authors_sheet(self) -> None:
        rows: list[Row] = self.get_author_rows(html=False)
        AuthorsSheet(
            rows,
            self.workbook.add_chart({"type": "pie"}),  # type: ignore
            self.header_authors(html=False),
            self.workbook.add_worksheet("Authors"),
            self,
        )

    def add_authors_files_sheet(self) -> None:
        rows: list[Row] = self.get_authors_files_rows(html=False)
        AuthorsFilesSheet(
            rows,
            self.header_authors_files(html=False),
            self.workbook.add_worksheet("Authors-Files"),
            self,
        )

    def add_files_authors_sheet(self) -> None:
        rows: list[Row] = self.get_files_authors_rows(html=False)
        FilesAuthorsSheet(
            rows,
            self.header_files_authors(html=False),
            self.workbook.add_worksheet("Files-Authors"),
            self,
        )

    def add_files_sheet(self) -> None:
        rows: list[Row] = self.get_files_rows()
        FilesSheet(
            rows,
            self.header_files(),
            self.workbook.add_worksheet("Files"),
            self,
        )

    def add_blame_sheet(
        self,
        name,
        rows: list[Row],
        iscomments: list[bool],
    ) -> None:
        if rows:
            sheet_name = name.replace("/", ">")
            BlameSheet(
                rows,
                iscomments,
                self.header_blames(self.args),
                self.workbook.add_worksheet(sheet_name),
                self,
            )

    def add_blame_sheets(
        self,
    ) -> None:
        fstrs: list[FileStr] = []
        fstr2rows: dict[FileStr, list[Row]] = {}
        fstr2iscomments: dict[FileStr, list[bool]] = {}

        for fstr in self.fstrs:
            rows, iscomments = self.get_fstr_blame_rows(fstr)
            if rows:
                fstrs.append(fstr)
                fstr2rows[fstr] = rows
                fstr2iscomments[fstr] = iscomments

        relative_fstrs = [
            get_relative_fstr(fstr, self.args.subfolder) for fstr in fstrs
        ]
        relative_fstr2truncated = self.string2truncated(
            relative_fstrs, MAX_LENGTH_SHEET_NAME
        )

        for fstr, rel_fstr in zip(fstrs, relative_fstrs):
            self.add_blame_sheet(
                relative_fstr2truncated[rel_fstr],
                fstr2rows[fstr],
                fstr2iscomments[fstr],
            )

    def close(self) -> None:
        self.workbook.close()
