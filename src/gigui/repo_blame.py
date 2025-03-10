import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from pathlib import Path

from git import Repo as GitRepo

from gigui._logging import log_dots
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
class Blame:
    author: Author = ""
    email: Email = ""
    date: datetime = 0  # type: ignore
    message: str = ""
    sha: SHA = ""
    oid: OID = ""
    commit_nr: int = 0
    fstr: FileStr = ""
    is_comment_lines: list[bool] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def merge(self, b: "Blame"):
        assert not self.oid or not b.oid or self.oid == b.oid, (
            f"Cannot merge different OIDs: {self.oid} != {b.oid}"
        )
        assert not self.sha or not b.sha or self.sha == b.sha, (
            f"Cannot merge different SHAs: {self.sha} != {b.sha}"
        )
        assert not self.commit_nr or not b.commit_nr or self.commit_nr == b.commit_nr, (
            f"Cannot merge different commit numbers: {self.commit_nr} != {b.commit_nr}"
        )
        # assert not self.fstr or not b.fstr or self.fstr == b.fstr, (
        #     f"Cannot merge different file strings: {self.fstr} != {b.fstr}"
        # )
        if self.fstr and b.fstr and self.fstr != b.fstr:
            logger.warning(f"Merge overwrites {self.fstr} by {b.fstr} in {self}")
        self.oid = b.oid if b.oid else self.oid
        self.sha = b.sha if b.sha else self.sha
        self.commit_nr = b.commit_nr if b.commit_nr else self.commit_nr
        self.author = b.author if b.author else self.author
        self.email = b.email if b.email else self.email
        self.date = b.date if b.date else self.date
        self.message = b.message if b.message else self.message
        self.fstr = b.fstr if b.fstr else self.fstr
        self.is_comment_lines.extend(b.is_comment_lines)
        self.lines.extend(b.lines)


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
        blame_lines, _ = self._get_git_blames_for(fstr, start_sha)
        if self.args.verbosity == 0 and not self.args.multicore:
            log_dots(i, i_max, "", "\n")
        logger.info(" " * 8 + f"{i} of {i_max}: {self.name} {fstr}")
        blames: list[Blame] = self._process_blame_lines(fstr, blame_lines)
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
        fstr: FileStr,
        blame_opts: list[str],
    ) -> BlameStr:
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

    def _process_blame_lines(self, fstr: FileStr, lines: list[BlameStr]) -> list[Blame]:
        blames: list[Blame] = []
        oid2blame: dict[
            OID, Blame
        ] = {}  # associates OIDs with Blame objects without blame lines
        oid: OID = ""
        current_oid: OID = ""

        # True if we are obtaining commit info other than blame files, such as author,
        # email and sha.
        oid_in_progress: bool = False
        code_str: str = ""
        i: int = 0
        self.blame = Blame()
        is_comment_lines: list[bool]
        while i < len(lines):
            line = lines[i]
            if re.match(r"^[a-f0-9]{40} ", line):
                oid = line.split()[0]
                if oid != current_oid:
                    # new oid
                    if self.blame.oid:
                        # save the current blame object
                        blames.append(self.blame)
                    if oid in oid2blame:
                        self.blame = oid2blame[oid]
                    else:
                        self.blame = Blame()
                    current_oid = oid
                    oid_in_progress = True
                    self._parse_git_blame_porcelain(line, fstr)
                else:  # oid == current_oid
                    i += 1
                    line = lines[i]
                    if line.startswith("filename "):
                        new_fstr = line[len("filename ") :]
                        if self.blame.fstr != fstr:
                            logger.warning(
                                f"File {fstr} has two blame files {self.blame.fstr} "
                                f"and {new_fstr} for commit {self.blame.sha},"
                                f"ignoring {new_fstr}."
                            )
                        i += 1
                        line = lines[i]
                    assert line.startswith("\t"), f"Expected tab, got {line}"
                    code_str = line[1:]
                    self.blame.lines.append(code_str)
                    is_comment_lines, _ = get_is_comment_lines(
                        lines=[code_str],
                        fstr=fstr,
                    )
                    self.blame.is_comment_lines.extend(is_comment_lines)
            elif oid_in_progress:
                self._parse_git_blame_porcelain(line, fstr)
                if line.startswith("filename "):
                    oid2blame[oid] = self.blame
                    self._parse_git_blame_porcelain(line, fstr)
                    oid_in_progress = False
                    i += 1
                    self._parse_git_blame_porcelain(lines[i], fstr)
            else:
                raise ValueError(f"Unexpected line: {line}")
            i += 1

        for b in oid2blame.values():
            blames.append(b)
        return blames

    def _parse_git_blame_porcelain(self, line: str, fstr: FileStr) -> None:
        b: Blame = Blame()
        if re.match(r"^[a-f0-9]{40} ", line):
            parts = line.split()
            b.oid = parts[0]
            b.sha = self.oid2sha[b.oid]
            b.commit_nr = self.sha2nr[b.sha]
        elif line.startswith("author "):
            b.author = line[len("author ") :]
        elif line.startswith("author-mail "):
            b.email = line[len("author-mail ") :].strip("<>")
        elif line.startswith("author-time "):
            b.date = datetime.fromtimestamp(int(line[len("author-time ") :]))
        elif line.startswith("summary "):
            b.message = line[len("summary ") :]
        elif line.startswith("filename "):
            b.fstr = line[len("filename ") :]
        elif line.startswith("\t"):
            b.lines = [line[1:]]
            b.is_comment_lines, _ = get_is_comment_lines(
                lines=b.lines,
                fstr=fstr,
            )
        self.blame.merge(b)


