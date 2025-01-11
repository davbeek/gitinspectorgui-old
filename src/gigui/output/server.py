import logging
from multiprocessing import Queue
from threading import Thread

from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

import gigui._logging  # noqa
from gigui.output.html import Html

PORT = 8080

logging.getLogger("werkzeug").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

url_map = Map(
    [
        Rule("/load-table/<table_id>", endpoint="load_table"),
        Rule("/shutdown", endpoint="shutdown", methods=["POST"]),
        Rule("/", endpoint="serve_initial_html"),
    ]
)

shutdown_func = None  # Add this global variable


# This is the main function that runs on the server. It catches all requests from
# javascript and either calls server functions defined here, or sends the requests to
# the main process via the queue.
def run_server(q: Queue, html_code: Html, browser_id: str, port: int) -> None:
    global shutdown_func  # Use the global variable

    @Request.application
    def app(request: Request) -> Response:
        global shutdown_func  # Use the global variable
        shutdown_func = request.environ.get(
            "werkzeug.server.shutdown"
        )  # Store the shutdown function

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

    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received in module server")
        # Use werkzeug's shutdown mechanism
        if shutdown_func:
            shutdown_func()
        server_thread.join()
    finally:
        server_thread.join()
