import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path

import PySimpleGUI as sg

from gigui.args_settings_keys import AUTO, Keys, Settings
from gigui.constants import (
    AVAILABLE_FORMATS,
    DEFAULT_FILE_BASE,
    DISABLED_COLOR,
    ENABLED_COLOR,
    MAX_COL_HEIGHT,
    PARENT_HINT,
    REPO_HINT,
    WINDOW_HEIGHT_CORR,
)
from gigui.gui.commongui import icon
from gigui.repo import is_git_repo
from gigui.tiphelp import Help
from gigui.typedefs import FileStr

keys = Keys()


# Initial values of GUIState are not used. They are set to their proper values during
# initialization of the run_inner function.
@dataclass
class GUIState:
    col_percent: int
    input_fstrs: list[FileStr] = field(default_factory=list)
    input_paths: list[Path] = field(default_factory=list)
    fix: str = keys.prefix
    input_valid: bool = False
    outfile_base: str = DEFAULT_FILE_BASE


class WindowButtons:
    def __init__(self, window: sg.Window):
        self.window = window

        self.buttons: list[str] = [
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

    def disable_all(self):
        for button in self.buttons:
            self._update_button_state(button, True)

    def enable_all(self):
        for button in self.buttons:
            self._update_button_state(button, False)

    def _update_button_state(self, button: str, disabled: bool):
        if disabled:
            color = DISABLED_COLOR
        else:
            color = ENABLED_COLOR
        self.window[button].update(disabled=disabled, button_color=color)  # type: ignore


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
    element: sg.Element, window_height: int, last_window_height: int, state: GUIState
):
    column_height = element.Widget.canvas.winfo_height()  # type: ignore
    if column_height < MAX_COL_HEIGHT or (window_height - last_window_height) <= 0:
        column_height = int(
            (window_height - WINDOW_HEIGHT_CORR) * state.col_percent / 100
        )
        column_height = min(column_height, MAX_COL_HEIGHT)
        element.Widget.canvas.configure({"height": column_height})  # type: ignore


def update_col_percent(
    window: sg.Window, window_height: int, percent: int, state: GUIState
):
    config_column: sg.Column = window[keys.config_column]  # type: ignore
    if state.col_percent != percent:
        state.col_percent = percent
        update_column_height(config_column, window_height, window_height, state)


def help_window():
    def help_text(string):
        return sg.Text(string, text_color="black", background_color="white", pad=(0, 0))

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


def use_single_repo(input_paths: list[Path]) -> bool:
    return len(input_paths) == 1 and is_git_repo(str(input_paths[0]))


def update_outfile_str(
    window: sg.Window,
    state: GUIState,
):
    def get_outfile_str() -> str:

        def get_rename_file() -> str:
            if not state.input_valid:
                return ""

            if use_single_repo(state.input_paths):
                repo_name = state.input_paths[0].stem
            else:
                repo_name = REPO_HINT

            if state.fix == keys.postfix:
                return f"{state.outfile_base}-{repo_name}"
            elif state.fix == keys.prefix:
                return f"{repo_name}-{state.outfile_base}"
            else:  # fix == keys.nofix
                return state.outfile_base

        if state.input_fstrs:
            if state.input_valid:
                out_name = get_rename_file()
                if use_single_repo(state.input_paths):
                    return str(state.input_paths[0].parent) + "/" + out_name
                else:
                    return PARENT_HINT + out_name
            else:
                return ""
        else:
            return ""

    window[keys.outfile_path].update(value=get_outfile_str())  # type: ignore
