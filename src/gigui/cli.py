import logging
import multiprocessing
import os
import time
from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from pathlib import Path

from gigui import gitinspector
from gigui._logging import add_cli_handler, set_logging_level_from_verbosity
from gigui.args_settings_keys import Args, CLIArgs, Settings, SettingsFile
from gigui.cli_arguments import define_arguments
from gigui.common import log
from gigui.constants import DEFAULT_EXTENSIONS, DEFAULT_FORMAT
from gigui.gui.psg import run as run_gui
from gigui.tiphelp import Help

# Limit the width of the help text to 80 characters.
os.environ["COLUMNS"] = "90"

logger = logging.getLogger(__name__)
add_cli_handler()


def load_settings():
    settings: Settings
    error: str
    settings, error = SettingsFile.load()
    set_logging_level_from_verbosity(settings.verbosity)
    if error:
        log(
            """Cannot load settings file, loading default settings.
            Save settings to resolve the issue."""
        )

    return settings


def run_gitinspector_main(cli_args: CLIArgs, start_time: float):
    if not cli_args.format:
        cli_args.format = [DEFAULT_FORMAT]

    if len(cli_args.format) > 1 and "auto" in cli_args.format:
        others = [x for x in cli_args.format if x != "auto"]
        logger.warning(f"Format auto has priority: ignoring {", ".join(others)}")
        cli_args.format = ["auto"]

    if not cli_args.extensions:
        cli_args.extensions = DEFAULT_EXTENSIONS

    # Replace "." by current working dir
    input_fstr = [
        (os.getcwd() if fstr == "." else fstr) for fstr in cli_args.input_fstrs
    ]
    cli_args.input_fstrs = input_fstr

    if len(cli_args.input_fstrs) == 0:
        cli_args.input_fstrs.append(os.getcwd())

    logger.info(f"{cli_args = }")

    args: Args = cli_args.create_args()
    gitinspector.main(args, start_time)


def handle_settings_file(namespace: Namespace, cli_args: CLIArgs):
    if namespace.show:
        SettingsFile.show()
    elif namespace.save:
        cli_args.update_with_namespace(namespace)
        settings = cli_args.create_settings()
        settings.save()
        print(f"Settings saved to {SettingsFile.get_location()}.")
    elif namespace.saveas is not None:
        path = namespace.save_as
        if not path:
            print("Please specify a path for the settings file.")
            return

        cli_args.update_with_namespace(namespace)
        settings = cli_args.create_settings()
        if Path(path).suffix == ".json":
            settings.save_as(path)
            print(f"Settings saved to {path}.")
        else:
            print(f"PATH {path} should be a JSON file.")
    elif namespace.reset:
        SettingsFile.reset()
        log(f"Settings file reset to {SettingsFile.get_location()}.")
        settings, _ = SettingsFile.load()
        settings.log()
    elif namespace.load is not None:
        path = namespace.load
        if not path:
            print("Please specify a path for the settings file.")
            return

        settings, error = SettingsFile.load_from(path)
        if error:
            logger.error(f"Error loading settings from {path}: {error}")
            return

        SettingsFile.set_location(path)
        # The loaded settings are ignored, because the program exits immediately after
        # executing this command.
        log(f"Settings loaded from {path}.")


def main():
    start_time = time.time()

    parser = ArgumentParser(
        prog="gitinspectorgui",
        description="".join(Help.help_doc),
        formatter_class=RawDescriptionHelpFormatter,
    )

    define_arguments(parser)
    namespace = parser.parse_args()

    settings: Settings = load_settings()
    cli_args: CLIArgs = settings.to_cli_args()

    if namespace.gui:
        run_gui(settings)
    elif (
        namespace.show
        or namespace.save
        or namespace.save_as is not None
        or namespace.load is not None
        or namespace.reset
    ):
        handle_settings_file(namespace, cli_args)
    else:
        cli_args.update_with_namespace(namespace)
        run_gitinspector_main(cli_args, start_time)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
