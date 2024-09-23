import copy
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TypeVar

from git import Commit as GitCommit
from git import InvalidGitRepositoryError, NoSuchPathError, PathLike, Repo

from gigui.args_settings_keys import Args
from gigui.blame_manager import BlameManager, Commit
from gigui.common import divide_to_percentage, log
from gigui.data import FileStat, MultiCommit, Person, Persons, PersonStat, RepoStats
from gigui.typedefs import Author, FileStr, Rev, SHAlong, SHAshort

logger = logging.getLogger(__name__)


class GIRepo:
    args: Args

    # Here the values of the --ex-revision parameter are stored as a set.
    ex_revs: set[Rev] = set()

    def __init__(self, name: str, location: PathLike):
        self.name: str = name
        self.location: str = str(location)
        # The default True value of expand_vars can leads to confusing warnings from
        # GitPython:
        self.gitrepo: Repo = Repo(location, expand_vars=False)

        # List of all commits in the repo starting at the until date parameter (if set),
        # or else at the first commit of the repo. The list includes merge commits and
        # is sorted by commit date.
        self.commits: list[Commit]
        self.head_commit: GitCommit
        self.sha2commit: dict[SHAshort | SHAlong, Commit] = {}

        # Set of short SHAs of commits in the repo that are excluded by the
        # --ex-revision parameter together with the --ex-message parameter.
        self.ex_sha_shorts: set[SHAshort] = set()

        # List of files from the top commit of the repo:
        self.fstrs: list[FileStr] = []

        # Dict of file names to their sizes:
        self.fstr2lines: dict[FileStr, int] = {}

        self.fstr2mcommits: dict[FileStr, list[MultiCommit]] = {}
        self.stats = RepoStats()
        self.blame_manager: BlameManager
        self.thread_executor: (
            ThreadPoolExecutor  # To be set by self.set_thread_executor(...)
        )
        self._persons: Persons = Persons()

    # def __repr__(self) -> str:
    #     return f"GIRepo {self.gitrepo.working_dir}"
    def __repr__(self) -> str:
        return self.pathstr

    def __str__(self) -> str:
        return f"Repo {self.name}"

    @property
    def pathstr(self) -> str:
        return str(self.gitrepo.working_dir)

    @property
    def path(self) -> Path:
        return Path(self.gitrepo.working_dir)

    @property
    def authors_included(self) -> list[Author]:
        return [person.author for person in self.persons if not person.filter_matched]

    @property
    def authors_excluded(self) -> list[Author]:
        return [person.author for person in self.persons if person.filter_matched]

    @property
    def persons(self) -> list[Person]:
        return self._persons.persons

    @property
    def git(self):
        return self.gitrepo.git

    def get_author(self, author: Author | None) -> Author:
        return self._persons.get_person(author).author

    def get_person(self, author: Author | None) -> Person:
        return self._persons.get_person(author)

    def get_all_names(self, fstr: FileStr) -> list[FileStr]:
        names_str: str = self.git.log(
            "--follow", "--name-only", "--pretty=format:", str(fstr)
        )
        names = names_str.splitlines()
        unique_names = []
        current_name = None
        for f in names:
            if f:
                if f != current_name:
                    unique_names.append(f)
                    current_name = f
        return unique_names

    # Get list of top level files (based on the until parameter) that satisfy the
    # required extensions and do not match the exclude file patterns.
    # To get all files use --include-file=".*" as pattern
    # include_files takes priority over n_files
    def get_worktree_files(self) -> list[FileStr]:

        # Returns True if file should be excluded
        def matches_ex_file(fstr: FileStr) -> bool:
            return any(
                re.search(pattern, fstr, re.IGNORECASE)
                for pattern in self.args.ex_files
            )

        # Get the n biggest files in the worktree that:
        # - match the required extensions
        # - are not excluded
        def get_biggest_worktree_files(n: int) -> list[FileStr]:

            # Get the files with their file sizes that match the required extensions
            def get_worktree_files_sizes() -> list[tuple[FileStr, int]]:
                return [
                    (blob.path, blob.size)  # type: ignore
                    for blob in self.head_commit.tree.traverse()
                    if (
                        (blob.type == "blob")  # type: ignore
                        and (blob.path.split(".")[-1] in self.args.extensions)  # type: ignore
                    )
                ]

            assert n > 0
            sorted_files_sizes = sorted(
                get_worktree_files_sizes(), key=lambda x: x[1], reverse=True
            )
            sorted_files = [file_size[0] for file_size in sorted_files_sizes]
            sorted_files_filtered = [
                f for f in sorted_files if (not matches_ex_file(f))
            ]
            return sorted_files_filtered[0:n]

        include_files = self.args.include_files
        show_n_files = self.args.n_files
        if not include_files:
            matches = get_biggest_worktree_files(show_n_files)
        else:  # Get files matching file pattern
            matches: list[FileStr] = [
                blob.path  # type: ignore
                for blob in self.head_commit.tree.traverse()
                if (
                    blob.type == "blob"  # type: ignore
                    and blob.path.split(".")[-1] in self.args.extensions  # type: ignore
                    and not matches_ex_file(blob.path)  # type: ignore
                    and any(
                        re.search(pattern, blob.path, re.IGNORECASE)  # type: ignore
                        for pattern in include_files
                    )
                )
            ]
        return matches

    def set_head_commit(self):
        since = self.args.since
        until = self.args.until

        since_until_kwargs: dict = {}
        if since and until:
            since_until_kwargs = {"since": since, "until": until}
        elif since:
            since_until_kwargs = {"since": since}
        elif until:
            since_until_kwargs = {"until": until}

        self.head_commit = next(self.gitrepo.iter_commits(**since_until_kwargs))

    def set_fstr2lines(self):
        def count_lines_in_blob(blob):
            return len(blob.data_stream.read().decode("utf-8").split("\n"))

        self.fstr2lines["*"] = 0
        for blob in self.head_commit.tree.traverse():
            if (
                blob.type == "blob"  # type: ignore
                and blob.path in self.fstrs  # type: ignore
                and blob.path not in self.fstr2lines  # type: ignore
            ):
                lines: int = count_lines_in_blob(blob)
                self.fstr2lines[blob.path] = lines  # type: ignore
                self.fstr2lines["*"] += lines

    def get_since_until_args(self) -> list[str]:
        since = self.args.since
        until = self.args.until
        if since and until:
            return [f"--since={since}", f"--until={until}"]
        elif since:
            return [f"--since={since}"]
        elif until:
            return [f"--until={until}"]
        else:
            return []

    def get_commits_first_pass(self):
        commits: list[Commit] = []
        ex_sha_shorts: set[SHAshort] = set()
        sha_short: SHAshort
        sha_long: SHAlong

        # %H: commit hash long (SHAlong)
        # %h: commit hash long (SHAshort)
        # %ct: committer date, UNIX timestamp
        # %s: commit message
        # %aN: author name, respecting .mailmap
        # %aE: author email, respecting .mailmap
        # %n: newline
        args = self.get_since_until_args()
        args += [
            f"{self.head_commit.hexsha}",
            "--pretty=format:%H%n%h%n%ct%n%s%n%aN%n%aE%n",
        ]
        lines_str: str = self.git.log(*args)

        lines = lines_str.splitlines()
        while lines:
            line = lines.pop(0)
            if not line:
                continue
            sha_long = line
            sha_short = lines.pop(0)
            if any(sha_long.startswith(rev) for rev in self.ex_revs):
                ex_sha_shorts.add(sha_short)
                continue
            timestamp = int(lines.pop(0))
            message = lines.pop(0)
            if any(
                re.search(pattern, message, re.IGNORECASE)
                for pattern in self.args.ex_messages
            ):
                ex_sha_shorts.add(sha_short)
                continue
            author = lines.pop(0)
            email = lines.pop(0)
            self._persons.add_person(author, email)
            commit = Commit(sha_short, sha_long, timestamp)
            commits.append(commit)
            self.sha2commit[sha_short] = commit
            self.sha2commit[sha_long] = commit

        commits.sort(key=lambda x: x.date)
        self.commits = commits
        self.ex_sha_shorts = ex_sha_shorts

    def get_commit_lines_for(self, fstr: FileStr) -> tuple[str, FileStr]:
        def git_log_args() -> list[str]:
            args = self.get_since_until_args()
            if not self.args.whitespace:
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

    def process_commit_lines_for(
        self, fstr: FileStr, lines_str: str
    ) -> list[MultiCommit]:
        commits: list[MultiCommit] = []
        lines = lines_str.splitlines()
        while lines:
            line = lines.pop(0)
            if not line:
                continue
            sha_short, timestamp = line.split()
            if sha_short in self.ex_sha_shorts:
                continue
            author = lines.pop(0)
            person = self.get_person(author)
            if not lines:
                break
            stat_line = lines.pop(0)
            if person.filter_matched or not stat_line:
                continue
            stats = stat_line.split()
            insertions = int(stats.pop(0))
            deletions = int(stats.pop(0))
            line = " ".join(stats)
            if "=>" not in line:
                fstr = line
            elif "{" in line:
                # Eliminate the {...} abbreviation part of the line
                # which occur for file renames and file copies.
                # Examples of these lines are:
                # 1. gitinspector/{gitinspect_gui.py => gitinspector_gui.py}
                # 2. gitinspect_gui.py => gitinspector/gitinspect_gui.py
                # 3. src/gigui/{ => gi}/gitinspector.py
                prefix, rest = line.split("{")
                old_part, rest = rest.split(" => ")
                new_part, suffix = rest.split("}")
                prev_name = f"{prefix}{old_part}{suffix}"
                new_name = f"{prefix}{new_part}{suffix}"
                # src/gigui/{ => gi}/gitinspector.py leads to:
                # src/gigui//gitinspector.py => src/gigui/gi/gitinspector.py
                prev_name = prev_name.replace("//", "/")
                fstr = new_name = new_name.replace("//", "/")
            else:
                split = line.split(" => ")
                prev_name = split[0]
                fstr = new_name = split[1]
            if (
                len(commits) > 1
                and fstr == commits[-1].fstr
                and author == commits[-1].author
            ):
                commits[-1].date_sum += int(timestamp) * insertions
                commits[-1].commits |= {sha_short}
                commits[-1].insertions += insertions
                commits[-1].deletions += deletions
            else:
                commit = MultiCommit(
                    date_sum=int(timestamp) * insertions,
                    author=author,
                    fstr=fstr,
                    insertions=insertions,
                    deletions=deletions,
                    commits={sha_short},
                )
                commits.append(commit)
        return commits

    def set_fstr2commits(self, thread_executor: ThreadPoolExecutor):
        # When two lists of commits share the same commit at the end,
        # the duplicate commit is removed from the longer list.
        def reduce_commits():
            fstrs = copy.deepcopy(self.fstrs)
            # Default sorting order ascending: from small to large, so the first element
            # is the smallest.
            fstrs.sort(key=lambda x: len(self.fstr2mcommits[x]))
            while fstrs:
                fstr1 = fstrs.pop()
                mcommits1 = self.fstr2mcommits[fstr1]
                if not mcommits1:
                    continue
                for fstr2 in fstrs:
                    mcommits2 = self.fstr2mcommits[fstr2]
                    i = -1
                    while mcommits2 and mcommits1[i] == mcommits2[-1]:
                        mcommits2.pop()
                        i -= 1

        if self.args.multi_thread:
            futures = [
                thread_executor.submit(self.get_commit_lines_for, fstr)
                for fstr in self.fstrs
            ]
            for future in as_completed(futures):
                lines_str, fstr = future.result()
                self.fstr2mcommits[fstr] = self.process_commit_lines_for(
                    fstr, lines_str
                )
        else:  # single thread
            for fstr in self.fstrs:
                lines_str, fstr = self.get_commit_lines_for(fstr)
                self.fstr2mcommits[fstr] = self.process_commit_lines_for(
                    fstr, lines_str
                )
        reduce_commits()

    # Return true after successful execution. Return false if no stats have been found.
    def calculate_stats(self, thread_executor: ThreadPoolExecutor) -> bool:
        stats: RepoStats = self.stats
        self.set_head_commit()

        # Set list top level fstrs (based on until par and allowed file extensions)
        self.fstrs = self.get_worktree_files()

        self.set_fstr2lines()
        self.get_commits_first_pass()

        # This calculates all blames but also adds the author and email of
        # each blame to the persons list. This is necessary, because the blame
        # functionality can have another way to set/get the author and email of a
        # commit.
        self.blame_manager = BlameManager(
            self.gitrepo,
            self.args,
            self.authors_excluded,
            self.authors_included,
            self.ex_sha_shorts,
            self.fstrs,
            self.head_commit,
            self.sha2commit,
            thread_executor,
            self._persons,
        )

        # print(f"{"    Calc commit for":22}{self.gitrepo.working_dir}")
        self.set_fstr2commits(thread_executor)

        target = stats.author2fstr2fstat

        # Calculate self.author2fstr2fstat
        target["*"] = {}
        target["*"]["*"] = FileStat("*")
        for author in self.authors_included:
            target[author] = {}
            target[author]["*"] = FileStat("*")
        # Start with last commit and go back in time
        for fstr in self.fstrs:
            for mcommit in self.fstr2mcommits[fstr]:
                target["*"]["*"].stat.add_multicommit(mcommit)
                author = self.get_author(mcommit.author)
                target[author]["*"].stat.add_multicommit(mcommit)
                if fstr not in target[author]:
                    target[author][fstr] = FileStat(fstr)
                target[author][fstr].add_multicommit(mcommit)

        if list(target.keys()) == ["*"]:
            return False

        source = stats.author2fstr2fstat

        # Set lines in self.author2fstr2fstat
        self.blame_manager.process_blames(stats.author2fstr2fstat)

        # Calculate self.fstr2fstat
        target = stats.fstr2fstat
        fstrs = set()
        for author, fstr2fstat in source.items():
            if author == "*":
                target["*"] = source["*"]["*"]
            else:
                for fstr, fstat in fstr2fstat.items():
                    if fstr != "*":
                        fstrs.add(fstr)
                        if fstr not in target:
                            target[fstr] = FileStat(fstr)
                        target[fstr].stat.add(fstat.stat)
        for fstr in fstrs:
            for mcommit in self.fstr2mcommits[fstr]:
                # Order of names must correspond to the order of the commits
                target[fstr].add_name(mcommit.fstr)

        if list(target.keys()) == ["*"]:
            return False

        # source = self.author2fstr2fstat
        # Calculate target = self.fstr2author2fstat
        target = stats.fstr2author2fstat
        for author, fstr2fstat in source.items():
            if author == "*":
                target["*"] = source["*"]
                continue
            for fstr, fstat in fstr2fstat.items():
                if fstr == "*":
                    continue
                if fstr not in target:
                    target[fstr] = {}
                    target[fstr]["*"] = FileStat(fstr)
                target[fstr][author] = fstat
                target[fstr]["*"].stat.add(fstat.stat)
                target[fstr]["*"].names = stats.fstr2fstat[fstr].names

        # source = stats.author2fstr2fstat
        # Calculate stats.author2pstat
        target = stats.author2pstat
        for author, fstr2fstat in source.items():
            if author == "*":
                target["*"] = PersonStat(Person("*", "*"))
                target["*"].stat = source["*"]["*"].stat
                continue
            target[author] = PersonStat(self.get_person(author))
            for fstr, fstat in fstr2fstat.items():
                if fstr == "*":
                    continue
                target[author].stat.add(fstat.stat)

        PFStat = TypeVar("PFStat", PersonStat, FileStat)
        AuFi = TypeVar("AuFi", Author, FileStr)

        total_insertions = stats.author2pstat["*"].stat.insertions
        total_lines = stats.author2pstat["*"].stat.line_count

        # Calculate percentages, af is either an author or fstr
        def calculate_percentages(
            af2pfstat: dict[AuFi, PFStat], total_insertions: int, total_lines: int
        ):
            afs = af2pfstat.keys()
            for af in afs:
                af2pfstat[af].stat.percent_insertions = divide_to_percentage(
                    af2pfstat[af].stat.insertions, total_insertions
                )
                af2pfstat[af].stat.percent_lines = divide_to_percentage(
                    af2pfstat[af].stat.line_count, total_lines
                )

        calculate_percentages(stats.fstr2fstat, total_insertions, total_lines)
        calculate_percentages(stats.author2pstat, total_insertions, total_lines)
        for author, fstr2fstat in stats.author2fstr2fstat.items():
            calculate_percentages(fstr2fstat, total_insertions, total_lines)
        for fstr, author2fstat in stats.fstr2author2fstat.items():
            calculate_percentages(author2fstat, total_insertions, total_lines)

        self.gitrepo.close()
        return True

    @classmethod
    def set_args(cls, args: Args):
        cls.args = args
        cls.ex_revs = set(args.ex_revisions)


