import PySimpleGUI as sg  # type: ignore

from gigui.repo import GIRepo
from gigui.typedefs import Html

# Set to True at the start of gui.psg.run
gui = False  # pylint: disable=invalid-name

# Set to the value of the GUI window at the start of gui.psg.run
gui_window: sg.Window | None = None

current_repo: GIRepo = GIRepo("", "")  # pylint: disable=invalid-name
repo_name: str = ""
html_code: Html = ""
css_code: str = ""
