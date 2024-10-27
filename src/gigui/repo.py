import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

from git import InvalidGitRepositoryError, NoSuchPathError, PathLike, Repo

from gigui.args_settings import Args
from gigui.blame_reader import Blame, BlameBaseReader, BlameHistoryReader, BlameReader
from gigui.data import CommitGroup, FileStat, Person, PersonsDB, PersonStat
from gigui.repo_reader import RepoReader
from gigui.typedefs import Author, FileStr, SHALong
from gigui.utils import divide_to_percentage, log

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

        self.repo_reader = RepoReader(self.name, self.location)
        self.blame_reader: BlameReader
        self.blame_history_reader: BlameHistoryReader

        self.stat_tables = StatTables()

        self.author2fstr2fstat: dict[str, dict[str, FileStat]] = {}
        self.fstr2fstat: dict[str, FileStat] = {}
        self.fstr2author2fstat: dict[str, dict[str, FileStat]] = {}
        self.author2pstat: dict[str, PersonStat] = {}

        # Valid only after self.run has been called. This call calculates the sorted
        # versions of self.fstrs and self.star_fstrs.
        self.fstrs: list[str]
        self.star_fstrs: list[str]

    # Valid only after self.run has been called.
    @property
    def authors_included(self) -> list[Author]:
        return self.blame_reader.persons_db.authors_included  # type: ignore

    def run(self, thread_executor: ThreadPoolExecutor) -> bool:
        """
        Generate tables encoded as dictionaries in self.stats.

        Returns:
            bool: True after successful execution, False if no stats have been found.
        """

        success: bool
        fstr2shas: dict[FileStr, list[SHALong]] = {}
        try:
            success = self._run_blame_no_history(thread_executor)
            if not success:
                return False
            if self.args.blame_history:
                fstr2shas = self.get_fstr2shas()
                self.blame_history_reader = BlameHistoryReader(
                    self.blame_reader.fstr2blames,
                    self.fstr2fstat,
                    fstr2shas,
                    self.repo_reader.git_repo,
                    self.repo_reader.ex_sha_shorts,
                    self.blame_reader.fstrs,
                    self.repo_reader.persons_db,
                )
            return True
        finally:
            self.repo_reader.git_repo.close()

    def _run_blame_no_history(self, thread_executor: ThreadPoolExecutor) -> bool:
        self.repo_reader.run(thread_executor)

        # Use results from repo_reader to initialize the other classes.
        self.blame_reader = BlameReader(
            self.repo_reader.head_commit.hexsha,
            self.repo_reader.git_repo,
            self.repo_reader.ex_sha_shorts,
            self.repo_reader.fstrs,
            self.repo_reader.persons_db,
        )

        # This calculates all blames but also adds the author and email of
        # each blame to the persons list. This is necessary, because the blame
        # functionality can have another way to set/get the author and email of a
        # commit.
        self.blame_reader.run(thread_executor)

        # Set stats.author2fstr2fstat, the basis of all other stat tables
        self.author2fstr2fstat = self.stat_tables.get_author2fstr2fstat(
            self.repo_reader.fstrs,
            self.repo_reader.fstr2commit_groups,
            self.repo_reader.persons_db,
        )
        if list(self.author2fstr2fstat.keys()) == ["*"]:
            return False

        # Update author2fstr2fstat with line counts for each author.
        self.author2fstr2fstat = self.blame_reader.update_author2fstr2fstat(
            self.author2fstr2fstat
        )

        self.fstr2fstat = self.stat_tables.get_fstr2fstat(
            self.author2fstr2fstat, self.repo_reader.fstr2commit_groups
        )

        # Set self.fstrs and self.star_fstrs and sort by line count
        fstrs = self.fstr2fstat.keys()
        self.star_fstrs = sorted(
            fstrs, key=lambda x: self.fstr2fstat[x].stat.line_count, reverse=True
        )
        if self.star_fstrs and self.star_fstrs[0] == "*":
            self.fstrs = self.star_fstrs[1:]  # remove "*"
        else:
            self.fstrs = self.star_fstrs

        if list(self.fstr2fstat.keys()) == ["*"]:
            return False

        self.fstr2author2fstat = self.stat_tables.get_fstr2author2fstat(
            self.author2fstr2fstat
        )

        self.author2pstat = self.stat_tables.get_author2pstat(
            self.author2fstr2fstat, self.repo_reader.persons_db
        )

        total_insertions = self.author2pstat["*"].stat.insertions
        total_lines = self.author2pstat["*"].stat.line_count

        self.stat_tables.calculate_percentages(
            self.fstr2fstat, total_insertions, total_lines
        )
        self.stat_tables.calculate_percentages(
            self.author2pstat, total_insertions, total_lines
        )
        for _, fstr2fstat in self.author2fstr2fstat.items():
            self.stat_tables.calculate_percentages(
                fstr2fstat, total_insertions, total_lines
            )
        for _, author2fstat in self.fstr2author2fstat.items():
            self.stat_tables.calculate_percentages(
                author2fstat, total_insertions, total_lines
            )
        return True

    @property
    def path(self) -> Path:
        return Path(self.pathstr)

    def get_person(self, author: Author) -> Person:
        return self.repo_reader.get_person(author)

    def get_sorted_fstrs(self) -> list[str]:
        return self.fstrs

    def get_fstr2shas(self) -> dict[FileStr, list[SHALong]]:
        fstr2shas: dict[str, list[SHALong]] = {}
        for fstr in self.fstrs:
            blames: list[Blame] = self.blame_reader.fstr2blames[fstr]
            shas = {blame.sha_long for blame in blames}
            fstr2shas[fstr] = sorted(
                shas, key=lambda sha: self.blame_reader.sha2nr[sha], reverse=True
            )
        return fstr2shas

    @classmethod
    def set_args(cls, args: Args):
        GIRepo.args = RepoReader.args = StatTables.args = args
        RepoReader.ex_revs = set(args.ex_revisions)
        BlameBaseReader.args = args


