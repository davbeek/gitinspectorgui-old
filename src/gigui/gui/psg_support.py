import glob
import os
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path

import PySimpleGUI as sg  # type: ignore

from gigui.args_settings import Settings, SettingsFile
from gigui.constants import (
    AVAILABLE_FORMATS,
    DEFAULT_FILE_BASE,
    DISABLED_COLOR,
    ENABLED_COLOR,
    INVALID_INPUT_COLOR,
    MAX_COL_HEIGHT,
    PARENT_HINT,
    REPO_HINT,
    VALID_INPUT_COLOR,
    WINDOW_HEIGHT_CORR,
)
from gigui.keys import Keys
from gigui.repo import is_git_repo
from gigui.tiphelp import Help
from gigui.typedefs import FilePattern, FileStr

keys = Keys()


# Initial values of GUIState are not used. They are set to their proper values during
# initialization of the run_inner function.
@dataclass
class GUIState:
    col_percent: int
    gui_settings_full_path: bool
    input_patterns: list[FilePattern] = field(default_factory=list)
    input_fstrs: list[FileStr] = field(default_factory=list)
    input_repo_path: Path | None = None
    fix: str = keys.prefix
    outfile_base: str = DEFAULT_FILE_BASE
    subfolder_path: Path = Path()
    n_files: int = 0


class WindowButtons:
    def __init__(self, window: sg.Window):
        self.window = window

        self.buttons: list[str] = [
            keys.execute,
            keys.clear,
            keys.save,
            keys.save_as,
            keys.load,
            keys.reset,
            keys.help,
            keys.about,
            keys.browse_input_fstr,
        ]

    def disable_all(self) -> None:
        for button in self.buttons:
            self._update_button_state(button, True)

    def enable_all(self) -> None:
        for button in self.buttons:
            self._update_button_state(button, False)

    def _update_button_state(self, button: str, disabled: bool) -> None:
        if disabled:
            color = DISABLED_COLOR
        else:
            color = ENABLED_COLOR
        self.window[button].update(disabled=disabled, button_color=color)  # type: ignore


def window_state_from_settings(window: sg.Window, settings: Settings) -> None:
    settings_dict = asdict(settings)
    # settings_min is settings dict with 5 keys removed: keys.fix - keys.multi_core
    settings_min = {
        key: value
        for key, value in settings_dict.items()
        if key
        not in {
            keys.fix,
            keys.format,
            keys.gui_settings_full_path,
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
        for key in set(AVAILABLE_FORMATS):
            window.Element(key).Update(  # type:ignore
                value=key in settings.format
            )

    window.write_event_value(keys.input_fstrs, ",".join(settings.input_fstrs))
    window.write_event_value(keys.outfile_base, settings.outfile_base)
    window.write_event_value(keys.include_files, ",".join(settings.include_files))
    window.write_event_value(keys.verbosity, settings.verbosity)

    # First set column height too big, then set it to the correct value to ensure
    # correct displaying of the column height
    window.write_event_value(keys.col_percent, min(settings.col_percent + 5, 100))
    window.write_event_value(keys.col_percent, settings.col_percent)
    if settings.gui_settings_full_path:
        settings_fstr = str(SettingsFile.get_location())
    else:
        settings_fstr = SettingsFile.get_location().stem
    window[keys.settings_file].update(value=settings_fstr)  # type: ignore


def disable_element(ele: sg.Element) -> None:
    ele.update(disabled=True)


def enable_element(ele: sg.Element) -> None:
    ele.update(disabled=False)


def update_column_height(
    element: sg.Element, window_height: int, last_window_height: int, state: GUIState
) -> None:
    column_height = element.Widget.canvas.winfo_height()  # type: ignore
    if column_height < MAX_COL_HEIGHT or (window_height - last_window_height) <= 0:
        column_height = int(
            (window_height - WINDOW_HEIGHT_CORR) * state.col_percent / 100
        )
        column_height = min(column_height, MAX_COL_HEIGHT)
        element.Widget.canvas.configure({"height": column_height})  # type: ignore


def update_col_percent(
    window: sg.Window, window_height: int, percent: int, state: GUIState
) -> None:
    config_column: sg.Column = window[keys.config_column]  # type: ignore
    if state.col_percent != percent:
        state.col_percent = percent
        update_column_height(config_column, window_height, window_height, state)


def help_window() -> None:
    def help_text(string) -> sg.Text:
        return sg.Text(string, text_color="black", background_color="white", pad=(0, 0))

    def hyperlink_text(url) -> sg.Text:
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
        ],
        [sg.VPush()],  # Add vertical space
        [sg.VPush()],  # Add vertical space
        [sg.Column([[sg.Button("OK", key="OK_BUTTON")]], justification="center")],
    ]

    window = sg.Window(
        "Help Documentation",
        layout,
        finalize=True,
        keep_on_top=True,
        background_color="white",
    )

    while True:
        event, _ = window.read()  # type: ignore
        if event == sg.WINDOW_CLOSED or event == "OK_BUTTON":
            break
        if event.startswith("URL "):
            url = event.split(" ")[1]
            webbrowser.open(url)

    window.close()


