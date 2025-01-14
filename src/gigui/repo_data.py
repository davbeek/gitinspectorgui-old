import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

from gigui.constants import STATIC
from gigui.data import CommitGroup, FileStat, Person, PersonsDB, PersonStat
from gigui.repo_blame import RepoBlameHistory
from gigui.typedefs import SHA, Author, FileStr
from gigui.utils import divide_to_percentage

logger = logging.getLogger(__name__)


class RepoData(RepoBlameHistory):
    blame_history: str
    dry_run: int

    def __init__(self, name: str, location: Path):
        super().__init__(name, location)

        self.path = Path(location).resolve()
        self.pathstr = str(self.path)

        self.stat_tables = StatTables()

        self.author2fstr2fstat: dict[str, dict[str, FileStat]] = {}
        self.fstr2fstat: dict[str, FileStat] = {}
        self.fstr2author2fstat: dict[str, dict[str, FileStat]] = {}
        self.author2pstat: dict[str, PersonStat] = {}

        # Valid only after self.run_no_history has been called, which calculates the
        # sorted versions of self.fstrs and self.star_fstrs.
        self.star_fstrs: list[str] = []

        # Sorted list of non-excluded authors, valid only after self.run has been called.
        self.authors_included: list[Author] = []

        self.fr2f2a2shas: dict[FileStr, dict[FileStr, dict[Author, list[SHA]]]] = {}

        # Valid only after self.run has been called with option --blame-history.
        self.fstr2shas: dict[FileStr, list[SHA]] = {}

        self.author2nr: dict[Author, int] = {}  # does not include "*" as author
        self.author_star2nr: dict[Author, int] = {}  # includes "*" as author

        self.sha2author_nr: dict[SHA, int] = {}

    def run_analysis(self, thread_executor: ThreadPoolExecutor) -> bool:
        """
        Generate tables encoded as dictionaries in self.stats.

        Returns:
            bool: True after successful execution, False if no stats have been found.
        """

        try:
            if self.dry_run == 2:
                return True
            self.init_git_repo()
            self.run_base(thread_executor)
            self.run_blame(thread_executor)
            success = self._run_no_history()
            if not success:
                return False

            self._set_final_data()
            if self.blame_history == STATIC and not self.blame_skip:
                super().run_blame_history_static()
            return True
        finally:
            if self.dry_run <= 1:
                self.git_repo.close()

    def _run_no_history(self) -> bool:
        if self.dry_run == 2:
            return True

        # Set stats.author2fstr2fstat, the basis of all other stat tables
        self.author2fstr2fstat = self.stat_tables.get_author2fstr2fstat(
            self.fstrs,
            self.fstr2commit_groups,
            self.persons_db,
        )
        if list(self.author2fstr2fstat.keys()) == ["*"]:
            return False

        # Update author2fstr2fstat with line counts for each author.
        self.author2fstr2fstat = self.update_author2fstr2fstat(self.author2fstr2fstat)

        self.fstr2fstat = self.stat_tables.get_fstr2fstat(
            self.author2fstr2fstat, self.fstr2commit_groups
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
            self.author2fstr2fstat, self.persons_db
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

    def _set_final_data(self) -> None:

        # update self.sha2author with new author definitions in person database
        sha2author: dict[SHA, Author] = {}
        for sha, author in self.sha2author.items():
            new_author = self.persons_db[author].author
            sha2author[sha] = new_author
        self.sha2author = sha2author

        self.fr2f2a2shas = self.fr2f2a2sha_set_to_list(self.fr2f2a2sha_set)

        self.fr2f2shas = self.fr2f2sha_set_to_list(
            self.get_fr2f2sha_set(self.fr2f2a2sha_set)
        )

        for fstr in self.fstrs:
            shas_fr = set()
            for shas in self.fr2f2shas[fstr].values():
                shas_fr.update(shas)
            shas_fr_sorted = sorted(shas_fr, key=lambda x: self.sha2nr[x], reverse=True)
            self.fstr2shas[fstr] = shas_fr_sorted

        # calculate sorted version of self.authors_included
        authors_included: list[Author] = self.persons_db.authors_included
        self.authors_included = sorted(
            authors_included,
            key=lambda x: self.author2pstat[x].stat.line_count,
            reverse=True,
        )

        for i, author in enumerate(self.authors_included):
            self.author_star2nr[author] = i  # "*" author gets nr 0
        for author in self.persons_db.authors_excluded:
            self.author_star2nr[author] = 0

        self.author2nr = {k: v for k, v in self.author_star2nr.items() if k != "*"}

        for sha, author in self.sha2author.items():
            self.sha2author_nr[sha] = self.author2nr[author]

    @property
    def real_authors_included(self) -> list[Author]:
        return [author for author in self.authors_included if not author == "*"]

    # from set to list
    def fr2f2a2sha_set_to_list(
        self, source: dict[FileStr, dict[FileStr, dict[Author, set[SHA]]]]
    ) -> dict[FileStr, dict[FileStr, dict[Author, list[SHA]]]]:
        target: dict[FileStr, dict[FileStr, dict[Author, list[SHA]]]] = {}
        for fstr_root, fstr_root_dict in source.items():
            target[fstr_root] = {}
            for fstr, fstr_dict in fstr_root_dict.items():
                target[fstr_root][fstr] = {}
                for author, shas in fstr_dict.items():
                    person_author = self.persons_db[author].author
                    shas_sorted = sorted(
                        shas, key=lambda x: self.sha2nr[x], reverse=True
                    )
                    target[fstr_root][fstr][person_author] = shas_sorted
        return target

    def get_fr2f2sha_set(
        self, source: dict[FileStr, dict[FileStr, dict[Author, set[SHA]]]]
    ) -> dict[FileStr, dict[FileStr, set[SHA]]]:
        target: dict[FileStr, dict[FileStr, set[SHA]]] = {}
        for fstr_root, fstr_root_dict in source.items():
            target[fstr_root] = {}
            for fstr, fstr_dict in fstr_root_dict.items():
                target[fstr_root][fstr] = set()
                for shas in fstr_dict.values():
                    target[fstr_root][fstr].update(shas)
        return target

    def fr2f2sha_set_to_list(
        self, source: dict[FileStr, dict[FileStr, set[SHA]]]
    ) -> dict[FileStr, dict[FileStr, list[SHA]]]:
        target: dict[FileStr, dict[FileStr, list[SHA]]] = {}
        for fstr_root, fstr_root_dict in source.items():
            target[fstr_root] = {}
            for fstr, shas in fstr_root_dict.items():
                target[fstr_root][fstr] = sorted(
                    shas, key=lambda x: self.sha2nr[x], reverse=True
                )
        return target


class StatTables:
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
                author = persons_db[commit_group.author].author
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
            target[author] = PersonStat(persons_db[author])
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
