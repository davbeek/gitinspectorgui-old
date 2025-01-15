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

# Avoid having to use quotes for forward references in type hints
# This feature is available in Python 3.13

import logging
import queue
from logging import Formatter, Handler, LogRecord, StreamHandler, getLogger
from logging.handlers import QueueHandler, QueueListener

import colorlog

from gigui import shared
from gigui.constants import DEFAULT_VERBOSITY

FORMAT = "%(levelname)s %(name)s %(funcName)s %(lineno)s\n%(message)s\n"
FORMAT_INFO = "%(message)s"

DEBUG_KEY = "debug"
LOG_KEY = "log"


def ini_for_cli(verbosity: int = DEFAULT_VERBOSITY) -> StreamHandler:
    set_logging_level_from_verbosity(verbosity)
    handler = add_cli_handler()
    return handler


# Cannot add GUI handler here because the GUI is not yet running.
# The GUI handler is added in module psg_window in make_window().
def ini_for_gui_base(verbosity: int = DEFAULT_VERBOSITY) -> None:
    set_logging_level_from_verbosity(verbosity)


def ini_for_multiprocessing_cli(
    logging_queue: queue.Queue, verbosity: int = DEFAULT_VERBOSITY
) -> None:
    getLogger().addHandler(QueueHandler(logging_queue))


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


def add_cli_handler() -> StreamHandler:
    cli_handler = StreamHandler()
    cli_handler.setFormatter(get_custom_cli_color_formatter())
    getLogger().addHandler(cli_handler)
    return cli_handler


def add_gui_handler() -> None:
    gui_handler = GUIOutputHandler()
    gui_handler.setFormatter(get_custom_gui_formatter())
    getLogger().addHandler(gui_handler)


def start_logging_listener(logging_queue: queue.Queue, verbosity: int) -> QueueListener:
    cli_handler = StreamHandler()
    cli_handler.setFormatter(get_custom_cli_color_formatter())
    queue_listener = QueueListener(logging_queue, cli_handler)
    queue_listener.start()
    return queue_listener


def get_custom_cli_color_formatter() -> "CustomColoredFormatter":
    return CustomColoredFormatter(
        "%(log_color)s" + FORMAT,
        info_fmt="%(log_color)s" + FORMAT_INFO,  # Different format for INFO level
        reset=True,
        log_colors={
            "DEBUG": "cyan",  # Changed from blue to cyan for better readability on black
            "VERBOSE": "green",
            "INFO": "white",
            "WARNING": "yellow",  # Changed from orange to yellow for better readability on black
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        style="%",
    )


class CustomFormatter(Formatter):
    def __init__(self, fmt, info_fmt, *args, **kwargs):
        super().__init__(fmt, *args, **kwargs)
        self.default_fmt = fmt
        self.info_fmt = info_fmt

    def format(self, record):
        if record.levelno == logging.INFO:
            original_fmt = self._style._fmt
            self._style._fmt = self.info_fmt
            result = super().format(record)
            self._style._fmt = original_fmt
            return result
        else:
            return super().format(record)


def get_custom_gui_formatter() -> "CustomFormatter":
    return CustomFormatter(
        FORMAT,
        info_fmt=FORMAT_INFO,  # Different format for INFO level
    )


# For GUI logger
class GUIOutputHandler(Handler):
    def emit(self, record: LogRecord) -> None:
        log_entry = self.format(record)
        match record.levelno:
            case logging.DEBUG:
                shared.gui_window.write_event_value(DEBUG_KEY, (log_entry, "blue"))  # type: ignore
            case 15:  # VERBOSE
                shared.gui_window.write_event_value(DEBUG_KEY, (log_entry, "green"))  # type: ignore
            case logging.INFO:
                shared.gui_window.write_event_value(LOG_KEY, (log_entry + "\n", "black"))  # type: ignore
            case logging.WARNING:
                shared.gui_window.write_event_value(DEBUG_KEY, (log_entry, "orange"))  # type: ignore
            case logging.ERROR:
                shared.gui_window.write_event_value(DEBUG_KEY, (log_entry, "red"))  # type: ignore
            case logging.CRITICAL:
                shared.gui_window.write_event_value(DEBUG_KEY, (log_entry, "red"))  # type: ignore
            case _:
                raise ValueError(f"Unknown log level: {record.levelno}")


class CustomColoredFormatter(colorlog.ColoredFormatter):
    def __init__(self, fmt, info_fmt, *args, **kwargs):
        super().__init__(fmt, *args, **kwargs)
        self.default_fmt = fmt
        self.info_fmt = info_fmt

    def format(self, record):
        if record.levelno == logging.INFO:
            original_fmt = self._style._fmt
            self._style._fmt = self.info_fmt
            result = super().format(record)
            self._style._fmt = original_fmt
            return result
        else:
            return super().format(record)
