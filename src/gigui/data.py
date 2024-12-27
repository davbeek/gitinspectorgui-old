import logging
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from math import floor

from gigui.typedefs import SHA, Author, Email, FileStr, Row
from gigui.utils import get_relative_fstr

SECONDS_IN_DAY = 60 * 60 * 24
DAYS_IN_MONTH = 30.44
DAYS_IN_YEAR = 365.25

logger = logging.getLogger(__name__)

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
        self.shas: set[SHA] = set()
        self.insertions: int = 0
        self.deletions: int = 0
        self.date_sum: int = 0  # Sum of Unix timestamps in seconds
        self.line_count: int = 0  # DEFINED BY BLAME, NOT BY FILE SIZE!!!
        self.percent_insertions: float = 0
        self.percent_deletions: float = 0
        self.percent_lines: float = 0

    @property
    def stability(self) -> int | str:
        return (
            min(100, round(100 * self.line_count / self.insertions))
            if self.insertions and self.line_count
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
        self.line_count = self.line_count + other.line_count

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
    def __init__(self, person: "Person"):
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
        s = f"FileStat: {self.names_str}\n"
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

    @property
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
class RepoStats:
    author2pstat: dict[Author, PersonStat] = field(default_factory=dict)
    author2fstr2fstat: dict[Author, dict[FileStr, FileStat]] = field(
        default_factory=dict
    )
    fstr2author2fstat: dict[FileStr, dict[Author, FileStat]] = field(
        default_factory=dict
    )
    # Dict to gather statistics of the files of this repo, defined by --include-n-files
    # or --include-files:
    fstr2fstat: dict[FileStr, FileStat] = field(default_factory=dict)


class Person:
    show_renames: bool
    ex_author_patterns: list[str] = []
    ex_email_patterns: list[str] = []

    def __init__(self, author: Author, email: Email):
        super().__init__()
        self.authors: set[Author] = {author}
        self.emails: set[Email] = {email}
        self.author: Author = self.get_author()

        # If any of the filters match, this will be set to True
        # so that the person will be excluded from the output.
        self.filter_matched: bool = False

        self.match_author_filter(author)
        self.match_email_filter(email)

    def match_author_filter(self, author: str):
        self.find_filter_match(self.ex_author_patterns, author)

    def match_email_filter(self, email: str):
        self.find_filter_match(self.ex_email_patterns, email)

    def find_filter_match(self, patterns: list[str], author_or_email: str):
        if (
            not self.filter_matched
            and not author_or_email == "*"
            and any(fnmatch(author_or_email, pattern) for pattern in patterns)
        ):
            self.filter_matched = True

    #  other is a person with a defined author and defined email
    def merge(self, other: "Person") -> "Person":
        self.authors |= other.authors
        if self.emails == {"Unknown"}:
            self.emails = other.emails
        else:
            self.emails |= other.emails
        self.filter_matched = self.filter_matched or other.filter_matched
        self.author = self.get_author()
        return self

    def __repr__(self):
        authors = self.authors_str
        emails = self.emails_str
        s = f"person({self.__str__()})\n"
        s += f"  author = {authors}\n"
        s += f"  email = {emails}\n"
        s += f"  filter_matched = {self.filter_matched}\n"
        return s

    def __str__(self):
        s = f"{self.authors_str}, {self.emails_str}\n"
        return s

    # Required for manipulating Person objects in a set
    def __hash__(self) -> int:
        return hash((frozenset(self.authors), frozenset(self.emails)))

    def get_authors(self) -> list[Author]:
        # nice authors have first and last name
        nice_authors = {author for author in self.authors if " " in author}

        # top authors also do not have a period or comma in their name.
        top_authors = {
            author
            for author in nice_authors
            if all(c.isalnum() or c.isspace() for c in author)
        }

        nice_authors = nice_authors - top_authors
        other_authors = self.authors - top_authors - nice_authors
        return (
            sorted(top_authors, key=len)
            + sorted(nice_authors, key=len)
            + sorted(other_authors, key=len)
        )

    def get_author(self) -> Author:
        return self.get_authors()[0]

    @property
    def authors_str(self) -> str:
        if self.show_renames:
            authors = self.get_authors()
            return " | ".join(authors)
        else:
            return self.author

    @property
    def emails_str(self) -> str:
        emails = list(self.emails)
        emails = sorted(emails, key=len)
        if len(emails) == 1:
            return emails[0]
        elif self.show_renames:
            return " | ".join(emails)
        else:
            email_list = list(self.emails)
            name_parts = self.author.split(" ")
            name_parts = [part.lower() for part in name_parts if len(part) >= 3]
            # If any part with size >= 3 of author name is in the email, use that email
            nice_emails = [
                email
                for email in email_list
                if any(part in email for part in name_parts)
            ]
            if nice_emails:
                return nice_emails[0]
            else:
                return email_list[0]  # assume self.emails cannot be empty


class PersonsDB(dict[Author | Email, Person]):
    """
    The database with known persons.

    It stores found email addresses and usernames of users in the analyzed
    repositories and tries to merge the information if they seem to point
    to the same person. A person can have several usernames and/or several
    email addresses.
    """

    def __init__(self) -> None:
        super().__init__()
        self["*"] = Person("*", "*")
        # There can only be one "Unknown" key. If the "Unknown" key is present, it
        # belongs to a person where both author and email are "Unknown"

    # pylint: disable=too-many-branches disable=too-many-return-statements
    def add_person(self, author: Author | None, email: Email | None) -> "Person":
        author = self.define(author)
        email = self.define(email)

        if author == "Unknown":
            if email != "Unknown":
                logger.warning(
                    f"Author is 'Unknown' but email is not. Author: {author}, Email: {email}"
                    "Git should not allow this. Using 'Unknown' for both."
                )
            if "Unknown" in self:
                return self["Unknown"]
            else:
                person = Person("Unknown", "Unknown")
                self["Unknown"] = person
                return person
        elif email == "Unknown":
            person = self.add_author_with_unknown_email(author)
            return person
        else:
            # Both author and email are known
            p_author = self.get(author)
            p_email = self.get(email)

            if p_author is not None:
                if p_email is not None:
                    if p_author == p_email:
                        return p_author  # existing person
                    else:
                        return p_author.merge(p_email)  # merge persons
                else:
                    # author exists, email is new
                    p_author.merge(Person(author, email))
                    self[email] = p_author
                    return p_author
            else:
                if p_email is not None:
                    p_email.merge(Person(author, email))
                    self[author] = p_email
                    return p_email
                else:  # new person
                    person = Person(author, email)
                    self[author] = person
                    self[email] = person
                    return person

    def __repr__(self):
        return "\n".join(f"{key}:\n{repr(person)}" for key, person in self.items())

    def __str__(self):
        return "\n".join(str(person) for person in self.persons)

    @property
    def persons(self) -> list["Person"]:
        persons = self.values()
        persons_set = set(persons)
        return sorted(persons_set, key=lambda x: x.author)

    @property
    def authors(self) -> list[Author]:
        return [person.author for person in self.persons]

    @property
    def filtered_persons(self) -> list["Person"]:
        persons_set_filtered = {
            person for person in self.persons if not person.filter_matched
        }
        return sorted(persons_set_filtered, key=lambda x: x.author)

    @property
    def authors_included(self) -> list[Author]:
        return [person.author for person in self.persons if not person.filter_matched]

    @property
    def authors_excluded(self) -> list[Author]:
        return [person.author for person in self.persons if person.filter_matched]

    def add_author_with_unknown_email(self, author: Author) -> "Person":
        if author in self:
            return self[author]
        else:
            person = Person(author, "Unknown")
            self[author] = person
            return person

    def get_person(self, author: Author | None) -> "Person":
        defined_author: Author = "Unknown" if author is None else author
        return self[defined_author]

    def get_filtered_author(self, author: Author | None) -> Author | None:
        person = self.get_person(author)
        if person.filter_matched:
            return None
        else:
            return person.author

    # The final value of get_author is correct only after RepoBlame.run() has been
    # called.
    def get_author(self, author: Author | None) -> Author:
        """
        Return the main author name for the given author name, based on the person
        associated with the given author.
        """
        return self.get_person(author).author

    @staticmethod
    def define(ae: Author | Email | None) -> Author | Email:
        return "Unknown" if ae is None or ae == "" else ae


@dataclass
class OutputSingleLevel:
    header: list[str]
    data: list[Row]
