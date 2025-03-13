import select
import sys
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from cProfile import Profile
from logging import getLogger
from logging.handlers import QueueListener
from multiprocessing.synchronize import Event as multiprocessingEvent
from pathlib import Path
from queue import Queue

from gigui import _logging, shared
from gigui._logging import log, start_logging_listener
from gigui.args_settings import Args
from gigui.constants import AUTO, DYNAMIC_BLAME_HISTORY, MAX_CORE_WORKERS
from gigui.data import IniRepo
from gigui.gi_runner_base import GiRunnerBase
from gigui.messages import CLOSE_OUTPUT_VIEWERS_MSG
from gigui.output.repo_html_server import HTMLServer, require_server
from gigui.queues_events import RunnerQueues
from gigui.repo_runner import RepoRunner
from gigui.typedefs import FileStr
from gigui.utils import (
    get_dir_matches,
    log_end_time,
    open_file,
    out_profile,
    setup_sigint_handler,
)

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = getLogger(__name__)


class GIRunner(GiRunnerBase):
    args: Args

    def __init__(
        self,
        args: Args,
        start_time: float,
        queues: RunnerQueues,
        logging_queue: Queue,
        sigint_event: multiprocessingEvent | threading.Event,
        html_server: HTMLServer | None = None,
    ) -> None:
        GiRunnerBase.__init__(self, args)
        self.queues: RunnerQueues = queues
        self.logging_queue: Queue = logging_queue
        self.sigint_event: multiprocessingEvent | threading.Event = sigint_event
        self.html_server: HTMLServer | None = html_server
        if self.html_server:
            self.html_server.set_runner_queues(queues)

        self.start_time: float = start_time
        self.queue_listener: QueueListener | None = None
        self.future_to_ini_repo: dict[Future, IniRepo] = {}
        self.nr_workers: int = 0
        self.nr_started_prev: int = -1
        self.nr_done_prev: int = -1

        if self.args.view == DYNAMIC_BLAME_HISTORY and self.args.multicore:
            log(
                "Dynamic blame history is not supported in multicore mode. "
                "Executing in single core mode."
            )
            self.args.multicore = False

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
        if self.html_server:
            self.html_server.len_repos = self.len_repos

        if self.len_repos == 0:
            logger.warning("No repositories found, exiting.")
            return

        if not self._check_options(self.len_repos):
            return

        if self.args.multicore:
            self.queue_listener = start_logging_listener(
                self.logging_queue, self.args.verbosity
            )
            self.process_tasks_multicore(repo_lists)
            if self.queue_listener:
                self.queue_listener.stop()
        else:  # single core
            self.process_repos_singlecore(repo_lists)

        if require_server(self.args):
            log("Done")
        out_profile(profiler, self.args.profile)

    def process_tasks_multicore(
        self,
        repo_lists: list[list[IniRepo]],
    ) -> None:
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
            initargs=(self.logging_queue, shared.gui),
        ) as process_executor:
            for _ in range(self.len_repos):
                future = process_executor.submit(
                    multicore_worker,
                    self.queues,
                    self.args.verbosity,
                )
                futures.append(future)

            if self.args.dryrun == 0:
                self.await_tasks_process_output()

            for future in as_completed(futures):
                logger.debug("future done:", future.result())

    def await_tasks_process_output(self) -> None:
        i: int = 0
        browser_output: bool = False
        repo_name: str = ""
        while i < self.len_repos:
            repo_name = self.queues.task_done.get()
            i += 1
            if self.len_repos > 1:
                logger.info(f"    {repo_name}: analysis done {i} of {self.len_repos}")
        log_end_time(self.start_time)

        i = 0
        if self.args.view == AUTO and self.args.file_formats:
            while i < self.len_repos:
                i += 1
                repo_name, out_file_name = self.queues.open_file.get()
                if out_file_name is None:
                    logger.info(
                        f"{repo_name}:    no output:"
                        + (f" {i} of {self.len_repos}" if self.len_repos > 1 else "")
                    )
                    continue
                open_file(out_file_name)
                logger.info(
                    f"{repo_name}:    {out_file_name}: output done "
                    + (f" {i} of {self.len_repos}" if self.len_repos > 1 else "")
                )
        elif require_server(self.args) and not shared.gui:
            # CLI
            assert self.html_server is not None
            self.html_server.start_server()
            self.html_server.start_monitor()
            if self.args.view == AUTO and not self.args.file_formats:
                self.html_server.set_localhost_data()
                for i, data in enumerate(self.html_server.id2host_data.values()):
                    if data.html_doc:
                        browser_output = True
                        self.html_server.open_new_tab(
                            data.name,
                            data.browser_id,
                            data.html_doc,
                            i + 1,
                        )
            elif self.args.view == DYNAMIC_BLAME_HISTORY:
                self.html_server.set_localhost_repo_data()
                for i, data in enumerate(self.html_server.id2host_repo_data.values()):
                    if data.html_doc:
                        browser_output = True
                        self.html_server.open_new_tab(
                            data.name,
                            data.browser_id,
                            data.html_doc,
                            i + 1,
                        )
            if browser_output:
                log(CLOSE_OUTPUT_VIEWERS_MSG)
                while True:
                    if self.html_server.events.server_shutdown_done.is_set():
                        break
                    if select.select([sys.stdin], [], [], 1)[0]:
                        input()
                        self.html_server.send_shutdown_request()
                        self.html_server.events.server_shutdown_done.wait()
                        break
                    time.sleep(0.1)
            else:
                self.html_server.send_shutdown_request()
                self.html_server.events.server_shutdown_done.wait()
        elif require_server(self.args) and shared.gui:
            # GUI
            assert self.html_server is not None
            if not self.html_server.server:
                self.html_server.start_server()
            if self.args.view == AUTO and not self.args.file_formats:
                self.html_server.set_localhost_data()
            elif self.args.view == DYNAMIC_BLAME_HISTORY:
                self.html_server.set_localhost_repo_data()
            self.html_server.gui_open_new_tabs()

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
        if self.args.dryrun == 0:
            self.await_tasks_process_output()

    @staticmethod
    def total_len(repo_lists: list[list[IniRepo]]) -> int:
        return sum(len(repo_list) for repo_list in repo_lists)


# Main function to run the analysis and create the output
def start_gi_runner(
    args: Args,
    start_time: float,
    queues: RunnerQueues,
    logging_queue: Queue,
    sigint_event: multiprocessingEvent | threading.Event,
    html_server: HTMLServer | None = None,
) -> None:
    setup_sigint_handler(sigint_event)
    GIRunner(args, start_time, queues, logging_queue, sigint_event, html_server)


# Runs on a separate core, receives tasks one by one and executes each task by a
# repo_runner instance.
def multicore_worker(
    queues: RunnerQueues,
    verbosity: int,
) -> str:
    ini_repo: IniRepo
    repo_name: str = "unknown"

    global logger
    try:
        _logging.set_logging_level_from_verbosity(verbosity)
        logger = getLogger(__name__)

        # Take into account that the SyncManager can be shut down in the main process,
        # which will cause subsequent logging to fail.
        while True:
            ini_repo = queues.task.get()
            repo_name = ini_repo.name
            repo_runner = RepoRunner(ini_repo, queues)
            repo_runner.process_repo()
            queues.task.task_done()
            return ini_repo.name
    except Exception as e:
        logger.error(f"Exception for repo {repo_name}:")
        logger.exception(e)
        return repo_name
