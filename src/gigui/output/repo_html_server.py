import logging
import re
import threading
import time
import webbrowser
from dataclasses import dataclass
from logging import getLogger
from threading import Thread
from typing import Iterable
from uuid import uuid4
from wsgiref.types import StartResponse, WSGIEnvironment

import requests
from werkzeug.routing import Map, Rule
from werkzeug.serving import BaseWSGIServer, make_server
from werkzeug.wrappers import Request, Response

from gigui import shared
from gigui.args_settings import Args
from gigui.constants import AUTO, DEBUG_WERKZEUG_SERVER, DYNAMIC_BLAME_HISTORY
from gigui.output.repo_html import RepoHTML
from gigui.queues_events import RunnerEvents, RunnerQueues
from gigui.repo_runner import RepoRunner
from gigui.typedefs import SHA, FileStr, HtmlStr

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
class HostData:
    name: str
    browser_id: str
    html_doc: HtmlStr | None


@dataclass
class HostRepoData(HostData):
    repo: RepoRunner


class HTMLServer(RepoHTML):
    def __init__(
        self,
        args: Args,
        queues: RunnerQueues,
    ) -> None:
        super().__init__(args)

        self.queues: RunnerQueues = queues
        self.events: RunnerEvents = RunnerEvents()
        self.sigint_event: threading.Event = threading.Event()

        self.len_repos: int = 0
        self.id2host_data: dict[str, HostData] = {}
        self.id2host_repo_data: dict[str, HostRepoData] = {}
        self.browser_ids: list[str] = []

        self.server_thread: Thread | None = None
        self.monitor_thread: Thread | None = None

        self.server: BaseWSGIServer

    def open_new_tab(
        self, name: str, browser_id: str, html_doc_code: HtmlStr | None, i: int
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
            print(
                # Use name instead of repo.name because repo can be unbound
                f"{name} port number {shared.port_value} main body exception {e}"
            )
            raise e

    def monitor_events(self) -> None:
        assert self.server_thread is not None
        while True:
            if self.args.multicore:
                # no sigint_event
                self.events.server_shutdown_request.wait()
                break
            else:  # single core
                if self.events.server_shutdown_request.wait(timeout=0.1):
                    break
                if self.sigint_event.is_set():
                    self.send_shutdown_request()
                    time.sleep(0.1)
                    self.events.server_shutdown_request.wait()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        self.events.server_shutdown_done.set()

    def server_app(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        browser_id: str
        shutdown_id: str
        load_table_request: str
        load_table_id: str
        repo: RepoRunner
        try:
            request = Request(environ)
            logger.debug(
                f"browser request = {request.path} " + f"{request.args.get('id')}"
            )  # type: ignore
            if request.path == "/":
                browser_id = request.args.get("id")  # type: ignore
                response = Response(
                    self.get_html_doc(browser_id),
                    content_type="text/html; charset=utf-8",
                )
            elif request.path.startswith("/shutdown"):
                shutdown_id = request.args.get("id")  # type: ignore
                if shutdown_id in self.browser_ids:
                    self.events.server_shutdown_request.set()
                    response = Response(content_type="text/plain")
                else:
                    logger.info(
                        f"Invalid shutdown: {shutdown_id} not in {self.browser_ids}"
                    )
                    response = Response("Invalid shutdown ID", status=403)
            elif request.path.startswith("/load-table/"):
                load_table_request = request.path.split("/")[-1]
                load_table_id = request.args.get("id")  # type: ignore
                if load_table_id in self.browser_ids:
                    repo = self.id2host_repo_data[load_table_id].repo
                    table_html = self.handle_load_table(
                        repo, load_table_request, repo.dynamic_blame_history_selected()
                    )
                    response = Response(table_html, content_type="text/html")
                else:
                    response = Response("Invalid browser ID", status=403)
            elif request.path == "/favicon.ico":
                response = Response(status=404)  # Ignore favicon requests
            else:
                response = Response("Not found", status=404)

            start_response(response.status, list(response.headers.items()))
            return [response.data]
        except Exception as e:
            print(f"port number {shared.port_value} server app exception {e}")
            raise e

    def get_html_doc(self, browser_id: str) -> HtmlStr | None:
        if browser_id in self.id2host_data:
            return self.id2host_data[browser_id].html_doc
        elif browser_id in self.id2host_repo_data:
            return self.id2host_repo_data[browser_id].html_doc
        else:
            raise ValueError(f"Invalid browser ID: {browser_id}")

    def handle_load_table(
        self, repo: RepoRunner, table_id: str, dynamic_blame_history_enabled: bool
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
            browser_id: str = self.browser_ids[0]
            response = requests.post(
                f"http://localhost:{shared.port_value}/shutdown?id={browser_id}",
                timeout=1,
            )
            if response.status_code != 200:
                print(f"Failed to send shutdown request: {response.status_code}")
        except requests.exceptions.Timeout:
            print(
                f"Timeout sending shutdown request on port {shared.port_value} "
                f"browser_id {browser_id}"  # type: ignore
            )

    def join_threads(self) -> None:
        # server thread is joined in monitor_events()
        if self.monitor_thread is not None:
            self.monitor_thread.join()

    def set_localhost_data(self) -> None:
        # self.args.view == AUTO and not elf.args.file_formats
        i: int = 0
        name: str
        browser_id: str
        html_code: str | None
        while i < self.len_repos:
            i += 1
            name, html_code = self.queues.html.get()  # type: ignore
            browser_id = f"{name}-{str(uuid4())[-12:]}"
            html_doc_code = (
                self.create_html_document(html_code, self.load_css(), browser_id)
                if html_code is not None
                else None
            )
            self.id2host_data[browser_id] = HostData(
                name=name,
                browser_id=browser_id,
                html_doc=html_doc_code,
            )
            self.browser_ids = list(self.id2host_data.keys())

    def set_localhost_repo_data(self) -> None:
        # self.args.view == DYNAMIC_BLAME_HISTORY
        i: int = 0
        name: str
        browser_id: str
        html_code: str | None
        repo: RepoRunner
        while i < self.len_repos:
            i += 1
            repo, html_code = self.queues.html.get()  # type: ignore
            name = repo.name
            browser_id = f"{name}-{str(uuid4())[-12:]}"
            html_doc_code = (
                self.create_html_document(html_code, self.load_css(), browser_id)
                if html_code is not None
                else None
            )
            self.id2host_repo_data[browser_id] = HostRepoData(
                name=name,
                browser_id=browser_id,
                html_doc=html_doc_code,
                repo=repo,
            )
            self.browser_ids = list(self.id2host_repo_data.keys())

    def start_server_threads(self) -> None:
        self.browser = webbrowser.get()
        self.server = make_server(
            "localhost",
            shared.port_value,
            self.server_app,
            threaded=False,
            processes=0,
        )
        self.server_thread = Thread(
            target=self.server.serve_forever,
            args=(0.1,),  # 0.1 is the poll interval
            name=f"Werkzeug server on port {shared.port_value}",
        )
        self.server_thread.start()
        self.monitor_thread = Thread(
            target=self.monitor_events,
            name=f"Event monitor for server on port {shared.port_value}",
        )
        self.monitor_thread.start()

    def delay(self) -> None:
        time.sleep(0.1)

    def gui_open_new_tabs(self) -> None:
        if self.args.view == AUTO and not self.args.file_formats:
            for i, data in enumerate(self.id2host_data.values()):
                self.open_new_tab(
                    data.name,
                    data.browser_id,
                    data.html_doc,
                    i + 1,
                )
        elif self.args.view == DYNAMIC_BLAME_HISTORY:
            for i, data in enumerate(self.id2host_repo_data.values()):
                self.open_new_tab(
                    data.name,
                    data.browser_id,
                    data.html_doc,
                    i + 1,
                )
