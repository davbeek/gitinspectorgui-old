# noinspection PyPep8Naming
import logging
from pathlib import Path

import PySimpleGUI as sg

from gigui._logging import add_gui_handler
from gigui.args_settings_keys import AUTO, VIEWER_CHOICES, Keys, SettingsFile
from gigui.constants import (
    ENABLED_COLOR,
    INIT_COL_PERCENT,
    MAX_COL_HEIGHT,
    OPTION_TITLE_WIDTH,
    WINDOW_HEIGHT_CORR,
    WINDOW_SIZE_X,
    WINDOW_SIZE_Y,
)
from gigui.gui.commongui import icon
from gigui.tiphelp import Tip

logger = logging.getLogger(__name__)

RADIO_BUTTON_GROUP_FIX_ID = 2
BUTTON_PADDING = (3, 2)

tip = Tip()
keys = Keys()


# Do NOT use None as default value for size, because that will lead to an exception:
SIZE_NONE = (None, None)


def button(text: str, key: str, pad=BUTTON_PADDING) -> sg.Button:
    return sg.B(
        text,
        k=key,
        pad=pad,
        button_color=ENABLED_COLOR,
    )


def name_basic(text: str, tooltip, size=SIZE_NONE, pad=None) -> sg.Text:
    return sg.Text(
        text,
        tooltip=tooltip,
        size=size,
        pad=pad,
        text_color="black",
        background_color="white",
    )


def name_header(text: str, tooltip) -> sg.Text:
    return name_basic(
        text,
        tooltip,
        pad=(0, 4),
        size=OPTION_TITLE_WIDTH,
    )


def name_choice(text: str, tooltip) -> sg.Text:
    return name_basic(text, tooltip, pad=(0, 0))


def name_input(text: str, tooltip, pad=(0, 0)) -> sg.Text:
    return name_basic(text, tooltip, pad=pad)


def input_box(
    key: str,
    disabled: bool = False,
    size=SIZE_NONE,
) -> sg.Input:
    return sg.Input(
        k=key,
        pad=((3, 2), 2),
        expand_x=True,
        enable_events=True,
        disabled=disabled,
        tooltip=getattr(tip, key),
        text_color="black",
        background_color="white",
        disabled_readonly_background_color="grey92",
        size=size,
    )


def checkbox(
    text: str,
    key: str,
    disabled=False,
) -> sg.Checkbox:
    return sg.Checkbox(
        text,
        k=key,
        tooltip=getattr(tip, key),
        pad=((0, 6), 0),
        enable_events=True,
        disabled=disabled,
        text_color="black",
        background_color="white",
    )


def spinbox(key: str, spin_range: list[int], pad=None) -> sg.Spin:
    return sg.Spin(
        spin_range,
        initial_value=1,
        k=key,
        enable_events=True,
        pad=((3, 10), None) if pad is None else pad,
        size=2,
        readonly=True,
        background_color="white",
    )


def radio(
    text: str,
    group_id: int,
    key: str,
) -> sg.Radio:
    return sg.Radio(
        text,
        group_id,
        k=key,
        default=False,
        enable_events=True,
        pad=((0, 0), 2),
        tooltip=getattr(tip, key),
        text_color="black",
        background_color="white",
    )


def frame(title: str, layout: list, pad: tuple[int, int] = (0, 0)) -> sg.Frame:
    return sg.Frame(
        layout=layout,
        title=title,
        relief=sg.RELIEF_SUNKEN,
        expand_x=True,
        pad=pad,
        title_color="black",
        background_color="white",
    )


def column(layout: list, col_height, key=None) -> sg.Column:
    return sg.Column(
        layout,
        k=key,
        vertical_scroll_only=True,
        scrollable=True,
        expand_x=True,
        size=(None, col_height),
        background_color="white",
    )


def configure_canvas(event, canvas, frame_id):
    canvas.itemconfig(frame_id, width=event.width)


def configure_frame(canvas):
    canvas.configure(scrollregion=canvas.bbox("all"))


def popup(title, message):
    sg.popup(title, message, keep_on_top=True, text_color="black")


