import logging
import re
import threading
import time
import webbrowser
from logging import getLogger
from queue import Queue
from threading import Thread
from typing import Callable
from uuid import uuid4

from werkzeug.routing import Map, Rule
from werkzeug.serving import BaseWSGIServer, make_server
from werkzeug.wrappers import Request, Response

from gigui.args_settings import MiniRepo
from gigui.constants import DEBUG_WERKZEUG_SERVER, DYNAMIC
from gigui.output.repo_html import RepoHTML
from gigui.typedefs import SHA, FileStr, HtmlStr

PORT = 8080

logger = getLogger(__name__)
if DEBUG_WERKZEUG_SERVER:
    getLogger("werkzeug").setLevel(logging.DEBUG)
else:
    getLogger("werkzeug").setLevel(logging.ERROR)

url_map = Map(
    [
        Rule("/load-table/<table_id>", endpoint="load_table"),
        Rule("/shutdown", endpoint="shutdown", methods=["POST"]),
        Rule("/", endpoint="serve_initial_html"),
    ]
)


shutdown_func: Callable


class RepoHTMLServer(RepoHTML):
    def __init__(
        self,
        mini_repo: MiniRepo,
        server_started_event: threading.Event,
        worker_done_event: threading.Event,
        host_port_queue: Queue | None,
    ) -> None:
        super().__init__(mini_repo)

        self.server_started_event: threading.Event = server_started_event
        self.worker_done_event: threading.Event = worker_done_event
        self.server_shutting_down_event: threading.Event = threading.Event()
        self.host_port_queue: Queue | None = host_port_queue

        self.run_server_thread: Thread
        self.server_thread: Thread
        self.browser_thread: Thread
        self.monitor_thread: Thread

        self.server: BaseWSGIServer
        self.port_value: int = 0
        self.browser_id: str = ""
        self.html_doc_code: HtmlStr = ""

    def start_werkzeug_server_with_html(
        self,
        html_code: HtmlStr,
    ) -> None:
        assert self.host_port_queue is not None
        self.browser_id = f"{self.name}-{str(uuid4())[-12:]}"
        self.html_doc_code = self.create_html_document(
            html_code, self.load_css(), self.browser_id
        )
        try:
            self.port_value = self.host_port_queue.get()
            self.host_port_queue.put(self.port_value + 1)

            self.server = make_server(
                "localhost",
                self.port_value,
                lambda environ, start_response: self.server_app(
                    environ,
                    start_response,
                ),  # type: ignore
                threaded=False,
                processes=0,
            )

            self.server_thread = Thread(
                target=self.run_server,
                name=f"Werkzeug server for {self.name}",
            )
            self.server_thread.start()

            if self.args.multicore:
                self.server_shutting_down_event.wait()
                self.server_thread.join()
                self.browser_thread.join()
                self.worker_done_event.set()
            else:  # Single core
                Thread(
                    target=self.monitor_events_single_core,
                    name=f"Event monitor for {self.name}",
                ).start()
        except Exception as e:
            print(f"{self.name} port number {self.port_value} main body exception {e}")
            raise e

    def run_server(self) -> None:
        try:
            self.browser_thread = Thread(target=self.open_browser)
            self.browser_thread.start()
            logger.info(f"{self.name}: starting server on port {self.port_value}")
            self.server_started_event.set()
            self.server.serve_forever()
        except Exception as e:
            print(f"{self.name} port number {self.port_value} server exception {e}")
            raise e

    def open_browser(self) -> None:
        # Open the web browser to serve the initial contents
        try:
            time.sleep(0.1)  # Wait for the server to start
            browser = webbrowser.get()
            logger.info(f"{self.name}: opening browser tab on port {self.port_value}")
            browser.open_new_tab(
                f"http://localhost:{self.port_value}?v={self.browser_id}"
            )
        except Exception as e:
            print(f"{self.name} port number {self.port_value} browser exception {e}")
            raise e

    def monitor_events_single_core(self) -> None:
        self.server_shutting_down_event.wait()
        self.server_thread.join()
        self.browser_thread.join()
        self.worker_done_event.set()

    def server_app(
        self,
        environ,
        start_response,
    ) -> Response:
        try:
            request = Request(environ)
            logger.info(f"{self.name}: browser request = {request.path} {request.args.get('id')}")  # type: ignore
            if request.path == "/":
                response = Response(
                    self.html_doc_code, content_type="text/html; charset=utf-8"
                )
            elif request.path.startswith("/shutdown"):
                shutdown_id = request.args.get("id")
                if shutdown_id == self.browser_id:
                    Thread(
                        target=self.server.shutdown,
                        name=f"Shutdown thread for {self.name}",
                    ).start()  # calling shutdown_directly leads to deadlock
                    self.server_shutting_down_event.set()  # Set shutting_down_event
                    response = Response(content_type="text/plain")
                else:
                    logger.info(f"Invalid shutdown: {shutdown_id=}  {self.browser_id=}")
                    response = Response("Invalid shutdown ID", status=403)
            elif request.path.startswith("/load-table/"):
                table_id = request.path.split("/")[-1]
                load_table_id = request.args.get("id")
                if load_table_id == self.browser_id:
                    table_html = self.handle_load_table(
                        table_id, self.args.blame_history
                    )
                    response = Response(table_html, content_type="text/html")
                else:
                    response = Response("Invalid browser ID", status=403)
            elif request.path == "/favicon.ico":
                response = Response(status=404)  # Ignore favicon requests

            else:
                response = Response("Not found", status=404)
            return response(environ, start_response)  # type: ignore
        except Exception as e:
            print(f"{self.name} port number {self.port_value} server app exception {e}")
            raise e

    def handle_load_table(self, table_id: str, blame_history: str) -> HtmlStr:
        # Extract file_nr and commit_nr from table_id
        table_html: HtmlStr = ""
        match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
        if match:
            file_nr = int(match.group(1))
            commit_nr = int(match.group(2))
            if blame_history == DYNAMIC:
                table_html = self.generate_fstr_commit_table(file_nr, commit_nr)
            else:  # NONE
                logger.error("Error: blame history option is not enabled.")
        else:
            logger.error(
                "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'"
            )
        return table_html

    # For DYNAMIC blame history
    def generate_fstr_commit_table(self, file_nr: int, commit_nr: int) -> HtmlStr:
        root_fstr: FileStr = self.fstrs[file_nr]
        sha: SHA = self.nr2sha[commit_nr]
        rows, iscomments = self.generate_fr_sha_blame_rows(root_fstr, sha)
        table = self._get_blame_table_from_rows(rows, iscomments, file_nr, commit_nr)
        html_code = str(table)
        html_code = html_code.replace("&amp;nbsp;", "&nbsp;")
        html_code = html_code.replace("&amp;lt;", "&lt;")
        html_code = html_code.replace("&amp;gt;", "&gt;")
        html_code = html_code.replace("&amp;quot;", "&quot;")
        return html_code
