import signal
import threading
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from cProfile import Profile
from logging import getLogger
from logging.handlers import QueueListener
from pathlib import Path
from queue import Queue

from gigui import _logging, shared
from gigui._logging import log, start_logging_listener
from gigui.args_settings import Args
from gigui.constants import AUTO, DYNAMIC_BLAME_HISTORY, MAX_CORE_WORKERS, NONE
from gigui.data import IniRepo
from gigui.gi_runner_base import GiRunnerBase
from gigui.keys import Keys
from gigui.messages import CLOSE_OUTPUT_VIEWERS_CLI_MSG
from gigui.output.repo_html_server import HTMLServer
from gigui.queues_events import RunnerQueues
from gigui.repo_runner import RepoRunner
from gigui.typedefs import FileStr
from gigui.utils import get_dir_matches, log_end_time, open_file, out_profile

# pylint: disable=too-many-arguments disable=too-many-positional-arguments

logger = getLogger(__name__)


class GIRunner(GiRunnerBase, HTMLServer):
    args: Args

    def __init__(
        self,
        args: Args,
        start_time: float,
        queues: RunnerQueues,
        logging_queue: Queue,
    ) -> None:
        GiRunnerBase.__init__(self, args)
        HTMLServer.__init__(self, args, queues)
        self.logging_queue: Queue = logging_queue

        self.start_time: float = start_time
        self.queue_listener: QueueListener | None = None
        self.requires_server: bool = (
            not self.args.file_formats and not self.args.view == NONE
        )
        self.future_to_ini_repo: dict[Future, IniRepo] = {}
        self.nr_workers: int = 0
        self.nr_started_prev: int = -1
        self.nr_done_prev: int = -1

        if self.args.view == DYNAMIC_BLAME_HISTORY and self.args.multicore:
            log(
                "Dynamic blame history is not supported in multicore mode. "
                "Switching to single core."
            )
            self.args.multicore = False

        if not shared.gui:
            if args.multicore and not shared.gui:
                signal.signal(signal.SIGINT, shutdown_handler_main_multi_core)
                signal.signal(signal.SIGTERM, shutdown_handler_main_multi_core)
            else:  # single core
                signal.signal(
                    signal.SIGINT,
                    lambda signum, frame: shutdown_handler_main(
                        signum,
                        frame,
                        self.sigint_event,
                    ),
                )
                signal.signal(
                    signal.SIGTERM,
                    lambda signum, frame: shutdown_handler_main(
                        signum,
                        frame,
                        self.sigint_event,
                    ),
                )

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
                self.logging_queue, self.args.verbosity
            )
            self.process_tasks_multicore(repo_lists)
            if self.queue_listener:
                self.queue_listener.stop()
        else:  # single core
            self.process_repos_singlecore(repo_lists)

        if self.requires_server and not shared.gui:
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

            self.await_tasks_process_output()

            for future in as_completed(futures):
                logger.debug("future done:", future.result())

    def await_tasks_process_output(self) -> None:
        i: int = 0
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
                if shared.gui:
                    shared.gui_window.write_event_value(Keys.open_file, out_file_name)  # type: ignore
                else:
                    open_file(out_file_name)
                logger.info(
                    f"{repo_name}:    {out_file_name}: output done "
                    + (f" {i} of {self.len_repos}" if self.len_repos > 1 else "")
                )

        elif self.requires_server and not shared.gui:
            self.start_server_threads()
            if self.args.view == AUTO and not self.args.file_formats:
                self.set_localhost_data()
                for i, data in enumerate(self.id2host_data.values()):
                    self.open_new_tab(
                        data.name,
                        data.browser_id,
                        data.html_doc,
                        i + 1,
                    )
            elif self.args.view == DYNAMIC_BLAME_HISTORY:
                self.set_localhost_repo_data()
                for i, data in enumerate(self.id2host_repo_data.values()):
                    self.open_new_tab(
                        data.name,
                        data.browser_id,
                        data.html_doc,
                        i + 1,
                    )
            log(CLOSE_OUTPUT_VIEWERS_CLI_MSG)
            self.events.server_shutdown_done.wait()

        elif self.requires_server and shared.gui:
            shared.gui_window.write_event_value(Keys.start_server_threads, self)  # type: ignore
            if self.args.view == AUTO and not self.args.file_formats:
                self.set_localhost_data()
            elif self.args.view == DYNAMIC_BLAME_HISTORY:
                self.set_localhost_repo_data()
            shared.gui_window.write_event_value(Keys.delay, self)  # type: ignore
            shared.gui_window.write_event_value(Keys.gui_open_new_tabs, self)  # type: ignore
            self.events.server_shutdown_done.wait()

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

        self.await_tasks_process_output()

    @staticmethod
    def total_len(repo_lists: list[list[IniRepo]]) -> int:
        return sum(len(repo_list) for repo_list in repo_lists)


def shutdown_handler_main_multi_core(signum, frame) -> None:
    pass


def shutdown_handler_main(signum, frame, sigint_event: threading.Event) -> None:
    sigint_event.set()  # Only used for single core


# Main function to run the analysis and create the output
def start_gi_runner(
    args: Args,
    start_time: float,
    queues: RunnerQueues,
    logging_queue: Queue,
) -> None:
    GIRunner(args, start_time, queues, logging_queue).run_repos()


def shutdown_handler_worker(signum, frame, sigint_event: threading.Event) -> None:
    sigint_event.set()  # Only used for multicore


# Runs on a separate core, receives tasks one by one and executes each task by a
# repo_runner instance.
def multicore_worker(
    queues: RunnerQueues,
    verbosity: int,
) -> str:
    ini_repo: IniRepo

    global logger
    _logging.set_logging_level_from_verbosity(verbosity)
    logger = getLogger(__name__)

    # Take into account that the SyncManager can be shut down in the main process,
    # which will cause subsequent logging to fail.
    while True:
        ini_repo = queues.task.get()
        repo_runner = RepoRunner(ini_repo, queues)
        repo_runner.process_repo()
        queues.task.task_done()
        return ini_repo.name