# pylint: disable=too-many-locals
def make_window() -> sg.Window:
    # Cannot use logging here, as there is not yet any new window to log to and the
    # window in common and _logging still points to the old window after a "Reset
    # settings file" command has been given.

    col_height = int((WINDOW_SIZE_Y - WINDOW_HEIGHT_CORR) * INIT_COL_PERCENT / 100)
    col_height = min(MAX_COL_HEIGHT, col_height)

    sg.theme("SystemDefault")

    io_config = frame(
        "IO configuration",
        layout=[
            [
                name_header("Input folder path", tooltip=tip.input_fstrs),
                input_box(
                    keys.input_fstrs,
                ),
                # s.FolderBrowse automatically puts the selected folder string into the
                # preceding input box.
                sg.FolderBrowse(
                    key=keys.browse_input_fstr,
                    initial_folder=Path.home(),
                ),
            ],
            [
                name_header("Output file path", tip.outfile_path),
                input_box(
                    keys.outfile_path,
                    disabled=True,
                ),
            ],
            [
                name_header("Output prepostfix", tip.out_file_option),
                radio(
                    "Prefix with repository",
                    RADIO_BUTTON_GROUP_FIX_ID,
                    keys.prefix,
                ),
                radio(
                    "Postfix with repository",
                    RADIO_BUTTON_GROUP_FIX_ID,
                    keys.postfix,
                ),
                radio(
                    "No prefix or postfix",
                    RADIO_BUTTON_GROUP_FIX_ID,
                    keys.nofix,
                ),
            ],
            [
                name_header("Options", ""),
                name_choice(
                    "Search depth",
                    tooltip=tip.depth,
                ),
                spinbox(
                    keys.depth,
                    list(range(10)),
                ),
                name_input("Output file base", tooltip=tip.outfile_base),
                input_box(
                    keys.outfile_base,
                ),
            ],
        ],
    )

    output_formats = frame(
        "Output generation and formatting",
        layout=[
            [
                frame(
                    "",
                    layout=[
                        [
                            name_header("Output formats", tooltip=tip.format_excel),
                            checkbox(
                                keys.auto,
                                keys.auto,
                            ),
                            checkbox(
                                keys.html,
                                keys.html,
                            ),
                            checkbox(
                                keys.excel,
                                keys.excel,
                            ),
                            sg.Text("", expand_x=True, background_color="white"),
                        ],
                        [
                            name_header("Options", ""),
                            checkbox(
                                "Show renames",
                                key=keys.show_renames,
                            ),
                            checkbox(
                                "Scaled percentages",
                                key=keys.scaled_percentages,
                            ),
                            checkbox(
                                "Blame omit exclusions",
                                key=keys.blame_omit_exclusions,
                            ),
                            checkbox(
                                "Blame skip",
                                key=keys.blame_skip,
                            ),
                        ],
                        [
                            name_header("Options", ""),
                            name_choice(
                                "Viewer",
                                tooltip=tip.viewer,
                            ),
                            sg.Combo(
                                VIEWER_CHOICES,
                                default_value=AUTO,
                                key=keys.viewer,
                                enable_events=True,
                                size=5,
                                pad=((3, 10), 2),
                                readonly=True,
                                text_color="black",
                                background_color="white",
                            ),
                            name_choice(
                                "Debug",
                                tooltip=tip.verbosity,
                            ),
                            spinbox(
                                keys.verbosity,
                                list(range(3)),
                            ),
                            name_choice(
                                "Dry run",
                                tooltip=tip.dry_run,
                            ),
                            spinbox(
                                keys.dry_run,
                                list(range(3)),
                            ),
                        ],
                    ],
                ),
            ],
        ],
    )

    general_config_frame = frame(
        "Inclusions and exclusions",
        layout=[
            [
                name_header("Include files", tooltip=tip.file_options),
                name_choice(
                    "N files",
                    tooltip=tip.n_files,
                ),
                spinbox(
                    keys.n_files,
                    list(range(100)),
                ),
                name_input(
                    "File pattern",
                    tooltip=tip.include_files,
                ),
                input_box(
                    keys.include_files,
                    size=10,
                ),
                name_input(
                    "Subfolder",
                    tooltip=tip.subfolder,
                    pad=((6, 0), 0),
                ),
                input_box(
                    keys.subfolder,
                    size=10,
                ),
            ],
            [
                name_header("Options", ""),
                name_input(
                    "Since",
                    tooltip=tip.since,
                ),
                sg.Input(
                    k=keys.since,
                    size=(11, 1),
                    enable_events=True,
                    tooltip=tip.since_box,
                    text_color="black",
                    background_color="white",
                ),
                sg.CalendarButton(
                    ".",
                    target=keys.since,
                    format="%Y-%m-%d",
                    begin_at_sunday_plus=1,
                    no_titlebar=False,
                    title="Choose Since Date",
                ),
                name_input(
                    "Until",
                    tooltip=tip.until,
                ),
                sg.Input(
                    k=keys.until,
                    size=(11, 1),
                    enable_events=True,
                    tooltip=tip.until_box,
                    text_color="black",
                    background_color="white",
                ),
                sg.CalendarButton(
                    ".",
                    target=keys.until,
                    format="%Y-%m-%d",
                    begin_at_sunday_plus=1,
                    no_titlebar=False,
                    title="Choose Until Date",
                ),
                name_input(
                    "Extensions",
                    tooltip=tip.extensions,
                ),
                input_box(
                    keys.extensions,
                ),
            ],
        ],
    )

    analysis_options = frame(
        "Analysis options",
        layout=[
            [
                name_header("Include", ""),
                checkbox(
                    "Deletions",
                    keys.deletions,
                ),
                checkbox(
                    "Whitespace",
                    keys.whitespace,
                ),
                checkbox(
                    "Empty lines",
                    keys.empty_lines,
                ),
                checkbox(
                    "Comments",
                    keys.comments,
                ),
                name_choice(
                    "Copy move",
                    tooltip=tip.copy_move,
                ),
                spinbox(
                    keys.copy_move,
                    list(range(5)),
                ),
            ],
        ],
    )
    size = (10, None)
    title_size = 10
    left_column = [
        [
            name_header("Author", tooltip=tip.ex_authors),
            input_box(
                keys.ex_authors,
                size=size,
            ),
        ],
        [
            name_header("File/Folder", tooltip=tip.ex_files),
            input_box(keys.ex_files, size=size),
        ],
    ]

    right_column = [
        [
            name_basic("Email", tooltip=tip.ex_emails, size=title_size),
            input_box(
                keys.ex_emails,
                size=size,
            ),
        ],
        [
            name_basic("Revision hash", tooltip=tip.ex_revisions, size=title_size),
            input_box(
                keys.ex_revisions,
                size=size,
            ),
        ],
    ]

    exclusion_patterns_frame = frame(
        "Exclusion patterns",
        layout=[
            [
                sg.Column(
                    left_column, expand_x=True, pad=(0, 0), background_color="white"
                ),
                sg.Column(
                    right_column, expand_x=True, pad=(0, 0), background_color="white"
                ),
            ],
            [
                name_header("Commit message", tooltip=tip.ex_messages),
                input_box(
                    keys.ex_messages,
                ),
            ],
        ],
    )

    # All the stuff inside the window
    layout = [
        [
            sg.Column(
                [
                    [
                        button("Execute", keys.execute),
                        button("Clear", keys.clear),
                        button("Show", keys.show, pad=((20, 3), 2)),
                        button("Save", keys.save),
                        sg.FileSaveAs(
                            "Save As",
                            key=keys.save_as,
                            target=keys.save_as,
                            file_types=(("JSON", "*.json"),),
                            default_extension=".json",
                            enable_events=True,
                            initial_folder=str(SettingsFile.get_location()),
                            pad=BUTTON_PADDING,
                        ),
                        sg.FileBrowse(
                            "Load",
                            key=keys.load,
                            target=keys.load,
                            file_types=(("JSON", "*.json"),),
                            enable_events=True,
                            initial_folder=str(SettingsFile.get_location().parent),
                            pad=BUTTON_PADDING,
                        ),
                        button("Reset", keys.reset, pad=((3, 20), 2)),
                        button("Help", keys.help),
                        button("About", keys.about),
                        button("Exit", keys.exit),
                    ]
                ],
                pad=(0, (4, 0)),
                background_color="white",
            ),
            sg.Column(
                [
                    [
                        spinbox(
                            keys.col_percent,
                            list(range(20, 100, 5)),
                            pad=((0, 5), None),
                        ),
                        sg.Text(
                            "%",
                            pad=((0, 5), None),
                            text_color="black",
                            background_color="white",
                        ),
                    ]
                ],
                element_justification="right",
                expand_x=True,
                pad=(0, (4, 0)),
                background_color="white",
            ),
        ],
        [
            column(
                [
                    [io_config],
                    [output_formats],
                    [general_config_frame],
                    [analysis_options],
                    [exclusion_patterns_frame],
                ],
                col_height,
                keys.config_column,
            )
        ],
        [
            sg.Multiline(
                size=(70, 10),
                write_only=True,
                key=keys.multiline,
                reroute_cprint=True,
                expand_y=True,
                expand_x=True,
                auto_refresh=True,
                background_color="white",
            )
        ],
    ]

    # create the window
    window = sg.Window(
        "GitinspectorGUI",
        layout,
        size=(WINDOW_SIZE_X, WINDOW_SIZE_Y),
        icon=icon,
        finalize=True,
        resizable=True,
        margins=(0, 0),
        background_color="white",
    )
    add_gui_handler()
    config_column = window[keys.config_column]
    widget = config_column.Widget  # type: ignore
    assert widget is not None
    frame_id = widget.frame_id
    tk_frame = widget.TKFrame
    canvas = widget.canvas
    window.bind("<Configure>", "Conf")
    canvas.bind(
        "<Configure>",
        lambda event, canvas=canvas, frame_id=frame_id: configure_canvas(
            event, canvas, frame_id
        ),
    )
    tk_frame.bind("<Configure>", lambda event, canvas=canvas: configure_frame(canvas))
    canvas.itemconfig(frame_id, width=canvas.winfo_width())
    sg.cprint_set_output_destination(window, keys.multiline)
    window.refresh()
    return window
