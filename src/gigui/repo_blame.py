import copy
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from pathlib import Path

from git import Repo as GitRepo

from gigui.comment import get_is_comment_lines
from gigui.constants import BLAME_CHUNK_SIZE, MAX_THREAD_WORKERS
from gigui.data import FileStat, IniRepo
from gigui.repo_base import RepoBase
from gigui.typedefs import (
    OID,
    SHA,
    Author,
    BlameStr,
    Email,
    FileStr,
)

logger = getLogger(__name__)


@dataclass
class LineData:
    line: str = ""
    fstr: FileStr = ""
    line_nr: int = 0  # line number in file fstr
    is_comment: bool = False


@dataclass
class Blame:
    author: Author = ""
    email: Email = ""
    date: datetime = 0  # type: ignore
    message: str = ""
    sha: SHA = ""
    oid: OID = ""
    commit_nr: int = 0
    line_datas: list[LineData] = field(default_factory=list)


class RepoBlameBase(RepoBase):
    def __init__(self, ini_repo: IniRepo) -> None:
        super().__init__(ini_repo)

        # List of blame authors, so no filtering, ordered by highest blame line count.
        self.blame_authors: list[Author] = []

        self.fstr2blames: dict[FileStr, list[Blame]] = {}
        self.blame: Blame = Blame()

    def get_blames_for(
        self, fstr: FileStr, start_sha: SHA, i: int, i_max: int
    ) -> tuple[FileStr, list[Blame]]:
        blame_lines: list[BlameStr]
        blames: list[Blame]
        blame_lines, _ = self._get_git_blames_for(fstr, start_sha)
        if self.args.verbosity == 0 and not self.args.multicore:
            self.log_dot()
        logger.info(" " * 8 + f"{i} of {i_max}: {self.name} {fstr}")
        blames = BlameReader(blame_lines, self).process_lines(fstr)
        self.fstr2blames[fstr] = blames
        return fstr, blames

    def _get_git_blames_for(
        self, fstr: FileStr, start_sha: SHA
    ) -> tuple[list[BlameStr], FileStr]:
        copy_move_int2opts: dict[int, list[str]] = {
            0: [],
            1: ["-M"],
            2: ["-C"],
            3: ["-C", "-C"],
            4: ["-C", "-C", "-C"],
        }
        blame_opts: list[str] = copy_move_int2opts[self.args.copy_move]
        if not self.args.whitespace:
            blame_opts.append("-w")
        for rev in self.ex_shas:
            blame_opts.append(f"--ignore-rev={rev}")
        working_dir = self.location
        ignore_revs_path = Path(working_dir) / "_git-blame-ignore-revs.txt"
        if ignore_revs_path.exists():
            blame_opts.append(f"--ignore-revs-file={str(ignore_revs_path)}")
        # Run the git command to get the blames for the file.
        blame_str: BlameStr = self._run_git_blame(start_sha, fstr, blame_opts)
        return blame_str.splitlines(), fstr

    def _run_git_blame(
        self,
        start_sha: SHA,
        root_fstr: FileStr,
        blame_opts: list[str],
    ) -> BlameStr:
        fstr = self.get_fstr_for_sha(root_fstr, start_sha)
        if not fstr:
            raise ValueError(
                f"File {root_fstr} not found at {start_sha}, "
                f"number {self.sha2nr[start_sha]}."
            )
        start_oid = self.sha2oid[start_sha]
        blame_str: BlameStr
        if self.args.multithread:
            # GitPython is not tread-safe, so we create a new GitRepo object ,just to be
            # sure.
            git_repo = GitRepo(self.location)
            blame_str = git_repo.git.blame(
                start_oid, fstr, "--follow", "--porcelain", *blame_opts
            )  # type: ignore
            git_repo.close()
        else:
            blame_str = self.git_repo.git.blame(
                start_oid, fstr, "--follow", "--porcelain", *blame_opts
            )  # type: ignore
        return blame_str


