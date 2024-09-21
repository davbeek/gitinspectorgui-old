# noinspection PyPep8Naming
import logging
import multiprocessing
import sys
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime
from multiprocessing import Process
from pathlib import Path
from typing import Any

import PySimpleGUI as sg

from gigui import _logging, common
from gigui._logging import set_logging_level_from_verbosity
from gigui.args_settings_keys import AUTO, Args, Keys, Settings, SettingsFile
from gigui.common import open_webview, str_split_comma
from gigui.constants import (
    AVAILABLE_FORMATS,
    DEBUG_SHOW_MAIN_EVENT_LOOP,
    DEFAULT_EXTENSIONS,
    DEFAULT_FILE_BASE,
    DISABLED_COLOR,
    ENABLED_COLOR,
    MAX_COL_HEIGHT,
    PARENT_HINT,
    REPO_HINT,
    WINDOW_HEIGHT_CORR,
)
from gigui.gitinspector import main as gitinspector_main
from gigui.gui.commongui import icon, paths_valid
from gigui.gui.psgwindow import make_window
from gigui.repo import is_git_repo
from gigui.tiphelp import Help, Tip
from gigui.typedefs import FileStr

logger = logging.getLogger(__name__)

tip = Tip()
keys = Keys()

buttons = [
    keys.execute,
    keys.clear,
    keys.show,
    keys.save,
    keys.save_as,
    keys.load,
    keys.reset,
    keys.help,
    keys.about,
    keys.browse_input_fstr,
]


# Initial values of GUIState are not used. They are set to their proper values during
# initialization of the rungui_inner function.
@dataclass
class GUIState:
    col_percent: int
    input_fstrs: list[FileStr] = field(default_factory=list)
    input_paths: list[Path] = field(default_factory=list)
    fix: str = keys.prefix
    input_valid: bool = False
    outfile_base: str = DEFAULT_FILE_BASE


def update_button_state(ele: sg.Button, disabled: bool):
    if disabled:
        color = DISABLED_COLOR
    else:
        color = ENABLED_COLOR
    ele.update(disabled=disabled, button_color=color)


def execute(
    window: sg.Window,
    values: dict,
    input_paths: list[Path],
    input_valid: bool,
    outfile_base: FileStr,
):

    def popup(title, message):
        sg.popup(
            title,
            message,
            keep_on_top=True,
            text_color="black",
            background_color="white",
        )

    start_time = time.time()
    logger.info(f"{values = }")

    def disable_buttons(window: sg.Window):
        for bt in buttons:
            update_button_state(window[bt], True)  # type: ignore

    if not input_valid:
        popup("Error", "Input folder path not valid")
        return

    if not input_paths:
        popup("Error", "Input folder path empty")
        return

    if not outfile_base:
        popup("Error", "Output file base empty")
        return

    args = Args()
    settings_schema: dict[str, Any] = SettingsFile.SETTINGS_SCHEMA["properties"]
    for key, value in settings_schema.items():
        if key not in {
            keys.profile,
            keys.fix,
            keys.format,
            keys.extensions,
            keys.since,
            keys.until,
            keys.multi_thread,
            keys.multi_core,
        }:
            if value["type"] == "array":
                setattr(args, key, str_split_comma(values[key]))  # type: ignore
            else:
                setattr(args, key, values[key])

    if values[keys.prefix]:
        args.fix = keys.prefix
    elif values[keys.postfix]:
        args.fix = keys.postfix
    else:
        args.fix = keys.nofix

    out_format_selected = []
    for key in AVAILABLE_FORMATS:
        if values[key]:
            out_format_selected.append(key)
    args.format = out_format_selected

    for key in keys.since, keys.until:
        val = values[key]
        if not val or val == "":
            continue
        try:
            val = datetime.strptime(values[key], "%Y-%m-%d").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            popup(
                "Reminder",
                "Invalid date format. Correct format is YYYY-MM-DD. Please try again.",
            )
            return
        setattr(args, key, str(val))

    args.extensions = (
        str_split_comma(values[keys.extensions])
        if values[keys.extensions]
        else DEFAULT_EXTENSIONS
    )

    logger.info(f"{args = }")
    disable_buttons(window)
    window.perform_long_operation(
        lambda: gitinspector_main(args, start_time, window), keys.end
    )


def rungui(settings: Settings):
    recreate_window: bool = True
    while recreate_window:
        recreate_window = rungui_inner(settings)
        settings = Settings()
        set_logging_level_from_verbosity(settings.verbosity)


