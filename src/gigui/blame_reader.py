import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pygit2 import Oid  # pygit2 Object id is a binary representation of a long SHA
from pygit2 import Commit
from pygit2.blame import Blame as GitBlame
from pygit2.enums import BlameFlag
from pygit2.repository import Repository

from gigui.comment import get_is_comment_lines
from gigui.constants import STATIC
from gigui.data import FileStat, PersonsDB
from gigui.repo import GIRepo
from gigui.repo_reader import RepoReader
from gigui.typedefs import Author, BlameLines, Email, FileStr, GitBlames, SHAShort

logger = logging.getLogger(__name__)


# SHAShortDate object is used to order and number commits by date, starting at 1 for the
# initial commit.
@dataclass
class SHAShortDate:
    sha_short: SHAShort
    date: int


@dataclass
class Blame:
    author: Author
    email: Email
    date: datetime
    message: str
    sha_short: SHAShort
    commit_nr: int
    is_comment_lines: list[bool]
    lines: BlameLines


class BlameBaseReader:
    copy_move: int
    since: str
    whitespace: bool

    def __init__(
        self,
        repo_reader: RepoReader,
        repo: GIRepo,
    ):
        self.repo_reader: RepoReader = repo_reader
        self.repo: GIRepo = repo

        self.git_repo: Repository = self.repo_reader.git_repo
        self.ex_sha_shorts: set[SHAShort] = self.repo_reader.ex_sha_shorts

        self.sha_short2id: dict[SHAShort, Oid] = self.repo_reader.sha_short2id
        self.sha_short2nr: dict[SHAShort, int] = self.repo.sha_short2nr
        self.head_commit: Commit = self.repo_reader.head_commit
        self.initial_commit: Commit = self.repo_reader.initial_commit
        self.oldest_id: Oid = self.repo_reader.oldest_id
        self.newest_id: Oid = self.repo_reader.newest_id

        # Unfiltered list of files, may still include files that belong completely to an
        # excluded author.
        self.all_fstrs = self.repo_reader.fstrs

        # List of files in repo module with complete filtering, so no files that belong
        # to excluded authors.
        self.fstrs: list[FileStr] = self.repo.fstrs
        self.fstr2fstat: dict[FileStr, FileStat] = self.repo.fstr2fstat
        self.persons_db: PersonsDB = self.repo.persons_db

        # List of blame authors, so no filtering, ordered by highest blame line count.
        self.blame_authors: list[Author] = []

        self.fstr2blames: dict[FileStr, list[Blame]] = {}

    def _get_git_blames_for(
        self, fstr: FileStr, start_sha_short: SHAShort = ""
    ) -> tuple[GitBlame, FileStr]:
        newest_id = (
            self.sha_short2id[start_sha_short] if start_sha_short else self.newest_id
        )
        repo: Repository = self.git_repo
        blame_flags: BlameFlag = (
            BlameFlag.NORMAL if self.whitespace else BlameFlag.IGNORE_WHITESPACE
        )
        match self.copy_move:
            case 1:
                blame_flags |= BlameFlag.TRACK_COPIES_SAME_FILE
            case 2:
                blame_flags |= BlameFlag.TRACK_COPIES_SAME_COMMIT_MOVES
            case 3:
                blame_flags |= BlameFlag.TRACK_COPIES_SAME_COMMIT_COPIES
            case 4:
                blame_flags |= BlameFlag.TRACK_COPIES_ANY_COMMIT_COPIES
        blame: GitBlame = repo.blame(
            fstr,
            flags=blame_flags,
            newest_commit=newest_id,
            oldest_commit=self.oldest_id,
        )
        return blame, fstr

    def _process_git_blames(self, fstr: FileStr, git_blames: GitBlames) -> list[Blame]:
        blames: list[Blame] = []
        dot_ext = Path(fstr).suffix
        extension = dot_ext[1:] if dot_ext else ""
        in_multi_comment = False
        for b in git_blames:  # type: ignore
            if not b:
                continue
            c: Commit = b[0]  # type: ignore

            author = c.author.name  # type: ignore
            email = c.author.email  # type: ignore
            self.persons_db.add_person(author, email)

            lines: BlameLines = b[1]  # type: ignore
            is_comment_lines: list[bool]
            is_comment_lines, _ = get_is_comment_lines(
                extension, lines, in_multi_comment
            )
            sha_short = c.short_id
            nr = self.sha_short2nr[sha_short]
            blame: Blame = Blame(
                author,  # type: ignore
                email,  # type: ignore
                c.committed_datetime,  # type: ignore
                c.message,  # type: ignore
                sha_short,
                nr,  # commit number
                is_comment_lines,
                lines,  # type: ignore
            )
            blames.append(blame)
        return blames


