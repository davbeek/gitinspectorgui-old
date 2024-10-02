import argparse
import logging
import platform
import subprocess
import time
from cProfile import Profile
from io import StringIO
from pathlib import Path
from pstats import Stats

import PySimpleGUI as sg
import webview

from gigui.constants import WEBVIEW_HEIGHT, WEBVIEW_WIDTH
from gigui.keys import Keys
from gigui.typedefs import FileStr

STDOUT = True
DEFAULT_WRAP_WIDTH = 88

logger = logging.getLogger(__name__)

# Set to True at the start of gui.psg.run
gui = False  # pylint: disable=invalid-name

# Set to the value of the GUI window at the start of gui.psg.run
gui_window: sg.Window | None = None


def log(arg, text_color=None, end="\n"):
    if gui:
        gui_window.write_event_value("log", (arg, end, text_color))  # type: ignore
    else:
        print(arg, end=end)


def open_files(fstrs: list[str]):
    """
    Ask the OS to open the given html filenames.

    :param fstrs: The file paths to open.
    """
    if fstrs:
        match platform.system():
            case "Darwin":
                subprocess.run(["open"] + fstrs, check=True)
            case "Linux":
                subprocess.run(["xdg-open"] + fstrs, check=True)
            case "Windows":
                if len(fstrs) != 1:
                    raise RuntimeError(
                        "Illegal attempt to open multiple html files at once on Windows."
                    )

                # First argument "" is the title for the new command prompt window.
                subprocess.run(["start", "", fstrs[0]], check=True, shell=True)

            case _:
                raise RuntimeError(f"Unknown platform {platform.system()}")


def open_webview(html_code: str, repo_name: str):
    webview.create_window(
        f"{repo_name} viewer",
        html=html_code,
        width=WEBVIEW_WIDTH,
        height=WEBVIEW_HEIGHT,
    )
    webview.start()


def log_end_time(start_time: float):
    """
    Output a log entry to the log of the currently amount of passed time since 'start_time'.
    """
    end_time = time.time()
    log(f"Done in {end_time - start_time:.1f} s")


def get_outfile_name(fix: str, outfile_base: str, repo_name: str) -> FileStr:
    base_name = Path(outfile_base).name
    if fix == Keys.prefix:
        outfile_name = repo_name + "-" + base_name
    elif fix == Keys.postfix:
        outfile_name = base_name + "-" + repo_name
    else:
        outfile_name = base_name
    return outfile_name


def divide_to_percentage(dividend: int, divisor: int) -> float:
    if dividend and divisor:
        return round(dividend / divisor * 100)
    else:
        return float("NaN")


def get_digit(arg):
    try:
        arg = int(arg)
        if 0 <= arg < 10:
            return arg
        else:
            raise ValueError
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(
            f"Invalid value '{arg}', use a single digit integer >= 0."
        ) from e


def get_pos_number(arg):
    try:
        arg = int(arg)
        if 0 <= arg:
            return arg
        else:
            raise ValueError
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(
            f"Invalid value '{arg}', use a positive integer number."
        ) from e


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
    my_dir = Path(__file__).resolve().parent
    version_file = my_dir / "version.txt"
    with open(version_file, "r", encoding="utf-8") as file:
        version = file.read().strip()
    return version


def out_profile(args, profiler):
    def log_profile(profile: Profile, sort: str):
        io_stream = StringIO()
        stats = Stats(profile, stream=io_stream).strip_dirs()
        stats.sort_stats(sort).print_stats(args.profile)
        s = io_stream.getvalue()
        log(s)

    if args.profile:
        assert profiler is not None
        log("Profiling results:")
        profiler.disable()
        if 0 < args.profile < 100:
            log_profile(profiler, "cumulative")
            log_profile(profiler, "time")
        else:
            stats = Stats(profiler).strip_dirs()
            log("printing to: gigui.prof")
            stats.dump_stats("gigui.prof")
