import logging
from multiprocessing import Queue
from threading import Thread  # Add this import

from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

import gigui._logging  # noqa # Ensure the verbose method is added to the logger
from gigui.output.html import Html

PORT = 8080

# logging.getLogger("werkzeug").setLevel(logging.INFO)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


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
def run_server(q: Queue, html_code: Html, browser_id: str, port: int) -> None:
    @Request.application
    def app(request: Request) -> Response:
        logger.verbose(f"From browser = {request.path} {request.args.get('id')}")  # type: ignore

        if request.path == "/":
            return Response(html_code, content_type="text/html; charset=utf-8")

        elif request.path.startswith("/shutdown"):
            shutdown_id = request.args.get("id")
            if shutdown_id == browser_id:
                q.put(("shutdown", browser_id))  # Send to main process
                return Response(
                    content_type="text/plain",
                )
            else:
                return Response("Invalid shutdown ID", status=403)

        elif request.path.startswith("/load-table/"):
            table_id = request.path.split("/")[-1]
            load_table_id = request.args.get("id")
            if load_table_id == browser_id:
                q.put(("load_table", table_id, browser_id))  # Send to main process
                table_html = q.get()  # Wait for response from main process
                return Response(table_html, content_type="text/html")
            else:
                return Response("Invalid browser ID", status=403)

        else:
            return Response("Not found", status=404)

    # Run the server in a new thread
    server_thread = Thread(target=run_simple, args=("localhost", port, app))
    server_thread.start()
