import webbrowser
from copy import copy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Union

import dearpygui.dearpygui as dpg
from git import InvalidGitRepositoryError, NoSuchPathError
from git import Repo as GitRepo

from gigui.args_settings import Args, Settings, SettingsFile
from gigui.constants import (
    AUTO,
    DEFAULT_FILE_BASE,
    DISABLED_COLOR,
    DYNAMIC_BLAME_HISTORY,
    ENABLED_COLOR,
    FILE_FORMATS,
    INVALID_INPUT_RGBA_COLOR,
    NONE,
    PARENT_HINT,
    PREPOSTFIX_OPTIONS,
    REPO_HINT,
    VALID_INPUT_RGBA_COLOR,
)
from gigui.keys import Keys
from gigui.tiphelp import Help
from gigui.typedefs import FilePattern, FileStr
from gigui.utils import get_posix_dir_matches_for, to_posix_fstrs

keys = Keys()

class DPGBase:
    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        self.args: Args
        self.window: dict[str, Union[int, str]]

        # All file strings are in POSIX format, containing only forward slashes as path
        # separators, apart from outfile_base which is not supposed to contain path
        # separators.
        self.col_percent: int = self.settings.col_percent
        self.gui_settings_full_path: bool = self.settings.gui_settings_full_path
        self.multithread: bool = self.settings.multithread
        self.input_fstrs: list[FilePattern] = []  # as entered by user
        self.input_fstr_matches: list[FileStr] = []
        self.input_repo_path: Path | None = None
        self.fix: str = keys.prefix
        self.outfile_base: FileStr = DEFAULT_FILE_BASE
        self.subfolder: FileStr = ""
        self.subfolder_valid: bool = True
        self.buttons: list[str] = [
            keys.run,
            keys.clear,
            keys.save,
            keys.save_as,
            keys.load,
            keys.reset,
            keys.help,
            keys.about,
            keys.exit,
            keys.browse_input_fstr,
        ]

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

        self.update_input_fstrs(", ".join(settings.input_fstrs))
        self.update_window_value(keys.outfile_base, settings.outfile_base)
        self.update_window_value(
            keys.include_files, ", ".join(settings.include_files)
        )
        self.update_window_value(keys.subfolder, settings.subfolder)
        self.update_window_value(keys.verbosity, settings.verbosity)

        # First set column height too big, then set it to the correct value to ensure
        # correct displaying of the column height
        self.update_window_value(
            keys.col_percent, min(settings.col_percent + 5, 100)
        )
        self.update_window_value(keys.col_percent, settings.col_percent)
        if settings.gui_settings_full_path:
            settings_fstr = str(SettingsFile.get_location_path())
        else:
            settings_fstr = SettingsFile.get_location_path().stem
        self.update_window_value(keys.settings_file, settings_fstr)  # type: ignore

    def update_window_value(self, key: str, value: Any) -> None:
        dpg.set_value(self.window[key], value)

    def update_input_fstrs(self, value: str) -> None:
        self.update_window_value(keys.input_fstrs, value)
        self.process_input_fstrs(value)

    def update_outfile_str(self) -> None:
        def get_outfile_path() -> Path:
            def get_rename_file() -> str:
                if self.input_repo_path:
                    repo_name = self.input_repo_path.stem
                else:
                    repo_name = REPO_HINT

                if self.fix == keys.postfix:
                    return f"{self.outfile_base}-{repo_name}"
                elif self.fix == keys.prefix:
                    return f"{repo_name}-{self.outfile_base}"
                else:  # fix == keys.nofix
                    return self.outfile_base

            if not self.input_fstrs or not self.input_fstr_matches:
                return Path("")

            out_name = get_rename_file()
            if self.input_repo_path:
                return self.input_repo_path.parent / out_name
            else:
                return Path(PARENT_HINT) / out_name

        self.update_window_value(keys.outfile_path, str(get_outfile_path()))  # type: ignore

    def update_settings_file_str(
        self,
        full_path: bool,
    ) -> None:
        if full_path:
            file_string = str(SettingsFile.get_location_path())
        else:
            file_string = SettingsFile.get_location_path().stem
        self.window[keys.settings_file].update(value=file_string)  # type: ignore

    def process_input_fstrs(self, input_fstr_patterns: str) -> None:
        try:
            input_fstrs: list[FileStr] = input_fstr_patterns.split(",")
        except ValueError:
            self.update_input_backgroundcolor(keys.input_fstrs, INVALID_INPUT_RGBA_COLOR)  # type: ignore
            return
        self.input_fstrs = to_posix_fstrs(input_fstrs)
        self.process_inputs()

    def process_inputs(self) -> None:
        if not self.input_fstrs:
            self.input_fstr_matches = []
            self.input_repo_path = None
            self.show_nofix_option()
            enable_element(keys.depth)  # type: ignore
            self.update_outfile_str()
            return

        matches: list[FileStr] = self.get_posix_dir_matches(self.input_fstrs, keys.input_fstrs)  # type: ignore
        self.input_fstr_matches = matches

        if len(matches) == 1 and is_git_repo(Path(matches[0])):
            self.input_repo_path = Path(matches[0])
            self.show_nofix_option()
            disable_element(keys.depth)  # type: ignore
            self.update_outfile_str()
            self.check_subfolder()
        else:
            self.input_repo_path = None
            self.hide_nofix_option()
            enable_element(keys.depth)  # type: ignore
            self.update_outfile_str()

    def get_posix_dir_matches(
        self, patterns: list[FilePattern], input_key: str, colored: bool = True
    ) -> list[FileStr]:
        all_matches: list[FileStr] = []
        for pattern in patterns:
            matches: list[FileStr] = get_posix_dir_matches_for(pattern)
            if not matches:
                if colored:
                    self.update_input_backgroundcolor(input_key, INVALID_INPUT_RGBA_COLOR)
                return []
            else:
                all_matches.extend(matches)

        self.update_input_backgroundcolor(input_key, VALID_INPUT_RGBA_COLOR)
        unique_matches = []
        for match in all_matches:
            if match not in unique_matches:
                unique_matches.append(match)
        return unique_matches

    def check_subfolder(self) -> None:
        # check_subfolder() is called by process_inputs() when state.input_repo_path
        # is valid
        if not self.subfolder:
            self.subfolder_valid = True
            self.update_input_backgroundcolor(keys.subfolder, VALID_INPUT_RGBA_COLOR)  # type: ignore
            return

        subfolder_exists: bool
        repo = GitRepo(self.input_repo_path)  # type: ignore
        tree = repo.head.commit.tree

        subfolder_path = self.subfolder.split("/")
        if not subfolder_path[0]:
            subfolder_path = subfolder_path[1:]
        if not subfolder_path[-1]:
            subfolder_path = subfolder_path[:-1]
        subfolder_exists = True
        for part in subfolder_path:
            try:
                # Note that "if part in tree" does not work properly:
                # - It works for the first part, but not for the second part.
                # - For the second part, it always returns False, even if the
                #   part (subfolder) exists.
                tree_or_blob = tree[part]  # type: ignore
                if not tree_or_blob.type == "tree":  # Check if the part is a directory
                    subfolder_exists = False
                    break
                tree = tree_or_blob
            except KeyError:
                subfolder_exists = False
                break

        if subfolder_exists:
            self.subfolder_valid = True
            self.update_input_backgroundcolor(keys.subfolder, VALID_INPUT_RGBA_COLOR)  # type: ignore
        else:
            self.subfolder_valid = False
            self.update_input_backgroundcolor(keys.subfolder, INVALID_INPUT_RGBA_COLOR)  # type: ignore

    def process_n_files(self, n_files_str: str, key: str) -> None:
        # Filter out any initial zero and all non-digit characters
        filtered_str = "".join(filter(str.isdigit, n_files_str)).lstrip("0")
        self.update_window_value(key, filtered_str)

    def process_view_format_radio_buttons(self, html_key: str) -> None:
        match html_key:
            case keys.auto:
                self.update_window_value(keys.dynamic_blame_history, False)  # type: ignore
            case keys.dynamic_blame_history:
                self.update_window_value(keys.auto, False)  # type: ignore
                self.update_window_value(keys.html, False)  # type: ignore
                self.update_window_value(keys.excel, False)  # type: ignore
            case keys.html:
                self.update_window_value(keys.dynamic_blame_history, False)  # type: ignore
            case keys.excel:
                self.update_window_value(keys.dynamic_blame_history, False)  # type: ignore

    def set_args(self, values: dict) -> None:
        self.args = Args()
        settings_schema: dict[str, Any] = SettingsFile.SETTINGS_SCHEMA["properties"]
        for schema_key, schema_value in settings_schema.items():
            if schema_key not in {
                keys.profile,
                keys.fix,
                keys.n_files,
                keys.view,
                keys.file_formats,
                keys.since,
                keys.until,
                keys.multithread,
                keys.gui_settings_full_path,
            }:
                if schema_value["type"] == "array":
                    setattr(self.args, schema_key, values[schema_key].split(","))  # type: ignore
                else:
                    setattr(self.args, schema_key, values[schema_key])

        self.args.multithread = self.multithread

        if values[keys.prefix]:
            self.args.fix = keys.prefix
        elif values[keys.postfix]:
            self.args.fix = keys.postfix
        else:
            self.args.fix = keys.nofix

        if values[keys.auto]:
            self.args.view = AUTO
        elif values[keys.dynamic_blame_history]:
            self.args.view = DYNAMIC_BLAME_HISTORY
        else:
            self.args.view = NONE

        self.args.n_files = 0 if not values[keys.n_files] else int(values[keys.n_files])

        file_formats = []
        for schema_key in FILE_FORMATS:
            if values[schema_key]:
                file_formats.append(schema_key)
        self.args.file_formats = file_formats

        for schema_key in keys.since, keys.until:
            val = values[schema_key]
            if not val or val == "":
                continue
            try:
                val = datetime.strptime(values[schema_key], "%Y-%m-%d").strftime(
                    "%Y-%m-%d"
                )
            except (TypeError, ValueError):
                # popup(
                #     "Reminder",
                #     "Invalid date format. Correct format is YYYY-MM-DD. Please try again.",
                # )
                return
            setattr(self.args, schema_key, str(val))

        self.args.normalize()

    def update_input_backgroundcolor(self, key: str, color: tuple[int, ...]) -> None:
        # dpg.set_value(key + "theme", color)
        print("background")

    def hide_nofix_option(self) -> None:
        options = tuple(PREPOSTFIX_OPTIONS.values())[:-1]
        dpg.configure_item(keys.fix, items=options)

    def show_nofix_option(self) -> None:
        dpg.configure_item(keys.fix, items=tuple(PREPOSTFIX_OPTIONS.values()))

    def disable_buttons(self) -> None:
        for button in self.buttons:
            self.update_button_state(button, enabled=False)

    def enable_buttons(self) -> None:
        for button in self.buttons:
            self.update_button_state(button, enabled=True)

    def update_button_state(self, key: str, enabled: bool) -> None:
        print(key)
        # print(self.window[key])
        dpg.configure_item(key, enabled=enabled)
        # if disabled:
        #     color = DISABLED_COLOR
        # else:
        #     color = ENABLED_COLOR
        # self.window[button].update(disabled=disabled, button_color=color)  # type: ignore

    def log(self, *args: str, color:tuple[int, ...]=(-255, 0, 0, 255)) -> None:
        dpg.add_text("\n".join(args), color=color, parent=keys.multiline, wrap=-1)


