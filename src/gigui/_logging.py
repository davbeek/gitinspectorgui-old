import logging
import multiprocessing
from logging.handlers import QueueHandler, QueueListener

import colorlog

from gigui import shared

FORMAT = "%(levelname)s %(name)s %(funcName)s %(lineno)s\n%(message)s\n"
FORMAT_INFO = "%(message)s"

DEBUG = "debug"
LOG = "log"
VERBOSE = 15

logging.addLevelName(VERBOSE, "VERBOSE")

# Root logger should not have a name, so that all loggers with names are automatically
# children of the root logger.
# Do not use the root logger for logging, only use a named (child) logger instead.
root_logger = logging.getLogger()


# For GUI logger
class GUIOutputHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        match record.levelno:
            case logging.DEBUG:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "blue"))  # type: ignore
            case 15:  # VERBOSE
                shared.gui_window.write_event_value(DEBUG, (log_entry, "green"))  # type: ignore
            case logging.INFO:
                shared.gui_window.write_event_value(LOG, (log_entry + "\n", "black"))  # type: ignore
            case logging.WARNING:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "orange"))  # type: ignore
            case logging.ERROR:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "red"))  # type: ignore
            case logging.CRITICAL:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "red"))  # type: ignore
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


class CustomFormatter(logging.Formatter):
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


def get_custom_cli_color_formatter() -> CustomColoredFormatter:
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


def get_custom_gui_formatter() -> CustomFormatter:
    return CustomFormatter(
        FORMAT,
        info_fmt=FORMAT_INFO,  # Different format for INFO level
    )


def add_cli_handler():
    cli_handler = logging.StreamHandler()
    cli_formatter = get_custom_cli_color_formatter()
    cli_handler.setFormatter(cli_formatter)
    root_logger.addHandler(cli_handler)


def add_gui_handler():
    gui_handler = GUIOutputHandler()
    gui_formatter = get_custom_gui_formatter()
    gui_handler.setFormatter(gui_formatter)
    root_logger.addHandler(gui_handler)


def set_logging_level_from_verbosity(verbosity: int):
    match verbosity:
        case 0:
            root_logger.setLevel(logging.WARNING)  # verbosity == 0
        case 1:
            root_logger.setLevel(logging.INFO)  # verbosity == 1
        case 2:
            root_logger.setLevel(VERBOSE)  # verbosity == 2
        case _:
            root_logger.setLevel(logging.DEBUG)  # verbosity >= 3


def verbose(self, message, *args, **kwargs):
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs, stacklevel=2)


setattr(logging.Logger, "verbose", verbose)


def configure_logging_for_multiprocessing(queue: multiprocessing.Queue, verbosity):
    handler = QueueHandler(queue)
    root = logging.getLogger()
    root.addHandler(handler)
    set_logging_level_from_verbosity(verbosity)


def start_logging_listener(queue: multiprocessing.Queue) -> QueueListener:
    cli_formatter = get_custom_cli_color_formatter()
    cli_handler = logging.StreamHandler()
    cli_handler.setFormatter(cli_formatter)
    queue_listener = QueueListener(queue, cli_handler)
    queue_listener.start()
    return queue_listener
