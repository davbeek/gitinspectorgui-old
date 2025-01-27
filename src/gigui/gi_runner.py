import multiprocessing
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from cProfile import Profile
from logging import getLogger
from logging.handlers import QueueListener
from multiprocessing.managers import SyncManager
from pathlib import Path
from queue import Queue

import gigui.repo_runner as repo_runner
from gigui import _logging, shared
from gigui._logging import log, start_logging_listener
from gigui.args_settings import Args, MiniRepo
from gigui.constants import DYNAMIC, MAX_BROWSER_TABS
from gigui.gi_runner_base import GiRunnerBase
from gigui.repo_runner import RepoRunner
from gigui.typedefs import FileStr
from gigui.utils import get_dir_matches, log_analysis_end_time, out_profile

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = getLogger(__name__)


class GIRunner(GiRunnerBase):
    args: Args

    def __init__(
        self,
        args: Args,
        manager: SyncManager | None,
        host_port_queue: Queue | None,
        logging_queue: Queue,
    ) -> None:
        super().__init__(args)
        self.manager: SyncManager | None = manager
        self.host_port_queue: Queue | None = host_port_queue
        self.logging_queue: Queue = logging_queue

        self.server_started_events: list[threading.Event] = []
        self.worker_done_events: list[threading.Event] = []
        self.host_port_queue: Queue | None
        self.logging_queue: Queue
        self.queue_listener: QueueListener | None = None

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
            self.process_repos_multicore(
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

        log("Done")
        out_profile(profiler, self.args.profile)

    # Process multiple repositories in case len(repos) > 1 on multiple cores.
    def process_repos_multicore(
        self,
        repo_lists: list[list[MiniRepo]],
        len_repos: int,
        start_time: float,
    ) -> None:
        max_workers = (
            multiprocessing.cpu_count()
            if not self.args.blame_history == DYNAMIC
            else min(len_repos, MAX_BROWSER_TABS)
        )
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_logging.ini_worker_for_multiprocessing,
            initargs=(self.logging_queue, self.args.verbosity, shared.gui),
        ) as process_executor:
            future_to_mini_repo: dict[Future, MiniRepo] = {}
            for repos in repo_lists:
                len_repos = len(repos)
                repo_parent_str = str(repos[0].location.resolve().parent)
                log("Output in folder " + repo_parent_str)
                for mini_repo in repos:
                    server_started_event, worker_done_event = self.create_events()
                    future_to_mini_repo |= {
                        process_executor.submit(
                            repo_runner.process_repo_multicore,
                            mini_repo,
                            server_started_event,
                            worker_done_event,
                            self.host_port_queue,
                        ): mini_repo
                    }

            if not self.args.formats and self.args.view:
                self.await_all_servers_started()
                log_analysis_end_time(start_time)
                self.stop_and_await_workers_done()

            # Show the full exception trace if an exception occurred in
            # repo_runner.process_repo_multicore
            for future in as_completed(future_to_mini_repo):
                future.result()  # only purpose is to raise an exception if one occurred

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

    def await_all_servers_started(self) -> None:
        servers_started: bool = False
        nr_started: int = 0
        nr_started_prev: int = -1
        while not servers_started:
            nr_started = sum(event.is_set() for event in self.server_started_events)
            if nr_started != nr_started_prev:
                nr_started_prev = nr_started
                logger.info(
                    f"Main: {nr_started} of {len(self.server_started_events)} "
                    "server started events are set"
                )
            if nr_started == len(self.server_started_events):
                break
            time.sleep(1)

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

        count = 1
        runs = 0
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
        if not self.args.formats and self.args.view:
            self.stop_and_await_workers_done()

    def stop_and_await_workers_done(self) -> None:
        nr_done: int = 0
        nr_done_prev: int = -1

        log("Close browser tabs to continue")
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
    logging_queue: Queue,
) -> None:
    GIRunner(args, manager, host_port_queue, logging_queue).run_repos(start_time)
