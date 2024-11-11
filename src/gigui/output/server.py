import logging
import multiprocessing
from pathlib import Path

from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from gigui.output.html import Html

PORT = 8080

# logging.getLogger("werkzeug").setLevel(logging.INFO)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

url_map = Map(
    [
        Rule("/load-table/<table_id>", endpoint="load_table"),
        Rule("/shutdown", endpoint="shutdown", methods=["POST"]),
        Rule("/", endpoint="serve_initial_html"),
    ]
)


# This is the main function that runs on the server. It catches all requests from
# javascript and either calls server functions defined here, or sends the requests to
# the main process via the queue.
def run_server(q: multiprocessing.Queue, shared_data_dict, port: int) -> None:
    @Request.application
    def app(request: Request) -> Response:
        if request.path == "/":
            return on_serve_initial_html(shared_data_dict)  # runs on server

        elif request.path == "/shutdown":
            q.put("shutdown")  # value "shutdown" doesn't matter, send to main process
            return Response(
                "Server is shutting down",
                content_type="text/plain",
            )  # Response is sent to the client browser, but in this case it doesn't matter

        elif request.path.startswith("/load-table/"):
            table_id = request.path.split("/")[-1]
            q.put(("load_table", table_id))  # Send to main process
            table_html = q.get()  # Wait for response from main process
            return Response(table_html, content_type="text/html")

        else:
            return Response("Not found", status=404)

    run_simple("localhost", port, app)


# Runs in server process
def on_serve_initial_html(shared_data_dict) -> Response:
    """
    Serve the initial HTML code when the server is accessed.
    """
    html_code: Html
    html_code = shared_data_dict["html_code"]
    html_code = html_code.replace(
        "</head>",
        f"<style>{shared_data_dict['css_code']}</style></head>",
    )
    html_code = html_code.replace(
        "</title>", f"{shared_data_dict['repo_name']}</title>"
    )

    # Read and insert JavaScript files
    js_files = [
        "adjustHeader.js",
        "updateRows.js",
        "tabActivation.js",
        "truncateTabNames.js",
        "shutdown.js",
    ]
    js_code = ""
    for js_file in js_files:
        js_path = Path(__file__).parent / "static" / "js" / js_file
        with open(js_path, "r", encoding="utf-8") as f:
            js_code += f"<script>{f.read()}</script>\n"

    html_code = html_code.replace("</body>", f"{js_code}</body>")

    response = Response(html_code, content_type="text/html; charset=utf-8")
    return response
