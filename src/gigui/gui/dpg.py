import dearpygui.dearpygui as dpg

from gigui.constants import (
    BLAME_EXCLUSION_CHOICES,
    BLAME_HISTORY_CHOICES,
    INIT_COL_PERCENT,
    MAX_COL_HEIGHT,
    NONE,
    SHOW,
    WINDOW_HEIGHT_CORR,
    WINDOW_SIZE_X,
    WINDOW_SIZE_Y,
)
from gigui.keys import Keys
from gigui.tiphelp import Help

keys = Keys()

TEXT_WRAP = 350
LABEL_WIDTH = 200

WINDOW_HEIGHT = 800


def _on_demo_close(sender, app_data, user_data):
    print("_on_demo_close")


def gui_handle(sender, app_data, user_data):
    print(f"sender: {sender}, \t app_data: {app_data}, \t user_data: {user_data}")


def runDPGui():
    dpg.create_context()

    with dpg.window(label="GitinspectorGUI", width=785, height=WINDOW_HEIGHT, no_close=True):
        with dpg.group(horizontal=True):
            dpg.add_button(label=Keys.run, callback=gui_handle)
            dpg.add_button(label=Keys.stop, callback=gui_handle)
            dpg.add_button(label=Keys.clear, callback=gui_handle)
            dpg.add_button(label=Keys.help, callback=gui_handle)
            dpg.add_button(label=Keys.about, callback=gui_handle)
            dpg.add_button(label=Keys.exit, callback=gui_handle)

        dpg.add_separator(label="IO Configuration")

        with dpg.child_window(height=127):
            with dpg.group(horizontal=True):
                dpg.add_text("Input folder path")
                dpg.add_input_text(
                    default_value="Hello, world!", callback=gui_handle, width=-1
                )

                with dpg.file_dialog(
                    label="Demo File Dialog",
                    width=300,
                    height=400,
                    show=False,
                    callback=lambda s, a, u: print(s, a, u),
                    tag="__demo_filedialog",
                ):
                    dpg.add_file_extension(".*", color=(255, 255, 255, 255))
                    dpg.add_file_extension(
                        "Source files (*.cpp *.h *.hpp){.cpp,.h,.hpp}",
                        color=(0, 255, 255, 255),
                    )
                    dpg.add_file_extension(".cpp", color=(255, 255, 0, 255))
                    dpg.add_file_extension(
                        ".h", color=(255, 0, 255, 255), custom_text="header"
                    )
                    dpg.add_file_extension("Python(.py){.py}", color=(0, 255, 0, 255))
                    # dpg.add_button(label="Button on file dialog")

                dpg.add_button(
                    label="Browse",
                    user_data=dpg.last_container(),
                    callback=lambda s, a, u: dpg.configure_item(u, show=True),
                )

            with dpg.group(horizontal=True):
                with dpg.group(width=LABEL_WIDTH):
                    dpg.add_text("Output file base")
                dpg.add_input_text(
                    default_value="Hello, world!", callback=gui_handle, width=-1
                )

            with dpg.group(horizontal=True):
                dpg.add_text("Output prepostfix")
                dpg.add_radio_button(
                    (
                        "Prefix with repository",
                        "Postfix with repository",
                        "No prefix or postfix",
                    ),
                    callback=gui_handle,
                    horizontal=True,
                )

            with dpg.group(horizontal=True):
                dpg.add_text("Options")
                dpg.add_text("Search Depth")
                dpg.add_input_int(
                    label="",
                    min_value=0,
                    max_value=10,
                    min_clamped=True,
                    max_clamped=True,
                    width=100,
                    callback=gui_handle,
                )

                dpg.add_text("Output file base")
                dpg.add_input_text(
                    default_value="Hello, world!", callback=gui_handle, width=-1
                )

            with dpg.group(horizontal=True):
                dpg.add_text("Include files")
                dpg.add_text("Subfolder")
                dpg.add_input_text(default_value="", width=100, callback=gui_handle)
                dpg.add_text("N files")
                dpg.add_input_text(default_value="5", width=50, callback=gui_handle)

                dpg.add_text("File patterns")
                dpg.add_input_text(default_value="", callback=gui_handle, width=-1)

        dpg.add_separator(label="Output generation and formatting")

        with dpg.child_window(height=150):
            with dpg.group(horizontal=True):
                dpg.add_text("Output formats")
                dpg.add_checkbox(label=keys.view)
                dpg.add_checkbox(label=keys.html)
                dpg.add_checkbox(label=keys.excel)

            with dpg.group(horizontal=True):
                dpg.add_text("Statistics output")
                dpg.add_checkbox(label="Show renames")
                dpg.add_checkbox(label="Deletions")
                dpg.add_checkbox(label="Scaled %")

            with dpg.group(horizontal=True):
                dpg.add_text("Blame options")

                dpg.add_text("History")
                dpg.add_combo(
                    BLAME_HISTORY_CHOICES,
                    label="Blame options",
                    width=60,
                    default_value=NONE,
                    callback=gui_handle,
                )

                dpg.add_text("Exclusions")
                dpg.add_combo(
                    BLAME_EXCLUSION_CHOICES,
                    label="Exclusions",
                    width=60,
                    default_value=SHOW,
                    callback=gui_handle,
                )

                dpg.add_text("Copy move")
                dpg.add_input_int(
                    label="",
                    min_value=0,
                    max_value=5,
                    min_clamped=True,
                    max_clamped=True,
                    width=60,
                    callback=gui_handle,
                )

                dpg.add_text("Blame skip")
                dpg.add_checkbox(label=keys.blame_skip)

            with dpg.group(horizontal=True):
                dpg.add_text("Blame inclusions")
                dpg.add_checkbox(label="Empty lines")
                dpg.add_checkbox(label="Comments")

            with dpg.group(horizontal=True):
                dpg.add_text("General options")
                dpg.add_checkbox(label="Whitespace")
                dpg.add_checkbox(label="Multicore")

                dpg.add_text("Since")
                # # dpg.add_text("", user_data=keys.since)
                # dpg.add_date_picker(label=keys.since, level=dpg.mvDatePickerLevel_Day) #, show=False, default_value={'month_day': 8, 'year':93, 'month':5})
                # dpg.add_text("Until")
                # # dpg.add_text("", user_data=keys.until)
                # dpg.add_date_picker(label=keys.until, level=dpg.mvDatePickerLevel_Day)

            with dpg.group(horizontal=True):
                dpg.add_text("General options")
                dpg.add_text("Verbosity")
                dpg.add_input_int(
                    label="",
                    min_value=0,
                    max_value=3,
                    min_clamped=True,
                    max_clamped=True,
                    width=60,
                    callback=gui_handle,
                )
                dpg.add_text("Dry run")
                dpg.add_input_int(
                    label="",
                    min_value=0,
                    max_value=3,
                    min_clamped=True,
                    max_clamped=True,
                    width=60,
                    callback=gui_handle,
                )

                dpg.add_text("Extensions")
                dpg.add_input_text(
                    default_value="c cc cif cpp", width=-1, callback=gui_handle
                )

        with dpg.child_window(height=60):
            with dpg.group(horizontal=True):
                dpg.add_text("Settings file")
                dpg.add_input_text(default_value="", width=-1)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", callback=gui_handle)
                dpg.add_button(label="Save As", callback=gui_handle)
                dpg.add_button(label="Load", callback=gui_handle)
                dpg.add_button(label="Reset", callback=gui_handle)
                dpg.add_button(label="Reset File", callback=gui_handle)
                dpg.add_button(label="Toggle", callback=gui_handle)

        dpg.add_separator(label="Exclusion patterns")

        with dpg.child_window(height=85):
            with dpg.table(
                header_row=False,
                borders_innerH=False,
                borders_outerH=False,
                borders_innerV=False,
                borders_outerV=False,
                no_host_extendX=True
            ):

                dpg.add_table_column()
                dpg.add_table_column()

                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Author")
                        dpg.add_input_text(default_value="", width=-1)

                    with dpg.group(horizontal=True):
                        dpg.add_text("Email")
                        dpg.add_input_text(default_value="", width=-1)

                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("File/Folder")
                        dpg.add_input_text(default_value="", width=400)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Revision hash")
                        dpg.add_input_text(default_value="", width=-1)

            with dpg.group(horizontal=True):
                dpg.add_text("Commit message")
                dpg.add_input_text(default_value="", width=-1)

        dpg.add_input_text(default_value="", width=-1, height=-1, multiline=True, readonly=True)

    dpg.create_viewport(title="GitinspectorGUI", width=800, height=WINDOW_HEIGHT)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
