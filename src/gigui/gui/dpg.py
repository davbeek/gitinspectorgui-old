from copy import copy
from dataclasses import asdict
from typing import Any, Union

import dearpygui.dearpygui as dpg

from gigui.args_settings import Settings
from gigui.constants import (
    BLAME_EXCLUSION_CHOICES,
    FILE_FORMATS,
    INIT_COL_PERCENT,
    MAX_COL_HEIGHT,
    NONE,
    PREPOSTFIX_OPTIONS,
    SHOW,
    WINDOW_HEIGHT_CORR,
    WINDOW_SIZE_X,
    WINDOW_SIZE_Y,
)
from gigui.keys import Keys
from gigui.tiphelp import Help

keys = Keys()

TEXT_WRAP = 350
LABEL_WIDTH = 200

WINDOW_HEIGHT = 800


def _on_demo_close(sender, app_data, user_data):
    print("_on_demo_close")


def gui_handle(sender, app_data, user_data):
    print(f"sender: {sender}, \t app_data: {app_data}, \t user_data: {user_data}")


class DPGui:
    def __init__(self, settings: Settings) -> None:
        print(settings)
        self.settings = settings
        self.window: dict[str, Union[int, str]] = {}
        self.make_window()
        self.window_state_from_settings()
        self.show_gui()

    def get_outfile_str(self):
        return ""

    def window_state_from_settings(self) -> None:
        settings = copy(
            self.settings
        ).as_system()  # ensure all file strings are in system format
        settings_dict = asdict(settings)

        settings_min = {
            key: value
            for key, value in settings_dict.items()
            if key
            not in {
                keys.fix,
                keys.view,
                keys.file_formats,
                keys.gui_settings_full_path,
                keys.profile,
                keys.multithread,
            }
        }
        for key, val in settings_min.items():
            if isinstance(val, list):
                print(key, val)
                value_strings = ", ".join(val)
                self.update_window_value(key, value_strings)  # type: ignore
            else:
                self.update_window_value(key, val)  # type: ignore

        # Default values of boolean window.Element are False
        # Enable the fix radio button that corresponds to the settings.fix value
        self.update_window_value(keys.fix, PREPOSTFIX_OPTIONS[settings.fix])

        # # Default values of boolean window.Element are False
        # # Enable the view radio button that corresponds to the settings.view value
        if settings.view != NONE:
            self.update_window_value(settings.view, True)  # type:ignore

        if settings.file_formats:
            for key in set(FILE_FORMATS):
                self.update_window_value(key, value=key in settings.file_formats)

    def add_dg_checkbox(self, label: str, key: str) -> None:
        cb = dpg.add_checkbox(label=label, tag=key, callback=gui_handle)
        self.window[key] = cb

    def add_dg_input_text(self, tag: str, width: int = -1) -> None:
        it = dpg.add_input_text(tag=tag, width=width, callback=gui_handle)
        self.window[tag] = it

    def update_window_value(self, key: str, value: Any) -> None:
        dpg.set_value(self.window[key], value)

    def make_window(self):
        dpg.create_context()

        with dpg.window(
            label="GitinspectorGUI", width=785, height=WINDOW_HEIGHT, no_close=True
        ):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Run", tag=keys.run, callback=gui_handle)
                dpg.add_button(label="Clear", tag=keys.clear, callback=gui_handle)
                dpg.add_button(label="Help", tag=keys.help, callback=gui_handle)
                dpg.add_button(label="About", tag=keys.about, callback=gui_handle)
                dpg.add_button(label="Exit", tag=keys.exit, callback=gui_handle)

                self.window[keys.col_percent] = dpg.add_input_int(
                    label="%",
                    width=75,
                    min_value=20,
                    max_value=100,
                    step=5,
                    tag=keys.col_percent,
                    callback=gui_handle,
                )

            dpg.add_separator(label="IO Configuration")

            with dpg.child_window(height=127):
                with dpg.group(horizontal=True):
                    dpg.add_text("Input folder path")
                    self.add_dg_input_text(keys.input_fstrs, 567)

                    with dpg.file_dialog(
                        width=300,
                        height=400,
                        show=False,
                        callback=gui_handle,
                        tag=keys.browse_input_fstr,
                    ):
                        dpg.add_file_extension(".*", color=(255, 255, 255, 255))
                        dpg.add_file_extension(
                            "Source files (*.cpp *.h *.hpp){.cpp,.h,.hpp}",
                            color=(0, 255, 255, 255),
                        )
                        dpg.add_file_extension(".cpp", color=(255, 255, 0, 255))
                        dpg.add_file_extension(
                            ".h", color=(255, 0, 255, 255), custom_text="header"
                        )
                        dpg.add_file_extension(
                            "Python(.py){.py}", color=(0, 255, 0, 255)
                        )
                        # dpg.add_button(label="Button on file dialog")

                    dpg.add_button(
                        label="Browse",
                        user_data=dpg.last_container(),
                        callback=lambda s, a, u: dpg.configure_item(u, show=True),
                    )

                with dpg.group(horizontal=True):
                    with dpg.group(width=LABEL_WIDTH):
                        dpg.add_text("Output file path")
                    dpg.add_input_text(
                        default_value=self.get_outfile_str(),
                        callback=gui_handle,
                        width=-1,
                    )

                with dpg.group(horizontal=True):
                    dpg.add_text("Output prepostfix")
                    self.window[keys.fix] = dpg.add_radio_button(
                        tuple(PREPOSTFIX_OPTIONS.values()),
                        tag=keys.fix,
                        # default_value=self.get_output_prepostfix(),
                        callback=gui_handle,
                        horizontal=True,
                    )

                with dpg.group(horizontal=True):
                    dpg.add_text("Options")
                    dpg.add_text("Search Depth")
                    self.window[keys.depth] = dpg.add_input_int(
                        tag=keys.depth,
                        # default_value=self.get_settings_by_key(keys.depth),
                        min_value=0,
                        max_value=10,
                        min_clamped=True,
                        max_clamped=True,
                        width=100,
                        callback=gui_handle,
                    )

                    dpg.add_text("Output file base")
                    self.add_dg_input_text(keys.outfile_base)

                with dpg.group(horizontal=True):
                    dpg.add_text("Include files")
                    dpg.add_text("Subfolder")
                    self.add_dg_input_text(keys.subfolder, 100)
                    dpg.add_text("N files")
                    self.add_dg_input_text(keys.n_files, 50)

                    dpg.add_text("File patterns")
                    self.add_dg_input_text(keys.include_files)

            dpg.add_separator(label="Output generation and formatting")

            with dpg.child_window(height=150):
                with dpg.group(horizontal=True):
                    dpg.add_text("View options")
                    # dpg.add_checkbox(label=keys.auto)
                    self.add_dg_checkbox(keys.auto, keys.auto)
                    self.add_dg_checkbox(
                        "dynamic blame history", keys.dynamic_blame_history
                    )

                with dpg.group(horizontal=True):
                    dpg.add_text("File formats")
                    self.add_dg_checkbox(keys.html, keys.html)
                    self.add_dg_checkbox(keys.excel, keys.excel)

                with dpg.group(horizontal=True):
                    dpg.add_text("Statistics output")
                    self.add_dg_checkbox("Show renames", keys.show_renames)
                    self.add_dg_checkbox("Deletions", keys.deletions)
                    self.add_dg_checkbox("Scaled %", keys.scaled_percentages)

                with dpg.group(horizontal=True):
                    dpg.add_text("Blame options")

                    dpg.add_text("Exclusions")
                    self.window[keys.blame_exclusions] = dpg.add_combo(
                        BLAME_EXCLUSION_CHOICES,
                        width=60,
                        tag=keys.blame_exclusions,
                        callback=gui_handle,
                    )

                    dpg.add_text("Copy move")
                    self.window[keys.copy_move] = dpg.add_input_int(
                        tag=keys.copy_move,
                        min_value=0,
                        max_value=5,
                        min_clamped=True,
                        max_clamped=True,
                        width=60,
                        callback=gui_handle,
                    )

                    self.add_dg_checkbox("Blame skip", keys.blame_skip)

                with dpg.group(horizontal=True):
                    dpg.add_text("Blame inclusions")
                    self.add_dg_checkbox("Empty lines", keys.empty_lines)
                    self.add_dg_checkbox("Comments", keys.comments)

                with dpg.group(horizontal=True):
                    dpg.add_text("General options")
                    self.add_dg_checkbox("Whitespace", keys.whitespace)
                    self.add_dg_checkbox("Multicore", keys.multicore)

                    dpg.add_text("Since")
                    self.window[keys.since] = dpg.add_input_text(tag=keys.since)
                    # self.window[keys.since] = dpg.add_date_picker(tag=keys.since, level=dpg.mvDatePickerLevel_Day) #, show=False, default_value={'month_day': 8, 'year':93, 'month':5})
                    dpg.add_text("Until")
                    self.window[keys.until] = dpg.add_input_text(tag=keys.until)
                    # self.window[keys.ntil] = dpg.add_date_picker(label=keys.until, level=dpg.mvDatePickerLevel_Day)

                with dpg.group(horizontal=True):
                    dpg.add_text("General options")
                    dpg.add_text("Verbosity")
                    self.window[keys.verbosity] = dpg.add_input_int(
                        tag=keys.verbosity,
                        min_value=0,
                        max_value=3,
                        min_clamped=True,
                        max_clamped=True,
                        width=60,
                        callback=gui_handle,
                    )
                    dpg.add_text("Dry run")
                    self.window[keys.dryrun] = dpg.add_input_int(
                        tag=keys.dryrun,
                        min_value=0,
                        max_value=3,
                        min_clamped=True,
                        max_clamped=True,
                        width=60,
                        callback=gui_handle,
                    )

                    dpg.add_text("Extensions")
                    self.add_dg_input_text(keys.extensions)

            with dpg.child_window(height=60):
                with dpg.group(horizontal=True):
                    dpg.add_text("Settings file")
                    self.add_dg_input_text("")

                with dpg.group(horizontal=True):
                    dpg.add_button(label="Save", tag=keys.save, callback=gui_handle)
                    dpg.add_button(
                        label="Save As", tag=keys.save_as, callback=gui_handle
                    )
                    dpg.add_button(label="Load", tag=keys.load, callback=gui_handle)
                    dpg.add_button(label="Reset", tag=keys.reset, callback=gui_handle)
                    dpg.add_button(
                        label="Reset File", tag=keys.reset_file, callback=gui_handle
                    )
                    dpg.add_button(
                        label="Toggle",
                        tag=keys.toggle_settings_file,
                        callback=gui_handle,
                    )

            dpg.add_separator(label="Exclusion patterns")

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
                            dpg.add_text("Author")
                            self.add_dg_input_text(keys.ex_authors)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Email")
                            self.add_dg_input_text(keys.ex_emails)

                    with dpg.table_row():
                        with dpg.group(horizontal=True):
                            dpg.add_text("File/Folder")
                            self.add_dg_input_text(keys.ex_files, 400)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Revision hash")
                            self.add_dg_input_text(keys.ex_revisions)

                with dpg.group(horizontal=True):
                    dpg.add_text("Commit message")
                    self.add_dg_input_text(keys.ex_messages)

            dpg.add_input_text(
                tag=keys.multiline, width=-1, height=-1, multiline=True, readonly=True
            )

    def show_gui(self):
        dpg.create_viewport(title="GitinspectorGUI", width=800, height=WINDOW_HEIGHT)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def process_view_format_radio_buttons(self, html_key: str) -> None:
        match html_key:
            case keys.auto:
                self.update_window_value(keys.dynamic_blame_history, False)
            case keys.dynamic_blame_history:
                self.update_window_value(keys.auto, False)
                self.update_window_value(keys.html, False)
                self.update_window_value(keys.excel, False)
            case keys.html:
                self.update_window_value(keys.dynamic_blame_history, value=False)
            case keys.excel:
                self.update_window_value(keys.dynamic_blame_history, False)
