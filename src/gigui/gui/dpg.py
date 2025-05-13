import multiprocessing
import threading
import time
from logging import getLogger
from multiprocessing.managers import SyncManager
from multiprocessing.synchronize import Event as multiprocessingEvent
from queue import Queue
from typing import Any, Union

import dearpygui.dearpygui as dpg

from gigui import shared
from gigui._logging import set_logging_level_from_verbosity
from gigui.args_settings import Args, Settings
from gigui.constants import PREPOSTFIX_OPTIONS
from gigui.gi_runner import GIRunner
from gigui.gui.dpg_base import DPGBase, help_window, popup
from gigui.gui.dpg_window import make_window, show_window
from gigui.keys import Keys
from gigui.output.repo_html_server import HTMLServer, require_server
from gigui.runner_queues import RunnerQueues, get_runner_queues
from gigui.tiphelp import Help
from gigui.utils import (
    to_posix_fstr
)

logger = getLogger(__name__)

keys = Keys()

TEXT_WRAP = 350
LABEL_WIDTH = 200

WINDOW_HEIGHT = 800


def _on_demo_close(sender, app_data, user_data):
    print("_on_demo_close")

class DPGui(DPGBase):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        print(settings)
        self.settings: Settings = settings

        # THe following 5 vars are defined when the event keys.run is triggered
        self.queues: RunnerQueues
        self.manager: SyncManager | None = None
        self.logging_queue: Queue
        self.gi_runner_thread: threading.Thread | None = None
        self.html_server: HTMLServer = HTMLServer()

        self.recreate_window: bool = True
        self.args: Args

        while self.recreate_window:
            self.recreate_window = self.run_inner()
            set_logging_level_from_verbosity(self.settings.verbosity)

    def run_inner(self) -> bool:
        logger.debug(f"{self.settings = }")  # type: ignore

        shared.gui = True

        # Is set to True when handling "Reset settings file" menu item
        recreate_window: bool = False

        self.window = make_window(self.gui_handle)
        # shared.gui_window = self.window

        self.enable_buttons()

        self.window_state_from_settings()  # type: ignore
        # last_window_height: int = self.window.Size[1]  # type: ignore
        show_window()

        return recreate_window

    def run(
        self,
        values: dict,
    ) -> None:
        start_time = time.time()
        logger.debug(f"{values = }")  # type: ignore

        if self.input_fstrs and not self.input_fstr_matches:
            popup("Error", "Input folder path invalid")
            return
        if not self.input_fstrs:
            popup("Error", "Input folder path empty")
            return
        if not self.outfile_base:
            popup("Error", "Output file base empty")
            return
        if not self.subfolder_valid:
            popup(
                "Error",
                "Subfolder invalid: should be empty or a folder that exists in the "
                '"Input folder path"',
            )
            return

        self.set_args(values)
        self.disable_buttons()
        self.queues, self.logging_queue, self.manager = get_runner_queues(
            self.args.multicore
        )
        logger.debug(f"{self.args = }")  # type: ignore

        if require_server(self.args):
            if not self.html_server:
                self.html_server = HTMLServer()
            self.html_server.set_args(self.args)

        self.gi_runner_thread = threading.Thread(
            target=self.start_gi_runner,
            args=(
                self.args,
                start_time,
                self.queues,
                self.logging_queue,
                multiprocessing.Event() if self.args.multicore else threading.Event(),
                self.html_server,
            ),
            name="GI Runner",
        )
        self.gi_runner_thread.start()

    def start_gi_runner(
        self,
        args: Args,
        start_time: float,
        queues: RunnerQueues,
        logging_queue: Queue,
        sync_event: multiprocessingEvent | threading.Event,
        html_server: HTMLServer | None = None,
    ) -> None:
        GIRunner(
            args,
            start_time,
            queues,
            logging_queue,
            sync_event,
            html_server,
        )

    def shutdown_html_server(self) -> None:
        if self.html_server.server:
            self.html_server.send_general_shutdown_request()
            self.html_server.server_shutdown_request.wait()
            self.html_server.server.shutdown()
            self.html_server.server.server_close()
            if (
                self.html_server.server_thread
                and self.html_server.server_thread.is_alive()
            ):
                self.html_server.server_thread.join()

    def close(self) -> None:
        self.shutdown_html_server()
        if self.gi_runner_thread:
            shared.gui_window_closed = True
            self.gi_runner_thread.join()
            if self.manager:
                self.manager.shutdown()

    def gui_handle(self, sender, app_data, user_data):
        print(f"sender: {sender}, \t app_data: {app_data}, \t user_data: {user_data}")
        match sender:

            case keys.clear:
                dpg.delete_item(keys.multiline, children_only=True)

            case keys.help:
                help_window()

            case keys.about:
                self.log(Help.about_info)

            case keys.browse_input_fstr:
                dpg.configure_item(keys.file_dialog, show=True)

            case keys.file_dialog:
                self.update_input_fstrs(app_data["file_path_name"])

            # Exit button clicked
            case keys.exit:
                self.close()
                return False

            # # IO configuration
            # ##################################
            case keys.input_fstrs:
                self.process_input_fstrs(app_data)

            case keys.outfile_base:
                self.update_outfile_str()

            case keys.fix:
                for key, value in PREPOSTFIX_OPTIONS.items():
                    if value == app_data:
                        self.fix = key
                        break
                self.update_outfile_str()

            case keys.subfolder:
                self.subfolder = to_posix_fstr(app_data)
                self.process_inputs()

            case keys.n_files:
                self.process_n_files(app_data, self.window[keys.n_files])  # type: ignore

            # Output generation and formatting
            #################################
            case keys.auto | keys.dynamic_blame_history | keys.html | keys.excel:
                self.process_view_format_radio_buttons(sender)

            case keys.verbosity:
                set_logging_level_from_verbosity(app_data)

            case keys.toggle_settings_file:
                self.gui_settings_full_path = not self.gui_settings_full_path
                if self.gui_settings_full_path:
                    self.update_settings_file_str(True)
                else:
                    self.update_settings_file_str(False)