class StatTables:
    args: Args

    @staticmethod
    def get_author2fstr2fstat(
        fstrs: list[FileStr],
        fstr2commit_groups: dict[FileStr, list[CommitGroup]],
        persons_db: PersonsDB,
    ) -> dict[Author, dict[FileStr, FileStat]]:
        target: dict[Author, dict[FileStr, FileStat]] = {"*": {}}
        target["*"]["*"] = FileStat("*")
        for author in persons_db.authors_included:
            target[author] = {}
            target[author]["*"] = FileStat("*")
        # Start with last commit and go back in time
        for fstr in fstrs:
            for commit_group in fstr2commit_groups[fstr]:
                target["*"]["*"].stat.add_commit_group(commit_group)
                author = persons_db.get_author(commit_group.author)
                target[author]["*"].stat.add_commit_group(commit_group)
                if fstr not in target[author]:
                    target[author][fstr] = FileStat(fstr)
                target[author][fstr].add_commit_group(commit_group)
        return target

    @staticmethod
    def get_fstr2fstat(
        author2fstr2fstat: dict[Author, dict[FileStr, FileStat]],
        fstr2commit_group: dict[FileStr, list[CommitGroup]],
    ) -> dict[FileStr, FileStat]:
        source = author2fstr2fstat
        target: dict[FileStr, FileStat] = {}
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
            for commit_group in fstr2commit_group[fstr]:
                # Order of names must correspond to the order of the commits
                target[fstr].add_name(commit_group.fstr)
        return target

    @staticmethod
    def get_fstr2author2fstat(
        author2fstr2fstat: dict[Author, dict[FileStr, FileStat]],
    ) -> dict[Author, dict[FileStr, FileStat]]:
        source = author2fstr2fstat
        target: dict[FileStr, dict[Author, FileStat]] = {}
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
                target[fstr]["*"].names = fstr2fstat[fstr].names
        return target

    @staticmethod
    def get_author2pstat(
        author2fstr2fstat: dict[Author, dict[FileStr, FileStat]], persons_db: PersonsDB
    ) -> dict[Author, PersonStat]:
        source = author2fstr2fstat
        target: dict[Author, PersonStat] = {}
        for author, fstr2fstat in source.items():
            if author == "*":
                target["*"] = PersonStat(Person("*", "*"))
                target["*"].stat = source["*"]["*"].stat
                continue
            target[author] = PersonStat(persons_db.get_person(author))
            for fstr, fstat in fstr2fstat.items():
                if fstr == "*":
                    continue
                target[author].stat.add(fstat.stat)
        return target

    AuthorOrFileStr = TypeVar("AuthorOrFileStr", Author, FileStr)
    PersonStatOrFileStat = TypeVar("PersonStatOrFileStat", PersonStat, FileStat)

    @staticmethod
    def calculate_percentages(
        af2pf_stat: dict[AuthorOrFileStr, PersonStatOrFileStat],
        total_insertions: int,
        total_lines: int,
    ) -> None:
        """
        Calculate the percentage of insertions and lines for each author or file.
        The percentages are stored in the stat objects from the af2pf_stat dictionary.
        This dictionary is edited in place and serves as input and output.
        """
        for af in af2pf_stat.keys():  # af is either an author or fstr
            af2pf_stat[af].stat.percent_insertions = divide_to_percentage(
                af2pf_stat[af].stat.insertions, total_insertions
            )
            af2pf_stat[af].stat.percent_lines = divide_to_percentage(
                af2pf_stat[af].stat.line_count, total_lines
            )


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
                GIRepo(subdir.name, subdir) for subdir in subdirs if is_git_repo(subdir)
            ]
            repos = sorted(repos, key=lambda x: x.name)
            other_dirs: list[Path] = [
                subdir for subdir in subdirs if not is_git_repo(subdir)
            ]
            other_dirs = sorted(other_dirs)
            repo_lists = [repos] if repos else []
            for other_dir in other_dirs:
                repo_lists.extend(get_repos(other_dir, depth - 1))
            return repo_lists
    else:
        log(f"Path {pathlike} is not a directory")
        return []


def is_dir_safe(pathlike: PathLike) -> bool:
    try:
        return os.path.isdir(pathlike)
    except PermissionError:
        logger.warning(f"Permission denied for path {str(pathlike)}")
        return False


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


def subdirs_safe(pathlike: PathLike) -> list[Path]:
    try:
        if not is_dir_safe(pathlike):
            return []
        subs = os.listdir(pathlike)
        sub_paths = [Path(pathlike) / sub for sub in subs]
        return [path for path in sub_paths if is_dir_safe(path)]
    # Exception when the os does not allow to list the contents of the path dir:
    except PermissionError:
        logger.warning(f"Permission denied for path {str(pathlike)}")
        return []


def total_len(repo_lists: list[list[GIRepo]]) -> int:
    return sum(len(repo_list) for repo_list in repo_lists)