class BlameReader(BlameBaseReader):
    multi_thread: bool
    comments: bool
    empty_lines: bool

    def __init__(self, head_sha_short: SHAShort, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.head_sha_short: SHAShort = head_sha_short

    # Set the fstr2blames dictionary, but also add the author and email of each
    # blame to the persons list. This is necessary, because the blame functionality
    # can have another way to set/get the author and email of a commit.
    def run(self, thread_executor: ThreadPoolExecutor) -> None:
        git_blames: GitBlames
        blames: list[Blame]

        if self.multi_thread:
            futures = [
                thread_executor.submit(
                    self._get_git_blames_for, fstr, self.head_sha_short
                )
                for fstr in self.all_fstrs
            ]
            for future in as_completed(futures):
                git_blames, fstr = future.result()
                blames = self._process_git_blames(fstr, git_blames)
                self.fstr2blames[fstr] = blames
        else:  # single thread
            for fstr in self.all_fstrs:
                git_blames, fstr = self._get_git_blames_for(fstr, self.head_sha_short)
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
                blame.author = self.persons_db.get_author(blame.author)
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
                person = self.persons_db.get_person(b.author)
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


class BlameHistoryReader(BlameBaseReader):
    blame_history: str

    # pylint: disable=too-many-arguments disable=too-many-positional-arguments
    def __init__(
        self,
        fstr2blames: dict[FileStr, list[Blame]],
        fr2f2sha_shorts: dict[FileStr, dict[FileStr, list[SHAShort]]],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fstr2blames: dict[FileStr, list[Blame]] = fstr2blames
        self.fr2f2sha_shorts: dict[FileStr, dict[FileStr, list[SHAShort]]] = (
            fr2f2sha_shorts
        )

        # Dict from a file to all its previous names (due to renaming) in the repo
        self.fstr2names: dict[FileStr, list[FileStr]] = {}

        self.fstr2sha2blames: dict[FileStr, dict[SHAShort, list[Blame]]] = {}
        self.run()

    def run(self) -> None:
        git_blames: GitBlames
        blames: list[Blame]

        if self.blame_history == STATIC:
            for root_fstr in self.fstrs:
                head_sha = self.fr2f2sha_shorts[root_fstr][root_fstr][0]
                self.fstr2sha2blames[root_fstr] = {}
                self.fstr2sha2blames[root_fstr][head_sha] = self.fstr2blames[root_fstr]
                for fstr, sha_shorts in self.fr2f2sha_shorts[root_fstr].items():
                    for sha_short in sha_shorts:
                        if fstr == root_fstr and sha_short == head_sha:
                            continue
                        git_blames, _ = self._get_git_blames_for(fstr, sha_short)
                        # root_str needed only for file extension to determine
                        # comment lines
                        blames = self._process_git_blames(root_fstr, git_blames)
                        self.fstr2sha2blames[root_fstr][sha_short] = blames

        # Assume that no new authors are found when using earlier root commit_shas, so
        # do not update authors of the blames with the possibly newly found persons as
        # in BlameReader.run().

    def generate_fr_blame_history(
        self, root_fstr: FileStr, sha_short: SHAShort
    ) -> list[Blame]:
        git_blames: GitBlames
        fstr: FileStr = self.get_file_for_sha_short(root_fstr, sha_short)
        git_blames, _ = self._get_git_blames_for(fstr, sha_short)
        blames: list[Blame] = self._process_git_blames(root_fstr, git_blames)
        return blames

    def generate_fr_f_blame_history(
        self, root_fstr: FileStr, fstr: FileStr, sha_short: SHAShort
    ) -> list[Blame]:
        git_blames: GitBlames
        git_blames, _ = self._get_git_blames_for(fstr, sha_short)
        blames: list[Blame] = self._process_git_blames(root_fstr, git_blames)
        return blames

    def get_file_for_sha_short(
        self, root_fstr: FileStr, sha_short: SHAShort
    ) -> FileStr:
        for fstr, sha_shorts in self.fr2f2sha_shorts[root_fstr].items():
            if sha_short in sha_shorts:
                return fstr
        raise ValueError(f"SHA {sha_short} not found in {root_fstr} SHAs")
