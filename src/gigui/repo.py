import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

from git import InvalidGitRepositoryError, NoSuchPathError, PathLike, Repo

from gigui.args_settings_keys import Args
from gigui.blame import BlameReader, BlameTables
from gigui.common import divide_to_percentage, log
from gigui.data import FileStat, MultiCommit, Person, PersonsDB, PersonStat, RepoStats
from gigui.repo_reader import RepoReader
from gigui.typedefs import Author, FileStr

logger = logging.getLogger(__name__)


class GIRepo:
    args: Args

    def __init__(self, name: str, location: PathLike):
        self.name = name
        self.location = str(location)
        self.pathstr = str(Path(location).resolve())

        self.repo_reader = RepoReader(
            name,
            location,
        )

        # These cannot be set now, they are set in run()
        self.blame_reader: BlameReader
        self.blame_tables: BlameTables
        self.stat_tables: StatTables

    # Valid only after self.run has been called.
    @property
    def authors_included(self) -> list[Author]:
        return self.blame_reader.persons_db.authors_included

    def run(self, thread_executor: ThreadPoolExecutor) -> bool:
        """
        Generate tables encoded as dictionaries in self.stats.

        Returns:
            bool: True after successful execution, False if no stats have been found.
        """

        self.repo_reader.run(thread_executor)

        # Use results from repo_reader to initialize the other classes.
        self.blame_reader = BlameReader(
            self.repo_reader.gitrepo,
            self.repo_reader.head_commit,
            self.repo_reader.ex_sha_shorts,
            self.repo_reader.fstrs,
            self.repo_reader.persons_db,
        )
        self.blame_tables = BlameTables(
            self.repo_reader.fstrs,
            self.repo_reader.persons_db,
            self.blame_reader.fstr2blames,
        )
        self.stat_tables = StatTables(
            self.name,
            self.repo_reader.fstrs,
            self.repo_reader.fstr2mcommits,
            self.repo_reader.persons_db,
        )

        # This calculates all blames but also adds the author and email of
        # each blame to the persons list. This is necessary, because the blame
        # functionality can have another way to set/get the author and email of a
        # commit.
        self.blame_reader.run(thread_executor)

        # Set stats.author2fstr2fstat, the basis of all other stat tables
        self.stat_tables.set_stats_author2fstr2fstat()

        # Update author2fstr2fstat with line counts for each author.
        self.blame_tables.run(self.stats.author2fstr2fstat)

        # Calculate the other tables
        ok: bool = self.stat_tables.run()

        self.repo_reader.gitrepo.close()
        return ok

    @property
    def path(self) -> Path:
        return Path(self.pathstr)

    @property
    def stats(self) -> RepoStats:
        return self.stat_tables.stats

    def get_person(self, author: Author) -> Person:
        return self.repo_reader.get_person(author)

    @classmethod
    def set_args(cls, args: Args):
        GIRepo.args = RepoReader.args = StatTables.args = args
        BlameReader.args = BlameTables.args = args
        RepoReader.ex_revs = set(args.ex_revisions)


class StatTables:
    args: Args

    def __init__(
        self,
        name: str,
        fstrs: list[FileStr],
        fstr2mcommits: dict[FileStr, list[MultiCommit]],
        perons_db: PersonsDB,
    ):
        self.name = name
        self.fstrs = fstrs
        self.fstr2mcommits = fstr2mcommits
        self.persons_db = perons_db

        self.stats = RepoStats()

    def set_stats_author2fstr2fstat(self):
        target = self.stats.author2fstr2fstat
        target["*"] = {}
        target["*"]["*"] = FileStat("*")
        for author in self.persons_db.authors_included:
            target[author] = {}
            target[author]["*"] = FileStat("*")
        # Start with last commit and go back in time
        for fstr in self.fstrs:
            for mcommit in self.fstr2mcommits[fstr]:
                target["*"]["*"].stat.add_multicommit(mcommit)
                author = self.persons_db.get_author(mcommit.author)
                target[author]["*"].stat.add_multicommit(mcommit)
                if fstr not in target[author]:
                    target[author][fstr] = FileStat(fstr)
                target[author][fstr].add_multicommit(mcommit)

    def run(self) -> bool:
        """
        Generate tables encoded as dictionaries in self.stats.

        Returns:
            bool: True after successful execution, False if no stats have been found.
        """

        if list(self.stats.author2fstr2fstat.keys()) == ["*"]:
            return False

        stats = self.stats
        source = stats.author2fstr2fstat

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
            target[author] = PersonStat(self.persons_db.get_person(author))
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
        return True


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
