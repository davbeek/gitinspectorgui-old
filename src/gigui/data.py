import time
from dataclasses import dataclass
from logging import getLogger
from math import floor
from pathlib import Path

from gigui.args_settings import Args
from gigui.person_data import Person
from gigui.typedefs import SHA, Author, FileStr
from gigui.utils import get_relative_fstr

SECONDS_IN_DAY = 60 * 60 * 24
DAYS_IN_MONTH = 30.44
DAYS_IN_YEAR = 365.25

logger = getLogger(__name__)

NOW = int(time.time())  # current time as Unix timestamp in seconds since epoch


# A CommitGroup holds the sum of commit data for commits that share the same person
# author and file name.
@dataclass
class CommitGroup:
    fstr: FileStr
    author: Author
    insertions: int
    deletions: int
    date_sum: int
    shas: set[SHA]


class Stat:
    def __init__(self) -> None:
        self.shas: set[SHA] = (
            set()
        )  # Use to caclulate the number of commits as len(shas)
        self.insertions: int = 0
        self.deletions: int = 0
        self.date_sum: int = 0  # Sum of Unix timestamps in seconds
        self.blame_line_count: int = 0
        self.percent_insertions: float = 0
        self.percent_deletions: float = 0
        self.percent_lines: float = 0

    @property
    def stability(self) -> int | str:
        return (
            min(100, round(100 * self.blame_line_count / self.insertions))
            if self.insertions and self.blame_line_count
            else ""
        )

    @property
    def age(self) -> str:
        return (
            self.timestamp_to_age(round(self.date_sum / self.insertions))
            if self.insertions > 0
            else ""
        )

    def __repr__(self):
        s = ""
        s += f"  insertions = {self.insertions}\n"
        s += f"  deletions = {self.deletions}\n"
        return s

    def __str__(self):
        return self.__repr__()

    def add(self, other: "Stat"):
        self.shas = self.shas | other.shas
        self.insertions = self.insertions + other.insertions
        self.deletions = self.deletions + other.deletions
        self.date_sum = self.date_sum + other.date_sum
        self.blame_line_count = self.blame_line_count + other.blame_line_count

    def add_commit_group(self, commit_group: CommitGroup):
        self.shas |= commit_group.shas
        self.insertions += commit_group.insertions
        self.deletions += commit_group.deletions
        self.date_sum += commit_group.date_sum

    @staticmethod
    def timestamp_to_age(time_stamp: int) -> str:
        seconds: int = NOW - time_stamp
        days: float = seconds / SECONDS_IN_DAY
        years: int = floor(days / DAYS_IN_YEAR)
        remaining_days: float = days - years * DAYS_IN_YEAR
        months: int = floor(remaining_days / DAYS_IN_MONTH)
        remaining_days = round(remaining_days - months * DAYS_IN_MONTH)
        if years:
            return f"{years}:{months:02}:{remaining_days:02}"
        else:
            return f"{months:02}:{remaining_days:02}"


class PersonStat:
    def __init__(self, person: Person):
        self.person: Person = person
        self.stat: Stat = Stat()

    def __repr__(self):
        s = f"person stat: {self.person.authors_str}\n"
        s += f"{repr(self.stat)}\n"
        return s

    def __str__(self):
        return self.__repr__()


class FileStat:
    show_renames: bool

    def __init__(self, fstr: FileStr):
        self.fstr: FileStr = fstr
        self.names: list[FileStr] = []
        self.stat: Stat = Stat()

    def __repr__(self):
        s = f"FileStat: {self.names_str()}\n"
        s += f"{repr(self.stat)}\n"
        return s

    def __str__(self):
        return self.__repr__()

    def add_name(self, name: FileStr):
        if name not in self.names:
            self.names.append(name)

    def add_commit_group(self, commit_group: CommitGroup) -> None:
        assert commit_group.fstr != ""
        self.add_name(commit_group.fstr)
        self.stat.add_commit_group(commit_group)

    def names_str(self) -> str:
        names = self.names
        if self.fstr == "*":
            return "*"
        elif len(names) == 0:
            return self.fstr + ": no commits"
        elif not self.show_renames:
            return self.fstr
        elif self.fstr in names:
            return " + ".join(names)
        else:
            return self.fstr + ": " + " + ".join(names)

    def relative_names_str(self, subfolder: str) -> str:
        if self.fstr == "*":
            return "*"

        names = []
        for name in self.names:
            names.append(get_relative_fstr(name, subfolder))

        fstr = get_relative_fstr(self.fstr, subfolder)
        if len(names) == 0:
            return fstr + ": no commits"
        elif not self.show_renames:
            return fstr
        elif fstr in names:
            return " + ".join(names)
        else:
            return fstr + ": " + " + ".join(names)


@dataclass
class IniRepo:
    name: str
    location: Path
    args: Args
