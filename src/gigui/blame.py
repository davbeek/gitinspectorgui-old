from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import Commit as GitCommit
from git import Repo

from gigui.args_settings_keys import Args
from gigui.comment import get_is_comment_lines
from gigui.common import log
from gigui.data import FileStat, PersonsDB
from gigui.typedefs import (
    Author,
    BlameLines,
    Email,
    FileStr,
    GitBlames,
    Row,
    SHAlong,
    SHAshort,
)


# Commit that is used to order and number commits by date, starting at 1 for the
# initial commit.
@dataclass
class Commit:
    sha_short: SHAshort
    sha_long: SHAlong
    date: int


@dataclass
class Blame:
    author: Author
    email: Email
    date: datetime
    message: str
    sha_long: SHAlong
    commit_nr: int
    is_comment_lines: list[bool]
    lines: BlameLines


class BlameReader:
    args: Args

    # pylint: disable=too-many-arguments disable=too-many-positional-arguments
    def __init__(
        self,
        gitrepo: Repo,
        head_commit: GitCommit,
        ex_sha_shorts: set[SHAshort],
        fstrs: list[FileStr],
        persons_db: PersonsDB,
    ):
        self.gitrepo = gitrepo
        self.head_commit = head_commit
        self.ex_sha_shorts = ex_sha_shorts
        self.fstrs = fstrs
        self.persons_db = persons_db

        self.fstr2blames: dict[FileStr, list[Blame]] = {}

        self.sha_long2nr: dict[SHAlong, int] = self._set_sha_long2nr()

    # Sets the fstr2blames dictionary, but also adds the author and email of each
    # blame to the persons list. This is necessary, because the blame functionality
    # can have another way to set/get the author and email of a commit.
    def run(self, thread_executor: ThreadPoolExecutor):
        git_blames: GitBlames
        blames: list[Blame]
        if self.args.multi_thread:
            futures = [
                thread_executor.submit(self._get_git_blames_for, fstr)
                for fstr in self.fstrs
            ]
            for future in as_completed(futures):
                git_blames, fstr = future.result()
                blames = self._process_git_blames(fstr, git_blames)
                self.fstr2blames[fstr] = blames
        else:  # single thread
            for fstr in self.fstrs:
                git_blames, fstr = self._get_git_blames_for(fstr)
                blames = self._process_git_blames(fstr, git_blames)
                self.fstr2blames[fstr] = blames  # type: ignore

        # New authors and emails may have been found in the blames, so update
        # the authors of the blames with the possibly newly found persons
        fstr2blames: dict[FileStr, list[Blame]] = {}
        for fstr in self.fstrs:
            fstr2blames[fstr] = []
            for blame in self.fstr2blames[fstr]:
                blame.author = self.persons_db.get_author(blame.author)
                fstr2blames[fstr].append(blame)
        self.fstr2blames = fstr2blames

    # Need to number the complete list of all commits, because even when --since
    # severely restricts the number of commits to analyse, the result of git blame
    # always needs a commit that changed the file in question, even when there is no
    # such commit that satisfies the --since criterion.
    def _set_sha_long2nr(self) -> dict[SHAlong, int]:
        c: GitCommit
        sha_long2nr: dict[SHAlong, int] = {}
        i = 1
        for c in self.gitrepo.iter_commits(reverse=True):
            sha_long2nr[c.hexsha] = i
            i += 1
        return sha_long2nr

    def _get_git_blames_for(self, fstr: FileStr) -> tuple[GitBlames, FileStr]:
        copy_move_int2opts: dict[int, list[str]] = {
            0: [],
            1: ["-M"],
            2: ["-C"],
            3: ["-C", "-C"],
            4: ["-C", "-C", "-C"],
        }
        blame_opts: list[str] = copy_move_int2opts[self.args.copy_move]
        if self.args.since:
            blame_opts.append(f"--since={self.args.since}")
        if not self.args.whitespace:
            blame_opts.append("-w")
        for rev in self.ex_sha_shorts:
            blame_opts.append(f"--ignore-rev={rev}")
        working_dir = self.gitrepo.working_dir
        ignore_revs_path = Path(working_dir) / "_git-blame-ignore-revs.txt"
        if ignore_revs_path.exists():
            blame_opts.append(f"--ignore-revs-file={str(ignore_revs_path)}")

        # Run the git command to get the blames for the file.
        git_blames: GitBlames = self.gitrepo.blame(
            self.head_commit.hexsha, fstr, rev_opts=blame_opts
        )  # type: ignore
        return git_blames, fstr

    def _process_git_blames(self, fstr: FileStr, git_blames: GitBlames) -> list[Blame]:
        blames: list[Blame] = []
        dot_ext = Path(fstr).suffix
        extension = dot_ext[1:] if dot_ext else ""
        in_multi_comment = False
        for b in git_blames:  # type: ignore
            c: GitCommit = b[0]  # type: ignore

            author = c.author.name  # type: ignore
            email = c.author.email  # type: ignore
            self.persons_db.add_person(author, email)

            nr = self.sha_long2nr[c.hexsha]  # type: ignore
            lines: BlameLines = b[1]  # type: ignore
            is_comment_lines: list[bool]
            is_comment_lines, _ = get_is_comment_lines(
                extension, lines, in_multi_comment
            )
            blame: Blame = Blame(
                author,  # type: ignore
                email,  # type: ignore
                c.committed_datetime,  # type: ignore
                c.message,  # type: ignore
                c.hexsha,  # type: ignore
                nr,  # commit number
                is_comment_lines,
                lines,  # type: ignore
            )
            blames.append(blame)
        return blames


