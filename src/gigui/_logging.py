"""

Multiple calls to logging.getLogger("name") with the same "name" string will always
return the same logger instance. If no name is provided, as in logging.getLogger(),
the root logger is returned. This ensures that loggers are singletons and can be
configured centrally.

To get the root logger, use logging.getLogger(). Root logger should not have a name,
so that all loggers with names are automatically children of the root logger. Do not
use the root logger for logging, only use a named (child) logger instead.

Do not define a global root logger in this module to be used as a globally shared
variable in the functions in this module, as in root_logger =
logging.getLogger(). Always use logging.getLogger() in the functions in this module,
so that the functions can be used in a multiprocessing environment and always the root
logger of each multiprocessing process is used.
"""

import logging
import multiprocessing.util as multiprocessing_util
import queue
from collections.abc import Mapping
from logging import Formatter, Handler, LogRecord, StreamHandler, getLogger
from logging.handlers import QueueHandler, QueueListener
from typing import Any

import colorlog

from gigui import shared
from gigui.constants import (
    ALLOW_GITPYTHON_DEBUG,
    DEBUG_MULTIPROCESSING,
    DEFAULT_VERBOSITY,
)

# For CRITICAL, ERROR, WARNING and DEBUG
CUSTOM_FORMAT = "%(levelname)s/%(name)s/%(funcName)s %(lineno)s\n%(message)s\n"

# For INFO and ALWAYS_LOG_LEVEL: normal formatting as used in print()
PRINT_FORMAT = "%(message)s"

ALWAYS_LOG_LEVEL = (logging.CRITICAL + logging.ERROR) // 2  # 45
ALWAYS_LOG_LEVEL_NAME = "always_log"

CLI_LEVEL_COLOR_DICT: Mapping[str, str] = {
    "DEBUG": "cyan",  # Changed from blue to cyan for better readability on black
    "INFO": "white",
    "WARNING": "yellow",  # Changed from orange to yellow for better readability on black
    "ERROR": "red",
    ALWAYS_LOG_LEVEL_NAME: "white",
    "CRITICAL": "red,bg_white",
}

# used for communication with GUI
LOGGING_KEY = "logging"
LOG_KEY = "log"

logging.addLevelName(ALWAYS_LOG_LEVEL, ALWAYS_LOG_LEVEL_NAME)

gui_multicore = False
logger = getLogger(__name__)
# logging.getLogger("git").setLevel(logging.WARNING)

if DEBUG_MULTIPROCESSING:
    multiprocessing_util.log_to_stderr()
if not ALLOW_GITPYTHON_DEBUG:
    logging.getLogger("git").setLevel(max(logging.WARNING, logging.getLogger().level))


def ini_for_cli(verbosity: int = DEFAULT_VERBOSITY) -> None:
    set_logging_level_from_verbosity(verbosity)
    add_cli_handler()


# Cannot add GUI handler here because the GUI is not yet running.
# The GUI handler is added in module psg_window in make_window().
def ini_for_gui_base(verbosity: int = DEFAULT_VERBOSITY) -> None:
    set_logging_level_from_verbosity(verbosity)


def set_logging_level_from_verbosity(verbosity: int | None) -> None:
    root_logger = getLogger()
    if verbosity is None:
        verbosity = DEFAULT_VERBOSITY
    match verbosity:
        case 0:
            root_logger.setLevel(logging.WARNING)  # verbosity == 0
        case 1:
            root_logger.setLevel(logging.INFO)  # verbosity == 1
        case 2:
            root_logger.setLevel(logging.DEBUG)  # verbosity == 2
        case _:
            raise ValueError(f"Unknown verbosity level: {verbosity}")


def add_cli_handler() -> None:
    getLogger().addHandler(get_cli_handler())


def add_gui_handler() -> None:
    getLogger().addHandler(get_gui_handler())


def get_cli_handler() -> StreamHandler:
    cli_handler = StreamHandler()
    cli_handler.setFormatter(get_custom_cli_formatter())
    return cli_handler


