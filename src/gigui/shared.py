import PySimpleGUI as sg  # type: ignore

# Set to True at the start of gui.psg.run
gui = False  # pylint: disable=invalid-name

# Set to true in module cli. Note that when the GUI is started from the CLI, the
# variables gui and cli are both True.
cli = False  # pylint: disable=invalid-name

# Set to the value of the GUI window at the start of gui.psg.run
gui_window: sg.Window | None = None

gui_window_closed = False  # pylint: disable=invalid-name
