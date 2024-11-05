import logging
import os
import re
import sys
import threading
import webbrowser
from pathlib import Path

import requests  # type: ignore
from flask import Flask, Response, make_response, render_template_string, request
from flask_cors import CORS  # type: ignore

from gigui import shared_data
from gigui.constants import DYNAMIC, STATIC
from gigui.output.blame_rows import BlameHistoryRows
from gigui.output.html import BlameHistoryStaticTableSoup, BlameTableSoup, logger
from gigui.typedefs import FileStr, Html, SHALong

# Suppress Flask startup messages
cli = sys.modules["flask.cli"]
cli.show_server_banner = lambda *x: None  # type: ignore

app = Flask(__name__)
CORS(app)  # Enable CORS for the Flask app

# Configure Werkzeug logger to suppress default access logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)

active_tabs = 0  # pylint: disable=invalid-name
active_tabs_lock = threading.Lock()


@app.route("/load-table/<table_id>")
def load_table(table_id) -> Html:
    # Extract file_nr and commit_nr from table_id
    table_html: Html = ""
    match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
    if match:
        file_nr = int(match.group(1))
        commit_nr = int(match.group(2))
        if shared_data.current_repo.blame_history == STATIC:
            table_html = get_fstr_commit_table(file_nr, commit_nr)
        elif shared_data.current_repo.blame_history == DYNAMIC:
            table_html = generate_fstr_commit_table(file_nr, commit_nr)
        else:  # NONE
            table_html = "Blame history is not enabled."
            logger.error("Error in blame history option: blame history is not enabled.")
        return table_html
    else:
        return (
            "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'"
        )


@app.route("/increment-tabs", methods=["POST"])
def increment_tabs() -> str:
    global active_tabs
    with active_tabs_lock:
        active_tabs += 1
    return "Tab count incremented"


@app.route("/decrement-tabs", methods=["POST"])
def decrement_tabs() -> str:
    global active_tabs
    with active_tabs_lock:
        active_tabs -= 1
        if active_tabs <= 0:
            shutdown_server = request.environ.get("werkzeug.server.shutdown")
            if shutdown_server is not None:
                shutdown_server()
            else:
                os._exit(0)
    return "Tab count decremented"


@app.route("/shutdown", methods=["POST"])
def shutdown() -> str:
    shutdown_server = request.environ.get("werkzeug.server.shutdown")
    if shutdown_server is not None:
        shutdown_server()
    else:
        os._exit(0)
    return "Server shutting down..."


@app.route("/")
def serve_initial_html() -> Response:
    """
    Serve the initial HTML code when the Flask server is accessed.
    """
    response = make_response(
        render_template_string(
            f"<title>{shared_data.repo_name}</title>{shared_data.html_code}",
            css_code=shared_data.css_code,
        )
    )
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


def start_flask_server() -> None:
    app.run(host="localhost", port=8080)


# Remove this method and dependencies
def start_flask_server_in_thread() -> threading.Thread:
    server_thread = threading.Thread(target=start_flask_server)
    server_thread.daemon = (
        True  # This ensures the thread will exit when the main program exits
    )
    server_thread.start()
    return server_thread


def start_flask_server_in_thread_with_html(
    generated_html: Html, name: str, css: str
) -> threading.Thread:
    shared_data.html_code = generated_html
    shared_data.repo_name = name
    shared_data.css_code = css
    return start_flask_server_in_thread()


def shutdown_flask_server() -> None:
    try:
        response = requests.post("http://127.0.0.1:8080/shutdown", timeout=5)
        if response.status_code == 200:
            logger.info("Flask server shut down successfully.")
        else:
            logger.error(f"Failed to shut down Flask server: {response.status_code}")
    except requests.exceptions.ConnectionError:
        logger.warning("Flask server is not running.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error shutting down Flask server: {e}")


def open_web_browser_for_flask_server() -> None:
    """
    Open the default web browser to display the HTML code served by the Flask server.
    """
    url = "http://localhost:8080"
    webbrowser.open(url)


def load_css() -> str:
    css_file = Path(__file__).parent / "files" / "styles.css"
    with open(css_file, "r", encoding="utf-8") as f:
        return f.read()


def get_fstr_commit_table(file_nr, commit_nr) -> Html:
    rows, iscomments = BlameHistoryRows(
        shared_data.current_repo
    ).get_fstr_sha_blame_rows(
        shared_data.current_repo.fstrs[file_nr],
        shared_data.current_repo.nr2sha[commit_nr],
        html=True,
    )
    table = BlameHistoryStaticTableSoup(shared_data.current_repo).get_table(
        rows, iscomments
    )
    html = str(table)
    html = html.replace("&amp;nbsp;", "&nbsp;")
    html = html.replace("&amp;lt;", "&lt;")
    html = html.replace("&amp;gt;", "&gt;")
    html = html.replace("&amp;quot;", "&quot;")
    return html


def generate_fstr_commit_table(file_nr, commit_nr) -> Html:
    fstr: FileStr = shared_data.current_repo.fstrs[file_nr]
    sha: SHALong = shared_data.current_repo.nr2sha[commit_nr]
    rows, iscomments = BlameHistoryRows(
        shared_data.current_repo
    ).generate_fstr_sha_blame_rows(fstr, sha, html=True)
    table = BlameTableSoup(shared_data.current_repo).get_table(
        rows, iscomments, file_nr, commit_nr
    )
    html = str(table)
    html = html.replace("&amp;nbsp;", "&nbsp;")
    html = html.replace("&amp;lt;", "&lt;")
    html = html.replace("&amp;gt;", "&gt;")
    html = html.replace("&amp;quot;", "&quot;")
    return html