# Function to open the hyperlink
def open_hyperlink(sender, app_data, user_data):
    webbrowser.open(user_data)

def help_window() -> None:
    txt_start, url, txt_end = Help.help_doc
    with dpg.theme() as hyperlink_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))  # Transparent background
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (0, 102, 204, 50))  # Light hover effect
            dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 102, 204))  # Blue text color

    with dpg.window(label="Help Documentation", pos=(40, 100), width=550, height=100, show=True, tag="hyperlink_window"):
        with dpg.group(horizontal=True):
            dpg.add_text(txt_start)
            hyperlink_button = dpg.add_button(label=url, callback=open_hyperlink, user_data=url)
            dpg.add_text(txt_end)
            dpg.bind_item_theme(hyperlink_button, hyperlink_theme)  # Apply the hyperlink theme

        dpg.add_spacer(height=10)  # Add some space
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=250)  # Adjust width to center the button
            dpg.add_button(label="OK", callback=lambda: dpg.configure_item("hyperlink_window", show=False))


def use_single_repo(input_paths: list[Path]) -> bool:
    return len(input_paths) == 1 and is_git_repo(input_paths[0])


def is_git_repo(path: Path) -> bool:
    try:
        if path.stem == ".resolve":
            # path.resolve() crashes on macOS for path.stem == ".resolve"
            return False
        git_path = (path / ".git").resolve()
        if not git_path.is_dir():
            return False
    except (PermissionError, TimeoutError):  # git_path.is_symlink() may time out
        return False

    try:
        # The default True value of expand_vars leads to confusing warnings from
        # GitPython for many paths from system folders.
        repo = GitRepo(path, expand_vars=False)
        return not repo.bare
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False


def enable_element(key: str) -> None:
    dpg.configure_item(key, enabled=True)

def disable_element(key: str) -> None:
    dpg.configure_item(key, enabled=False)


def popup(title: str, message: str):
    with dpg.window(label=title, modal=True, tag="popup_window"):
        dpg.add_text(message)
        dpg.add_button(label="Ok", callback=lambda: dpg.delete_item("popup_window"))
