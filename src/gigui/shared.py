import PySimpleGUI as sg  # type: ignore

DEBUG_SHOW_FILES: bool = False

# Set to True at the start of gui.psg.run
gui = False  # pylint: disable=invalid-name

# Set to the value of the GUI window at the start of gui.psg.run
gui_window: sg.Window | None = None