def popup(title, message):
    sg.popup(
        title,
        message,
        keep_on_top=True,
        text_color="black",
        background_color="white",
    )


def popup_custom(title, message, user_input=None) -> str | None:
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


def log(*args: str, color=None) -> None:
    sg.cprint("\n".join(args), c=color)


def use_single_repo(input_paths: list[Path]) -> bool:
    return len(input_paths) == 1 and is_git_repo(input_paths[0])


def update_outfile_str(
    state: GUIState,
    window: sg.Window,
) -> None:
    def get_outfile_str() -> str:

        def get_rename_file() -> str:
            if state.input_repo_path:
                repo_name = state.input_repo_path.stem
            else:
                repo_name = REPO_HINT

            if state.fix == keys.postfix:
                return f"{state.outfile_base}-{repo_name}"
            elif state.fix == keys.prefix:
                return f"{repo_name}-{state.outfile_base}"
            else:  # fix == keys.nofix
                return state.outfile_base

        if not state.input_patterns or not state.input_fstrs:
            return ""

        out_name = get_rename_file()
        if state.input_repo_path:
            return str(state.input_repo_path.parent) + "/" + out_name
        else:
            return PARENT_HINT + out_name

    window[keys.outfile_path].update(value=get_outfile_str())  # type: ignore


def update_settings_file_str(
    full_path: bool,
    window: sg.Window,
) -> None:
    if full_path:
        file_string = str(SettingsFile.get_location())
    else:
        file_string = SettingsFile.get_location().stem
    window[keys.settings_file].update(value=file_string)  # type: ignore


def process_input_patterns(
    state: GUIState,
    sg_input: sg.Input,
    window: sg.Window,
) -> GUIState:
    if not state.input_patterns:
        state.input_fstrs = []
        state.input_repo_path = None
        enable_element(window[keys.prefix])  # type: ignore
        enable_element(window[keys.postfix])  # type: ignore
        enable_element(window[keys.nofix])  # type: ignore
        enable_element(window[keys.depth])  # type: ignore
        update_outfile_str(state, window)
        return state

    matches: list[FileStr] = get_dir_matches(state.input_patterns, sg_input)  # type: ignore
    state.input_fstrs = matches

    if len(matches) == 1 and is_git_repo(Path(matches[0])):
        state.input_repo_path = Path(matches[0])
        enable_element(window[keys.prefix])  # type: ignore
        enable_element(window[keys.postfix])  # type: ignore
        enable_element(window[keys.nofix])  # type: ignore
        disable_element(window[keys.depth])  # type: ignore
        update_outfile_str(state, window)
        return state
    else:
        state.input_repo_path = None
        enable_element(window[keys.prefix])  # type: ignore
        enable_element(window[keys.postfix])  # type: ignore
        disable_element(window[keys.nofix])  # type: ignore
        enable_element(window[keys.depth])  # type: ignore
        update_outfile_str(state, window)
        return state


def process_subfolder(
    subfolder: FileStr,
    sg_input: sg.Input,
) -> Path | None:
    if not subfolder:
        return None

    path = set_dir_path(subfolder, sg_input)  # type: ignore
    return path


def get_dir_matches(
    patterns: list[FilePattern], sg_input: sg.Input, colored: bool = True
) -> list[FileStr]:
    all_matches: list[FileStr] = []
    for pattern in patterns:
        matches: list[FileStr] = [
            match for match in glob.glob(pattern) if os.path.isdir(match)
        ]
        if not matches:
            if colored:
                sg_input.update(background_color=INVALID_INPUT_COLOR)
            return []
        else:
            all_matches.extend(matches)
    sg_input.update(background_color=VALID_INPUT_COLOR)
    unique_matches = []
    for match in all_matches:
        if match not in unique_matches:
            unique_matches.append(match)
    return unique_matches


def set_dir_path(state: GUIState, subfolder: FileStr, sg_input: sg.Input) -> None:
    this_dir_path = Path(__file__).resolve().parent
    repo_path = this_dir_path.parent.parent.parent
    subfolder_path = repo_path / Path(subfolder)
    if subfolder_path.is_dir():
        sg_input.update(background_color=VALID_INPUT_COLOR)
        state.subfolder_path = subfolder_path
    else:
        sg_input.update(background_color=INVALID_INPUT_COLOR)
        state.subfolder_path = repo_path


def process_include_files(patterns: str, input_field: sg.Input) -> None:
    # Filter out all non-alpha-numerical characters except allowed special characters.
    # Commas are allowed to separate patterns and asterisks are allowed as wildcards.
    allowed_chars = set(" .,-_*")
    filtered_patterns = "".join(
        c for c in patterns if c.isalnum() or c in allowed_chars
    )
    input_field.update(filtered_patterns)


def process_n_files(state: GUIState, n_files_str: str, input_field: sg.Input) -> None:
    # Filter out any initial zero and all non-digit characters
    filtered_str = "".join(filter(str.isdigit, n_files_str)).lstrip("0")
    n_files: int = int(filtered_str) if filtered_str else 0
    input_field.update(filtered_str)
    state.n_files = n_files
