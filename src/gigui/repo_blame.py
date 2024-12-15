import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# pygit2 Object id is a binary representation of a long SHA
from pygit2 import Commit  # pylint: disable=E0611:no-name-in-module
from pygit2 import Oid  # pylint: disable=E0611:no-name-in-module
from pygit2.blame import Blame as GitBlame
from pygit2.enums import BlameFlag
from pygit2.repository import Repository

from gigui.comment import get_is_comment_lines
from gigui.constants import STATIC
from gigui.data import FileStat
from gigui.repo_base import RepoBase
from gigui.typedefs import Author, BlameLines, Email, FileStr, SHAShort

logger = logging.getLogger(__name__)


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


class RepoBlameBase(RepoBase):
    copy_move: int
    since: str
    whitespace: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        git_blame: GitBlame = repo.blame(
            fstr,
            flags=blame_flags,
            newest_commit=newest_id,
            oldest_commit=self.oldest_id,
        )
        return git_blame, fstr

    def _process_git_blames(
        self, fstr: FileStr, git_blame: GitBlame, commit_sha: SHAShort
    ) -> list[Blame]:
        blames: list[Blame] = []
        dot_ext = Path(fstr).suffix
        extension = dot_ext[1:] if dot_ext else ""
        in_multi_comment = False

        arg_commit = self.git_repo.get(self.sha_short2id[commit_sha])  # type: ignore

        tree = arg_commit.tree  # type: ignore
        blob = None
        for entry, path in self._traverse_tree(tree):
            if path == fstr:
                blob = entry.data
                break
        if not blob:
            raise FileNotFoundError(f"File {fstr} not found in commit {commit_sha}")

        file_lines = blob.decode("utf-8").splitlines()

        # hunks = []
        # if fstr == "lib/ctrl-test.cif":
        #     for hunk in git_blame:
        #         if not hunk:
        #             continue
        #         hunks.append(hunk)

        for hunk in git_blame:
            if not hunk:
                continue
            oid: Oid = hunk.final_commit_id
            commit: Commit = self.git_repo.get(oid)  # type: ignore
            author = commit.author.name
            email = commit.author.email
            self.persons_db.add_person(author, email)

            lines: BlameLines = file_lines[
                hunk.final_start_line_number
                - 1 : hunk.final_start_line_number
                - 1
                + hunk.lines_in_hunk
            ]
            is_comment_lines: list[bool]
            is_comment_lines, _ = get_is_comment_lines(
                extension, lines, in_multi_comment
            )
            sha_short = commit.short_id
            nr = self.sha_short2nr[sha_short]
            date = datetime.fromtimestamp(commit.commit_time)
            blame: Blame = Blame(
                author,
                email,
                date,
                commit.message,
                commit.short_id,
                nr,
                is_comment_lines,
                lines,
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
        git_blame: GitBlame
        blames: list[Blame]

        if self.multi_thread:
            futures = [
                thread_executor.submit(
                    self._get_git_blames_for, fstr, self.head_sha_short
                )
                for fstr in self.all_fstrs
            ]
            for future in as_completed(futures):
                git_blame, fstr = future.result()
                blames = self._process_git_blames(fstr, git_blame, self.head_sha_short)
                self.fstr2blames[fstr] = blames
        else:  # single thread
            for fstr in self.all_fstrs:
                git_blame, fstr = self._get_git_blames_for(fstr, self.head_sha_short)
                blames = self._process_git_blames(fstr, git_blame, self.head_sha_short)
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


class RepoBlameHistory(RepoBlame):
    blame_history: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fr2f2sha_shorts: dict[FileStr, dict[FileStr, list[SHAShort]]] = {}
        self.fstr2sha2blames: dict[FileStr, dict[SHAShort, list[Blame]]] = {}

    def run_blame_history(self) -> None:
        git_blame: GitBlame
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
                        git_blame, _ = self._get_git_blames_for(fstr, sha_short)
                        # root_str needed only for file extension to determine
                        # comment lines
                        blames = self._process_git_blames(
                            root_fstr, git_blame, sha_short
                        )
                        self.fstr2sha2blames[root_fstr][sha_short] = blames

        # Assume that no new authors are found when using earlier root commit_shas, so
        # do not update authors of the blames with the possibly newly found persons as
        # in RepoBlame.run().

    def generate_fr_blame_history(
        self, root_fstr: FileStr, sha_short: SHAShort
    ) -> list[Blame]:
        git_blame: GitBlame
        fstr: FileStr = self.get_file_for_sha_short(root_fstr, sha_short)
        git_blame, _ = self._get_git_blames_for(fstr, sha_short)
        blames: list[Blame] = self._process_git_blames(root_fstr, git_blame, sha_short)
        return blames

    def generate_fr_f_blame_history(
        self, root_fstr: FileStr, fstr: FileStr, sha_short: SHAShort
    ) -> list[Blame]:
        git_blame: GitBlame
        git_blame, _ = self._get_git_blames_for(fstr, sha_short)
        blames: list[Blame] = self._process_git_blames(root_fstr, git_blame, sha_short)
        return blames

    def get_file_for_sha_short(
        self, root_fstr: FileStr, sha_short: SHAShort
    ) -> FileStr:
        for fstr, sha_shorts in self.fr2f2sha_shorts[root_fstr].items():
            if sha_short in sha_shorts:
                return fstr
        raise ValueError(f"SHA {sha_short} not found in {root_fstr} SHAs")
