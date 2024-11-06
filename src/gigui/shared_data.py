import PySimpleGUI as sg  # type: ignore

from gigui.typedefs import Html

# Set to True at the start of gui.psg.run
gui = False  # pylint: disable=invalid-name

# Set to the value of the GUI window at the start of gui.psg.run
gui_window: sg.Window | None = None

# Cannot import type hint GIRepo for current_repo due to circular import
current_repo = None  # pylint: disable=invalid-name
repo_name: str = ""
html_code: Html = ""
css_code: str = ""
