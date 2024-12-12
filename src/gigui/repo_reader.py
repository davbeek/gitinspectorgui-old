import copy
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatch

from git import Repo as GitRepo
from pygit2 import Blob, Commit, Tree
from pygit2.enums import DeltaStatus, DiffOption, SortMode
from pygit2.repository import Repository

from gigui.blame_reader import BlameReader, SHAShortDate
from gigui.data import CommitGroup, Person, PersonsDB, RepoStats
from gigui.typedefs import Author, FileStr, Rev, SHALong, SHAShort

logger = logging.getLogger(__name__)


@dataclass
class CommitData:
    fstr: FileStr
    author: Author
    insertions: int
    deletions: int
    timestamp: int
    sha_short: SHAShort


class RepoReader:
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

    def __init__(
        self,
        name: str,
        location: str,
        persons_db: PersonsDB,
    ):
        self.name: str = name
        self.persons_db: PersonsDB = persons_db

        # The default True value of expand_vars can lead to confusing warnings from
        # GitPython:
        self.git_repo: GitRepo = GitRepo(location, expand_vars=False)

        self.pygit2_repo = Repository(location)

        # List of all commits in the repo starting at the until date parameter (if set),
        # or else at the first commit of the repo. The list includes merge commits and
        # is sorted by commit date.
        self.commits: list[SHAShortDate]

        self.head_commit: Commit
        self.head_sha_short: SHAShort

        self.fr2f2a2sha_short_set: dict[
            FileStr, dict[FileStr, dict[Author, set[SHAShort]]]
        ] = {}

        # Set of short SHAs of commits in the repo that are excluded by the
        # --ex-revision parameter together with the --ex-message parameter.
        self.ex_sha_shorts: set[SHAShort] = set()

        # List of files from the top commit of the repo.
        # Unfiltered files, which may still include files from authors that are excluded
        # later, because the blame run may find new authors that match an excluded
        # author and thus must be excluded later.
        self.fstrs: list[FileStr] = []

        # Dict of file names to their sizes:
        self.fstr2line_count: dict[FileStr, int] = {}

        self.fstr2commit_groups: dict[FileStr, list[CommitGroup]] = {}
        self.stats = RepoStats()

        self.thread_executor: ThreadPoolExecutor
        self.blame_reader: BlameReader

        self.sha_short2sha_long: dict[SHAShort, SHALong] = {}
        self.sha_long2sha_short: dict[SHALong, SHAShort] = {}
        self.sha_short2nr: dict[SHAShort, int] = {}
        self.nr2sha_short: dict[int, SHAShort] = {}

        commits = self.pygit2_repo.walk(self.pygit2_repo.head.target, SortMode.REVERSE)
        commit_nr = 1
        for commit in commits:
            sha_long = str(commit.id)
            sha_short = commit.short_id
            self.sha_short2sha_long[sha_short] = sha_long
            self.sha_long2sha_short[sha_long] = sha_short
            self.sha_short2nr[sha_short] = commit_nr
            self.nr2sha_short[commit_nr] = sha_short
            commit_nr += 1

        self.since_timestamp: int
        self.until_timestamp: int
        if self.since:
            self.since_timestamp = self._convert_to_timestamp(self.since)
        if self.until:
            self.until_timestamp = self._convert_to_timestamp(self.until)

    @property
    def git(self):
        return self.git_repo.git

    def run(self, thread_executor: ThreadPoolExecutor) -> None:
        self._set_head_attrs()

        # Set list top level fstrs (based on until par and allowed file extensions)
        self.fstrs = self._get_worktree_files()

        self._set_fstr2line_count()
        self._get_commits_first_pass()

        self._set_fstr2commits(thread_executor)

    def get_person(self, author: Author | None) -> Person:
        return self.persons_db.get_person(author)

    def _convert_to_timestamp(self, date_str: str) -> int:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())

    def _set_head_attrs(self) -> None:
        for commit in self.pygit2_repo.walk(
            self.pygit2_repo.head.target, SortMode.TIME
        ):
            if self.until and commit.commit_time > self.until_timestamp:  # type: ignore
                continue
            self.head_commit = commit
            break

        self.head_sha_short = self.sha_long2sha_short[str(self.head_commit.id)]

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
                fstr
                for entry, fstr in self._traverse_tree(self.head_commit.tree)
                if (
                    entry.type_str == "blob"
                    and fstr.split(".")[-1] in self.extensions
                    and not self._matches_ex_file(fstr)
                    and any(fnmatch(fstr, pattern) for pattern in self.include_files)
                    and fnmatch(fstr, f"{self.subfolder}*")
                )
            ]
        return matches

    def _traverse_tree(self, tree: Tree, base_path: str = "") -> list[tuple[Blob, str]]:
        entries: list[tuple[Blob, str]] = []
        for entry in tree:
            entry_path = f"{base_path}/{entry.name}" if base_path else entry.name
            if entry.type_str == "tree":
                entries.extend(self._traverse_tree(entry, entry_path))  # type: ignore
            else:
                entries.append((entry, entry_path))  # type: ignore
        return entries

    def get_worktree_files_sizes(self) -> list[tuple[FileStr, int]]:
        def get_subfolder_entries() -> list:
            return [
                (entry, fstr)
                for entry, fstr in self._traverse_tree(self.head_commit.tree)
                if (entry.type_str == "blob" and fnmatch(fstr, f"{self.subfolder}*"))
            ]

        entries: list = get_subfolder_entries()
        if not entries:
            logging.warning(f"No files found in subfolder {self.subfolder}")
            return []
        return [
            (fstr, entry.size)
            for entry, fstr in entries
            if (
                fstr.split(".")[-1] in self.extensions
                and not self._matches_ex_file(fstr)
            )
        ]

    # Get the n biggest files in the worktree that:
    # - match the required file extensions
    def _get_biggest_worktree_files(self, n: int) -> list[FileStr]:
        # Get the files with their file sizes that match the required extensions
        def get_subfolder_entries() -> list:
            return [
                (entry, fstr)
                for entry, fstr in self._traverse_tree(self.head_commit.tree)
                if (entry.type_str == "blob" and fnmatch(fstr, f"{self.subfolder}*"))
            ]

        def get_worktree_files_sizes() -> list[tuple[FileStr, int]]:
            entries: list = get_subfolder_entries()
            if not entries:
                logging.warning(f"No files found in subfolder {self.subfolder}")
                return []
            return [
                (fstr, entry.size)
                for entry, fstr in entries
                if (
                    fstr.split(".")[-1] in self.extensions
                    and not self._matches_ex_file(fstr)
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
        for blob, fstr in self._traverse_tree(self.head_commit.tree):
            if (
                blob.type == "blob"
                and fstr in self.fstrs
                and fstr not in self.fstr2line_count
            ):
                # number of lines in blob
                line_count: int = len(
                    blob.data_stream.read().decode("utf-8").split("\n")  # type: ignore
                )
                self.fstr2line_count[fstr] = line_count
                self.fstr2line_count["*"] += line_count

    def _get_commits_first_pass(self) -> None:
        commits: list[SHAShortDate] = []
        ex_sha_shorts: set[SHAShort] = set()
        sha_short: SHAShort
        sha_long: SHALong

        for commit in self.pygit2_repo.walk(
            self.pygit2_repo.head.target, SortMode.TIME
        ):
            if self.until and commit.commit_time > self.until_timestamp:
                continue
            if self.since and commit.commit_time < self.since_timestamp:
                break

            sha_long = str(commit.id)
            sha_short = commit.short_id
            if any(sha_long.startswith(rev) for rev in self.ex_revs):
                ex_sha_shorts.add(sha_short)
                continue
            timestamp = commit.commit_time
            message = commit.message
            if any(fnmatch(message, pattern) for pattern in self.ex_messages):
                ex_sha_shorts.add(sha_short)
                continue
            author = commit.author.name
            email = commit.author.email
            self.persons_db.add_person(author, email)
            commit_obj = SHAShortDate(sha_short, timestamp)
            commits.append(commit_obj)

        commits.sort(key=lambda x: x.date)
        self.commits = commits
        self.ex_sha_shorts = ex_sha_shorts

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
                thread_executor.submit(self._get_commit_data_for, fstr)
                for fstr in self.fstrs
            ]
            for future in as_completed(futures):
                commit_datas_list, fstr = future.result()
                self.fstr2commit_groups[fstr] = self._process_commit_data_for(
                    commit_datas_list, fstr
                )
        else:  # single thread
            for fstr in self.fstrs:
                commit_datas_list, fstr = self._get_commit_data_for(fstr)
                self.fstr2commit_groups[fstr] = self._process_commit_data_for(
                    commit_datas_list, fstr
                )
        reduce_commits()

    def _get_commit_data_for(
        self, fstr: FileStr
    ) -> tuple[list[list[CommitData]], FileStr]:

        root_fstr = fstr
        fstr_parts = fstr.split("/")
        commit_datas_list: list[list[CommitData]] = []
        commit_datas: list[CommitData] = []
        for commit in self.pygit2_repo.walk(
            self.pygit2_repo.head.target, SortMode.TIME
        ):
            if self.file_in_tree(commit.tree, fstr_parts):
                sha_short = commit.short_id
                if sha_short in self.ex_sha_shorts:
                    continue
                timestamp = commit.commit_time
                author = commit.author.name
                person = self.get_person(author)
                if person.filter_matched:
                    continue
                if not commit.parents:  # Initial commit
                    blob = self.get_blob_from_tree(commit.tree, fstr_parts)
                    if blob:
                        insertions = len(blob.data.decode("utf-8").split("\n"))  # type: ignore
                        commit_data = CommitData(
                            fstr,
                            author,
                            insertions,
                            0,
                            timestamp,
                            sha_short,
                        )
                        commit_datas.append(commit_data)
                        commit_datas_list.append(commit_datas)
                        commit_datas = []
                else:
                    # Ignore merge commits
                    if len(commit.parents) > 1:
                        continue
                    parent = commit.parents[0]
                    diff_option = (
                        DiffOption.NORMAL
                        if self.whitespace
                        else DiffOption.IGNORE_WHITESPACE
                    )
                    diff_option |= DiffOption.IGNORE_FILEMODE
                    diff = parent.tree.diff_to_tree(commit.tree, flags=diff_option)
                    diff.find_similar()
                    for patch in diff:
                        old_fstr = patch.delta.old_file.path
                        new_fstr = patch.delta.new_file.path
                        if new_fstr == fstr:
                            insertions = patch.line_stats[1]
                            deletions = patch.line_stats[2]
                            commit_data = CommitData(
                                fstr,
                                author,
                                insertions,
                                deletions,
                                timestamp,
                                sha_short,
                            )
                            commit_datas.append(commit_data)
                            if patch.delta.status == DeltaStatus.RENAMED:
                                fstr = old_fstr
                                fstr_parts = fstr.split("/")
                                if commit_datas:
                                    commit_datas_list.append(commit_datas)
                                    commit_datas = []
        if commit_datas:
            commit_datas_list.append(commit_datas)
        return commit_datas_list, root_fstr

    def file_in_tree(self, tree: Tree, fstr_parts: list[str]) -> bool:
        if not fstr_parts:
            return False
        for entry in tree:
            if entry.type_str == "tree" and len(fstr_parts) > 1:
                if entry.name == fstr_parts[0]:
                    return self.file_in_tree(entry, fstr_parts[1:])  # type: ignore
            elif (
                entry.type_str == "blob"
                and len(fstr_parts) == 1
                and entry.name == fstr_parts[0]
            ):
                return True
        return False

    def get_blob_from_tree(self, tree: Tree, fstr_parts: list[str]):
        if not fstr_parts:
            return None
        for entry in tree:
            if entry.type_str == "tree" and len(fstr_parts) > 1:
                if entry.name == fstr_parts[0]:
                    return self.get_blob_from_tree(entry, fstr_parts[1:])  # type: ignore
            elif (
                entry.type_str == "blob"
                and len(fstr_parts) == 1
                and entry.name == fstr_parts[0]
            ):
                return entry
        return None

    # pylint: disable=too-many-locals
    def _process_commit_data_for(
        self, commit_datas_list: list[list[CommitData]], fstr_root: FileStr
    ) -> list[CommitGroup]:
        commit_groups: list[CommitGroup] = []
        for commit_datas in commit_datas_list:
            for commit_data in commit_datas:
                fstr = commit_data.fstr
                author = commit_data.author
                sha_short = commit_data.sha_short
                timestamp = commit_data.timestamp
                insertions = commit_data.insertions
                deletions = commit_data.deletions

                target = self.fr2f2a2sha_short_set
                if fstr_root not in target:
                    target[fstr_root] = {}
                if fstr not in target[fstr_root]:
                    target[fstr_root][fstr] = {}
                if author not in target[fstr_root][fstr]:
                    target[fstr_root][fstr][author] = set()
                target[fstr_root][fstr][author].add(sha_short)

                if (
                    commit_groups
                    and fstr == commit_groups[-1].fstr
                    and author == commit_groups[-1].author
                ):
                    commit_groups[-1].date_sum += int(timestamp) * insertions
                    commit_groups[-1].sha_shorts |= {sha_short}
                    commit_groups[-1].insertions += insertions
                    commit_groups[-1].deletions += deletions
                else:
                    commit_group = CommitGroup(
                        author=author,
                        fstr=fstr,
                        insertions=insertions,
                        deletions=deletions,
                        date_sum=int(timestamp) * insertions,
                        sha_shorts={sha_short},
                    )
                    commit_groups.append(commit_group)
        return commit_groups