class RepoBlame(RepoBlameBase):
    # Set the fstr2blames dictionary, but also add the author and email of each blame to
    # the persons list. This is necessary, because the blame functionality can have
    # another way to set/get the author and email of a commit.
    def run_blame(self) -> None:
        logger = getLogger(__name__)
        i_max: int = len(self.fstrs)
        i: int = 0
        chunk_size: int = BLAME_CHUNK_SIZE
        logger.info(" " * 8 + f"Blame: {self.name}: {i_max} files")
        if self.args.multithread:
            with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
                for chunk_start in range(0, i_max, chunk_size):
                    chunk_end = min(chunk_start + chunk_size, i_max)
                    chunk_fstrs = self.fstrs[chunk_start:chunk_end]
                    futures = [
                        thread_executor.submit(
                            self.get_blames_for, fstr, self.head_sha, i + inc + 1, i_max
                        )
                        for inc, fstr in enumerate(chunk_fstrs)
                    ]
                    for future in as_completed(futures):
                        fstr, blames = future.result()
                        self.fstr2blames[fstr] = blames

        else:  # single thread
            for fstr in self.fstrs:
                fstr, blames = self.get_blames_for(fstr, self.head_sha, i, i_max)
                self.fstr2blames[fstr] = blames
                i += 1

        # New authors and emails may have been found in the blames, so update
        # the authors of the blames with the possibly newly found persons.
        # Create a local version of self.fstr2blames with the new authors.
        fstr2blames: dict[FileStr, list[Blame]] = {}
        for fstr in self.fstrs:
            # fstr2blames will be the new value of self.fstr2blames
            fstr2blames[fstr] = []
            for b in self.fstr2blames[fstr]:
                # update author
                b.author = self.persons_db[b.author].author
                fstr2blames[fstr].append(b)
        self.fstr2blames = fstr2blames

    def update_author2fstr2fstat(
        self, author2fstr2fstat: dict[Author, dict[FileStr, FileStat]]
    ) -> dict[Author, dict[FileStr, FileStat]]:
        """
        Update author2fstr2fstat with line counts for each author.
        Set local list of sorted unfiltered _blame_authors.
        """
        author2line_count: dict[Author, int] = {}
        target = author2fstr2fstat
        b: Blame
        for fstr in self.fstrs:
            blames: list[Blame] = self.fstr2blames[fstr]
            for b in blames:
                if b.commit_nr not in self.sha_since_until_nrs:
                    continue
                person = self.persons_db[b.author]
                author = person.author
                if author not in author2line_count:
                    author2line_count[author] = 0
                total_line_count = len(b.line_datas)  # type: ignore
                comment_lines_subtract = (
                    0
                    if self.args.comments
                    else [bl.is_comment for bl in b.line_datas].count(True)
                )
                empty_lines_subtract = (
                    0
                    if self.args.empty_lines
                    else len([bl.line for bl in b.line_datas if not bl.line.strip()])
                )
                line_count = (
                    total_line_count - comment_lines_subtract - empty_lines_subtract
                )
                author2line_count[author] += line_count
                if not person.filter_matched:
                    if fstr not in target[author]:
                        target[author][fstr] = FileStat(fstr)
                    target[author][fstr].stat.blame_line_count += line_count  # type: ignore
                    target[author]["*"].stat.blame_line_count += line_count
                    target["*"]["*"].stat.blame_line_count += line_count
        return target

    def get_blame_shas_for_fstr(self, fstr: FileStr) -> list[SHA]:
        shas: set[SHA] = set()
        shas_sorted: list[SHA]
        blames: list[Blame] = self.fstr2blames[fstr]
        b: Blame
        d: LineData
        d_ok: bool
        first_sha_nr: int  # nr of the commit where fstr was first added
        first_sha_nr = self.fr2sha_nrs[fstr][-1]
        sha_nr: int

        # Note that exclusion of revisions is already done in the blame generation.
        for b in blames:
            for d in b.line_datas:
                d_ok = self.line_data_ok(b, d)
                if d_ok:
                    sha_nr = self.sha2nr[b.sha]
                    if sha_nr >= first_sha_nr:
                        shas.add(b.sha)
        shas.add(self.head_sha)
        shas_sorted = sorted(shas, key=lambda x: self.sha2nr[x], reverse=True)
        return shas_sorted

    def line_data_ok(self, b: Blame, d: LineData) -> bool:
        comment_ok: bool = self.args.comments or not d.is_comment
        empty_ok: bool = self.args.empty_lines or not d.line.strip() == ""
        author_ok: bool = b.author not in self.args.ex_authors
        date_ok: bool = b.commit_nr in self.sha_since_until_nrs
        ok: bool = comment_ok and empty_ok and author_ok and date_ok
        return ok


class RepoBlameHistory(RepoBlame):
    def __init__(self, ini_repo: IniRepo) -> None:
        super().__init__(ini_repo)

        self.fr2f2shas: dict[FileStr, dict[FileStr, list[SHA]]] = {}
        self.fstr2sha2blames: dict[FileStr, dict[SHA, list[Blame]]] = {}

    def generate_fr_blame_history(self, root_fstr: FileStr, sha: SHA) -> list[Blame]:
        blame_lines: list[BlameStr]
        blame_lines, _ = self._get_git_blames_for(root_fstr, sha)
        blames: list[Blame] = BlameReader(blame_lines, self).process_lines(root_fstr)
        return blames


