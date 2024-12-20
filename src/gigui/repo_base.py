import copy
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

from git import Commit, Repo

from gigui.data import CommitGroup, Person, PersonsDB, RepoStats
from gigui.typedefs import OID, SHA, Author, FileStr, Rev

logger = logging.getLogger(__name__)


# SHAShortDate object is used to order and number commits by date, starting at 1 for the
# initial commit.
@dataclass
class SHADate:
    sha: SHA
    date: int


class RepoBase:
    since: str
    until: str
    include_files: list[FileStr]
    n_files: int
    subfolder: str
    extensions: list[str]
    whitespace: bool
    multi_thread: bool
    ex_files: list[FileStr]
    ex_messages: list[str]

    # Here the values of the --ex-revision parameter are stored as a set.
    ex_revs: set[Rev] = set()

    def __init__(self, name: str, location: Path):
        self.name: str = name
        self.location: Path = location
        self.persons_db: PersonsDB = PersonsDB()
        self.git_repo: Repo = Repo(location)

        # self.fstrs is a list of files from the top commit of the repo.

        # Initially, the list is unfiltered and may still include files from authors
        # that are excluded later, because the blame run may find new authors that match
        # an excluded author and thus must be excluded later.

        # In self.run_gi_no_history from GIRepo, self.fstrs is sorted and all excluded
        # files are removed.
        self.fstrs: list[FileStr] = []

        # self.all_fstrs is the unfiltered list of files, may still include files that
        # belong completely to an excluded author.
        self.all_fstrs: list[FileStr]

        # List of the shas of the repo commits starting at the until date parameter (if set),
        # or else at the first commit of the repo. The list includes merge commits and
        # is sorted by commit date.
        self.shas_dated: list[SHADate]

        self.head_commit: Commit
        self.head_sha: SHA

        self.fr2f2a2sha_set: dict[FileStr, dict[FileStr, dict[Author, set[SHA]]]] = {}

        # Set of short SHAs of commits in the repo that are excluded by the
        # --ex-revision parameter together with the --ex-message parameter.
        self.ex_shas: set[SHA] = set()

        # Dict of file names to their sizes:
        self.fstr2line_count: dict[FileStr, int] = {}

        self.fstr2commit_groups: dict[FileStr, list[CommitGroup]] = {}
        self.stats = RepoStats()

        self.thread_executor: ThreadPoolExecutor

        self.sha2oid: dict[SHA, OID] = {}
        self.oid2sha: dict[OID, SHA] = {}
        self.sha2nr: dict[SHA, int] = {}
        self.nr2sha: dict[int, SHA] = {}
        self.nr2id: dict[int, OID] = {}
        self.id2nr: dict[OID, int] = {}
        self.sha2author: dict[SHA, Author] = {}

        # Use git log to get both long and short SHAs
        # First line represents the last commit
        log_output = self.git.log("--pretty=format:%H %h")

        lines = log_output.splitlines()

        # Set nr of first output line to the number of commits
        # Initial commit gets nr = 1
        nr = len(lines)
        for line in lines:
            oid, sha = line.split()
            self.sha2oid[sha] = oid
            self.oid2sha[oid] = sha
            self.sha2nr[sha] = nr
            self.nr2sha[nr] = sha
            nr -= 1

        self.head_commit = next(self.git_repo.iter_commits())
        self.head_sha = self.oid2sha[self.head_commit.hexsha]

    @property
    def git(self):
        return self.git_repo.git

    def run_base(self, thread_executor: ThreadPoolExecutor) -> None:

        # Set list top level fstrs (based on until par and allowed file extensions)
        self.fstrs = self._get_worktree_files()

        self._set_fstr2line_count()
        self._get_commits_first_pass()

        self._set_fstr2commits(thread_executor)
        self.all_fstrs = copy.deepcopy(self.fstrs)

    def get_person(self, author: Author | None) -> Person:
        return self.persons_db.get_person(author)

    def _convert_to_timestamp(self, date_str: str) -> int:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())

    # Get list of top level files (based on the until parameter) that satisfy the
    # required extensions and do not match the exclude file patterns.
    # To get all files use --include-file="*" as pattern
    # include_files takes priority over n_files
    def _get_worktree_files(self) -> list[FileStr]:
        matches: list[FileStr]
        if not self.include_files:
            matches = self._get_biggest_worktree_files(self.n_files)
        else:  # Get files matching file pattern
            matches = [
                blob.path  # type: ignore
                for blob in self.head_commit.tree.traverse()
                if (
                    blob.type == "blob"  # type: ignore
                    and blob.path.split(".")[-1] in self.extensions  # type: ignore
                    and not self._matches_ex_file(blob.path)  # type: ignore
                    and any(
                        fnmatch(blob.path, pattern)  # type: ignore
                        for pattern in self.include_files
                    )
                    and fnmatch(blob.path, f"{self.subfolder}*")  # type: ignore
                )
            ]
        return matches

    # Get the n biggest files in the worktree that:
    # - match the required file extensions
    def _get_biggest_worktree_files(self, n: int) -> list[FileStr]:
        # Get the files with their file sizes that match the required extensions
        def get_subfolder_blobs() -> list:
            return [
                blob
                for blob in self.head_commit.tree.traverse()
                if (
                    (blob.type == "blob")  # type: ignore
                    and fnmatch(blob.path, f"{self.subfolder}*")  # type: ignore
                )
            ]

        def get_worktree_files_sizes() -> list[tuple[FileStr, int]]:
            blobs: list = get_subfolder_blobs()
            if not blobs:
                logging.warning(f"No files found in subfolder {self.subfolder}")
                return []
            return [
                (blob.path, blob.size)  # type: ignore
                for blob in blobs
                if (
                    ((blob.path.split(".")[-1] in self.extensions))  # type: ignore
                    and not self._matches_ex_file(blob.path)  # type: ignore
                )
            ]

        assert n > 0
        sorted_files_sizes = sorted(
            get_worktree_files_sizes(), key=lambda x: x[1], reverse=True
        )
        sorted_files = [file_size[0] for file_size in sorted_files_sizes]
        return sorted_files[0:n]

    # Returns True if file should be excluded
    def _matches_ex_file(self, fstr: FileStr) -> bool:
        return any(fnmatch(fstr, pattern) for pattern in self.ex_files)

    def _set_fstr2line_count(self) -> None:
        self.fstr2line_count["*"] = 0
        for blob in self.head_commit.tree.traverse():
            if (
                blob.type == "blob"  # type: ignore
                and blob.path in self.fstrs  # type: ignore
                and blob.path not in self.fstr2line_count  # type: ignore
            ):
                # number of lines in blob
                line_count: int = len(
                    blob.data_stream.read().decode("utf-8").split("\n")  # type: ignore
                )
                self.fstr2line_count[blob.path] = line_count  # type: ignore
                self.fstr2line_count["*"] += line_count

    def _get_commits_first_pass(self) -> None:
        shas_dated: list[SHADate] = []
        ex_shas: set[SHA] = set()  # set of excluded shas
        sha: SHA
        oid: OID

        # %h: commit hash (short)
        # %ct: committer date, UNIX timestamp
        # %s: commit message
        # %aN: author name, respecting .mailmap
        # %aE: author email, respecting .mailmap
        # %n: newline
        args = self._get_since_until_args()
        args += [
            f"{self.head_commit.hexsha}",
            "--pretty=format:%h%n%ct%n%s%n%aN%n%aE%n",
        ]
        lines_str: str = self.git.log(*args)

        lines = lines_str.splitlines()
        while lines:
            line = lines.pop(0)
            if not line:
                continue
            sha = line
            oid = self.sha2oid[sha]
            if any(oid.startswith(rev) for rev in self.ex_revs):
                ex_shas.add(sha)
                continue
            timestamp = int(lines.pop(0))
            message = lines.pop(0)
            if any(fnmatch(message, pattern) for pattern in self.ex_messages):
                ex_shas.add(sha)
                continue
            author = lines.pop(0)
            email = lines.pop(0)
            self.persons_db.add_person(author, email)
            self.sha2author[sha] = author
            sha_date = SHADate(sha, timestamp)
            shas_dated.append(sha_date)

        shas_dated.sort(key=lambda x: x.date)
        self.shas_dated = shas_dated
        self.ex_shas = ex_shas

    def _get_since_until_args(self) -> list[str]:
        since = self.since
        until = self.until
        if since and until:
            return [f"--since={since}", f"--until={until}"]
        elif since:
            return [f"--since={since}"]
        elif until:
            return [f"--until={until}"]
        else:
            return []

    def _set_fstr2commits(self, thread_executor: ThreadPoolExecutor):
        # When two lists of commits share the same commit at the end,
        # the duplicate commit is removed from the longer list.
        def reduce_commits():
            fstrs = copy.deepcopy(self.fstrs)
            # Default sorting order ascending: from small to large, so the first element
            # is the smallest.
            fstrs.sort(key=lambda x: len(self.fstr2commit_groups[x]))
            while fstrs:
                fstr1 = fstrs.pop()
                commit_groups1 = self.fstr2commit_groups[fstr1]
                if not commit_groups1:
                    continue
                for fstr2 in fstrs:
                    commit_groups2 = self.fstr2commit_groups[fstr2]
                    i = -1
                    while commit_groups2 and commit_groups1[i] == commit_groups2[-1]:
                        commit_groups2.pop()
                        i -= 1

        if self.multi_thread:
            futures = [
                thread_executor.submit(self._get_commit_lines_for, fstr)
                for fstr in self.fstrs
            ]
            for future in as_completed(futures):
                lines_str, fstr = future.result()
                self.fstr2commit_groups[fstr] = self._process_commit_lines_for(
                    lines_str, fstr
                )
        else:  # single thread
            for fstr in self.fstrs:
                lines_str, fstr = self._get_commit_lines_for(fstr)
                self.fstr2commit_groups[fstr] = self._process_commit_lines_for(
                    lines_str, fstr
                )
        reduce_commits()

    def _get_commit_lines_for(self, fstr: FileStr) -> tuple[str, FileStr]:
        def git_log_args() -> list[str]:
            args = self._get_since_until_args()
            if not self.whitespace:
                args.append("-w")
            args += [
                # %h: short commit hash
                # %ct: committer date, UNIX timestamp
                # %aN: author name, respecting .mailmap
                # %n: newline
                f"{self.head_commit.hexsha}",
                "--follow",
                "--numstat",
                "--pretty=format:%n%h %ct%n%aN",
                # Avoid confusion between revisions and files, after "--" git treats all
                # arguments as files.
                "--",
                str(fstr),
            ]
            return args

        lines_str: str = self.git.log(git_log_args())
        return lines_str, fstr

    # pylint: disable=too-many-locals
    def _process_commit_lines_for(
        self, lines_str: str, fstr_root: FileStr
    ) -> list[CommitGroup]:
        commit_groups: list[CommitGroup] = []

        lines: list[str] = lines_str.strip().splitlines()
        rename_pattern = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")

        while lines:
            line = lines.pop(0)
            if not line:
                continue
            sha, timestamp = line.split()
            if sha in self.ex_shas:
                continue
            author = lines.pop(0)
            person = self.get_person(author)
            if not lines:
                break
            stat_line = lines.pop(0)
            if person.filter_matched or not stat_line:
                continue
            parts = stat_line.split("\t")
            if not len(parts) == 3:
                continue
            insertions = int(parts[0])
            deletions = int(parts[1])
            file_name = parts[2]
            match = rename_pattern.match(file_name)
            if match:
                prefix = match.group(1)
                # old_part = match.group(2)
                new_part = match.group(3)
                suffix = match.group(4)
                # old_name = f"{prefix}{old_part}{suffix}".replace("//", "/")
                new_name = f"{prefix}{new_part}{suffix}".replace("//", "/")
                fstr = new_name
            else:
                fstr = file_name

            target = self.fr2f2a2sha_set
            if fstr_root not in target:
                target[fstr_root] = {}
            if fstr not in target[fstr_root]:
                target[fstr_root][fstr] = {}
            if author not in target[fstr_root][fstr]:
                target[fstr_root][fstr][author] = set()
            target[fstr_root][fstr][author].add(sha)

            if (
                len(commit_groups) > 1
                and fstr == commit_groups[-1].fstr
                and author == commit_groups[-1].author
            ):
                commit_groups[-1].date_sum += int(timestamp) * insertions
                commit_groups[-1].shas |= {sha}
                commit_groups[-1].insertions += insertions
                commit_groups[-1].deletions += deletions
            else:
                commit_group = CommitGroup(
                    date_sum=int(timestamp) * insertions,
                    author=author,
                    fstr=fstr,
                    insertions=insertions,
                    deletions=deletions,
                    shas={sha},
                )
                commit_groups.append(commit_group)
        return commit_groups
