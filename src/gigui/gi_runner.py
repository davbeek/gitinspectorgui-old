import threading
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from cProfile import Profile
from dataclasses import dataclass
from logging import getLogger
from logging.handlers import QueueListener
from pathlib import Path

from gigui import _logging, shared
from gigui._logging import log, start_logging_listener
from gigui.args_settings import Args
from gigui.constants import MAX_CORE_WORKERS
from gigui.data import IniRepo, RunnerQueues
from gigui.gi_runner_base import GiRunnerBase
from gigui.messages import CLOSE_OUTPUT_VIEWERS_CLI_MSG, CLOSE_OUTPUT_VIEWERS_MSG
from gigui.repo_runner import RepoRunner
from gigui.typedefs import FileStr
from gigui.utils import get_dir_matches, log_end_time, out_profile

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = getLogger(__name__)


@dataclass
class RepoTask:
    ini_repo: IniRepo
    server_started_event: threading.Event
    worker_done_event: threading.Event


class GIRunner(GiRunnerBase):
    args: Args

    def __init__(
        self,
        args: Args,
        runner_queues: RunnerQueues,
    ) -> None:
        super().__init__(args)
        self.queues: RunnerQueues = runner_queues

        self.queue_listener: QueueListener | None = None

        self.requires_server: bool = not self.args.formats and self.args.view
        self.future_to_ini_repo: dict[Future, IniRepo] = {}
        self.nr_workers: int = 0
        self.nr_started_prev: int = -1
        self.nr_done_prev: int = -1

    def run_repos(self, start_time: float) -> None:
        profiler: Profile | None = None
        repo_lists: list[list[IniRepo]] = []
        len_repos: int = 0
        dir_strs: list[FileStr]
        dirs_sorted: list[FileStr]

        self._set_options()

        dir_strs = get_dir_matches(self.args.input_fstrs)
        dirs_sorted = sorted(dir_strs)
        for dir_str in dirs_sorted:
            repo_lists.extend(self.get_repos(Path(dir_str), self.args.depth))
        len_repos = self.total_len(repo_lists)

        if len_repos == 0:
            logger.warning("No repositories found, exiting.")
            return

        if not self._check_options(len_repos):
            return

        if self.args.multicore:
            self.queue_listener = start_logging_listener(
                self.queues.logging, self.args.verbosity
            )
            self.process_tasks_multicore(
                repo_lists,
                len_repos,
                start_time,
            )
            if self.queue_listener:
                self.queue_listener.stop()
        else:  # single core
            self.process_repos_singlecore(
                repo_lists,
                len_repos,
                start_time,
            )

        if self.requires_server:
            log("Done")
        out_profile(profiler, self.args.profile)

    def process_tasks_multicore(
        self,
        repo_lists: list[list[IniRepo]],
        len_repos: int,
        start_time: float,
    ) -> None:
        i: int = 0
        futures: list[Future] = []
        max_workers: int = min(MAX_CORE_WORKERS, len_repos)

        for repos in repo_lists:
            repo_parent_str = str(repos[0].location.resolve().parent)
            log("Output in folder " + repo_parent_str)
            for ini_repo in repos:
                i += 1
                self.queues.task.put(ini_repo)
                self.queues.task_done_nr.put(i)
                self.queues.repo_done_nr.put(i)

        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_logging.ini_worker_for_multiprocessing,
            initargs=(self.queues.logging, self.args.verbosity, shared.gui),
        ) as process_executor:
            for _ in range(max_workers):
                future = process_executor.submit(
                    multicore_worker,
                    self.queues,
                    len_repos,
                    self.args.verbosity,
                    start_time,
                )
                futures.append(future)

            if self.requires_server:
                self.queues.task_done_nr.join()
                if shared.gui:
                    log(CLOSE_OUTPUT_VIEWERS_MSG)
                else:
                    log(CLOSE_OUTPUT_VIEWERS_CLI_MSG)
                self.queues.repo_done_nr.join()

            for _ in range(max_workers):
                self.queues.task.put(None)  # type: ignore # signal to stop worker

            for future in as_completed(futures):
                future.result()

    def process_repos_singlecore(
        self,
        repo_lists: list[list[IniRepo]],
        len_repos: int,
        start_time: float,
    ) -> None:
        """Processes repositories on a single core.

        Outputs repositories in batches, where each batch contains repositories
        from a single folder.

        Args:
            args: Command-line arguments.
            repo_lists: List of lists of repositories to process.
            len_repos: Total number of repositories.
            outfile_base: Base name for output files.
            gui_window: GUI window instance, if any.
            start_time: Start time of the process.
            shared_data: Shared data dictionary for inter-process communication.
        """
        i = 0
        while repo_lists:
            # output a batch of repos from the same folder in a single run
            repos = repo_lists.pop(0)
            repo_parent_str = str(repos[0].location.resolve().parent)
            log(
                "Output in folder "
                if self.args.formats
                else "Folder " + repo_parent_str
            )
            for ini_repo in repos:
                repo_runner = RepoRunner(
                    ini_repo,
                    self.queues,
                    len_repos,
                )
                i += 1
                self.queues.task_done_nr.put(i)
                self.queues.repo_done_nr.put(i)
                repo_runner.process_repo(
                    len_repos,
                    start_time,
                )

        if self.requires_server:
            self.queues.task_done_nr.join()
            if shared.gui:
                log(CLOSE_OUTPUT_VIEWERS_MSG)
            else:
                log(CLOSE_OUTPUT_VIEWERS_CLI_MSG)
            self.queues.repo_done_nr.join()
        else:
            log_end_time(start_time)

    @staticmethod
    def total_len(repo_lists: list[list[IniRepo]]) -> int:
        return sum(len(repo_list) for repo_list in repo_lists)


# Main function to run the analysis and create the output
def start_gi_runner(
    args: Args,
    start_time: float,
    runner_queues: RunnerQueues,
) -> None:
    GIRunner(args, runner_queues).run_repos(start_time)


# Runs on a separate core, receives tasks one by one and executes each task by a
# repo_runner instance.
def multicore_worker(
    runner_queues: RunnerQueues, len_repos: int, verbosity: int, start_time: float
) -> None:
    ini_repo: IniRepo
    repo_runners: list[RepoRunner] = []

    global logger
    _logging.set_logging_level_from_verbosity(verbosity)
    logger = getLogger(__name__)

    # Take into account the SyncManager be shut down in the main process.
    # which will cause logging to fail.
    while True:
        ini_repo = runner_queues.task.get()
        if ini_repo is None:
            break
        repo_runner = RepoRunner(ini_repo, runner_queues, len_repos)
        repo_runners.append(repo_runner)
        repo_runner.process_repo(len_repos, start_time)

        runner_queues.task.task_done()
