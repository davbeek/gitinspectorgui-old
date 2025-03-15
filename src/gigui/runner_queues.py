from dataclasses import dataclass
from multiprocessing.managers import SyncManager
from queue import Queue
from typing import TYPE_CHECKING

from gigui.data import IniRepo
from gigui.typedefs import HtmlStr

if TYPE_CHECKING:
    from gigui.repo_runner import RepoRunner


@dataclass
class RunnerQueues:
    task: Queue[IniRepo]
    task_done: Queue[str]
    open_file: Queue[tuple[str, str]]
    html: (
        Queue[tuple[str, HtmlStr]]
        | Queue[tuple["RepoRunner", HtmlStr]]  # for dynamic blame history
    )


def get_runner_queues(
    multicore: bool,
) -> tuple[RunnerQueues, Queue, SyncManager | None]:
    manager: SyncManager | None
    if multicore:
        manager = SyncManager()
        manager.start()
        task = manager.Queue()
        task_done_nr = manager.Queue()
        open_file = manager.Queue()
        html = manager.Queue()  # type: ignore
        logging = manager.Queue()  # type: ignore
    else:
        manager = None
        task = Queue()
        task_done_nr = Queue()
        open_file = Queue()
        html = Queue()
        logging = Queue()

    return (
        RunnerQueues(
            task,
            task_done_nr,
            open_file,
            html,
        ),
        logging,
        manager,
    )
