import logging
import os
import re
import sys
import threading
from pathlib import Path

import requests  # type: ignore
from flask import Flask, Response, make_response, request, send_from_directory
from flask_cors import CORS  # type: ignore

from gigui.args_settings import DYNAMIC, STATIC
from gigui.output import html
from gigui.output.html import generate_fstr_commit_table, get_fstr_commit_table, logger
from gigui.typedefs import FileStr, Html
from gigui.utils import log

# Suppress Flask startup messages
cli = sys.modules["flask.cli"]
cli.show_server_banner = lambda *x: None  # type: ignore

app = Flask(__name__)
CORS(app)  # Enable CORS for the Flask app

# Configure Werkzeug logger to suppress default access logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)

active_tabs = 0
active_tabs_lock = threading.Lock()


@app.route("/load-table/<table_id>")
def load_table(table_id) -> Html:
    # Extract file_nr and commit_nr from table_id
    match = re.match(r"file-(\d+)-sha-(\d+)", table_id)
    if match:
        file_nr = int(match.group(1))
        commit_nr = int(match.group(2))
        if html.current_repo.args.blame_history == STATIC:
            table_html = get_fstr_commit_table(file_nr, commit_nr)
        elif html.current_repo.args.blame_history == DYNAMIC:
            table_html = generate_fstr_commit_table(file_nr, commit_nr)
        else:  # NONE
            table_html = "Blame history is not enabled."
            logger.error("Error in blame history option: blame history is not enabled.")
        return table_html
    else:
        return "Invalid table_id"


@app.route("/files/<path:fstr>")
def serve_static(fstr: FileStr) -> Response:
    if not fstr.startswith("/"):
        fstr = "/" + fstr
    file_path = Path(fstr).resolve()
    if not file_path.exists():
        log(f"File not found: {file_path}")
        return make_response("File not found", 404)
    file_dir = str(file_path.parent)
    filename = file_path.name
    return send_from_directory(file_dir, filename)


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


def start_flask_server() -> None:
    app.run(host="localhost", port=8080)


def start_flask_server_in_thread() -> threading.Thread:
    server_thread = threading.Thread(target=start_flask_server)
    server_thread.daemon = (
        True  # This ensures the thread will exit when the main program exits
    )
    server_thread.start()
    return server_thread


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
