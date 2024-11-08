import multiprocessing
import re
import socket
import time  # Add this import
import webbrowser
from multiprocessing import Process, Queue
from multiprocessing.managers import DictProxy, SyncManager
from pathlib import Path

from gigui.constants import DYNAMIC, STATIC
from gigui.output import html  # to use the shared global variable current_repo
from gigui.output.blame_rows import BlameHistoryRows
from gigui.output.html import BlameHistoryStaticTableSoup, BlameTableSoup, logger
from gigui.output.werkzeug_server import PORT, run_server
from gigui.typedefs import FileStr, Html, SHALong

server = None  # pylint: disable=invalid-name


# This the main function that is called from the main process to start the server.
# It starts the server in a separate process and communicates with it via a queue.
# It also opens the web browser to serve the initial contents.
# The server process is terminated when the main process receives a shutdown request via
# the queue.
def start_werkzeug_server_in_process_with_html(
    html_code: Html, repo_name: str, css_code: str
) -> None:
    server_process: Process
    process_queue: Queue
    manager: SyncManager
    shared_data_dict: DictProxy

    process_queue = Queue()
    manager = multiprocessing.Manager()

    shared_data_dict = manager.dict()
    shared_data_dict["html_code"] = html_code
    shared_data_dict["repo_name"] = repo_name
    shared_data_dict["css_code"] = css_code
    shared_data_dict["blame_history"] = html.current_repo.blame_history
    shared_data_dict["fstrs"] = html.current_repo.fstrs
    shared_data_dict["nr2sha"] = html.current_repo.nr2sha

    port: int = PORT
    while is_port_in_use(port):
        port += 1

    try:
        # Start the server in a separate process and communicate with it via the queue and
        # shared data dictionary.
        # The target function get_token is the main process of the server process.
        server_process = Process(
            target=run_server, args=(process_queue, shared_data_dict, port)
        )
        server_process.start()

        # Add a small delay to ensure the server is fully started
        time.sleep(0.2)

        # Open the web browser to serve the initial contents
        webbrowser.open(f"http://localhost:{port}")

        while True:
            request = process_queue.get()
            if request == "shutdown":
                break
            if request[0] == "load_table":
                table_id = request[1]
                table_html = handle_load_table(table_id, shared_data_dict)
                process_queue.put(table_html)
            else:
                print(f"Unknown request: {request}")

        server_process.terminate()
    except Exception as e:
        server_process.terminate()  # type: ignore #
        raise e


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        in_use: bool = s.connect_ex(("localhost", port)) == 0
        print(f"Port {port} is in use: {in_use}")
        return in_use


# Runs in main process
def handle_load_table(table_id, shared_data_dict) -> Html:
    # Extract file_nr and commit_nr from table_id
    table_html: Html = ""
    match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
    if match:
        file_nr = int(match.group(1))
        commit_nr = int(match.group(2))
        blame_history = shared_data_dict["blame_history"]
        if blame_history == STATIC:
            table_html = get_fstr_commit_table(file_nr, commit_nr)
        elif blame_history == DYNAMIC:
            table_html = generate_fstr_commit_table(file_nr, commit_nr)
        else:  # NONE
            table_html = "Blame history is not enabled."
            logger.error("Error in blame history option: blame history is not enabled.")
    else:
        table_html = (
            "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'"
        )
    return table_html


# Is called by main process
def load_css() -> str:
    css_file = Path(__file__).parent / "files" / "styles.css"
    with open(css_file, "r", encoding="utf-8") as f:
        return f.read()


# Runs in main process
def get_fstr_commit_table(file_nr, commit_nr) -> Html:
    rows, iscomments = BlameHistoryRows(html.current_repo).get_fstr_sha_blame_rows(
        html.current_repo.fstrs[file_nr],
        html.current_repo.nr2sha[commit_nr],
        html=True,
    )
    table = BlameHistoryStaticTableSoup(html.current_repo).get_table(rows, iscomments)
    html_code = str(table)
    html_code = html_code.replace("&amp;nbsp;", "&nbsp;")
    html_code = html_code.replace("&amp;lt;", "&lt;")
    html_code = html_code.replace("&amp;gt;", "&gt;")
    html_code = html_code.replace("&amp;quot;", "&quot;")
    return html_code


# Runs in main process
def generate_fstr_commit_table(file_nr, commit_nr) -> Html:
    fstr: FileStr = html.current_repo.fstrs[file_nr]
    sha: SHALong = html.current_repo.nr2sha[commit_nr]
    rows, iscomments = BlameHistoryRows(html.current_repo).generate_fstr_sha_blame_rows(
        fstr, sha, html=True
    )
    table = BlameTableSoup(html.current_repo).get_table(
        rows, iscomments, file_nr, commit_nr
    )
    html_code = str(table)
    html_code = html_code.replace("&amp;nbsp;", "&nbsp;")
    html_code = html_code.replace("&amp;lt;", "&lt;")
    html_code = html_code.replace("&amp;gt;", "&gt;")
    html_code = html_code.replace("&amp;quot;", "&quot;")
    return html_code
