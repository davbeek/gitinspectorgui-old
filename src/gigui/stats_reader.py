import copy
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from git import Commit as GitCommit
from git import PathLike, Repo

from gigui.args_settings_keys import Args
from gigui.blame import BlameReader, Commit
from gigui.data import MultiCommit, Person, PersonsDB, RepoStats
from gigui.typedefs import Author, FileStr, Rev, SHAlong, SHAshort

logger = logging.getLogger(__name__)


class StatsReader:
    args: Args

    # Here the values of the --ex-revision parameter are stored as a set.
    ex_revs: set[Rev] = set()

    def __init__(self, name: str, location: PathLike):
        self.name: str = name

        # The default True value of expand_vars can lead to confusing warnings from
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
        self.persons_db: PersonsDB = PersonsDB()

        self.thread_executor: ThreadPoolExecutor
        self.blame_reader: BlameReader

    @property
    def git(self):
        return self.gitrepo.git

    def run(self, thread_executor: ThreadPoolExecutor):
        self._set_head_commit()

        # Set list top level fstrs (based on until par and allowed file extensions)
        self.fstrs = self._get_worktree_files()

        self._set_fstr2lines()
        self._get_commits_first_pass()

        # print(f"{"    Calc commit for":22}{self.gitrepo.working_dir}")
        self._set_fstr2commits(thread_executor)

    def get_person(self, author: Author | None) -> Person:
        return self.persons_db.get_person(author)

    # Get list of top level files (based on the until parameter) that satisfy the
    # required extensions and do not match the exclude file patterns.
    # To get all files use --include-file=".*" as pattern
    # include_files takes priority over n_files
    def _get_worktree_files(self) -> list[FileStr]:

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
                        and (
                            (
                                blob.path.split(".")[-1]  # type: ignore
                                in self.args.extensions
                            )
                        )
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

        matches: list[FileStr]
        if not include_files:
            matches = get_biggest_worktree_files(show_n_files)
        else:  # Get files matching file pattern
            matches = [
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

    def _set_head_commit(self) -> None:
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

    def _set_fstr2lines(self) -> None:
        self.fstr2lines["*"] = 0
        for blob in self.head_commit.tree.traverse():
            if (
                blob.type == "blob"  # type: ignore
                and blob.path in self.fstrs  # type: ignore
                and blob.path not in self.fstr2lines  # type: ignore
            ):
                # number of lines in blob
                line_count: int = len(
                    blob.data_stream.read().decode("utf-8").split("\n")  # type: ignore
                )
                self.fstr2lines[blob.path] = line_count  # type: ignore
                self.fstr2lines["*"] += line_count

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

    def _get_commits_first_pass(self) -> None:
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
        args = self._get_since_until_args()
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
            self.persons_db.add_person(author, email)
            commit = Commit(sha_short, sha_long, timestamp)
            commits.append(commit)
            self.sha2commit[sha_short] = commit
            self.sha2commit[sha_long] = commit

        commits.sort(key=lambda x: x.date)
        self.commits = commits
        self.ex_sha_shorts = ex_sha_shorts

    def _get_commit_lines_for(self, fstr: FileStr) -> tuple[str, FileStr]:
        def git_log_args() -> list[str]:
            args = self._get_since_until_args()
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

    # pylint: disable=too-many-locals
    def _process_commit_lines_for(self, lines_str: str) -> list[MultiCommit]:
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
                # if no renames or copies have been found, the line represents the file
                # name fstr
                fstr = line
            elif "{" in line:
                # If { is in the line, it is part of a {...} abbreviation in a rename or
                # copy expression. This means that the file has been renamed or copied
                # to a new name. Set fstr to this new name.
                #
                # To find the new name, the {...} abbreviation part of the line needs to
                # be eliminated. Examples of such lines are:
                #
                # 1. gitinspector/{gitinspect_gui.py => gitinspector_gui.py}
                # 2. src/gigui/{ => gi}/gitinspector.py

                prefix, rest = line.split("{")

                # _ is old_part
                _, rest = rest.split(" => ")

                new_part, suffix = rest.split("}")

                # prev_name = f"{prefix}{old_part}{suffix}"
                new_name = f"{prefix}{new_part}{suffix}"

                # src/gigui/{ => gi}/gitinspector.py leads to:
                # src/gigui//gitinspector.py => src/gigui/gi/gitinspector.py

                # prev_name = prev_name.replace("//", "/")
                # new_name = new_name.replace("//", "/")
                fstr = new_name.replace("//", "/")
            else:
                # gitinspect_gui.py => gitinspector/gitinspect_gui.py

                split = line.split(" => ")

                # prev_name = split[0]
                # new_name = split[1]
                fstr = split[1]

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

    def _set_fstr2commits(self, thread_executor: ThreadPoolExecutor):
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
                thread_executor.submit(self._get_commit_lines_for, fstr)
                for fstr in self.fstrs
            ]
            for future in as_completed(futures):
                lines_str, fstr = future.result()
                self.fstr2mcommits[fstr] = self._process_commit_lines_for(lines_str)
        else:  # single thread
            for fstr in self.fstrs:
                lines_str, fstr = self._get_commit_lines_for(fstr)
                self.fstr2mcommits[fstr] = self._process_commit_lines_for(lines_str)
        reduce_commits()

    @classmethod
    def set_args(cls, args: Args):
        cls.args = args
        cls.ex_revs = set(args.ex_revisions)
