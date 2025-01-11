import argparse
import logging
import platform
import subprocess
import time
from cProfile import Profile
from io import StringIO
from multiprocessing import Process
from pathlib import Path
from pstats import Stats
from typing import Any

import webview

from gigui import shared
from gigui.constants import WEBVIEW_HEIGHT, WEBVIEW_WIDTH
from gigui.keys import Keys
from gigui.typedefs import FileStr

STDOUT = True
DEFAULT_WRAP_WIDTH = 88

logger = logging.getLogger(__name__)


def log(arg: Any, text_color: str | None = None, end: str = "\n", flush: bool = False):
    if shared.gui:
        shared.gui_window.write_event_value(  # type: ignore
            "log", (str(arg) + end, (text_color if text_color else "black"))
        )
    else:
        print(arg, end=end, flush=flush)


def log_dots(
    i: int, i_max: int, prefix: str = "", postfix: str = "\n", multicore: bool = False
):
    # i from 1 to and including i_max
    if multicore:
        log(".", end="", flush=True)
    else:
        if i == 1:
            log(prefix, end="")
        log("." if i < i_max else "." + postfix, end="", flush=True)


def open_files(fstrs: list[str]):
    if fstrs:
        match platform.system():
            case "Darwin":
                subprocess.run(["open"] + fstrs, check=True)
            case "Linux":
                subprocess.run(["xdg-open"] + fstrs, check=True)
            case "Windows":
                for fstr in fstrs:
                    subprocess.run(["start", "", fstr], check=True, shell=True)
            case _:
                raise RuntimeError(f"Unknown platform {platform.system()}")


def open_file(fstr: FileStr):
    if fstr:
        match platform.system():
            case "Darwin":
                subprocess.run(["open", fstr], check=True)
            case "Linux":
                subprocess.run(["xdg-open", fstr], check=True)
            case "Windows":
                subprocess.run(["start", "", fstr], check=True, shell=True)
            case _:
                raise RuntimeError(f"Unknown platform {platform.system()}")


def open_webview(html_code: str, repo_name: str, gui: bool = False):
    if gui:
        webview_process = Process(target=_open_webview, args=(html_code, repo_name))
        webview_process.daemon = True
        webview_process.start()
    else:
        _open_webview(html_code, repo_name)


def _open_webview(html_code: str, repo_name: str):
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


def get_pos_number_or_empty(arg):
    if arg == "":
        return 0
    try:
        arg = int(arg)
        if 0 <= arg:
            return arg
        else:
            raise ValueError
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(
            f"Invalid value '{arg}', use a positive integer number or empty string \"\"."
        ) from e


def get_relative_fstr(fstr: str, subfolder: str):
    if len(subfolder):
        if fstr.startswith(subfolder):
            relative_fstr = fstr[len(subfolder) :]
            if relative_fstr.startswith("/"):
                return relative_fstr[1:]
            else:
                return relative_fstr
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


def out_profile(profiler, nr_lines: int):
    def log_profile(profile: Profile, sort: str):
        io_stream = StringIO()
        stats = Stats(profile, stream=io_stream).strip_dirs()
        stats.sort_stats(sort).print_stats(nr_lines)
        s = io_stream.getvalue()
        log(s)

    if nr_lines:
        assert profiler is not None
        log("Profiling results:")
        profiler.disable()
        if 0 < nr_lines < 100:
            log_profile(profiler, "cumulative")
            log_profile(profiler, "time")
        else:
            stats = Stats(profiler).strip_dirs()
            log("printing to: gigui.prof")
            stats.dump_stats("gigui.prof")


def non_hex_chars_in_list(s_list: list[str]) -> list[str]:
    hex_chars = set("0123456789abcdefABCDEF")
    non_hex_chars = [c for s in s_list for c in s if c not in hex_chars]
    return non_hex_chars


def to_posix_fstr(fstr: str) -> str:
    if not fstr:
        return fstr
    else:
        return Path(fstr).as_posix()


def to_posix_fstrs(fstrs: list[str]) -> list[str]:
    return [to_posix_fstr(fstr) for fstr in fstrs]


def to_system_fstr(fstr: FileStr) -> FileStr:
    if not fstr:
        return fstr
    else:
        return str(Path(fstr))


def to_system_fstrs(fstrs: list[str]) -> list[str]:
    return [to_system_fstr(fstr) for fstr in fstrs]


# Normally, the input paths have already been expanded by the shell, but in case the
# wildcard were protected in quotes, we expand them here.
def get_dir_matches(input_fstrs: list[FileStr]) -> list[FileStr]:
    matching_fstrs: list[FileStr] = []
    for pattern in input_fstrs:
        matches: list[FileStr] = get_posix_dir_matches_for(pattern)
        if not matches:
            logger.warning(
                f'No repositories found for input folder pattern "{pattern}"'
            )
        for match in matches:
            if match not in matching_fstrs:
                matching_fstrs.append(match)
    return matching_fstrs


def get_posix_dir_matches_for(pattern: FileStr) -> list[FileStr]:
    # Return a list of posix directories that match the pattern and are not hidden.
    # The pattern is case insensitive.
    # If the pattern is absolute, the search is done in the root directory.
    # If the pattern is relative, the search is done in the current directory.
    # The pattern can be posix or windows style.
    pattern_path = Path(pattern)
    rel_pattern = (
        pattern_path.relative_to(Path("/")).as_posix()
        if pattern_path.is_absolute()
        else pattern
    )
    base_path = Path("/") if pattern_path.is_absolute() else Path()
    matches: list[FileStr] = [
        path.as_posix()
        for path in base_path.glob(rel_pattern, case_sensitive=False)
        # Match only directories that are not hidden.
        if path.is_dir() and not path.name.startswith(".")
    ]
    return matches
