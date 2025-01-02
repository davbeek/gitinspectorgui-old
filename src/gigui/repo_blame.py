import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import Commit as GitCommit
from git import GitCommandError, Repo

from gigui.comment import get_is_comment_lines
from gigui.constants import BLAME_CHUNK_SIZE
from gigui.data import FileStat
from gigui.repo_base import RepoBase
from gigui.typedefs import SHA, Author, BlameLines, Email, FileStr, GitBlames

logger = logging.getLogger(__name__)


@dataclass
class Blame:
    author: Author
    email: Email
    date: datetime
    message: str
    sha: SHA
    commit_nr: int
    is_comment_lines: list[bool]
    lines: BlameLines


class RepoBlameBase(RepoBase):
    blame_skip: bool
    copy_move: int
    since: str
    whitespace: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # List of blame authors, so no filtering, ordered by highest blame line count.
        self.blame_authors: list[Author] = []

        self.fstr2blames: dict[FileStr, list[Blame]] = {}

    def _get_git_blames_for(
        self, fstr: FileStr, start_sha: SHA
    ) -> tuple[GitBlames, FileStr]:
        copy_move_int2opts: dict[int, list[str]] = {
            0: [],
            1: ["-M"],
            2: ["-C"],
            3: ["-C", "-C"],
            4: ["-C", "-C", "-C"],
        }
        blame_opts: list[str] = copy_move_int2opts[self.copy_move]
        if self.since:
            blame_opts.append(f"--since={self.since}")
        if not self.whitespace:
            blame_opts.append("-w")
        for rev in self.ex_shas:
            blame_opts.append(f"--ignore-rev={rev}")
        working_dir = self.location
        ignore_revs_path = Path(working_dir) / "_git-blame-ignore-revs.txt"
        if ignore_revs_path.exists():
            blame_opts.append(f"--ignore-revs-file={str(ignore_revs_path)}")
        # Run the git command to get the blames for the file.
        git_blames: GitBlames = self._run_git_command(start_sha, fstr, blame_opts)
        return git_blames, fstr

    def _run_git_command(
        self,
        start_sha: SHA,
        fstr: FileStr,
        blame_opts: list[str],
    ) -> GitBlames:
        start_oid = self.sha2oid[start_sha]
        git_blames: GitBlames
        try:
            if self.multi_thread:
                repo = Repo(self.location)
                git_blames = repo.blame(
                    start_oid, fstr, rev_opts=blame_opts
                )  # type: ignore
                repo.close()
            else:
                git_blames = self.git_repo.blame(
                    start_oid, fstr, rev_opts=blame_opts
                )  # type: ignore
            return git_blames
        except GitCommandError as e:
            logger.warning(f"GitCommandError: {e}")
            return []

    def _process_git_blames(self, fstr: FileStr, git_blames: GitBlames) -> list[Blame]:
        blames: list[Blame] = []
        dot_ext = Path(fstr).suffix
        extension = dot_ext[1:] if dot_ext else ""
        in_multi_comment = False
        for b in git_blames:  # type: ignore
            if not b:
                continue
            c: GitCommit = b[0]  # type: ignore

            author = c.author.name  # type: ignore
            email = c.author.email  # type: ignore
            self.persons_db.add_person(author, email)

            lines: BlameLines = b[1]  # type: ignore
            is_comment_lines: list[bool]
            is_comment_lines, _ = get_is_comment_lines(
                extension, lines, in_multi_comment
            )
            sha = self.oid2sha[c.hexsha]
            nr = self.sha2nr[sha]
            blame: Blame = Blame(
                author,  # type: ignore
                email,  # type: ignore
                c.committed_datetime,  # type: ignore
                c.message,  # type: ignore
                sha,
                nr,  # commit number
                is_comment_lines,
                lines,  # type: ignore
            )
            blames.append(blame)
        return blames


