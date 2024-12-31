import logging

import colorlog
import PySimpleGUI as sg  # type: ignore

from gigui import shared

FORMAT = "%(name)s %(funcName)s %(lineno)s\n%(message)s\n"
DEBUG = "debug"

# Root logger should not have a name, so that all loggers with names are automatically
# children of the root logger.
# Do not use the root logger for logging, only use a named (child) logger instead.
root_logger = logging.getLogger()


# For GUI logger
class GUIOutputHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        # Ensure log_entry always starts with a newline. This means that if two log
        # entries are written in succession, there will be an empty line between them.
        log_entry = "\n" + log_entry
        match record.levelno:
            case logging.ERROR:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "red"))  # type: ignore
            case logging.WARNING:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "orange"))  # type: ignore
            case logging.INFO:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "green"))  # type: ignore
            case logging.DEBUG:
                shared.gui_window.write_event_value(DEBUG, (log_entry, "blue"))  # type: ignore
            case _:
                sg.cprint(log_entry)


def add_cli_handler():
    cli_handler = logging.StreamHandler()
    cli_formatter = colorlog.ColoredFormatter(
        "%(log_color)s" + FORMAT,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        style="%",
    )
    cli_handler.setFormatter(cli_formatter)
    root_logger.addHandler(cli_handler)


def add_gui_handler():
    gui_handler = GUIOutputHandler()
    gui_handler.setFormatter(logging.Formatter(FORMAT))
    root_logger.addHandler(gui_handler)


def set_logging_level_from_verbosity(verbosity: int):
    match verbosity:
        case 0:
            shared.DEBUG_SHOW_FILES = False
            root_logger.setLevel(logging.WARNING)  # verbosity == 0
        case 1:
            shared.DEBUG_SHOW_FILES = True
            root_logger.setLevel(logging.WARNING)  # verbosity == 1
        case 2:
            shared.DEBUG_SHOW_FILES = True
            root_logger.setLevel(logging.INFO)  # verbosity == 2
        case _:
            shared.DEBUG_SHOW_FILES = True
            root_logger.setLevel(logging.DEBUG)  # verbosity >= 3


def get_logging_level_name() -> str:
    return logging.getLevelName(root_logger.level)
