import copy
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatchcase
from logging import getLogger
from pathlib import Path

from git import Commit as GitCommit
from git import Repo as GitRepo

from gigui._logging import log, log_dot, log_space
from gigui.args_settings import Args
from gigui.constants import GIT_LOG_CHUNK_SIZE, MAX_THREAD_WORKERS
from gigui.data import CommitGroup, IniRepo, PersonsDB, RepoStats
from gigui.keys import Keys
from gigui.typedefs import OID, SHA, Author, FileStr, Rev

logger = getLogger(__name__)


# SHAShortDate object is used to order and number commits by date, starting at 1 for the
# initial commit.
@dataclass
class SHADateNr:
    sha: SHA
    date: int
    nr: int


class RepoBase:
    def __init__(self, ini_repo: IniRepo):
        self.name: str = ini_repo.name
        self.location: Path = ini_repo.location
        self.args: Args = ini_repo.args

        # Here the values of the --ex-revision option are stored as a set.
        self.ex_revisions: set[Rev] = set(self.args.ex_revisions)

        self.persons_db: PersonsDB = PersonsDB()
        self.git_repo: GitRepo

        # self.fstrs is a list of files from the top commit of the repo.

        # Initially, the list is unfiltered and may still include files from authors
        # that are excluded later, because the blame run may find new authors that match
        # an excluded author and thus must be excluded later.

        # In self._run_no_history from RepoData, self.fstrs is sorted and all excluded
        # files are removed.
        self.fstrs: list[FileStr] = []

        # self.all_fstrs is the unfiltered list of files, may still include files that
        # belong completely to an excluded author.
        self.all_fstrs: list[FileStr]

        # List of the repo commits (shas) from date since to date until, sorted on
        # commit date. Merge commits are included.
        #
        # The list starts with the commit with the smallest date, which is the oldest
        # date, and which equals the since date or the first commit date. The newest
        # date is the until date or the head commit, and it is at the end of the list.
        #
        # Note that rename commits that do not change the file are not present in the
        # output of git log --follow --numstat and are therefore not present in
        # self.sha_date_nrs.
        self.sha_date_nrs: list[SHADateNr]

        # List of commit nrs from the commits in self.shas_date_nr.
        # These are the commits that fall in the date rage since to until.
        self.date_range_sha_nrs: list[int] = []

        # Dict of root_file to dict of the first sha, where the root_file or one of its
        # previous names was introduced, to this file name. This sha can either be the
        # initial sha or the sha where the file was renamed. The dict maps the sha to
        # the first introduction of the file name.
        self.fr2sha2f: dict[FileStr, dict[SHA, FileStr]] = {}
        self.fr2sha_nr2f: dict[FileStr, dict[int, FileStr]] = {}  # same for sha nrs

        # Dict of root_file to reverse sorted list of all sha nrs where the file was
        # renamed or first added.
        self.fr2sha_nrs: dict[FileStr, list[int]] = {}

        # Set of short SHAs of commits in the repo that are excluded by the
        # --ex-revision parameter together with the --ex-message parameter.
        self.ex_shas: set[SHA] = set()

        # Dict of file names to their sizes:
        self.fstr2line_count: dict[FileStr, int] = {}

        self.fstr2commit_groups: dict[FileStr, list[CommitGroup]] = {}
        self.stats = RepoStats()

        self.sha2author: dict[SHA, Author] = {}

        ###################################################
        # The following vars are to be set in init_git_repo
        ###################################################

        self.sha2oid: dict[SHA, OID] = {}
        self.oid2sha: dict[OID, SHA] = {}
        self.sha2nr: dict[SHA, int] = {}
        self.nr2sha: dict[int, SHA] = {}

        self.head_commit: GitCommit
        self.head_oid: OID
        self.head_sha: SHA

    def init_git_repo(self) -> None:
        # Init the git repo.
        # This function is called when processing is started. The repo is closed when
        # processing is finished to immediately when processing is finished to avoid
        # having too many files open.

        self.git_repo = GitRepo(self.location)

        # Use git log to get both long and short SHAs
        # First line represents the last commit
        log_output = self.git_repo.git.log("--pretty=format:%H %h")

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

        # Set head_commit to the top-level commit at the date given by self.args.until
        if self.args.until:
            commits = list(self.git_repo.iter_commits(until=self.args.until))
            if commits:
                self.head_commit = commits[0]
            else:
                self.head_commit = self.git_repo.head.commit
        else:
            self.head_commit = self.git_repo.head.commit

        self.head_oid = self.head_commit.hexsha
        self.head_sha = self.oid2sha[self.head_oid]

    def run_base(self) -> None:
        # Set list top level fstrs (based on until par and allowed file extensions)
        self.fstrs = self._get_worktree_files()

        self._set_fstr2line_count()
        self._get_commits_first_pass()

        self._set_fstr2commits()
        self.all_fstrs = copy.deepcopy(self.fstrs)
        self._set_fr2sha2f()
        self._set_fr2sha_nr2f()
        self._set_fr2sha_nrs()

    def _convert_to_timestamp(self, date_str: str) -> int:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())

    # Get list of top level files (based on the until parameter) that satisfy the
    # required extensions and do not match the exclude file patterns.
    # To get all files use --include-files="*" as pattern
    # include_files takes priority over n_files
    def _get_worktree_files(self) -> list[FileStr]:
        sorted_files: list[FileStr] = self._get_sorted_worktree_files()
        files_set: set[FileStr] = set(sorted_files)

        # dict from file to sort number
        file2nr: dict[FileStr, int] = {}
        for nr, file in enumerate(sorted_files):
            file2nr[file] = nr

        matches: list[FileStr]
        files: list[FileStr]
        if not self.args.include_files and not self.args.n_files == 0:
            return sorted_files[0 : self.args.n_files]
        else:
            # Return the n_files filtered files matching file pattern, sorted on file
            # size
            include_file_paths: list[Path] = [
                Path(self.args.subfolder) / fstr for fstr in self.args.include_files
            ]
            include_files: list[FileStr] = [str(path) for path in include_file_paths]
            matches = [
                blob.path  # type: ignore
                for blob in self.head_commit.tree.traverse()
                if (
                    blob.type == "blob"  # type: ignore
                    and any(
                        fnmatchcase(blob.path.lower(), pattern.lower())  # type: ignore
                        for pattern in include_files
                    )
                    and blob.path in files_set  # type: ignore
                )
            ]
            files = sorted(matches, key=lambda match: file2nr[match])
            if self.args.n_files == 0:
                return files
            else:
                return files[0 : self.args.n_files]

    # Get the files in the worktree, reverse sorted on file size that:
    # - match the required file extensions
    # - are not excluded
    # - are in args.subfolder
    def _get_sorted_worktree_files(self) -> list[FileStr]:
        # Get the files with their file sizes
        def _get_worktree_files_sizes() -> list[tuple[FileStr, int]]:
            # Get the blobs that are in subfolder
            def _get_subfolder_blobs() -> list:
                return [
                    blob
                    for blob in self.head_commit.tree.traverse()
                    if (
                        (blob.type == "blob")  # type: ignore
                        and fnmatchcase(
                            blob.path.lower(),  # type: ignore
                            f"{self.args.subfolder}*".lower(),  # type: ignore
                        )  # type: ignore
                    )
                ]

            blobs: list = _get_subfolder_blobs()
            if not blobs:
                log(" " * 8 + f"no files found in subfolder {self.args.subfolder}")
                return []
            return [
                (blob.path, blob.size)  # type: ignore
                for blob in blobs
                if (
                    # exclude files with incorrect extensions and those in ex_file
                    (
                        "*" in self.args.extensions
                        or (blob.path.split(".")[-1] in self.args.extensions)
                    )
                    and not self._matches_ex_file(blob.path)
                )
            ]

        sorted_files_sizes = sorted(
            _get_worktree_files_sizes(), key=lambda x: x[1], reverse=True
        )
        sorted_files = [file_size[0] for file_size in sorted_files_sizes]
        return sorted_files

    # Returns True if file should be excluded
    def _matches_ex_file(self, fstr: FileStr) -> bool:
        return any(
            fnmatchcase(fstr.lower(), pattern.lower()) for pattern in self.args.ex_files
        )

    def _get_biggest_files_from(self, matches: list[FileStr]) -> list[FileStr]:
        return matches

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
        sha_date_nrs: list[SHADateNr] = []
        ex_shas: set[SHA] = set()  # set of excluded shas
        sha: SHA
        oid: OID
        timestamp: int
        message: str
        author: Author
        email: str

        # %h: commit hash (short)
        # %ct: committer date, UNIX timestamp
        # %s: commit message
        # %aN: author name, respecting .mailmap
        # %aE: author email, respecting .mailmap
        # %n: newline
        args = self._get_since_until_args()
        args += [
            f"{self.head_oid}",
            "--pretty=format:%h%n%ct%n%s%n%aN%n%aE%n",
        ]
        lines_str: str = self.git_repo.git.log(*args)

        lines = lines_str.splitlines()
        i: int = 0
        while i < len(lines) - 4:
            line = lines[i]
            if not line:
                i += 1
                continue
            sha = line
            oid = self.sha2oid[sha]
            if any(oid.startswith(rev) for rev in self.ex_revisions):
                ex_shas.add(sha)
                i += 5
                continue
            timestamp = int(lines[i := i + 1])
            message = lines[i := i + 1]
            if any(
                fnmatchcase(message.lower(), pattern.lower())
                for pattern in self.args.ex_messages
            ):
                ex_shas.add(sha)
                i += 3
                continue
            author = lines[i := i + 1]
            email = lines[i := i + 1]
            self.persons_db.add_person(author, email)
            self.sha2author[sha] = author
            sha_date_nr = SHADateNr(sha, timestamp, self.sha2nr[sha])
            sha_date_nrs.append(sha_date_nr)
            i += 1

        sha_date_nrs.sort(key=lambda x: x.date)
        self.sha_date_nrs = sha_date_nrs
        self.date_range_sha_nrs = [sha_date_nr.nr for sha_date_nr in sha_date_nrs]
        self.ex_shas = ex_shas

    def _get_since_until_args(self) -> list[str]:
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

    def _set_fstr2commits(self) -> None:
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

        logger = getLogger(__name__)
        i_max: int = len(self.fstrs)
        i: int = 0
        chunk_size: int = GIT_LOG_CHUNK_SIZE
        prefix: str = " " * 8
        logger.info(
            prefix + f"Git log: {self.name}: {i_max} files"
        )  # Log message sent to QueueHandler
        if self.args.multithread:
            log_space(8)
            with ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as thread_executor:
                for chunk_start in range(0, i_max, chunk_size):
                    chunk_end = min(chunk_start + chunk_size, i_max)
                    chunk_fstrs = self.fstrs[chunk_start:chunk_end]
                    futures = [
                        thread_executor.submit(self._get_commit_lines_for, fstr)
                        for fstr in chunk_fstrs
                    ]
                    for future in as_completed(futures):
                        lines_str, fstr = future.result()
                        i += 1
                        if self.args.verbosity == 0:
                            log_dot(self.args.multicore)
                        else:
                            logger.info(
                                prefix
                                + f"log {i} of {i_max}: "
                                + (
                                    f"{self.name}: {fstr}"
                                    if self.args.multicore
                                    else f"{fstr}"
                                )
                            )
                        self.fstr2commit_groups[fstr] = self._process_commit_lines_for(
                            lines_str, fstr
                        )
        else:  # single thread
            log_space(8)
            for fstr in self.fstrs:
                lines_str, fstr = self._get_commit_lines_for(fstr)
                i += 1
                if self.args.verbosity == 0 and not self.args.multicore:
                    log_dot(self.args.multicore)
                else:
                    logger.info(prefix + f"{i} of {i_max}: {self.name} {fstr}")
                self.fstr2commit_groups[fstr] = self._process_commit_lines_for(
                    lines_str, fstr
                )
        log_space(2)
        reduce_commits()

    def _get_commit_lines_for(self, fstr: FileStr) -> tuple[str, FileStr]:
        # Note  that a rename commit that does not change the file is not shown in the
        # output of git log --follow --numstat.
        def git_log_args() -> list[str]:
            args = self._get_since_until_args()
            if not self.args.whitespace:
                args.append("-w")
            args += [
                # %h: short commit hash
                # %ct: committer date, UNIX timestamp
                # %aN: author name, respecting .mailmap
                # %n: newline
                f"{self.head_oid}",
                "--follow",
                "--numstat",  # insertions \t deletions \t file_name
                "--pretty=format:%n%h%n%ct%n%aN",
                # Avoid confusion between revisions and files, after "--" git treats all
                # arguments as files.
                "--",
                str(fstr),
            ]
            return args

        lines_str: str
        if self.args.multithread:
            git_repo = GitRepo(self.location)
            lines_str = git_repo.git.log(git_log_args())
            git_repo.close()
        else:
            lines_str = self.git_repo.git.log(git_log_args())
        return lines_str, fstr

    # pylint: disable=too-many-locals
    def _process_commit_lines_for(
        self, lines_str: str, fstr_root: FileStr
    ) -> list[CommitGroup]:
        commit_groups: list[CommitGroup] = []

        lines: list[str] = lines_str.strip().splitlines()
        rename_pattern = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")
        simple_rename_pattern = re.compile(r"^(.*) => (.*)$")

        # Possible rename of copy patterns are:
        # 1. gitinspector/{gitinspect_gui.py => gitinspector_gui.py}
        # 2. src/gigui/{ => gi}/gitinspector.py
        # 3. gitinspect_gui.py => gitinspector/gitinspect_gui.py

        sha: SHA
        timestamp: int
        author: Author
        stat_line: str

        i: int = 0
        while i < len(lines):
            line = lines[i]
            if not line:
                i += 1
                continue
            sha = line
            if sha in self.ex_shas:
                logger.info(f"Excluding commit {sha}")
                i += 4
                continue
            timestamp = int(lines[i := i + 1])
            author = lines[i := i + 1]
            person = self.persons_db[author]
            if not i + 1 < len(lines):
                # No stat line. This can happen eg when the only changes were in
                # whitespace
                break
            stat_line = lines[i := i + 1]
            if not stat_line:
                continue
            if person.filter_matched:
                i += 1
                continue
            parts = stat_line.split("\t")
            if not len(parts) == 3:
                logger.error(f"Error in stat line: {stat_line}")
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
                new_name = f"{prefix}{new_part}{suffix}".replace("//", "/")
                fstr = new_name
            else:
                match = simple_rename_pattern.match(file_name)
                if match:
                    fstr = match.group(2)
                else:
                    fstr = file_name
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
            i += 1
        return commit_groups

    def dynamic_blame_history_selected(self) -> bool:
        return self.args.view == Keys.dynamic_blame_history

    def _set_fr2sha2f(self) -> None:
        for fstr in self.all_fstrs:
            self.fr2sha2f[fstr] = self._get_sha2f_for_fstr(fstr)

    def _set_fr2sha_nr2f(self) -> None:
        for fstr in self.all_fstrs:
            if fstr not in self.fr2sha_nr2f:
                self.fr2sha_nr2f[fstr] = {}
            for sha, new_fstr in self.fr2sha2f[fstr].items():
                sha_nr = self.sha2nr[sha]
                self.fr2sha_nr2f[fstr][sha_nr] = new_fstr

    def _set_fr2sha_nrs(self) -> None:
        nrs: list[int]
        for fstr in self.all_fstrs:
            nrs = sorted(self.fr2sha_nr2f[fstr].keys(), reverse=True)
            self.fr2sha_nrs[fstr] = nrs

    def _get_sha2f_for_fstr(self, root_fstr: FileStr) -> dict[SHA, FileStr]:
        sha2f: dict[SHA, FileStr] = {}
        sha: SHA
        new_fstr: FileStr
        line: str
        i: int = 0

        lines: list[str] = self.git_repo.git.log(
            "--pretty=format:%h", "--follow", "--name-status", "--", root_fstr
        ).splitlines()

        while i < len(lines):
            line = lines[i]
            if not line:
                i += 1
                continue
            if i == len(lines) - 2:
                # get the last element, which is the addition of the file
                sha = line.strip()
                _, new_fstr = lines[i + 1].split("\t")
                sha2f[sha] = new_fstr.strip()
                break
            if "\t" not in line and lines[i + 1].startswith("R"):
                # get rename commit
                sha = line.strip()
                _, _, new_fstr = lines[i + 1].split("\t")
                sha2f[sha] = new_fstr.strip()
                i += 2
            else:
                i += 2
        return sha2f

    def get_fstr_for_sha(self, root_fstr: FileStr, sha: SHA) -> FileStr:  # type: ignore
        sha_nr: int = self.sha2nr[sha]
        nrs: list[int]
        nr: int

        nrs = sorted(self.fr2sha_nr2f[root_fstr].keys(), reverse=True)
        if not nrs:
            raise ValueError(f"No entries found for {root_fstr}.")
        for nr in nrs:
            if nr <= sha_nr:
                return self.fr2sha_nr2f[root_fstr][nr]
        # sha_nr smaller than the smallest sha nr in the list.
        return ""
