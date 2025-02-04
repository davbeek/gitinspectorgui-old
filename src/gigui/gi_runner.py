import signal
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from cProfile import Profile
from dataclasses import dataclass
from logging import getLogger
from logging.handlers import QueueListener
from pathlib import Path
from queue import Queue

from gigui import _logging, shared
from gigui._logging import log, start_logging_listener
from gigui.args_settings import Args
from gigui.constants import MAX_CORE_WORKERS, NONE
from gigui.data import IniRepo
from gigui.gi_runner_base import GiRunnerBase
from gigui.messages import CLOSE_OUTPUT_VIEWERS_CLI_MSG, CLOSE_OUTPUT_VIEWERS_MSG
from gigui.queues_setup import RunnerQueues
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
        start_time: float,
        runner_queues: RunnerQueues,
    ) -> None:
        super().__init__(args)
        self.queues: RunnerQueues = runner_queues
        self.start_time: float = start_time

        self.queue_listener: QueueListener | None = None

        self.requires_server: bool = (
            not self.args.file_formats and not self.args.view == NONE
        )
        self.future_to_ini_repo: dict[Future, IniRepo] = {}
        self.nr_workers: int = 0
        self.nr_started_prev: int = -1
        self.nr_done_prev: int = -1
        self.len_repos: int = 0

    def run_repos(self) -> None:
        profiler: Profile | None = None
        repo_lists: list[list[IniRepo]] = []
        dir_strs: list[FileStr]
        dirs_sorted: list[FileStr]

        self._set_options()

        dir_strs = get_dir_matches(self.args.input_fstrs)
        dirs_sorted = sorted(dir_strs)
        for dir_str in dirs_sorted:
            repo_lists.extend(self.get_repos(Path(dir_str), self.args.depth))
        self.len_repos = self.total_len(repo_lists)

        if self.len_repos == 0:
            logger.warning("No repositories found, exiting.")
            return

        if not self._check_options(self.len_repos):
            return

        if self.args.multicore:
            self.queue_listener = start_logging_listener(
                self.queues.logging, self.args.verbosity
            )
            self.process_tasks_multicore(repo_lists)
            if self.queue_listener:
                self.queue_listener.stop()
        else:  # single core
            self.process_repos_singlecore(repo_lists)

        if self.requires_server:
            log("Done")
        out_profile(profiler, self.args.profile)

    def process_tasks_multicore(
        self,
        repo_lists: list[list[IniRepo]],
    ) -> None:
        nr_workers: int = 0
        futures: list[Future] = []
        max_workers: int = min(MAX_CORE_WORKERS, self.len_repos)

        for repos in repo_lists:
            repo_parent_str = str(repos[0].location.resolve().parent)
            log("Output in folder " + repo_parent_str)
            for ini_repo in repos:
                self.queues.task.put(ini_repo)

        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_logging.ini_worker_for_multiprocessing,
            initargs=(self.queues.logging, self.args.verbosity, shared.gui),
        ) as process_executor:
            for i in range(max_workers):
                future = process_executor.submit(
                    multicore_worker, self.queues, self.args.verbosity, i
                )
                futures.append(future)
                nr_workers += 1

            for _ in range(nr_workers):
                self.queues.task.put(None)  # type: ignore

            self.await_tasks()

            for _ in range(max_workers):
                # signal to stop worker by sending None
                self.queues.task.put(None)  # type: ignore

            for future in as_completed(futures):
                future.result()

    def await_tasks(self) -> None:
        task_done_nr: int = 0
        repo_name: str = ""
        repo_done_nr: int = 0

        while task_done_nr < self.len_repos:
            repo_name = self.queues.task_done.get()
            task_done_nr += 1
            if self.len_repos > 1:
                logger.info(f"    {repo_name}: done {task_done_nr} of {self.len_repos}")
        log_end_time(self.start_time)

        if self.requires_server:
            time.sleep(0.1)  # wait for the server to start
            if shared.gui:
                log(CLOSE_OUTPUT_VIEWERS_MSG)
            else:
                log(CLOSE_OUTPUT_VIEWERS_CLI_MSG)

        repo_name = ""
        while repo_done_nr < self.len_repos:
            repo_name = self.queues.repo_done.get()
            repo_done_nr += 1
            if self.requires_server:
                logger.info(
                    f"    {repo_name}: server shutdown"
                    + (
                        f" {repo_done_nr} of {self.len_repos}"
                        if self.len_repos > 1
                        else ""
                    )
                )

    def process_repos_singlecore(
        self,
        repo_lists: list[list[IniRepo]],
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
        repo_runners: list[RepoRunner] = []
        while repo_lists:
            # output a batch of repos from the same folder in a single run
            repos = repo_lists.pop(0)
            repo_parent_str = str(repos[0].location.resolve().parent)
            log(
                ("Output in folder " if self.args.file_formats else "Folder ")
                + repo_parent_str
            )
            for ini_repo in repos:
                repo_runner = RepoRunner(
                    ini_repo,
                    self.queues,
                )
                repo_runners.append(repo_runner)
                repo_runner.process_repo()

            self.await_tasks()

        for repo_runner in repo_runners:
            repo_runner.join_threads()

    @staticmethod
    def total_len(repo_lists: list[list[IniRepo]]) -> int:
        return sum(len(repo_list) for repo_list in repo_lists)


def shutdown_handler_main_multi_core(
    signum, frame  # pylint: disable=unused-argument
) -> None:
    pass


def shutdown_handler_main(
    signum, frame, shutdown_all: Queue[None]  # pylint: disable=unused-argument
) -> None:
    shutdown_all.put(None)  # Only used for single core


# Main function to run the analysis and create the output
def start_gi_runner(
    args: Args,
    start_time: float,
    runner_queues: RunnerQueues,
) -> None:
    if args.multicore:
        signal.signal(signal.SIGINT, shutdown_handler_main_multi_core)
        signal.signal(signal.SIGTERM, shutdown_handler_main_multi_core)
    else:  # single core
        signal.signal(
            signal.SIGINT,
            lambda signum, frame: shutdown_handler_main(
                signum,
                frame,
                runner_queues.shutdown_all,
            ),
        )
        signal.signal(
            signal.SIGTERM,
            lambda signum, frame: shutdown_handler_main(
                signum,
                frame,
                runner_queues.shutdown_all,
            ),
        )
    GIRunner(args, start_time, runner_queues).run_repos()


def shutdown_handler_worker(
    signum, frame, shutdown_all: Queue[None], nr: int  # pylint: disable=unused-argument
) -> None:
    if nr == 0:
        shutdown_all.put(None)  # Only used for multicore


# Runs on a separate core, receives tasks one by one and executes each task by a
# repo_runner instance.
def multicore_worker(runner_queues: RunnerQueues, verbosity: int, nr: int) -> None:
    ini_repo: IniRepo
    repo_runners: list[RepoRunner] = []

    global logger
    _logging.set_logging_level_from_verbosity(verbosity)
    logger = getLogger(__name__)

    signal.signal(
        signal.SIGINT,
        lambda signum, frame: shutdown_handler_worker(
            signum,
            frame,
            runner_queues.shutdown_all,
            nr,
        ),
    )
    signal.signal(
        signal.SIGTERM,
        lambda signum, frame: shutdown_handler_worker(
            signum,
            frame,
            runner_queues.shutdown_all,
            nr,
        ),
    )

    # Take into account that the SyncManager can be shut down in the main process,
    # which will cause subsequent logging to fail.
    while True:
        ini_repo = runner_queues.task.get()
        if ini_repo is None:
            break
        repo_runner = RepoRunner(ini_repo, runner_queues)
        repo_runners.append(repo_runner)
        repo_runner.process_repo()
        runner_queues.task.task_done()

    for repo_runner in repo_runners:
        repo_runner.join_threads()
