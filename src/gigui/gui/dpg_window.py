import base64
import sys
from logging import getLogger
from pathlib import Path
from typing import Any, Union

import dearpygui.dearpygui as dpg

from gigui._logging import add_gui_handler
from gigui.args_settings import SettingsFile
from gigui.constants import (
    AUTO,
    BLAME_EXCLUSION_CHOICES,
    DEFAULT_FILE_BASE,
    DISABLED_COLOR,
    DYNAMIC_BLAME_HISTORY,
    ENABLED_COLOR,
    FILE_FORMATS,
    INIT_COL_PERCENT,
    INVALID_INPUT_RGBA_COLOR,
    MAX_COL_HEIGHT,
    NONE,
    PARENT_HINT,
    PREPOSTFIX_OPTIONS,
    REPO_HINT,
    SHOW,
    VALID_INPUT_RGBA_COLOR,
    WINDOW_HEIGHT_CORR,
    WINDOW_SIZE_X,
    WINDOW_SIZE_Y,
)
from gigui.gui.dpg_window_support import (
    button,
    checkbox,
    input_text,
    multiline,
    separator,
    spinner,
    text,
)
from gigui.keys import Keys
from gigui.tiphelp import Tip

TEXT_WRAP = 350
LABEL_WIDTH = 200

WINDOW_HEIGHT = 800

logger = getLogger(__name__)

COL_HEIGHT_UNLIMITED = int(
    (WINDOW_SIZE_Y - WINDOW_HEIGHT_CORR) * INIT_COL_PERCENT / 100
)
COL_HEIGHT = min(MAX_COL_HEIGHT, COL_HEIGHT_UNLIMITED)
RADIO_BUTTON_GROUP_FIX_ID = 2

tip = Tip()
keys = Keys()


