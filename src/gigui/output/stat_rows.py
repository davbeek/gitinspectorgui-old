from math import isnan
from typing import Any

from gigui.data import FileStat, PersonStat, Stat
from gigui.repo import GIRepo
from gigui.typedefs import Author, FileStr, Row

deletions: bool = False
scaled_percentages: bool = False


def header_stat() -> list[str]:
    return [
        "% Lines",
        "% Insertions",
        "Lines",
        "Insertions",
        "Stability",
        "Commits",
    ] + (["Deletions", "Age Y:M:D"] if deletions else ["Age Y:M:D"])


def header_authors(html: bool = True) -> list[str]:
    header_prefix = ["ID", "Author"] + (["Empty", "Email"] if html else ["Email"])
    if scaled_percentages:
        return (
            header_prefix
            + [
                "% Lines",
                "% Insertions",
                "% Scaled Lines",
                "% Scaled Insertions",
                "Lines",
                "Insertions",
                "Stability",
                "Commits",
            ]
            + (["Deletions", "Age"] if deletions else ["Age"])
        )
    else:
        return header_prefix + header_stat()


def header_authors_files(html: bool = True) -> list[str]:
    header_prefix = ["ID", "Author"] + (["Empty", "File"] if html else ["File"])
    return header_prefix + header_stat()


def header_files_authors(html: bool = True) -> list[str]:
    header_prefix = ["ID", "File"] + (["Empty", "Author"] if html else ["Author"])
    return header_prefix + header_stat()


def header_files() -> list[str]:
    return ["ID", "File"] + header_stat()


def percentage_to_out(percentage: float) -> int | str:
    if isnan(percentage):
        return ""
    else:
        return round(percentage)


class TableRows:
    subfolder: str = ""
    deletions: bool = False

    def __init__(self, repo: GIRepo):
        self.repo = repo
        self.rows: list[Row] = []

    def _get_stat_values(self, stat: Stat, nr_authors: int = 2) -> list[Any]:
        return (
            [
                percentage_to_out(stat.percent_lines),
                percentage_to_out(stat.percent_insertions),
            ]
            + (
                [
                    percentage_to_out(stat.percent_lines * nr_authors),
                    percentage_to_out(stat.percent_insertions * nr_authors),
                ]
                if scaled_percentages
                else []
            )
            + [
                stat.line_count,
                stat.insertions,
                stat.stability,
                len(stat.commits),
            ]
            + ([stat.deletions, stat.age] if self.deletions else [stat.age])
        )


class AuthorsTableRows(TableRows):
    def get_rows(self, html: bool = True) -> list[Row]:
        a2p: dict[Author, PersonStat] = self.repo.author2pstat
        row: Row
        rows: list[Row] = []
        id_val: int = 0
        for author in self.repo.authors_included:
            person = self.repo.get_person(author)
            row = [id_val, person.authors_str] + (
                ["", person.emails_str] if html else [person.emails_str]
            )  # type: ignore
            row.extend(self._get_stat_values(a2p[author].stat, len(a2p)))
            rows.append(row)
            id_val += 1
        return rows


class AuthorsFilesTableRows(TableRows):
    def get_rows(self, html: bool = True) -> list[Row]:
        a2f2f: dict[Author, dict[FileStr, FileStat]] = self.repo.author2fstr2fstat
        row: Row
        rows: list[Row] = []
        id_val: int = 0
        for author in self.repo.authors_included:
            person = self.repo.get_person(author)
            fstrs = list(a2f2f[author].keys())
            fstrs = sorted(
                fstrs,
                key=lambda x: self.repo.fstr2fstat[x].stat.line_count,
                reverse=True,
            )
            for fstr in fstrs:
                row = []
                rel_fstr = a2f2f[author][fstr].relative_names_str(self.subfolder)
                row.extend(
                    [id_val, person.authors_str]
                    + (["", rel_fstr] if html else [rel_fstr])  # type: ignore
                )
                stat = a2f2f[author][fstr].stat
                row.extend(self._get_stat_values(stat))
                rows.append(row)
            id_val += 1
        return rows


class FilesAuthorsTableRows(TableRows):
    def get_rows(self, html: bool = True) -> list[Row]:
        f2a2f: dict[FileStr, dict[Author, FileStat]] = self.repo.fstr2author2fstat
        row: Row
        rows: list[Row] = []
        id_val: int = 0
        fstrs = list(f2a2f.keys())
        fstrs = sorted(
            fstrs,
            key=lambda x: self.repo.fstr2fstat[x].stat.line_count,
            reverse=True,
        )
        for fstr in fstrs:
            authors = list(f2a2f[fstr].keys())
            authors = sorted(
                authors,
                key=lambda x: f2a2f[fstr][  # pylint: disable=cell-var-from-loop
                    x
                ].stat.line_count,
                reverse=True,
            )
            for author in authors:
                row = []
                row.extend(
                    [id_val, f2a2f[fstr][author].relative_names_str(self.subfolder)]
                    + (["", author] if html else [author])  # type: ignore
                )
                stat = f2a2f[fstr][author].stat
                row.extend(self._get_stat_values(stat))
                rows.append(row)
            id_val += 1
        return rows


class FilesTableRows(TableRows):
    def get_rows(self) -> list[Row]:
        f2f: dict[FileStr, FileStat] = self.repo.fstr2fstat
        rows: list[Row] = []
        row: Row
        id_val: int = 0
        for fstr in self.repo.star_fstrs:
            row = [id_val, f2f[fstr].relative_names_str(self.subfolder)]
            row.extend(self._get_stat_values(f2f[fstr].stat))
            rows.append(row)
            id_val += 1
        return rows
