import logging

import colorlog
import PySimpleGUI as sg

FORMAT = "%(name)s %(funcName)s %(lineno)s\n%(message)s\n"
DEBUG = "debug"
# Set to the value of the GUI window at the start of gui.psg.run
gui_window: sg.Window | None = None

# Root logger should not have a name, so that all loggers with names are automatically
# children of the root logger.
# Do not use the root logger for logging, only use a named (child) logger instead.
root_logger = logging.getLogger()


# For GUI logger
class GUIOutputHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        # Ensure log_entry always starts with a newline. This means that if two log
        # entries are written in succession, there will be an empty line between them.
        log_entry = "\n" + log_entry
        match record.levelno:
            case logging.ERROR:
                gui_window.write_event_value(DEBUG, (log_entry, "red"))  # type: ignore
            case logging.WARNING:
                gui_window.write_event_value(DEBUG, (log_entry, "orange"))  # type: ignore
            case logging.INFO:
                gui_window.write_event_value(DEBUG, (log_entry, "green"))  # type: ignore
            case logging.DEBUG:
                gui_window.write_event_value(DEBUG, (log_entry, "blue"))  # type: ignore
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
            root_logger.setLevel(logging.WARNING)  # verbosity == 0
        case 1:
            root_logger.setLevel(logging.INFO)  # verbosity == 1
        case _:
            root_logger.setLevel(logging.DEBUG)  # verbosity >= 2


def get_logging_level_name() -> str:
    return logging.getLevelName(root_logger.level)
