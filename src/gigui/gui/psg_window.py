# noinspection PyPep8Naming
import logging
from pathlib import Path

import PySimpleGUI as sg

from gigui._logging import add_gui_handler
from gigui.args_settings_keys import AUTO, VIEWER_CHOICES, Keys, SettingsFile
from gigui.constants import (
    INIT_COL_PERCENT,
    MAX_COL_HEIGHT,
    WINDOW_HEIGHT_CORR,
    WINDOW_SIZE_X,
    WINDOW_SIZE_Y,
)
from gigui.gui.commongui import icon
from gigui.gui.psg_window_support import (
    BUTTON_PADDING,
    button,
    checkbox,
    column,
    configure_canvas,
    configure_frame,
    frame,
    input_box,
    name_basic,
    name_choice,
    name_header,
    name_input,
    radio,
    spinbox,
)
from gigui.tiphelp import Tip

logger = logging.getLogger(__name__)

RADIO_BUTTON_GROUP_FIX_ID = 2


tip = Tip()
keys = Keys()


# pylint: disable=too-many-locals
def make_window() -> sg.Window:
    # Cannot use logging here, as there is not yet any new window to log to and the
    # window in common and _logging still points to the old window after a "Reset
    # settings file" command has been given.

    sg.theme("SystemDefault")

    # create the window
    window = sg.Window(
        "GitinspectorGUI",
        window_layout(),
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


# All the stuff inside the window
def window_layout() -> list[list[sg.Element] | list[sg.Column] | list[sg.Multiline]]:
    COL_HEIGHT_UNLIMITED = int(
        (WINDOW_SIZE_Y - WINDOW_HEIGHT_CORR) * INIT_COL_PERCENT / 100
    )
    COL_HEIGHT = min(MAX_COL_HEIGHT, COL_HEIGHT_UNLIMITED)

    return [
        layout_top_row(),
        [
            column(
                [
                    [io_config()],
                    [output_formats()],
                    [general_config_frame()],
                    [analysis_options()],
                    [exclusion_patterns_frame()],
                ],
                COL_HEIGHT,
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


def layout_top_row() -> list[sg.Element]:
    return [
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
    ]


def io_config() -> sg.Frame:
    return frame(
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
                    initial_folder=str(Path.home()),
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


def output_formats() -> sg.Frame:
    return frame(
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


def general_config_frame() -> sg.Frame:
    return frame(
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


def analysis_options() -> sg.Frame:
    return frame(
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


def exclusion_patterns_frame() -> sg.Frame:
    SIZE = (10, None)
    TITLE_SIZE = 10

    LEFT_COLUMN = [
        [
            name_header("Author", tooltip=tip.ex_authors),
            input_box(
                keys.ex_authors,
                size=SIZE,
            ),
        ],
        [
            name_header("File/Folder", tooltip=tip.ex_files),
            input_box(keys.ex_files, size=SIZE),
        ],
    ]

    RIGHT_COLUMN = [
        [
            name_basic("Email", tooltip=tip.ex_emails, size=TITLE_SIZE),
            input_box(
                keys.ex_emails,
                size=SIZE,
            ),
        ],
        [
            name_basic("Revision hash", tooltip=tip.ex_revisions, size=TITLE_SIZE),
            input_box(
                keys.ex_revisions,
                size=SIZE,
            ),
        ],
    ]

    return frame(
        "Exclusion patterns",
        layout=[
            [
                sg.Column(
                    LEFT_COLUMN, expand_x=True, pad=(0, 0), background_color="white"
                ),
                sg.Column(
                    RIGHT_COLUMN, expand_x=True, pad=(0, 0), background_color="white"
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
