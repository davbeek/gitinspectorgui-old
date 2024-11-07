import logging
import re
import threading
import webbrowser
from pathlib import Path

import requests  # type: ignore
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.routing import Map, Rule
from werkzeug.serving import make_server
from werkzeug.wrappers import Response

from gigui import shared_data
from gigui.constants import DYNAMIC, STATIC
from gigui.output.blame_rows import BlameHistoryRows
from gigui.output.html import BlameHistoryStaticTableSoup, BlameTableSoup, logger
from gigui.typedefs import FileStr, Html, SHALong

# Configure Werkzeug logger to suppress default access logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)

server = None  # pylint: disable=invalid-name

url_map = Map(
    [
        Rule("/load-table/<table_id>", endpoint="load_table"),
        Rule("/shutdown", endpoint="shutdown", methods=["POST"]),
        Rule("/", endpoint="serve_initial_html"),
    ]
)


def on_load_table(table_id) -> Response:
    print(f"on_load_table called with table_id: {table_id}")
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
        return Response(table_html, content_type="text/html")
    else:
        return Response(
            "Invalid table_id, should have the format 'file-<file_nr>-sha-<commit_nr>'",
            content_type="text/html",
        )


def on_shutdown() -> Response:
    print("on_shutdown called")
    if server is not None:
        server.shutdown()
    return Response("Server shutting down...", content_type="text/plain")


def on_serve_initial_html() -> Response:
    print("on_serve_initial_html called")
    """
    Serve the initial HTML code when the server is accessed.
    """
    html_code = f"""
    <html>
    <head>
        <title>{shared_data.repo_name}</title>
        <style>{shared_data.css_code}</style>
    </head>
    <body>
        {shared_data.html_code}
    </body>
    </html>
    """
    response = Response(html_code, content_type="text/html; charset=utf-8")
    return response


def application(environ, start_response):
    print("application called")
    urls = url_map.bind_to_environ(environ)
    try:
        endpoint, args = urls.match()
        print(f"Matched endpoint: {endpoint}, args: {args}")
        if endpoint == "load_table":
            response = on_load_table(**args)
        elif endpoint == "shutdown":
            response = on_shutdown()
        elif endpoint == "serve_initial_html":
            response = on_serve_initial_html()
        else:
            response = NotFound()
    except HTTPException as e:
        response = e
    return response(environ, start_response)


def start_werkzeug_server() -> None:
    global server
    if server is None:
        print("Starting Werkzeug server")
        server = make_server("localhost", 8080, application)
        server.serve_forever()
    else:
        print("Werkzeug server already running")


def start_werkzeug_server_in_thread() -> threading.Thread:
    global server
    print("Starting Werkzeug server in thread")
    server_thread = threading.Thread(target=start_werkzeug_server)
    server_thread.daemon = (
        True  # This ensures the thread will exit when the main program exits
    )
    server_thread.start()
    return server_thread


def start_werkzeug_server_in_thread_with_html(
    html_code: Html, repo_name: str, css_code: str
) -> threading.Thread:
    print(
        f"start_werkzeug_server_in_thread_with_html called with repo_name: {repo_name}"
    )
    shared_data.html_code = html_code
    shared_data.repo_name = repo_name
    shared_data.css_code = css_code

    # if server is None:
    return start_werkzeug_server_in_thread()


def shutdown_werkzeug_server() -> None:
    print("shutdown_werkzeug_server called")
    try:
        response = requests.post("http://127.0.0.1:8080/shutdown", timeout=5)
        if response.status_code == 200:
            logger.info("Werkzeug server shut down successfully.")
        else:
            logger.error(f"Failed to shut down Werkzeug server: {response.status_code}")
    except requests.exceptions.ConnectionError:
        logger.warning("Werkzeug server is not running.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error shutting down Werkzeug server: {e}")


def open_web_browser_for_werkzeug_server() -> None:
    """
    Open the default web browser to display the HTML code served by the Werkzeug server.
    """
    print("Opening web browser for Werkzeug server")
    url = "http://localhost:8080"
    webbrowser.open(url)


def load_css() -> str:
    print("Loading CSS")
    css_file = Path(__file__).parent / "files" / "styles.css"
    with open(css_file, "r", encoding="utf-8") as f:
        return f.read()


def get_fstr_commit_table(file_nr, commit_nr) -> Html:
    print(
        f"get_fstr_commit_table called with file_nr: {file_nr}, commit_nr: {commit_nr}"
    )
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
    print(
        f"generate_fstr_commit_table called with file_nr: {file_nr}, commit_nr: {commit_nr}"
    )
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
