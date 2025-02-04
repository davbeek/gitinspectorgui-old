import signal
from dataclasses import dataclass
from multiprocessing.managers import SyncManager
from queue import Queue

from gigui.constants import FIRST_PORT
from gigui.data import IniRepo


class CustomSyncManager(SyncManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

    def shutdown_handler(self, signum, frame):  # pylint: disable=unused-argument
        print("SyncManager received SIGINT")


@dataclass
class RunnerQueues:
    host_port: Queue[int]
    task: Queue[IniRepo]
    task_done: Queue[str]
    repo_done: Queue[str]
    logging: Queue[str]
    shutdown_all: Queue[None]


def get_runner_queues(multicore: bool) -> tuple[RunnerQueues, SyncManager | None]:
    manager: SyncManager | None
    if multicore:
        manager = CustomSyncManager()
        manager.start()
        host_port = manager.Queue()
        task = manager.Queue()
        task_done_nr = manager.Queue()
        repo_done_nr = manager.Queue()
        logging = manager.Queue()  # type: ignore
        shutdown_all = manager.Queue()
    else:
        manager = None
        host_port = Queue()
        task = Queue()
        task_done_nr = Queue()
        repo_done_nr = Queue()
        logging = Queue()
        shutdown_all = Queue()
    if host_port:
        host_port.put(FIRST_PORT)

    return (
        RunnerQueues(
            host_port,
            task,
            task_done_nr,
            repo_done_nr,
            logging,
            shutdown_all,
        ),
        manager,
    )