def make_window(gui_handle) -> dict[str, Union[int, str]]:
    window: dict[str, Union[int, str]] = {}
    dpg.create_context()

    with dpg.window(
        label="GitinspectorGUI", width=785, height=WINDOW_HEIGHT, no_close=True
    ):
        with dpg.group(horizontal=True):
            window[keys.run] = button("Run", keys.run, gui_handle)
            window[keys.clear] = button("Clear", keys.clear, gui_handle)
            window[keys.help] = button("Help", keys.help, gui_handle)
            window[keys.about] = button("About", keys.about, gui_handle)
            window[keys.exit] = button("Exit", keys.exit, gui_handle)

            window[keys.col_percent] = spinner(
                "%", 75, 20, 100, 5, keys.col_percent, gui_handle,
            )

        separator("IO Configuration")

        with dpg.child_window(height=127):
            with dpg.group(horizontal=True):
                text("Input folder path")
                window[keys.input_fstrs] = input_text(keys.input_fstrs, gui_handle, 567)

                with dpg.file_dialog(
                    directory_selector=True,
                    width=600,
                    height=400,
                    show=False,
                    callback=gui_handle,
                    tag=keys.file_dialog,
                ):
                    pass

                window[keys.browse_input_fstr] = button("Browse", keys.browse_input_fstr, gui_handle)

            with dpg.group(horizontal=True):
                with dpg.group(width=LABEL_WIDTH):
                    text("Output file path")
                window[keys.outfile_path] = input_text(keys.outfile_path, gui_handle)

            with dpg.group(horizontal=True):
                text("Output prepostfix")
                window[keys.fix] = dpg.add_radio_button(
                    tuple(PREPOSTFIX_OPTIONS.values()),
                    tag=keys.fix,
                    # default_value=self.get_output_prepostfix(),
                    callback=gui_handle,
                    horizontal=True,
                )

            with dpg.group(horizontal=True):
                text("Options")
                text("Search Depth")
                window[keys.depth] = spinner("", 80, 0, 10, 1, keys.depth, gui_handle)

                text("Output file base")
                window[keys.outfile_base] = input_text(keys.outfile_base, gui_handle)

            with dpg.group(horizontal=True):
                text("Include files")
                text("Subfolder")
                window[keys.subfolder] = input_text(keys.subfolder, gui_handle, 100)
                text("N files")
                window[keys.n_files] = input_text(keys.n_files, 50)

                text("File patterns")
                window[keys.include_files] = input_text(keys.include_files, gui_handle)

        separator(label="Output generation and formatting")

        with dpg.child_window(height=178):
            with dpg.group(horizontal=True):
                text("View options")
                # dpg.add_checkbox(label=keys.auto)
                window[keys.auto] = checkbox(keys.auto, keys.auto, gui_handle)
                window[keys.dynamic_blame_history] = checkbox(
                    "dynamic blame history", keys.dynamic_blame_history, gui_handle
                )

            with dpg.group(horizontal=True):
                text("File formats")
                window[keys.html] = checkbox(keys.html, keys.html, gui_handle)
                window[keys.excel] = checkbox(keys.excel, keys.excel, gui_handle)

            with dpg.group(horizontal=True):
                text("Statistics output")
                window[keys.show_renames] = checkbox("Show renames", keys.show_renames, gui_handle)
                window[keys.deletions] = checkbox("Deletions", keys.deletions, gui_handle)
                window[keys.scaled_percentages] = checkbox("Scaled %", keys.scaled_percentages, gui_handle)

            with dpg.group(horizontal=True):
                text("Blame options")

                text("Exclusions")
                window[keys.blame_exclusions] = dpg.add_combo(
                    BLAME_EXCLUSION_CHOICES,
                    width=60,
                    tag=keys.blame_exclusions,
                    callback=gui_handle,
                )

                text("Copy move")
                window[keys.copy_move] = spinner("", 60, 0, 5, 1, keys.copy_move, gui_handle)
                window[keys.blame_skip] = checkbox("Blame skip", keys.blame_skip, gui_handle)

            with dpg.group(horizontal=True):
                text("Blame inclusions")
                window[keys.empty_lines] = checkbox("Empty lines", keys.empty_lines, gui_handle)
                window[keys.comments] = checkbox("Comments", keys.comments, gui_handle)

            with dpg.group(horizontal=True):
                text("General options")
                window[keys.whitespace] = checkbox("Whitespace", keys.whitespace, gui_handle)
                window[keys.multicore] = checkbox("Multicore", keys.multicore, gui_handle)

                text("Since")
                window[keys.since] = dpg.add_input_text(tag=keys.since)
                # window[keys.since] = dpg.add_date_picker(tag=keys.since, level=dpg.mvDatePickerLevel_Day) #, show=False, default_value={'month_day': 8, 'year':93, 'month':5})
                text("Until")
                window[keys.until] = dpg.add_input_text(tag=keys.until)
                # window[keys.ntil] = dpg.add_date_picker(label=keys.until, level=dpg.mvDatePickerLevel_Day)

            with dpg.group(horizontal=True):
                text("General options")

                text("Verbosity")
                window[keys.verbosity] = spinner("", 60, 0, 3, 1, keys.verbosity, gui_handle)

                text("Dry run")
                window[keys.dryrun] = spinner("", 60, 0, 3, 1, keys.dryrun, gui_handle)

                text("Extensions")
                window[keys.extensions] = input_text(keys.extensions, gui_handle)

        with dpg.child_window(height=60):
            with dpg.group(horizontal=True):
                text("Settings")
                window[keys.settings_file] = input_text(keys.settings_file, gui_handle)

            with dpg.group(horizontal=True):
                window[keys.save] = button("Save", keys.save, gui_handle)
                window[keys.save_as] = button("Save As", keys.save_as, gui_handle)
                window[keys.load] = button("Load", keys.load, gui_handle)
                window[keys.reset] = button("Reset", keys.reset, gui_handle)
                window[keys.reset_file] = button("Reset File", keys.reset_file, gui_handle)
                window[keys.toggle_settings_file] = button("Toggle", keys.toggle_settings_file, gui_handle)

        separator(label="Exclusion patterns")

        with dpg.child_window(height=85):
            with dpg.table(
                header_row=False,
                borders_innerH=False,
                borders_outerH=False,
                borders_innerV=False,
                borders_outerV=False,
                no_host_extendX=True,
            ):

                dpg.add_table_column()
                dpg.add_table_column()

                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        text("Author")
                        window[keys.ex_authors] = input_text(keys.ex_authors, gui_handle)

                    with dpg.group(horizontal=True):
                        text("Email")
                        window[keys.ex_emails] = input_text(keys.ex_emails, gui_handle)

                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        text("File/Folder")
                        window[keys.ex_files] = input_text(keys.ex_files, gui_handle, width=400)
                    with dpg.group(horizontal=True):
                        text("Revision hash")
                        window[keys.ex_revisions] = input_text(keys.ex_revisions, gui_handle)

            with dpg.group(horizontal=True):
                text("Commit message")
                window[keys.ex_messages] = input_text(keys.ex_messages, gui_handle)

        multiline(keys.multiline)
    return window

def show_window():
    dpg.create_viewport(title="GitinspectorGUI", width=800, height=WINDOW_HEIGHT)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()

