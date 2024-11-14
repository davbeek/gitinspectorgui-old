import re
import socket
import time  # Add this import
import webbrowser
from multiprocessing import Process, Queue
from pathlib import Path
from uuid import uuid4

from gigui.constants import DYNAMIC, STATIC
from gigui.output import html  # to use the shared global variable current_repo
from gigui.output.blame_rows import BlameHistoryRows
from gigui.output.html import BlameHistoryStaticTableSoup, BlameTableSoup, logger
from gigui.output.server import PORT, run_server
from gigui.typedefs import FileStr, Html, SHALong


# This the main function that is called from the main process to start the server.
# It starts the server in a separate process and communicates with it via a queue.
# It also opens the web browser to serve the initial contents.
# The server process is terminated when the main process receives a shutdown request via
# the queue.
def start_werkzeug_server_in_process_with_html(html_code: Html, css_code: str) -> None:
    server_process: Process
    process_queue: Queue

    process_queue = Queue()
    browser_id = str(uuid4())[-12:]

    html_code = create_html_document(html_code, css_code, browser_id)

    port: int = PORT
    while is_port_in_use(port):
        port += 1

    try:
        # Start the server in a separate process and communicate with it via the queue and
        # shared data dictionary.
        server_process = Process(
            target=run_server,
            args=(process_queue, html_code, browser_id, port),
        )
        server_process.start()

        # Add a small delay to ensure the server is fully started
        time.sleep(0.2)

        # Open the web browser to serve the initial contents
        browser = webbrowser.get()
        browser.open_new_tab(f"http://localhost:{port}")

        while True:
            request = process_queue.get()
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

        server_process.terminate()
        server_process.join()  # Ensure the process is fully terminated
    except Exception as e:
        server_process.terminate()  # type: ignore
        server_process.join()  # type: ignore # Ensure the process is fully terminated
        raise e


def create_html_document(html_code: Html, css_code: str, browser_id: str) -> Html:

    # Insert CSS code
    html_code = html_code.replace(
        "</head>",
        f"<style>{css_code}</style></head>",
    )

    # Read and insert JavaScript files
    js_files = [
        "adjustHeader.js",
        "updateTableOnCodeButtonClick.js",
        "tabAndRadioButtonActivation.js",
        "truncateTabNames.js",
        "generateRandomQuery.js",
        "shutdown.js",
    ]
    html_js_code: Html = ""
    js_code: str
    for js_file in js_files:
        js_path = Path(__file__).parent / "static" / "js" / js_file
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()
            if js_file == "shutdown.js":
                # Insert the browser ID into the shutdown.js code
                js_code = js_code.replace("<%= browser_id %>", browser_id)
            elif js_file == "tabAndRadioButtonActivation.js":
                # Insert the browser ID option into the js code
                js_code = js_code.replace("<%= browser_id %>", browser_id)

            html_js_code += f"<script>{js_code}</script>\n"

    html_code = html_code.replace("</body>", f"{html_js_code}</body>")
    return html_code


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        in_use: bool = s.connect_ex(("localhost", port)) == 0
        return in_use


def handle_load_table(table_id: str, blame_history: str) -> Html:
    # Extract file_nr and commit_nr from table_id
    table_html: Html = ""
    match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
    if match:
        file_nr = int(match.group(1))
        commit_nr = int(match.group(2))
        if blame_history == STATIC:
            table_html = get_fstr_commit_table(file_nr, commit_nr)
        elif blame_history == DYNAMIC:
            table_html = generate_fstr_commit_table(file_nr, commit_nr)
        else:  # NONE
            logger.error("Error: blame history option is not enabled.")
    else:
        logger.error(
            "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'"
        )
    return table_html


def get_fstr_commit_table(file_nr: int, commit_nr: int) -> Html:
    rows, iscomments = BlameHistoryRows(html.current_repo).get_fstr_sha_blame_rows(
        html.current_repo.fstrs[file_nr], html.current_repo.nr2sha[commit_nr]
    )
    table = BlameHistoryStaticTableSoup(html.current_repo).get_table(rows, iscomments)
    html_code = str(table)
    html_code = html_code.replace("&amp;nbsp;", "&nbsp;")
    html_code = html_code.replace("&amp;lt;", "&lt;")
    html_code = html_code.replace("&amp;gt;", "&gt;")
    html_code = html_code.replace("&amp;quot;", "&quot;")
    return html_code


def generate_fstr_commit_table(file_nr: int, commit_nr: int) -> Html:
    fstr: FileStr = html.current_repo.fstrs[file_nr]
    sha: SHALong = html.current_repo.nr2sha[commit_nr]
    rows, iscomments = BlameHistoryRows(html.current_repo).generate_fstr_sha_blame_rows(
        fstr, sha
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
