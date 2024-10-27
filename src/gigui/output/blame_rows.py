from typing import Counter

from gigui.args_settings import Args
from gigui.blame_reader import Blame
from gigui.data import PersonsDB
from gigui.repo import GIRepo
from gigui.typedefs import Author, FileStr, Row, SHALong


def header_blames() -> list[str]:
    return [
        "ID",
        "Author",
        "Date",
        "Message",
        "SHA",
        "Commit number",
        "Line",
        "Code",
    ]


class BlameBaseRows:
    args: Args

    def __init__(self, repo: GIRepo):
        self.repo: GIRepo = repo

        self.blame_authors: list[Author] = repo.blame_reader.blame_authors
        self.persons_db: PersonsDB = repo.repo_reader.persons_db

    def get_blame_rows(
        self, html: bool, blames: list[Blame]
    ) -> tuple[list[Row], list[bool]]:
        rows: list[Row] = []
        is_comments: list[bool] = []
        line_nr = 1

        author2nr: dict[Author, int] = {}
        author_nr = 1
        for author in self.blame_authors:
            if author in self.persons_db.authors_included:
                author2nr[author] = author_nr
                author_nr += 1
            else:
                author2nr[author] = 0

        # Create row for each blame line.
        for b in blames:
            author = self.persons_db.get_author(b.author)
            for line, is_comment in zip(b.lines, b.is_comment_lines):
                exclude_comment = is_comment and not self.args.comments
                exclude_empty = line.strip() == "" and not self.args.empty_lines
                exclude_author = author in self.persons_db.authors_excluded
                if (
                    self.args.blame_hide_exclusions
                    and not html
                    and (exclude_comment or exclude_empty or exclude_author)
                ):
                    line_nr += 1
                else:
                    row: Row = [
                        0 if exclude_comment or exclude_author else author2nr[author],
                        author,
                        b.date.strftime("%Y-%m-%d"),
                        b.message,
                        b.sha_long[:7],
                        b.commit_nr,
                        line_nr,
                        line,
                    ]
                    rows.append(row)
                    is_comments.append(is_comment)
                    line_nr += 1
        return rows, is_comments


class BlameRows(BlameBaseRows):
    def __init__(self, repo: GIRepo):
        super().__init__(repo)
        self.fstr2blames: dict[FileStr, list[Blame]] = repo.blame_reader.fstr2blames

    def get_fstr_blame_rows(
        self, fstr: FileStr, html: bool
    ) -> tuple[list[Row], list[bool]]:
        blames: list[Blame] = self.fstr2blames[fstr]
        return self.get_blame_rows(html, blames)


class BlameHistoryRows(BlameBaseRows):
    def __init__(self, repo: GIRepo):
        super().__init__(repo)

        self.fstr2sha2blames: dict[FileStr, dict[SHALong, list[Blame]]] = (
            repo.blame_history_reader.fstr2sha2blames
        )

    # pylint: disable=too-many-locals
    def get_fstr_sha_blame_rows(
        self, fstr: FileStr, sha: SHALong, html: bool
    ) -> tuple[list[Row], list[bool]]:
        blames: list[Blame] = self.fstr2sha2blames[fstr][sha]
        return self.get_blame_rows(html, blames)


def string2truncated(orgs: list[str], max_length: int) -> dict[str, str]:

    def get_trunc2digits(org2trunc: dict[str, str]) -> dict[str, int]:
        count: Counter[str] = Counter(org2trunc.values())

        # If truncated value is unique, it does not need to be numbered and its nr of
        # digit are 0. If it is not unique and occurs n times, then digits is the number
        # of digits in the string repr of n.
        digits: dict[str, int] = {}
        for org in org2trunc:
            if count[org2trunc[org]] == 1:
                digits[org] = 0
            else:
                digits[org] = len(str(count[org2trunc[org]]))
        return digits

    # Precondition: All values of org2trunc are already shortened to max_length - 2 for
    # ".." prefix.
    # Shorten all values of org2trunc so that they can be prefixed with ".." and
    # postfixed with a number "-n" to make them unique.
    def truncate(org2trunc: dict[str, str]) -> dict[str, str]:
        # Take Count for org2trunc values. For each item org, trunc in org2trunc, if
        # trunc has a count value > 1, shorten to the required length by removing the
        # necessary characters. If trunc has a count of 1, keep it as is.
        count: Counter[str] = Counter(org2trunc.values())
        trunc2digits: dict[str, int] = get_trunc2digits(org2trunc)
        result = {}
        for org in org2trunc:
            if count[org2trunc[org]] > 1:
                n_digits = trunc2digits[org]
                # n_digits for number and 3 for ".." prefix and "-" suffix:
                required_length = max_length - n_digits - 3
                reduce_by = len(org2trunc[org]) - required_length
                if reduce_by > 0:
                    result[org] = org2trunc[org][reduce_by:]
                else:
                    result[org] = org2trunc[org]
            else:
                result[org] = org2trunc[org]
        return result

    def number(org2trunc: dict[str, str]) -> dict[str, str]:
        # Add ".." prefix and "-n" suffix if necessary.
        # Number each duplicate in org2trunc.values() sequentially
        count: Counter[str] = Counter(org2trunc.values())
        seen2i: dict[str, int] = {}
        result = {}
        for org in org2trunc:
            if count[org2trunc[org]] > 1:
                if org2trunc[org] in seen2i:
                    seen2i[org2trunc[org]] += 1
                else:
                    seen2i[org2trunc[org]] = 1
                result[org] = f"..{org2trunc[org]}-{seen2i[org2trunc[org]]}"
            else:
                result[org] = f"..{org2trunc[org]}"
        return result

    org_short: list[str] = []
    org2trunc: dict[str, str] = {}

    # Add strings < max_length chars to org_short, truncate others to max_length - 2 by
    # removing chars from the beginning
    for org in orgs:
        if len(org) <= max_length:
            org_short.append(org)
        else:
            org2trunc[org] = org[(len(org) - max_length) + 2 :]

    new_org2trunc = truncate(org2trunc)
    while new_org2trunc != org2trunc:
        org2trunc = new_org2trunc
        new_org2trunc = truncate(org2trunc)

    # Add prefix and postfix to truncated strings.
    org2trunc = number(org2trunc)

    for trunc in org2trunc.values():
        assert len(trunc) == max_length

    # Add strings < max_length chars to org2trunc
    for org in org_short:
        org2trunc[org] = org

    missing = set(orgs) - set(org2trunc.keys())
    extra = set(org2trunc.keys()) - set(orgs)
    assert len(extra) == 0
    assert len(missing) == 0

    for trunc in org2trunc.values():
        assert len(trunc) <= max_length

    # # Visually check that numbering has been done correctly
    # numbered = {trunc for trunc in org2trunc.values() if trunc[-1].isdigit()}
    # numbered = sorted(numbered)
    # for trunc in numbered:
    #     print(trunc)

    return org2trunc
