import logging
import multiprocessing
import re
import time

# import webbrowser
from multiprocessing import Process, Queue
from pathlib import Path

import requests  # type: ignore
from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

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


def on_serve_initial_html() -> Response:
    """
    Serve the initial HTML code when the server is accessed.
    """
    print("on_serve_initial_html called")
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


def send_terminate_token() -> None:
    url = "http://localhost:8080/?token=xyz123"  # token value xyz123 doesn't matter
    requests.get(url, timeout=1)  # Added timeout argument


def start_werkzeug_server_in_process_with_html(
    html_code: Html, repo_name: str, css_code: str
) -> None:
    print(f"Start werkzeug sever with html called for repo: {repo_name}")
    shared_data.html_code = html_code
    shared_data.repo_name = repo_name
    shared_data.css_code = css_code

    process_queue: Queue = Queue()
    server_process: Process = Process(target=get_token, args=(process_queue,))
    server_process.start()

    # Add a delay to ensure the server is up and running
    time.sleep(1)

    send_terminate_token()

    process_queue.get(block=True)
    server_process.terminate()


def get_token(q: multiprocessing.Queue) -> None:
    @Request.application
    def app(request: Request) -> Response:
        q.put(request.args["token"])
        return Response("", 204)

    run_simple("localhost", 8080, app)


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
