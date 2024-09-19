import argparse
import logging
from math import isnan
from pathlib import Path

import PySimpleGUI as sg
import webview

from gigui.constants import WEBVIEW_HEIGHT, WEBVIEW_WIDTH

STDOUT = True
DEFAULT_WRAP_WIDTH = 88

logger = logging.getLogger(__name__)

# Set to True at the start of gui.psg.rungui
gui = False

# Set to the value of the GUI window at the start of gui.psg.rungui
gui_window: sg.Window | None = None


def log(arg, text_color=None, end="\n"):
    if gui:
        gui_window.write_event_value("log", (arg, end, text_color))  # type: ignore
    else:
        print(arg, end=end)


def open_webview(html_code: str, repo_name: str):
    webview.create_window(
        f"{repo_name} viewer",
        html=html_code,
        width=WEBVIEW_WIDTH,
        height=WEBVIEW_HEIGHT,
    )
    webview.start()


def divide_to_percentage(dividend: int, divisor: int) -> float:
    if dividend and divisor:
        return round(dividend / divisor * 100)
    else:
        return float("NaN")


def percentage_to_out(percentage: float) -> int | str:
    if isnan(percentage):
        return ""
    else:
        return round(percentage)


def get_digit(arg):
    try:
        arg = int(arg)
        if 0 <= arg < 10:
            return arg
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"invalid value '{arg}', use a single digit integer >= 0."
        )


def get_pos_number(arg):
    try:
        arg = int(arg)
        if 0 <= arg:
            return arg
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"invalid value '{arg}', use a positive integer number."
        )


def str_split_comma(s: str) -> list[str]:
    xs = s.split(",")
    return [s.strip() for s in xs if s.strip()]


def get_relative_fstr(fstr: str, subfolder: str):
    if len(subfolder):
        if fstr.startswith(subfolder):
            return fstr[len(subfolder) :]
        else:
            return "/" + fstr
    else:
        return fstr


def get_version() -> str:
    mydir = Path(__file__).resolve().parent
    version_file = mydir / "version.txt"
    with open(version_file, "r") as file:
        version = file.read().strip()
    return version