class RepoBlame(RepoBlameBase):
    multi_thread: bool
    comments: bool
    empty_lines: bool

    # Set the fstr2blames dictionary, but also add the author and email of each
    # blame to the persons list. This is necessary, because the blame functionality
    # can have another way to set/get the author and email of a commit.
    def run_blame(self, thread_executor: ThreadPoolExecutor) -> None:
        git_blames: GitBlames
        blames: list[Blame]

        logger = logging.getLogger(__name__)
        i_max: int = len(self.all_fstrs)
        i: int = 0
        chunk_size: int = BLAME_CHUNK_SIZE
        prefix: str = "        "
        logger.info(prefix + f"Blame: {self.name}: {i_max} files")
        if self.multi_thread:
            for chunk_start in range(0, i_max, chunk_size):
                chunk_end = min(chunk_start + chunk_size, i_max)
                chunk_fstrs = self.all_fstrs[chunk_start:chunk_end]
                futures = [
                    thread_executor.submit(
                        self._get_git_blames_for, fstr, self.head_sha
                    )
                    for fstr in chunk_fstrs
                ]
                for future in as_completed(futures):
                    git_blames, fstr = future.result()
                    i += 1
                    logger.info(
                        prefix
                        + f"blame {i} of {i_max}: "
                        + (f"{self.name}: {fstr}" if self.multi_core else f"{fstr}")
                    )
                    blames = self._process_git_blames(fstr, git_blames)
                    self.fstr2blames[fstr] = blames
        else:  # single thread
            for fstr in self.all_fstrs:
                git_blames, fstr = self._get_git_blames_for(fstr, self.head_sha)
                i += 1
                logger.info(prefix + f"{i} of {i_max}: {fstr}")
                blames = self._process_git_blames(fstr, git_blames)
                self.fstr2blames[fstr] = blames  # type: ignore

        # New authors and emails may have been found in the blames, so update
        # the authors of the blames with the possibly newly found persons
        fstr2blames: dict[FileStr, list[Blame]] = {}
        for fstr in self.all_fstrs:
            # fstr2blames will be the new value of self.fstr2blames
            fstr2blames[fstr] = []
            for blame in self.fstr2blames[fstr]:
                # update author
                blame.author = self.persons_db[blame.author].author
                fstr2blames[fstr].append(blame)
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
        for fstr in self.all_fstrs:
            blames = self.fstr2blames[fstr]
            for b in blames:
                person = self.persons_db[b.author]
                author = person.author
                if author not in author2line_count:
                    author2line_count[author] = 0
                total_line_count = len(b.lines)  # type: ignore
                comment_lines_subtract = (
                    0 if self.comments else b.is_comment_lines.count(True)
                )
                empty_lines_subtract = (
                    0
                    if self.empty_lines
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


class RepoBlameHistory(RepoBlame):
    blame_history: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fr2f2shas: dict[FileStr, dict[FileStr, list[SHA]]] = {}
        self.fstr2sha2blames: dict[FileStr, dict[SHA, list[Blame]]] = {}

    def run_blame_history_static(self) -> None:
        git_blames: GitBlames
        blames: list[Blame]

        for root_fstr in self.fstrs:
            head_sha = self.fr2f2shas[root_fstr][root_fstr][0]
            self.fstr2sha2blames[root_fstr] = {}
            self.fstr2sha2blames[root_fstr][head_sha] = self.fstr2blames[root_fstr]
            for fstr, shas in self.fr2f2shas[root_fstr].items():
                for sha in shas:
                    if fstr == root_fstr and sha == head_sha:
                        continue
                    git_blames, _ = self._get_git_blames_for(fstr, sha)
                    # root_str needed only for file extension to determine
                    # comment lines
                    blames = self._process_git_blames(root_fstr, git_blames)
                    self.fstr2sha2blames[root_fstr][sha] = blames

        # Assume that no new authors are found when using earlier root commit_shas, so
        # do not update authors of the blames with the possibly newly found persons as
        # in RepoBlame.run().

    def generate_fr_blame_history(self, root_fstr: FileStr, sha: SHA) -> list[Blame]:
        git_blames: GitBlames
        fstr: FileStr = self.get_file_for_sha(root_fstr, sha)
        git_blames, _ = self._get_git_blames_for(fstr, sha)
        blames: list[Blame] = self._process_git_blames(root_fstr, git_blames)
        return blames

    def generate_fr_f_blame_history(
        self, root_fstr: FileStr, fstr: FileStr, sha: SHA
    ) -> list[Blame]:
        git_blames: GitBlames
        git_blames, _ = self._get_git_blames_for(fstr, sha)
        blames: list[Blame] = self._process_git_blames(root_fstr, git_blames)
        return blames

    def get_file_for_sha(self, root_fstr: FileStr, sha: SHA) -> FileStr:
        for fstr, shas in self.fr2f2shas[root_fstr].items():
            if sha in shas:
                return fstr
        raise ValueError(f"SHA {sha} not found in {root_fstr} SHAs")
