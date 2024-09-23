import datetime
import logging
import multiprocessing
import os
import time
from argparse import (
    Action,
    ArgumentParser,
    ArgumentTypeError,
    BooleanOptionalAction,
    RawDescriptionHelpFormatter,
)
from pathlib import Path

from gigui import gitinspector
from gigui._logging import add_cli_handler, set_logging_level_from_verbosity
from gigui.args_settings_keys import (
    FIXTYPE,
    VIEWER_CHOICES,
    Args,
    CLIArgs,
    Settings,
    SettingsFile,
)
from gigui.common import get_digit, get_pos_number, get_version, log, str_split_comma
from gigui.constants import AVAILABLE_FORMATS, DEFAULT_EXTENSIONS, DEFAULT_FORMAT
from gigui.gui.psg import rungui
from gigui.tiphelp import Help

# Limit the width of the help text to 80 characters.
os.environ["COLUMNS"] = "90"

logger = logging.getLogger(__name__)
add_cli_handler()

help = Help()


class SplitAppendArgs(Action):
    def __call__(self, parser, namespace, arg_string, option_string=None):

        # split arg_string over "," then remove spacing and remove empty strings
        xs = str_split_comma(arg_string)

        # When the option is not used at all, the option value is set to the default
        # value of the option.

        # if not from line below, allows for both "" and [] to be used as empty values
        if not getattr(namespace, self.dest):
            # first time the option is used, set the list
            setattr(namespace, self.dest, xs)
        else:
            # next occurrence of option, list is already there, so append to list
            getattr(namespace, self.dest).extend(xs)


def valid_datetime_type(arg_datetime_str):
    """custom argparse type for user datetime values given from the command line"""
    if arg_datetime_str == "":
        return arg_datetime_str
    else:
        try:
            return datetime.datetime.strptime(arg_datetime_str, "%Y-%m-%d").strftime(
                "%Y-%m-%d"
            )
        except ValueError as e:
            raise ArgumentTypeError(
                f"Given Datetime ({arg_datetime_str}) not valid! "
                "Expected format: 'YYYY-MM-DD'."
            ) from e


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


class InvalidOptionError(ValueError):
    def __init__(self, msg):
        msg = f"Invalid option: {msg}"
        super().__init__(msg)
        self.msg = msg


def process_subfolder(subfolder):
    if len(subfolder) and (not subfolder.endswith("/")):
        subfolder += "/"
    return subfolder


