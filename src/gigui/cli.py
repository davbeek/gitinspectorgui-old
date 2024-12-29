import logging
import multiprocessing
import os
import time
from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from pathlib import Path

from gigui import gitinspector
from gigui._logging import add_cli_handler, set_logging_level_from_verbosity
from gigui.args_settings import Args, CLIArgs, Settings, SettingsFile
from gigui.cli_arguments import define_arguments
from gigui.constants import AVAILABLE_FORMATS, DEFAULT_EXTENSIONS
from gigui.gui.psg import run as run_gui
from gigui.tiphelp import Help
from gigui.utils import log

# Limit the width of the help text to 80 characters.
os.environ["COLUMNS"] = "90"

logger = logging.getLogger(__name__)
add_cli_handler()


def main() -> None:
    start_time = time.time()

    parser = ArgumentParser(
        prog="gitinspectorgui",
        description="".join(Help.help_doc),
        formatter_class=RawDescriptionHelpFormatter,
    )

    define_arguments(parser)
    namespace = parser.parse_args()

    settings: Settings = load_settings(namespace.save, namespace.save_as)
    gui_settings_full_path = settings.gui_settings_full_path

    cli_args: CLIArgs = settings.to_cli_args()

    cli_args.update_with_namespace(namespace)

    if cli_args.profile:
        cli_args.view = False

    # Replace "." by current working dir and resolve paths.
    input_fstrs = [
        (os.getcwd() if fstr == "." else fstr) for fstr in cli_args.input_fstrs
    ]
    input_fstrs_resolved = [str(Path(fstr).resolve()) for fstr in input_fstrs]
    cli_args.input_fstrs = input_fstrs_resolved

    if len(cli_args.input_fstrs) == 0:
        cli_args.input_fstrs.append(os.getcwd())

    # Validate formats
    for fmt in cli_args.format:
        if fmt not in AVAILABLE_FORMATS:
            # Print error message and exit
            parser.error(
                f"Invalid format: {fmt}. Available formats: {', '.join(AVAILABLE_FORMATS)}"
            )

    if (
        namespace.show
        or namespace.save
        or namespace.save_as is not None
        or namespace.load is not None
        or namespace.reset
    ):
        handle_settings_file(namespace, cli_args)
        if namespace.save:
            SettingsFile.show()
        return

    if not cli_args.extensions:
        cli_args.extensions = DEFAULT_EXTENSIONS

    logger.info(f"{cli_args = }")

    args: Args = cli_args.create_args()

    if namespace.gui:
        run_gui(Settings.from_args(args, gui_settings_full_path))
    else:
        gitinspector.main(args, start_time)


def load_settings(save: bool, save_as: str) -> Settings:
    settings: Settings
    error: str
    settings, error = SettingsFile.load()
    set_logging_level_from_verbosity(settings.verbosity)
    if error:
        log("Cannot load settings file, loading default settings.")
        if not save and not save_as:
            log("Save settings so that they can be found next time.")

    return settings


def handle_settings_file(namespace: Namespace, cli_args: CLIArgs):
    if namespace.show:
        SettingsFile.show()

    elif namespace.save or namespace.save_as is not None:
        if namespace.save:
            settings = cli_args.create_settings()
            settings.save()
        else:  # save_as
            path_str = namespace.save_as
            if not path_str:
                print("Please specify a path for the settings file.")
                return
            settings = cli_args.create_settings()

            if Path(path_str).suffix == ".json":
                path = Path(path_str).resolve()
                settings.save_as(path)
                print(f"Settings saved to {path}.")
            else:
                print(f"PATH {path_str} should be a JSON file.")

    elif namespace.reset:
        SettingsFile.reset()
        log(f"Settings file reset to {SettingsFile.get_location()}.")
        settings, _ = SettingsFile.load()
        settings.log()

    elif namespace.load is not None:
        path_str = namespace.load
        if not path_str:
            print("Please specify a path for the settings file.")
            return
        settings, error = SettingsFile.load_from(path_str)
        if error:
            logger.error(f"Error loading settings from {path_str}: {error}")
            return
        SettingsFile.set_location(path_str)
        # The loaded settings are ignored, because the program exits immediately after
        # executing this command.
        log(f"Settings loaded from {path_str}.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
