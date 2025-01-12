import re
import threading
import time
import webbrowser
from multiprocessing import Process, Queue
from queue import Empty  # Add this import
from uuid import uuid4

from gigui.constants import DYNAMIC
from gigui.output import html, server
from gigui.output.blame_rows import BlameHistoryRows
from gigui.output.html import BlameTableSoup, create_html_document, load_css, logger
from gigui.typedefs import SHA, FileStr, Html

FIRST_PORT = 8080
port_global: int = FIRST_PORT


# This the main function that is called from the main process to start the server.
# It starts the server in a separate process and communicates with it via a queue.
# It also opens the web browser to serve the initial contents.
# The server process is terminated when the main process receives a shutdown request via
# the queue.
def start_werkzeug_server_in_process_with_html(
    html_code: Html,
    stop_event: threading.Event,
) -> None:
    server_process: Process
    process_queue: Queue

    process_queue = Queue()
    browser_id = str(uuid4())[-12:]

    port = get_port()
    html_code = create_html_document(html_code, load_css(), browser_id)

    try:
        # Start the server in a separate process and communicate with it via the queue and
        # shared data dictionary.

        server_process = Process(
            target=server.run,
            args=(process_queue, html_code, browser_id, port),
        )
        server_process.start()

        # Add a small delay to ensure the server is fully started
        time.sleep(0.2)

        # Open the web browser to serve the initial contents
        browser = webbrowser.get()
        browser.open_new_tab(f"http://localhost:{port}")

        while server_process.is_alive():  # Check if server_process is still alive
            if stop_event.is_set():
                process_queue.put(
                    ("shutdown", browser_id)
                )  # Send shutdown request to server_process
                break
            try:
                request = process_queue.get(timeout=0.2)
                if request[0] == "shutdown" and request[1] == browser_id:
                    break
                if request[0] == "load_table" and request[2] == browser_id:
                    table_id = request[1]
                    table_html = handle_load_table(
                        table_id, html.current_repo.blame_history
                    )
                    process_queue.put(table_html)
                else:
                    logger.error(f"Unknown request: {request}")
            except Empty:
                pass  # Handle the queue.Empty exception

    except KeyboardInterrupt:
        logger.info("server_main: keyboard interrupt received")
        process_queue.put(("shutdown", browser_id))  # Send shutdown request to server
    except Exception as e:
        logger.error("server_main: exception received in module server_main")
        raise e
    finally:
        time.sleep(0.1)  # Wait for the server_process to handle the shutdown request
        if server_process.is_alive():  # type: ignore
            server_process.terminate()  # type: ignore
            server_process.join()  # type: ignore # Ensure the process is fully terminated
        logger.info("server_main: terminated")


def get_port() -> int:
    global port_global
    port = port_global
    port_global += 1
    return port


def handle_load_table(table_id: str, blame_history: str) -> Html:
    # Extract file_nr and commit_nr from table_id
    table_html: Html = ""
    match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
    if match:
        file_nr = int(match.group(1))
        commit_nr = int(match.group(2))
        if blame_history == DYNAMIC:
            table_html = generate_fstr_commit_table(file_nr, commit_nr)
        else:  # NONE
            logger.error("Error: blame history option is not enabled.")
    else:
        logger.error(
            "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'"
        )
    return table_html


# For DYNAMIC blame history
def generate_fstr_commit_table(file_nr: int, commit_nr: int) -> Html:
    root_fstr: FileStr = html.current_repo.fstrs[file_nr]
    sha: SHA = html.current_repo.nr2sha[commit_nr]
    rows, iscomments = BlameHistoryRows(html.current_repo).generate_fr_sha_blame_rows(
        root_fstr, sha
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