class BlameReader:
    def __init__(self, lines: list[BlameStr], repo: RepoBase) -> None:
        self.lines: list[BlameStr] = lines
        self.fstr: FileStr = ""
        self.oid2blame: dict[
            OID, Blame
        ] = {}  # associates OIDs with Blame objects without blame lines
        self.repo: RepoBase = repo

    def process_lines(self, root_fstr: FileStr) -> list[Blame]:
        blame: Blame
        blames: list[Blame] = []
        code_lines: list[str] = []
        comment_lines: list[bool] = []
        i: int = 0
        while i < len(self.lines):
            blame, i = self.get_next_blame(i)
            blames.append(blame)
        code_lines = [bl.line for b in blames for bl in b.line_datas]
        comment_lines, _ = get_is_comment_lines(
            code_lines,
            fstr=root_fstr,
        )
        i = 0
        for b in blames:
            for bl in b.line_datas:
                bl.is_comment = comment_lines[i]
                i += 1
        return blames

    def get_next_blame(self, i: int) -> tuple[Blame, int]:
        line: BlameStr = self.lines[i]
        b: Blame
        if re.match(r"^[a-f0-9]{40} ", line):
            parts: list[str] = line.split()
            oid = parts[0]
            line_nr = int(parts[1])
            line_count = int(parts[3])
            if oid in self.oid2blame:
                b, i = self.get_additional_blame(oid, line_nr, line_count, i + 1)
            else:
                b, i = self.get_new_blame(oid, line_nr, line_count, i + 1)
                self.oid2blame[oid] = copy.deepcopy(b)
                self.oid2blame[oid].line_datas = []
        else:
            raise ValueError(f"Unexpected line: {line}")
        return b, i

    def get_new_blame(
        self, oid: OID, line_nr: int, line_count: int, i: int
    ) -> tuple[Blame, int]:
        line: BlameStr = self.lines[i]
        b: Blame = Blame()
        d: LineData = LineData()
        b.oid = oid
        b.sha = self.repo.oid2sha[b.oid]
        b.commit_nr = self.repo.sha2nr[self.repo.oid2sha[b.oid]]
        d.line_nr = line_nr
        while not line.startswith("filename "):
            if line.startswith("author "):
                b.author = line[len("author ") :]
            elif line.startswith("author-mail "):
                b.email = line[len("author-mail ") :].strip("<>")
            elif line.startswith("author-time "):
                b.date = datetime.fromtimestamp(int(line[len("author-time ") :]))
            elif line.startswith("summary "):
                b.message = line[len("summary ") :]
            i += 1
            line = self.lines[i]
        self.fstr = line[len("filename ") :]
        d.fstr = self.fstr
        i += 1
        d, i = self.parse_line(d, i)
        b.line_datas.append(d)
        for _ in range(line_count - 1):
            d, i = self.get_blame_oid_line(oid, i)
            b.line_datas.append(d)
        return b, i

    def get_additional_blame(
        self, oid: OID, line_nr: int, line_count: int, i: int
    ) -> tuple[Blame, int]:
        d: LineData = LineData()
        b: Blame = deepcopy(self.oid2blame[oid])
        line_datas: list[LineData] = []
        if self.lines[i].startswith("previous "):
            i += 1
        if self.lines[i].startswith("filename "):
            self.fstr = self.lines[i][len("filename ") :]
            i += 1
        d.line_nr = line_nr
        d.fstr = self.fstr
        d, i = self.parse_line(d, i)
        line_datas.append(d)
        for _ in range(line_count - 1):
            d, i = self.get_blame_oid_line(oid, i)
            line_datas.append(d)
        b.line_datas = line_datas
        return b, i

    def get_blame_oid_line(self, oid: OID, i: int) -> tuple[LineData, int]:
        line: BlameStr = self.lines[i]
        d: LineData = LineData()
        parts: list[str] = line.split()
        assert parts[0] == oid, f"Read {parts[0]} instead of {oid} in {line}"
        d.line_nr = int(parts[1])
        d.fstr = self.fstr
        line = self.lines[i + 1]
        assert line.startswith("\t"), f"Expected starting tab, got {line}"
        d.line = line[1:]
        return d, i + 2

    def parse_line(self, d: LineData, i: int) -> tuple[LineData, int]:
        line: BlameStr = self.lines[i]
        assert line.startswith("\t"), f"Expected starting tab, got {line}"
        d.line = line[1:]
        d.fstr = self.fstr
        return d, i + 1