def is_dir_safe(pathlike: PathLike) -> bool:

    try:
        return os.path.isdir(pathlike)
    except PermissionError:
        logger.warning(f"Permission denied for path {str(pathlike)}")
        return False


def subdirs_safe(pathlike: PathLike) -> list[Path]:
    try:
        if not is_dir_safe(pathlike):
            return []
        subs = os.listdir(pathlike)
        subpaths = [Path(pathlike) / sub for sub in subs]
        return [path for path in subpaths if is_dir_safe(path)]
    # Exception when the os does not allow to list the contents of the path dir:
    except PermissionError:
        logger.warning(f"Permission denied for path {str(pathlike)}")
        return []


def is_git_repo(pathlike: PathLike) -> bool:
    path = Path(pathlike)
    try:
        git_path = path / ".git"
        if git_path.is_symlink():
            git_path = git_path.resolve()
            if not git_path.is_dir():
                return False
        elif not git_path.is_dir():
            return False
    except (PermissionError, TimeoutError):  # git_path.is_symlink() may time out
        return False

    try:
        # The default True value of expand_vars leads to confusing warnings from
        # GitPython for many paths from system folders.
        repo = Repo(path, expand_vars=False)
        return not repo.bare
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False


def get_repos(pathlike: PathLike, depth: int) -> list[list[GIRepo]]:
    path = Path(pathlike)
    repo_lists: list[list[GIRepo]]
    if is_dir_safe(pathlike):
        if is_git_repo(pathlike):
            return [[GIRepo(path.name, path)]]  # independent of depth
        elif depth == 0:
            # For depth == 0, the input itself must be a repo, which is not the case.
            return []
        else:  # depth >= 1:
            subdirs: list[Path] = subdirs_safe(pathlike)
            repos: list[GIRepo] = [
                GIRepo(dir.name, dir) for dir in subdirs if is_git_repo(dir)
            ]
            repos = sorted(repos, key=lambda x: x.name)
            other_dirs: list[Path] = [dir for dir in subdirs if not is_git_repo(dir)]
            other_dirs = sorted(other_dirs)
            repo_lists = [repos] if repos else []
            for other_dir in other_dirs:
                repo_lists.extend(get_repos(other_dir, depth - 1))
            return repo_lists
    else:
        log(f"Path {pathlike} is not a directory")
        return []


def total_len(repo_lists: list[list[GIRepo]]) -> int:
    return sum(len(repo_list) for repo_list in repo_lists)