class BlameTables:
    args: Args

    def __init__(
        self,
        fstrs: list[FileStr],
        persons_db: PersonsDB,
        fstr2blames: dict[FileStr, list[Blame]],
    ):
        self.fstrs = fstrs
        self.persons_db = persons_db
        self.fstr2blames = fstr2blames

        # List of blame authors, so no filtering, ordered by highest blame line count.
        self._blame_authors: list[Author]

    def out_blames(self) -> dict[FileStr, tuple[list[Row], list[bool]]]:
        fstr2rows_iscomments: dict[FileStr, tuple[list[Row], list[bool]]] = {}
        for fstr in self.fstr2blames:
            rows, iscomments = self._out_blames_fstr(fstr)
            if rows:
                fstr2rows_iscomments[fstr] = rows, iscomments
            else:
                log(f"No blame output matching filters found for file {fstr}")
        return fstr2rows_iscomments

    # pylint: disable=too-many-locals
    def _out_blames_fstr(self, fstr: FileStr) -> tuple[list[Row], list[bool]]:
        blames: list[Blame] = self.fstr2blames[fstr]
        rows: list[Row] = []
        is_comments: list[bool] = []
        line_nr = 1

        author2nr: dict[Author, int] = {}
        author_nr = 1
        for author in self._blame_authors:
            if author in self.persons_db.authors_included:
                author2nr[author] = author_nr
                author_nr += 1
            else:
                author2nr[author] = 0

        # Create row for each blame line.
        for b in blames:
            author = self.persons_db.get_author(b.author)
            for line, is_comment in zip(b.lines, b.is_comment_lines):
                exclude_comment = is_comment and not self.args.comments
                exclude_empty = line.strip() == "" and not self.args.empty_lines
                exclude_author = author in self.persons_db.authors_excluded
                exclude_line = exclude_comment or exclude_empty or exclude_author
                if self.args.blame_omit_exclusions and exclude_line:
                    line_nr += 1
                else:
                    row = [
                        0 if exclude_line else author2nr[author],
                        author,
                        b.date.strftime("%Y-%m-%d"),
                        b.message,
                        b.sha_long[:7],
                        b.commit_nr,
                        line_nr,
                        line,
                    ]
                    rows.append(row)
                    is_comments.append(is_comment)
                    line_nr += 1
        return rows, is_comments

    def run(self, author2fstr2fstat: dict[Author, dict[FileStr, FileStat]]):
        """
        Update author2fstr2fstat with line counts for each author.
        Sets local list of sordered unfiltered _blame_authors.
        """
        author2line_count: dict[Author, int] = {}
        target = author2fstr2fstat
        for fstr in self.fstrs:
            blames = self.fstr2blames[fstr]
            for b in blames:
                person = self.persons_db.get_person(b.author)
                author = person.author
                if author not in author2line_count:
                    author2line_count[author] = 0
                total_line_count = len(b.lines)  # type: ignore
                comment_lines_subtract = (
                    0 if self.args.comments else b.is_comment_lines.count(True)
                )
                empty_lines_subtract = (
                    0
                    if self.args.empty_lines
                    else len([line for line in b.lines if not line.strip()])
                )
                line_count = (
                    total_line_count - comment_lines_subtract - empty_lines_subtract
                )
                author2line_count[author] += line_count
                if not person.filter_matched:
                    if fstr not in target[author]:
                        target[author][fstr] = FileStat(fstr)
                    target[author][fstr].stat.line_count += line_count  # type: ignore
                    target[author]["*"].stat.line_count += line_count
                    target["*"]["*"].stat.line_count += line_count
        authors = author2line_count.keys()
        authors = sorted(authors, key=lambda x: author2line_count[x], reverse=True)
        self._blame_authors = authors
