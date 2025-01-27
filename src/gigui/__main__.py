import os

from gigui import cli

try:
    cli.main()
except KeyboardInterrupt:
    os._exit(0)
