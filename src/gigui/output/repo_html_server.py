import logging
import re
import threading
import webbrowser
from dataclasses import dataclass
from logging import getLogger
from threading import Thread
from typing import Iterable
from uuid import uuid4
from webbrowser import BaseBrowser
from wsgiref.types import StartResponse, WSGIEnvironment

import requests
from werkzeug.routing import Map, Rule
from werkzeug.serving import BaseWSGIServer, make_server
from werkzeug.wrappers import Request, Response

from gigui import shared
from gigui._logging import log
from gigui.args_settings import Args
from gigui.constants import AUTO, DEBUG_WERKZEUG_SERVER, DYNAMIC_BLAME_HISTORY, NONE
from gigui.output.repo_html import RepoHTML
from gigui.repo_runner import RepoRunner
from gigui.runner_queues import RunnerQueues
from gigui.typedefs import SHA, BrowserID, FileStr, HtmlStr

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


@dataclass
class LocalHostData:
    name: str
    html_doc: HtmlStr | None
    repo: RepoRunner | None


class HTMLServer(RepoHTML):
    def __init__(self) -> None:
        self.args: Args
        self.queues: RunnerQueues
        self.server_shutdown_request: threading.Event = threading.Event()
        self.sigint_event: threading.Event = threading.Event()
        self.browser: BaseBrowser = webbrowser.get()

        self.len_repos: int = 0
        self.id2localhost_data: dict[BrowserID, LocalHostData] = {}
        self.id2new_localhost_data: dict[BrowserID, LocalHostData] = {}
        self.browser_ids: list[BrowserID] = []

        self.server_thread: Thread | None = None
        self.monitor_thread: Thread | None = None

        self.server: BaseWSGIServer | None = None

    def set_args(self, args: Args) -> None:
        self.args = args

    def set_runner_queues(self, queues: RunnerQueues) -> None:
        self.queues = queues

    def open_new_tab(
        self, name: str, browser_id: BrowserID, html_doc_code: HtmlStr | None, i: int
    ) -> None:
        try:
            if html_doc_code is None:
                logger.info(
                    f"    {name}: no output"
                    + (f" {i} of {self.len_repos}" if self.len_repos > 1 else "")
                )
            else:
                logger.info(
                    f"    {name}: starting server"
                    + (f" {i} of {self.len_repos}" if self.len_repos > 1 else "")
                )
                self.browser.open_new_tab(
                    f"http://localhost:{shared.port_value}/?id={browser_id}"
                )
        except Exception as e:
            logging.error(
                # Use name instead of repo.name because repo can be unbound
                f"{name} port number {shared.port_value} main body exception {e}"
            )
            raise e

    def server_app(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        browser_id: BrowserID
        shutdown_id: BrowserID
        load_table_request: str
        load_table_id: BrowserID
        repo: RepoRunner
        # try:
        request = Request(environ)
        logger.debug(f"browser request = {request.path} " + f"{request.args.get('id')}")  # type: ignore
        if request.path == "/":
            browser_id = request.args.get("id")  # type: ignore
            response = Response(
                self.get_html_doc(browser_id),
                content_type="text/html; charset=utf-8",
            )
        elif request.path.startswith("/shutdown"):
            shutdown_id = request.args.get("id")  # type: ignore
            if shutdown_id is None or shutdown_id in self.browser_ids:
                self.server_shutdown_request.set()
                response = Response(content_type="text/plain")
            else:
                response = Response("Invalid shutdown ID", status=403)
        elif request.path.startswith("/load-table/"):
            load_table_request = request.path.split("/")[-1]
            load_table_id = request.args.get("id")  # type: ignore
            if load_table_id in self.browser_ids:
                repo = self.id2localhost_data[load_table_id].repo  # type: ignore
                table_html = self.handle_load_table(
                    repo, load_table_request, repo.dynamic_blame_history_selected()
                )
                response = Response(table_html, content_type="text/html")
            else:
                # Ignore invalid load-table requests from old cache pages
                response = Response("Not found", status=404)
        elif request.path == "/favicon.ico":
            response = Response(status=404)  # Ignore favicon requests
        else:
            response = Response("Not found", status=404)

        start_response(response.status, list(response.headers.items()))
        return [response.data]
        # except Exception as e:
        #     logging.error(f"port number {shared.port_value} server app exception {e}")
        #     raise e

    def get_html_doc(self, browser_id: BrowserID) -> HtmlStr | None:
        if browser_id in self.id2localhost_data:
            return self.id2localhost_data[browser_id].html_doc
        else:
            logger.info(f"Invalid browser ID: {browser_id}")
            return None

    def handle_load_table(
        self, repo: RepoRunner, table_id: BrowserID, dynamic_blame_history_enabled: bool
    ) -> HtmlStr:
        # Extract file_nr and commit_nr from table_id
        table_html: HtmlStr = ""
        match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
        if match:
            file_nr = int(match.group(1))
            commit_nr = int(match.group(2))
            if dynamic_blame_history_enabled:
                table_html = self.generate_fstr_commit_table(repo, file_nr, commit_nr)
            else:  # NONE
                logger.error("Error: blame history option is not enabled.")
        else:
            logger.error(
                "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'"
            )
        return table_html

    # For DYNAMIC blame history
    def generate_fstr_commit_table(
        self, repo: RepoRunner, file_nr: int, commit_nr: int
    ) -> HtmlStr:
        root_fstr: FileStr = repo.fstrs[file_nr]
        sha: SHA = repo.nr2sha[commit_nr]
        rows, iscomments = repo.generate_fr_sha_blame_rows(root_fstr, sha)
        table = repo._get_blame_table_from_rows(rows, iscomments, file_nr, commit_nr)
        html_code = str(table)
        html_code = html_code.replace("&amp;nbsp;", "&nbsp;")
        html_code = html_code.replace("&amp;lt;", "&lt;")
        html_code = html_code.replace("&amp;gt;", "&gt;")
        html_code = html_code.replace("&amp;quot;", "&quot;")
        return html_code

    def send_shutdown_request(self) -> None:
        try:
            if not self.browser_ids:
                return
            browser_id: BrowserID = self.browser_ids[0]
            response = requests.post(
                f"http://localhost:{shared.port_value}/shutdown?id={browser_id}",
                timeout=1,
            )
            if response.status_code != 200:
                log(f"Failed to send shutdown request: {response.status_code}")
        except requests.exceptions.Timeout:
            logging.error(
                f"Timeout sending shutdown request on port {shared.port_value} "
                f"browser_id {browser_id}"  # type: ignore
            )

    def send_general_shutdown_request(self) -> None:
        try:
            response = requests.post(
                f"http://localhost:{shared.port_value}/shutdown",
                timeout=1,
            )
            if response.status_code != 200:
                logging.error(
                    f"Failed to send shutdown request: {response.status_code}"
                )
        except requests.exceptions.Timeout:
            logging.error(
                f"Timeout sending shutdown request on port {shared.port_value}"
            )

    def set_localhost_data(self) -> None:
        """Set localhost data for the server.

        For len_repos do:
        - Get repo name, html code, and a RepoRunner instance (in case of dynamic blame
          history) from queues.html.
        - Create html document via class RepoHTML from html code.
        - Set the following data in self.id2localhost_data:[browser_id]
            - repo name
            - html code
            - RepoRunner instance
        Finally, create the list of all browser_ids, a browser_id per repo..
        """
        i: int = 0
        name: str
        browser_id: BrowserID
        html_code: HtmlStr | None
        repo: RepoRunner
        while i < self.len_repos:
            i += 1
            name, html_code, repo = self.queues.html.get()  # type: ignore
            browser_id = f"{name}-{str(uuid4())[-12:]}"
            html_doc_code = (
                RepoHTML.create_html_document(
                    self.args, html_code, RepoHTML.load_css(), browser_id
                )
                if html_code is not None
                else None
            )
            self.id2localhost_data[browser_id] = self.id2new_localhost_data[
                browser_id
            ] = LocalHostData(
                name=name,
                html_doc=html_doc_code,
                repo=repo,
            )
            self.browser_ids = list(self.id2localhost_data.keys())

    def start_server(self) -> None:
        if not self.server:
            self.server = make_server(
                "localhost",
                shared.port_value,
                self.server_app,
                threaded=False,
                processes=0,
                passthrough_errors=True,
            )
            self.server_thread = Thread(
                target=self.server.serve_forever,
                args=(0.1,),  # 0.1 is the poll interval
                name=f"Werkzeug server on port {shared.port_value}",
            )
            self.server_thread.start()

    def gui_open_new_tabs(self) -> None:
        if require_server(self.args):
            for i, (browser_id, data) in enumerate(self.id2new_localhost_data.items()):
                self.open_new_tab(
                    data.name,
                    browser_id,
                    data.html_doc,
                    i + 1,
                )
            self.id2new_localhost_data.clear()


def require_server(args: Args) -> bool:
    return (
        args.view == AUTO
        and not args.file_formats
        or args.view == DYNAMIC_BLAME_HISTORY
    )