def get_gui_handler() -> "GUIOutputHandler":
    gui_handler = GUIOutputHandler()
    gui_handler.setFormatter(get_custom_gui_formatter())
    return gui_handler


# Executed by a new python interpreter in a worker process, which does not share memory
# with the main process. The worker process is created by the multiprocessing module.
def ini_worker_for_multiprocessing(
    logging_queue: queue.Queue, verbosity: int = DEFAULT_VERBOSITY, gui: bool = False
) -> None:
    global gui_multicore
    getLogger().addHandler(QueueHandler(logging_queue))
    gui_multicore = gui


def start_logging_listener(logging_queue: queue.Queue, verbosity: int) -> QueueListener:
    if shared.gui:
        queue_listener = QueueListener(
            logging_queue, get_cli_handler(), get_gui_handler()
        )
    else:
        queue_listener = QueueListener(logging_queue, get_cli_handler())
    queue_listener.start()
    return queue_listener


def get_custom_cli_formatter() -> colorlog.ColoredFormatter:  # subclass of Formatter
    class CustomCLIFormatter(colorlog.ColoredFormatter):
        def __init__(
            self,
            log_colors: Mapping[str, str],  # similar to read-only dict
        ):
            super().__init__(log_colors=log_colors)

        def format(self, record: LogRecord) -> str:
            self._style._fmt = "%(log_color)s" + (
                PRINT_FORMAT
                if record.levelno in {logging.INFO, ALWAYS_LOG_LEVEL}
                else CUSTOM_FORMAT
            )
            return super().format(record)

    return CustomCLIFormatter(CLI_LEVEL_COLOR_DICT)


# Custom GUI colors are not defined here, but in the class GUIOutputHandler below
def get_custom_gui_formatter() -> Formatter:
    class CustomGUIFormatter(Formatter):
        def format(self, record: LogRecord) -> str:
            self._style._fmt = (
                PRINT_FORMAT
                if record.levelno in {logging.INFO, ALWAYS_LOG_LEVEL}
                else CUSTOM_FORMAT
            )
            return super().format(record)

    return CustomGUIFormatter()


# For GUI logger
class GUIOutputHandler(Handler):
    def emit(self, record: LogRecord) -> None:
        log_entry = self.format(record)
        match record.levelno:
            case logging.DEBUG:
                shared.gui_window.write_event_value(LOGGING_KEY, (log_entry, "blue"))  # type: ignore
            case logging.INFO:
                shared.gui_window.write_event_value(LOGGING_KEY, (log_entry, "black"))  # type: ignore
            case logging.WARNING:
                shared.gui_window.write_event_value(LOGGING_KEY, (log_entry, "orange"))  # type: ignore
            case logging.ERROR:
                shared.gui_window.write_event_value(LOGGING_KEY, (log_entry, "red"))  # type: ignore
            case 45:  # ALWAYS_LOG_LEVEL
                shared.gui_window.write_event_value(LOGGING_KEY, (log_entry, "black"))  # type: ignore
            case logging.CRITICAL:
                shared.gui_window.write_event_value(LOGGING_KEY, (log_entry, "red"))  # type: ignore
            case _:
                raise ValueError(f"Unknown log level: {record.levelno}")


def log(arg: Any, text_color: str | None = None, end: str = "\n", flush: bool = False):
    if gui_multicore:
        logger.log(ALWAYS_LOG_LEVEL, arg)
    elif shared.gui:
        shared.gui_window.write_event_value(  # type: ignore
            "log", (str(arg) + end, (text_color if text_color else "black"))
        )
    else:
        print(arg, end=end, flush=flush)


def log_dots(
    i: int, i_max: int, prefix: str = "", postfix: str = "\n", multicore: bool = False
):
    if gui_multicore:
        return

    # i from 1 to and including i_max
    if multicore:
        log(".", end="", flush=True)
    else:
        if i == 1:
            log(prefix, end="")
        log("." if i < i_max else "." + postfix, end="", flush=True)
