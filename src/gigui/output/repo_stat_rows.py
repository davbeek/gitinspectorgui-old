from math import isnan
from typing import Any

from gigui.data import FileStat, PersonStat, Stat
from gigui.repo_data import RepoData
from gigui.typedefs import Author, FileStr, Row


class RepoStatRows(RepoData):
    def get_author_rows(self, html: bool = True) -> list[Row]:
        a2p: dict[Author, PersonStat] = self.author2pstat
        row: Row
        rows: list[Row] = []
        id_val: int = 0
        nr_authors = len(self.real_authors_included)
        for author in self.authors_included:
            person = self.persons_db[author]
            row = [id_val, person.authors_str] + (
                ["", person.emails_str] if html else [person.emails_str]
            )  # type: ignore
            row.extend(self._get_stat_values(a2p[author].stat, nr_authors))
            rows.append(row)
            id_val += 1
        return rows

    def get_authors_files_rows(self, html: bool = True) -> list[Row]:
        a2f2f: dict[Author, dict[FileStr, FileStat]] = self.author2fstr2fstat
        row: Row
        rows: list[Row] = []
        id_val: int = 0
        for author in self.authors_included:
            person = self.persons_db[author]
            fstrs = list(a2f2f[author].keys())
            fstrs = sorted(
                fstrs,
                key=lambda x: self.fstr2fstat[x].stat.blame_line_count,
                reverse=True,
            )
            for fstr in fstrs:
                row = []
                rel_fstr = a2f2f[author][fstr].relative_names_str(self.args.subfolder)
                row.extend(
                    [id_val, person.authors_str]
                    + (["", rel_fstr] if html else [rel_fstr])  # type: ignore
                )
                stat = a2f2f[author][fstr].stat
                row.extend(self._get_stat_values(stat))
                rows.append(row)
            id_val += 1
        return rows

    def get_files_authors_rows(self, html: bool = True) -> list[Row]:
        f2a2f: dict[FileStr, dict[Author, FileStat]] = self.fstr2author2fstat
        row: Row
        rows: list[Row] = []
        id_val: int = 0
        fstrs = list(f2a2f.keys())
        fstrs = sorted(
            fstrs,
            key=lambda x: self.fstr2fstat[x].stat.blame_line_count,
            reverse=True,
        )
        for fstr in fstrs:
            authors = list(f2a2f[fstr].keys())
            authors = sorted(
                authors,
                key=lambda x: f2a2f[fstr][  # pylint: disable=cell-var-from-loop
                    x
                ].stat.blame_line_count,
                reverse=True,
            )
            for author in authors:
                row = []
                row.extend(
                    [
                        id_val,
                        f2a2f[fstr][author].relative_names_str(self.args.subfolder),
                    ]
                    + (["", author] if html else [author])  # type: ignore
                )
                stat = f2a2f[fstr][author].stat
                row.extend(self._get_stat_values(stat))
                rows.append(row)
            id_val += 1
        return rows

    def get_files_rows(self) -> list[Row]:
        f2f: dict[FileStr, FileStat] = self.fstr2fstat
        rows: list[Row] = []
        row: Row
        id_val: int = 0
        for fstr in self.star_fstrs:
            row = [id_val, f2f[fstr].relative_names_str(self.args.subfolder)]
            row.extend(self._get_stat_values(f2f[fstr].stat))
            rows.append(row)
            id_val += 1
        return rows

    def _get_stat_values(self, stat: Stat, nr_authors: int = -1) -> list[Any]:
        return (
            [stat.blame_line_count]
            + [stat.insertions]
            + ([stat.deletions] if self.args.deletions else [])  # noqa: F821
            + [_percentage_to_out(stat.percent_lines)]
            + [_percentage_to_out(stat.percent_insertions)]
            + (
                [
                    _percentage_to_out(stat.percent_lines * nr_authors),
                    _percentage_to_out(stat.percent_insertions * nr_authors),
                ]
                if self.args.scaled_percentages and not nr_authors == -1  # noqa: F821
                else []
            )
            + [
                stat.stability,
                len(stat.shas),
                stat.age,
            ]
        )

    def header_authors(self, html: bool = True) -> list[str]:
        header_prefix = ["ID", "Author"] + (["Empty", "Email"] if html else ["Email"])
        if self.args.scaled_percentages:  # noqa: F821
            return (
                header_prefix
                + [
                    "Lines",
                    "Insertions",
                ]
                + (["Deletions"] if self.args.deletions else [])  # noqa: F821
                + [
                    "% Lines",
                    "% Insertions",
                    "% Scaled Lines",
                    "% Scaled Insertions",
                ]
                + [
                    "Stability",
                    "Commits",
                    "Age Y:M:D",
                ]  # noqa: F821
            )
        else:
            return header_prefix + self._header_stat()

    def header_authors_files(self, html: bool = True) -> list[str]:
        header_prefix = ["ID", "Author"] + (["Empty", "File"] if html else ["File"])
        return header_prefix + self._header_stat()

    def header_files_authors(self, html: bool = True) -> list[str]:
        header_prefix = ["ID", "File"] + (["Empty", "Author"] if html else ["Author"])
        return header_prefix + self._header_stat()

    def header_files(self) -> list[str]:
        return ["ID", "File"] + self._header_stat()

    def _header_stat(self) -> list[str]:
        return (
            [
                "Lines",
                "Insertions",
            ]
            + (["Deletions"] if self.args.deletions else [])  # noqa: F821
            + [
                "% Lines",
                "% Insertions",
            ]
            + [
                "Stability",
                "Commits",
                "Age Y:M:D",
            ]
        )


def _percentage_to_out(percentage: float) -> int | str:
    if isnan(percentage):
        return ""
    else:
        return round(percentage)