def rungui_inner(settings: Settings) -> bool:
    def window_state_from_settings(window: sg.Window, settings: Settings):
        settings_dict = asdict(settings)
        # settings_min is settings dict with 5 keys removed: keys.fix - keys.multi_core
        settings_min = {
            key: value
            for key, value in settings_dict.items()
            if key
            not in {
                keys.fix,
                keys.format,
                keys.profile,
                keys.multi_thread,
                keys.multi_core,
            }
        }
        for key, val in settings_min.items():
            if isinstance(val, list):
                value_list = ", ".join(val)
                window.Element(key).Update(value=value_list)  # type: ignore
            else:
                window.Element(key).Update(value=val)  # type: ignore

        # default values of boolean window.Element are False
        window.Element(settings.fix).Update(value=True)  # type: ignore

        if settings.format:
            if AUTO in settings.format:
                window.Element(AUTO).Update(value=True)  # type:ignore
            else:
                for key in set(AVAILABLE_FORMATS) - {AUTO}:
                    window.Element(key).Update(  # type:ignore
                        value=key in settings.format
                    )

        window.write_event_value(keys.input_fstrs, ".".join(settings.input_fstrs))
        window.write_event_value(keys.outfile_base, settings.outfile_base)
        window.write_event_value(keys.include_files, ".".join(settings.include_files))
        window.write_event_value(keys.verbosity, settings.verbosity)

    def disable_element(ele: sg.Element):
        ele.update(disabled=True)

    def enable_element(ele: sg.Element):
        ele.update(disabled=False)

    def update_column_height(
        element: sg.Element, window_height: int, last_window_height: int
    ):
        column_height = element.Widget.canvas.winfo_height()  # type: ignore
        if column_height < MAX_COL_HEIGHT or (window_height - last_window_height) <= 0:
            column_height = int(
                (window_height - WINDOW_HEIGHT_CORR) * state.col_percent / 100
            )
            column_height = min(column_height, MAX_COL_HEIGHT)
            element.Widget.canvas.configure({"height": column_height})  # type: ignore

    def update_col_percent(window: sg.Window, window_height: int, percent: int):
        config_column: sg.Column = window[keys.config_column]  # type: ignore
        if state.col_percent != percent:
            state.col_percent = percent
            update_column_height(config_column, window_height, window_height)

    def help_window():
        def help_text(string):
            return sg.Text(
                string, text_color="black", background_color="white", pad=(0, 0)
            )

        def hyperlink_text(url):
            return sg.Text(
                url,
                enable_events=True,
                font=("Helvetica", 12, "underline"),
                text_color="black",
                key="URL " + url,
                background_color="white",
                pad=(0, 0),
            )

        txt_start, url, txt_end = Help.help_doc
        layout = [
            [
                help_text(txt_start),
                hyperlink_text(url),
                help_text(txt_end),
            ]
        ]

        window = sg.Window(
            "Help Documentation",
            layout,
            icon=icon,
            finalize=True,
            keep_on_top=True,
            background_color="white",
        )
        assert window is not None

        while True:
            event, _ = window.read()  # type: ignore
            if event == sg.WINDOW_CLOSED:
                break
            if event.startswith("URL "):
                url = event.split(" ")[1]
                webbrowser.open(url)

        window.close()

    def popup_custom(title, message, user_input=None):
        layout = [[sg.Text(message, text_color="black", background_color="white")]]
        if user_input:
            layout += [
                [sg.Text(user_input, text_color="black", background_color="white")],
                [sg.OK()],
            ]
        else:
            layout += [[sg.OK(), sg.Cancel()]]
        window = sg.Window(title, layout, keep_on_top=True)
        event, _ = window.read()  # type: ignore
        window.close()
        return None if event != "OK" else event

    def log(*args: str, color=None):
        sg.cprint("\n".join(args), c=color)

    def use_single_repo():
        nonlocal input_paths
        return len(input_paths) == 1 and is_git_repo(str(input_paths[0]))

    def enable_buttons(window: sg.Window):
        for bt in buttons:
            update_button_state(window[bt], False)  # type: ignore

    def update_outfile_str(window: sg.Window, fix: str):

        def get_outfile_str() -> str:

            def get_rename_file() -> str:
                if not input_valid:
                    return ""

                if use_single_repo():
                    repo_name = input_paths[0].stem
                else:
                    repo_name = REPO_HINT

                if fix == keys.postfix:
                    return f"{state.outfile_base}-{repo_name}"
                elif fix == keys.prefix:
                    return f"{repo_name}-{state.outfile_base}"
                else:  # fix == keys.nofix
                    return state.outfile_base

            if input_fstrs:
                if input_valid:
                    out_name = get_rename_file()
                    if use_single_repo():
                        return str(input_paths[0].parent) + "/" + out_name
                    else:
                        return PARENT_HINT + out_name
                else:
                    return ""
            else:
                return ""

        window[keys.outfile_path].update(value=get_outfile_str())  # type: ignore

    logger.info(f"{settings = }")
    state: GUIState = GUIState(settings.col_percent)
    common.gui = True

    # Is set to True when handling "Reset settings file" menu item
    recreate_window: bool = False

    if sys.platform == "darwin":
        sg.set_options(font=("Any", 12))

    window: sg.Window
    window = make_window()
    common.gui_window = window
    _logging.gui_window = window

    window_state_from_settings(window, settings)  # type: ignore
    last_window_height: int = window.Size[1]  # type: ignore

    # Multi-core not working and not implemented in GUI. No checkbox to enable it.
    # Ensure that multi_core is False.
    settings.multi_core = False

    while True:
        event, values = window.read()  # type: ignore
        if DEBUG_SHOW_MAIN_EVENT_LOOP and (
            # ignore event generated by logger to prevent infinite loop
            not event
            == keys.debug
        ):
            if event in values.keys():
                value = values[event]
                logger.debug(
                    f"EVENT LOOP\n{event = },  {value = },  {type(value) = }\nvalues =\n{values}"
                )
            else:
                logger.debug(f"EVENT LOOP\n{event = }\nvalues = \n{values}")
        match event:
            case "Conf":
                window_height: int = window.Size[1]  # type: ignore
                if window_height == last_window_height:
                    continue
                config_column: sg.Column = window[keys.config_column]  # type: ignore
                update_column_height(config_column, window_height, last_window_height)
                last_window_height = window_height

            case keys.col_percent:
                update_col_percent(window, last_window_height, values[event])  # type: ignore

            case keys.execute:
                execute(
                    window,
                    values,
                    state.input_paths,
                    state.input_valid,
                    state.outfile_base,
                )

            case keys.clear:
                window[keys.multiline].update(value="")  # type: ignore

            case keys.show:
                SettingsFile.show()

            case keys.save:
                new_settings = Settings.from_values_dict(values)
                new_settings.save()
                log("Settings saved to " + SettingsFile.get_settings_file())

            case keys.save_as:
                destination = values[keys.save_as]
                new_settings = Settings.from_values_dict(values)
                new_settings.save_as(destination)
                log(f"Settings saved to {str(SettingsFile.get_location())}")

            case keys.load:
                settings_file = values[keys.load]
                settings_folder = str(Path(settings_file).parent)
                new_settings, _ = SettingsFile.load_from(settings_file)
                SettingsFile.set_location(settings_file)
                window[keys.load].InitialFolder = settings_folder  # type: ignore
                window_state_from_settings(window, new_settings)
                log(f"Settings loaded from {settings_file}")

            case keys.reset:
                res = popup_custom(
                    "Clear settings file",
                    "This will cause all settings to be reset to their default values. "
                    "Are you sure?",
                )
                if res == "OK":
                    SettingsFile.reset()
                    window.close()
                    recreate_window = True
                    break  # strangely enough also works without the break

            case keys.help:
                help_window()

            case keys.about:
                log(Help.about_info)

            # Window closed, or Exit button clicked
            case sg.WIN_CLOSED | keys.exit:
                break

            # Execute command has finished via window.perform_long_operation in
            # run_gitinspector().
            case keys.end:
                enable_buttons(window)

            case keys.log:
                message, end, color = values["log"]
                sg.cprint(message, end=end, text_color=color)

            # Custom logging for GUI, see gigui._logging.GUIOutputHandler.emit
            case keys.debug:
                message, color = values["debug"]
                sg.cprint(message, text_color=color)

            case keys.input_fstrs:
                input_string = values[event]

                input_fstrs = str_split_comma(input_string)
                input_paths = [Path(fstr) for fstr in input_fstrs]
                input_valid = paths_valid(input_paths, window[event])  # type: ignore
                state.input_fstrs = input_fstrs
                state.input_paths = input_paths
                state.input_valid = input_valid

                if not input_valid:
                    continue

                update_outfile_str(window, state.fix)
                if use_single_repo():
                    enable_element(window[keys.nofix])  # type: ignore
                    disable_element(window[keys.depth])  # type: ignore
                else:  # multiple repos
                    if state.fix == keys.nofix:
                        window.Element(keys.nofix).Update(value=False)  # type: ignore
                        window.Element(keys.prefix).Update(value=True)  # type: ignore
                        state.fix = keys.prefix
                    disable_element(window[keys.nofix])  # type: ignore
                    enable_element(window[keys.depth])  # type: ignore

            case keys.outfile_base:
                state.outfile_base = values[keys.outfile_base]
                update_outfile_str(window, state.fix)

            case event if event in (keys.postfix, keys.prefix, keys.nofix):
                state.fix = event
                update_outfile_str(window, event)

            case keys.auto:
                if values[keys.auto] is True:
                    window.Element(keys.html).Update(value=False)  # type: ignore
                    window.Element(keys.excel).Update(value=False)  # type: ignore
                else:
                    window.Element(keys.html).Update(value=True)  # type: ignore

            case keys.html | keys.excel:
                if values[event] is True:
                    window.Element(keys.auto).Update(value=False)  # type: ignore
                else:
                    if all(values[key] == 0 for key in AVAILABLE_FORMATS):
                        window.Element(keys.auto).Update(value=True)  # type: ignore

            case keys.include_files:
                if values[keys.include_files]:
                    disable_element(window[keys.n_files])  # type: ignore
                else:
                    enable_element(window[keys.n_files])  # type: ignore

            case keys.verbosity:
                set_logging_level_from_verbosity(values[event])

            case keys.open_webview:
                html_code, repo_name = values[event]
                webview_process = Process(
                    target=open_webview, args=(html_code, repo_name)
                )
                webview_process.daemon = True
                webview_process.start()
    return recreate_window


if __name__ == "__main__":
    current_settings: Settings
    error: str
    current_settings, error = SettingsFile.load()
    multiprocessing.freeze_support()
    rungui(current_settings)