def main():
    start_time = time.time()
    parser = ArgumentParser(
        prog="gitinspectorgui",
        description="".join(help.help_doc),
        formatter_class=RawDescriptionHelpFormatter,
    )

    mutex_group_titled = parser.add_argument_group("Mutually exclusive options")
    mutex_group = mutex_group_titled.add_mutually_exclusive_group()
    mutex_group.add_argument(
        "--gui",
        action="store_true",
        default=False,
        help=help.gui,
    )
    mutex_group.add_argument(
        "--show",
        action="store_true",
        default=False,
        help=help.show,
    )
    mutex_group.add_argument(
        "--save",
        action="store_true",
        default=False,
        help=help.save,
    )
    mutex_group.add_argument(
        "--save-as",
        type=str,
        metavar="PATH",
        help=help.save_as,
    )
    mutex_group.add_argument(
        "--load",
        type=str,
        metavar="PATH",
        help=help.load,
    )
    mutex_group.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help=help.reset,
    )
    mutex_group.add_argument(
        "-V",
        "--version",
        action="version",
        version=get_version(),
        help=help.version,
    )
    mutex_group.add_argument(
        "--about",
        action="version",
        version=help.about_info,
        help=help.about,
    )

    # Input
    group_input = parser.add_argument_group("Input")
    group_input.add_argument(
        "input_fstrs",
        nargs="*",  # produce a list of paths
        metavar="PATH",
        help=help.input_fstrs,
    )
    # folder and folders
    group_input.add_argument(
        "-d",
        "--depth",
        type=get_digit,
        help=help.depth,
    )

    # Output
    group_output = parser.add_argument_group("Output")
    group_output.add_argument(
        "-o",
        "--output",
        dest="outfile_base",
        metavar="FILEBASE",
        help=help.outfile_base,
    )
    group_output.add_argument(
        "--fix",
        choices=FIXTYPE,
        help=help.pre_postfix,
    )
    # Output generation and formatting
    group_generation = parser.add_argument_group("Output generation and formatting")
    group_generation.add_argument(
        "-F",
        "--format",
        action="append",
        # argparse adds each occurrence of the option to the list, therefore default is
        # []
        choices=AVAILABLE_FORMATS,
        help=help.format,
    )
    group_generation.add_argument(
        "--show-renames",
        action=BooleanOptionalAction,
        help=help.show_renames,
    )
    group_generation.add_argument(
        "--scaled-percentages",
        action=BooleanOptionalAction,
        help=help.scaled_percentages,
    )
    group_generation.add_argument(
        "--blame-omit-exclusions",
        action=BooleanOptionalAction,
        help=help.blame_omit_exclusions,
    )
    group_generation.add_argument(
        "--blame-skip",
        action=BooleanOptionalAction,
        help=help.blame_skip,
    )
    group_generation.add_argument(
        "--viewer",
        type=str,
        choices=VIEWER_CHOICES,
        help=help.viewer,
    )
    group_generation.add_argument(
        "-v",
        "--verbosity",
        action="count",
        help=help.cli_verbosity,
    )
    group_generation.add_argument(
        "--dry-run",
        type=int,
        choices=[0, 1, 2],
        help=help.dry_run,
    )

    # Inclusions and exclusions
    group_inc_exclusions = parser.add_argument_group("Inclusions and exclusions")
    files_group = group_inc_exclusions.add_mutually_exclusive_group()
    files_group.add_argument(
        "-n",
        "--n-files",
        "--include-n-files",
        type=get_pos_number,
        metavar="N",
        help=help.n_files,
    )
    files_group.add_argument(
        "-f",
        "--inc-files",
        "--include-files",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        dest="include_files",
        help=help.include_files,
    )
    group_inc_exclusions.add_argument(
        "--subfolder", type=process_subfolder, help=help.subfolder
    )
    group_inc_exclusions.add_argument(
        "--since", type=valid_datetime_type, help=help.since
    )
    group_inc_exclusions.add_argument(
        "--until", type=valid_datetime_type, help=help.until
    )
    group_inc_exclusions.add_argument(
        "-e",
        "--extensions",
        action=SplitAppendArgs,
        help=help.extensions,
    )

    # Analysis options
    # Include differences due to
    group_include_diffs = parser.add_argument_group(
        "Analysis options, include differences due to"
    )
    group_include_diffs.add_argument(
        "--deletions",
        action=BooleanOptionalAction,
        help=help.deletions,
    )
    group_include_diffs.add_argument(
        "--whitespace",
        action=BooleanOptionalAction,
        help=help.whitespace,
    )
    group_include_diffs.add_argument(
        "--empty-lines",
        action=BooleanOptionalAction,
        help=help.empty_lines,
    )
    group_include_diffs.add_argument(
        "--comments",
        action=BooleanOptionalAction,
        help=help.comments,
    )
    group_include_diffs.add_argument(
        "--copy-move",
        type=get_digit,
        metavar="N",
        help=help.copy_move,
    )

    # Multi-threading and multi-core
    group_general = parser.add_argument_group("Multi-threading and multi-core")
    group_general.add_argument(
        "--multi-thread",
        action=BooleanOptionalAction,
        help=help.multi_thread,
    )
    group_general.add_argument(
        "--multi-core",
        action=BooleanOptionalAction,
        help=help.multi_core,
    )

    # Exclusion options
    group_exclusions = parser.add_argument_group("Exclusion options", help.exclude)
    group_exclusions.add_argument(
        "--ex-files",
        "--exclude-files",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=help.ex_files,
    )
    group_exclusions.add_argument(
        "--ex-authors",
        "--exclude-authors",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=help.ex_authors,
    )
    group_exclusions.add_argument(
        "--ex-emails",
        "--exclude-emails",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=help.ex_emails,
    )
    group_exclusions.add_argument(
        "--ex-revisions",
        "--exclude-revisions",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=help.ex_revisions,
    )
    group_exclusions.add_argument(
        "--ex-messages",
        "--exclude-messages",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=help.ex_messages,
    )

    # Logging
    group_cli_only = parser.add_argument_group("Logging")

    group_cli_only.add_argument(
        "--profile",
        type=get_pos_number,
        metavar="N",
        help=help.profile,
    )

    namespace = parser.parse_args()

    settings: Settings = load_settings()
    cli_args: CLIArgs = settings.to_cli_args()
    if namespace.gui:
        rungui(settings)
    elif namespace.show:
        SettingsFile.show()
    elif namespace.save or namespace.save_as is not None:
        cli_args.update_with_namespace(namespace)
        settings = cli_args.create_settings()
        if namespace.save:
            settings.save()
            print(f"Settings saved to {SettingsFile.get_location()}.")
        else:
            path = namespace.save_as
            if path:
                if Path(path).suffix == ".json":
                    settings.save_as(path)
                    print(f"Settings saved to {path}.")
                else:
                    print(f"PATH {path} should be a JSON file.")
            else:
                print("Please specify a path for the settings file.")
    elif namespace.reset:
        SettingsFile.reset()
        log(f"Settings file reset to {SettingsFile.get_location()}.")
        settings, _ = SettingsFile.load()
        settings.log()
    else:
        error = ""
        if path := namespace.load:
            settings, error = SettingsFile.load_from(path)
            if error:
                logger.error(f"Error loading settings from {path}: {error}")
            else:
                SettingsFile.set_location(path)
                cli_args: CLIArgs = settings.to_cli_args()
                cli_args.update_with_namespace(namespace)
                log(f"Settings loaded from {path}.")
        else:  # not any of options: gui, show, save, save_as, reset, load
            cli_args.update_with_namespace(namespace)
        if not error:
            # Continue with preparations for running gitinspector.main
            if not cli_args.format:
                cli_args.format = [DEFAULT_FORMAT]

            if len(cli_args.format) > 1 and "auto" in cli_args.format:
                others = [x for x in cli_args.format if x != "auto"]
                logger.warning(
                    f"Format auto has priority: ignoring {", ".join(others)}"
                )
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


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
