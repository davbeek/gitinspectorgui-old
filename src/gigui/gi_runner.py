import platform
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed, wait
from cProfile import Profile
from dataclasses import dataclass
from logging import getLogger
from logging.handlers import QueueListener
from multiprocessing.managers import SyncManager
from pathlib import Path
from queue import Queue

from gigui import _logging, shared
from gigui._logging import log, start_logging_listener
from gigui.args_settings import Args, MiniRepo
from gigui.constants import MAX_BROWSER_TABS, MAX_CORE_WORKERS
from gigui.gi_runner_base import GiRunnerBase
from gigui.output.messages import CLOSE_OUTPUT_VIEWERS_CLI_MSG, CLOSE_OUTPUT_VIEWERS_MSG
from gigui.repo_runner import RepoRunner, process_repo_multicore
from gigui.typedefs import FileStr
from gigui.utils import (
    get_dir_matches,
    log_analysis_end_time,
    log_end_time,
    out_profile,
)

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = getLogger(__name__)


@dataclass
class RepoTask:
    mini_repo: MiniRepo
    server_started_event: threading.Event
    worker_done_event: threading.Event


class GIRunner(GiRunnerBase):
    args: Args

    def __init__(
        self,
        args: Args,
        manager: SyncManager | None,
        host_port_queue: Queue | None,
        task_queue: Queue,
        logging_queue: Queue,
    ) -> None:
        super().__init__(args)
        self.manager: SyncManager | None = manager
        self.host_port_queue: Queue | None = host_port_queue
        self.task_queue: Queue = task_queue
        self.logging_queue: Queue = logging_queue

        self.server_started_events: list[threading.Event] = []
        self.worker_done_events: list[threading.Event] = []
        self.queue_listener: QueueListener | None = None

        self.requires_server: bool = not self.args.formats and self.args.view
        self.future_to_mini_repo: dict[Future, MiniRepo] = {}
        self.nr_workers: int = 0
        self.nr_started_prev: int = -1
        self.nr_done_prev: int = -1

    def run_repos(self, start_time: float) -> None:
        profiler: Profile | None = None
        repo_lists: list[list[MiniRepo]] = []
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
                self.logging_queue, self.args.verbosity
            )
            if self.requires_server:
                self.manage_tasks_multicore_with_servers(
                    repo_lists,
                    len_repos,
                    start_time,
                )
            else:
                self.process_repos_multicore(repo_lists, start_time)
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

    def process_repos_multicore(
        self, repo_lists: list[list[MiniRepo]], start_time: float
    ) -> None:
        with ProcessPoolExecutor(
            initializer=_logging.ini_worker_for_multiprocessing,
            initargs=(self.logging_queue, self.args.verbosity, shared.gui),
        ) as process_executor:
            future_to_mini_repo: dict[Future, MiniRepo] = {}
            for repos in repo_lists:
                repo_parent_str = str(repos[0].location.resolve().parent)
                log("Output in folder " + repo_parent_str)
                for mini_repo in repos:
                    server_started_event, worker_done_event = self.create_events()
                    future_to_mini_repo |= {
                        process_executor.submit(
                            process_repo_multicore,
                            mini_repo,
                            server_started_event,
                            worker_done_event,
                            self.host_port_queue,
                        ): mini_repo
                    }
            for future in as_completed(future_to_mini_repo):
                future.result()  # raise an exception if one occurred
            log_end_time(start_time)

    def manage_tasks_multicore_with_servers(
        self,
        repo_lists: list[list[MiniRepo]],
        len_repos: int,
        start_time: float,
    ) -> None:
        max_workers = min(MAX_CORE_WORKERS, len_repos)
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_logging.ini_worker_for_multiprocessing,
            initargs=(self.logging_queue, self.args.verbosity, shared.gui),
        ) as process_executor:
            for repos in repo_lists:
                len_repos = len(repos)
                repo_parent_str = str(repos[0].location.resolve().parent)
                log("Output in folder " + repo_parent_str)
                for mini_repo in repos:
                    server_started_event, worker_done_event = self.create_events()
                    future = process_executor.submit(
                        process_repo_multicore,
                        mini_repo,
                        server_started_event,
                        worker_done_event,
                        self.host_port_queue,
                    )
                    self.future_to_mini_repo[future] = mini_repo
                    self.nr_workers += 1
                    self.monitor_futures(start_time)

            # Ensure all futures are completed
            while self.nr_workers > 0:
                self.monitor_futures(start_time)

    def monitor_futures(self, start_time: float) -> None:
        done, _ = wait(
            self.future_to_mini_repo.keys(), timeout=0.1, return_when="FIRST_COMPLETED"
        )
        for future in done:
            future.result()
            self.nr_workers -= 1
            del self.future_to_mini_repo[future]

        nr_started = sum(event.is_set() for event in self.server_started_events)
        if nr_started != self.nr_started_prev:
            self.nr_started_prev = nr_started
            logger.info(
                f"Main: {nr_started} of {len(self.server_started_events)} "
                "server started events are set"
            )
            if nr_started == len(self.server_started_events):
                log_analysis_end_time(start_time)
                if shared.gui:
                    log(CLOSE_OUTPUT_VIEWERS_MSG)
                else:
                    log(CLOSE_OUTPUT_VIEWERS_CLI_MSG)
        nr_done = sum(event.is_set() for event in self.worker_done_events)
        if nr_done != self.nr_done_prev:
            self.nr_done_prev = nr_done
            logger.info(
                f"Main: {nr_done} of {len(self.worker_done_events)} "
                "server done events set"
            )

    def create_events(self) -> tuple[threading.Event, threading.Event]:
        if self.args.multicore:
            server_started_event = self.manager.Event()  # type: ignore
            self.server_started_events.append(server_started_event)
            worker_done_event = self.manager.Event()  # type: ignore
            self.worker_done_events.append(worker_done_event)
        else:
            server_started_event = threading.Event()
            worker_done_event = threading.Event()
        return server_started_event, worker_done_event

    def process_repos_singlecore(
        self,
        repo_lists: list[list[MiniRepo]],
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

        runs = 0
        count = 1
        while repo_lists:
            # output a batch of repos from the same folder in a single run
            repos = repo_lists.pop(0)
            prefix: str = "Output in folder" if self.args.formats else "Folder"
            log(prefix + str(repos[0].location.resolve().parent))
            for mini_repo in repos:
                log(" " * 4 + f"{mini_repo.name} repository ({count} of {len_repos})")
                server_started_event = threading.Event()  # type: ignore
                worker_done_event = threading.Event()  # type: ignore
                self.worker_done_events.append(worker_done_event)
                repo_runner = RepoRunner(
                    mini_repo,
                    server_started_event,
                    worker_done_event,
                    self.host_port_queue,
                )
                repo_runner.process_repo_single_core(
                    len_repos,
                    start_time,
                )
                count += 1
            runs += 1
        if self.requires_server:
            log_analysis_end_time(start_time)
            self.await_workers_done()
        else:
            log_end_time(start_time)

    def await_workers_done(self) -> None:
        nr_done: int = 0
        nr_done_prev: int = -1

        ctrl = "Command" if platform.system() == "Darwin" else "Ctrl"
        if shared.gui:
            log(
                f"To continue, close the GUI window, or browser tab(s) ({ctrl}+W) once the pages have fully loaded."
            )
        else:
            log(
                f"To continue, close the browser tab(s) ({ctrl}+W) once the pages have fully loaded. Use {ctrl}+C if necessary."
            )
        while True:
            nr_done = sum(event.is_set() for event in self.worker_done_events)
            if nr_done != nr_done_prev:
                nr_done_prev = nr_done
                logger.info(
                    f"Main: {nr_done} of {len(self.worker_done_events)} "
                    "server done events set"
                )
            if nr_done == len(self.worker_done_events):
                # all servers and their monitor threads are finishing
                break
            time.sleep(0.1)

    @staticmethod
    def total_len(repo_lists: list[list[MiniRepo]]) -> int:
        return sum(len(repo_list) for repo_list in repo_lists)


# Main function to run the analysis and create the output
def run_repos(
    args: Args,
    start_time: float,
    manager: SyncManager | None,
    host_port_queue: Queue | None,
    task_queue: Queue,
    logging_queue: Queue,
) -> None:
    GIRunner(args, manager, host_port_queue, task_queue, logging_queue).run_repos(
        start_time
    )


# Runs on a separate core, receives tasks one by one and executes each task by a
# repo_runner instance.
def worker(
    args: Args,
    host_port_queue: Queue,
    task_queue: Queue,
) -> None:
    repo_task: RepoTask
    mini_repo: MiniRepo
    stats_found: bool
    server_started_event: threading.Event
    worker_done_event: threading.Event

    global logger
    _logging.set_logging_level_from_verbosity(args.verbosity)
    logger = getLogger(__name__)

    while True:
        repo_task = task_queue.get()
        mini_repo = repo_task.mini_repo
        mini_repo.args = args

        server_started_event = repo_task.server_started_event
        worker_done_event = repo_task.worker_done_event

        repo_runner = RepoRunner(
            mini_repo,
            repo_task.server_started_event,
            repo_task.worker_done_event,
            host_port_queue,
        )

        log(" " * 4 + f"Start {mini_repo.name}")
        stats_found = repo_runner.run_analysis()
        if stats_found:
            repo_runner.generate_output()
        elif mini_repo.args.dry_run <= 1:
            log(
                " " * 8 + "No statistics matching filters found for "
                f"repository {mini_repo.name}"
            )
        # Do not use log or logger here, as the syncmanager may have been shut down here
        if server_started_event is not None:
            server_started_event.set()
            if worker_done_event is not None:
                worker_done_event.set()

        task_queue.task_done()