class RepoBlame(RepoBlameBase):
    # Set the fstr2blames dictionary, but also add the author and email of each blame to
    # the persons list. This is necessary, because the blame functionality can have
    # another way to set/get the author and email of a commit.
    def run_blame(self) -> None:
        logger = getLogger(__name__)
        i_max: int = len(self.all_fstrs)
        i: int = 0
        chunk_size: int = BLAME_CHUNK_SIZE
        logger.info(" " * 8 + f"Blame: {self.name}: {i_max} files")
        if self.args.multithread:
            with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
                for chunk_start in range(0, i_max, chunk_size):
                    chunk_end = min(chunk_start + chunk_size, i_max)
                    chunk_fstrs = self.all_fstrs[chunk_start:chunk_end]
                    futures = [
                        thread_executor.submit(
                            self.get_blames_for, fstr, self.head_sha, i, i_max
                        )
                        for fstr in chunk_fstrs
                    ]
                    for future in as_completed(futures):
                        fstr, blames = future.result()
                        self.fstr2blames[fstr] = blames

        else:  # single thread
            for fstr in self.all_fstrs:
                fstr, blames = self.get_blames_for(fstr, self.head_sha, i, i_max)
                self.fstr2blames[fstr] = blames
                i += 1

        # New authors and emails may have been found in the blames, so update
        # the authors of the blames with the possibly newly found persons.
        # Create a local version of self.fstr2blames with the new authors.
        fstr2blames: dict[FileStr, list[Blame]] = {}
        for fstr in self.all_fstrs:
            # fstr2blames will be the new value of self.fstr2blames
            fstr2blames[fstr] = []
            for b in self.fstr2blames[fstr]:
                # update author
                b.author = self.persons_db[b.author].author
                fstr2blames[fstr].append(b)
        self.fstr2blames = fstr2blames

    def update_fr2f2a2sha_set_with_blames(self) -> None:
        # New files and shas may have been found in the blames for option --copy-move >=
        # 2, so update the files and shas.
        for fstr in self.all_fstrs:
            target = self.fr2f2a2sha_set
            if fstr not in target:
                target[fstr] = {}
            for b in self.fstr2blames[fstr]:
                if b.fstr not in target[fstr]:
                    target[fstr][b.fstr] = {}
                if b.author not in target[fstr][b.fstr]:
                    target[fstr][b.fstr][b.author] = set()
                target[fstr][b.fstr][b.author].add(b.sha)

    def update_author2fstr2fstat(
        self, author2fstr2fstat: dict[Author, dict[FileStr, FileStat]]
    ) -> dict[Author, dict[FileStr, FileStat]]:
        """
        Update author2fstr2fstat with line counts for each author.
        Set local list of sorted unfiltered _blame_authors.
        """
        author2line_count: dict[Author, int] = {}
        target = author2fstr2fstat
        for fstr in self.all_fstrs:
            blames: list[Blame] = self.fstr2blames[fstr]
            for b in blames:
                if b.commit_nr not in self.date_range_sha_nrs:
                    continue
                person = self.persons_db[b.author]
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
        return target

    def get_blame_shas_for_fstr(self, fstr: FileStr) -> list[SHA]:
        shas: list[SHA] = []
        blames: list[Blame] = self.fstr2blames[fstr]
        comments_ok: bool
        empty_ok: bool
        author_ok: bool
        date_ok: bool
        # Note that exclusion of revisions is already done in the blame generation.
        for b in blames:
            comments_ok = self.args.comments or any(
                not is_comment_line for is_comment_line in b.is_comment_lines
            )
            empty_ok = self.args.empty_lines or any([line.strip() for line in b.lines])
            author_ok = b.author not in self.args.ex_authors
            date_ok = b.commit_nr in self.date_range_sha_nrs
            if comments_ok and empty_ok and author_ok and date_ok:
                shas.append(b.sha)
        shas_sorted = sorted(shas, key=lambda x: self.sha2nr[x], reverse=True)
        return shas_sorted


class RepoBlameHistory(RepoBlame):
    def __init__(self, ini_repo: IniRepo) -> None:
        super().__init__(ini_repo)

        self.fr2f2shas: dict[FileStr, dict[FileStr, list[SHA]]] = {}
        self.fstr2sha2blames: dict[FileStr, dict[SHA, list[Blame]]] = {}

    def generate_fr_blame_history(self, root_fstr: FileStr, sha: SHA) -> list[Blame]:
        blame_lines: list[BlameStr]
        fstr: FileStr = self.get_file_for_sha(root_fstr, sha)
        blame_lines, _ = self._get_git_blames_for(fstr, sha)
        blames: list[Blame] = self._process_blame_lines(root_fstr, blame_lines)
        return blames

    def generate_fr_f_blame_history(
        self, root_fstr: FileStr, fstr: FileStr, sha: SHA
    ) -> list[Blame]:
        blame_lines: list[BlameStr]
        blame_lines, _ = self._get_git_blames_for(fstr, sha)
        blames: list[Blame] = self._process_blame_lines(root_fstr, blame_lines)
        return blames

    def get_file_for_sha(self, root_fstr: FileStr, sha: SHA) -> FileStr:
        for fstr, shas in self.fr2f2shas[root_fstr].items():
            if sha in shas:
                return fstr
        raise ValueError(f"SHA {sha} not found in {root_fstr} SHAs")
