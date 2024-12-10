import datetime
from argparse import (  # type: ignore
    Action,
    ArgumentParser,
    ArgumentTypeError,
    BooleanOptionalAction,
)

from gigui.constants import (
    AVAILABLE_FORMATS,
    BLAME_EXCLUSION_CHOICES,
    BLAME_HISTORY_CHOICES,
    FIX_TYPE,
)
from gigui.tiphelp import Help
from gigui.utils import get_digit, get_pos_number, get_version, str_split_comma

hlp = Help()


def define_arguments(parser: ArgumentParser):  # pylint: disable=too-many-statements
    mutex_group_titled = parser.add_argument_group("Mutually exclusive options")
    mutex_group = mutex_group_titled.add_mutually_exclusive_group()
    mutex_group.add_argument(
        "--gui",
        action="store_true",
        help=hlp.gui,
    )
    mutex_group.add_argument(
        "--show",
        action="store_true",
        help=hlp.show,
    )
    mutex_group.add_argument(
        "--save",
        action="store_true",
        help=hlp.save,
    )
    mutex_group.add_argument(
        "--save-as",
        type=str,
        metavar="PATH",
        help=hlp.save_as,
    )
    mutex_group.add_argument(
        "--load",
        type=str,
        metavar="PATH",
        help=hlp.load,
    )
    mutex_group.add_argument(
        "--reset",
        action="store_true",
        help=hlp.reset,
    )
    mutex_group.add_argument(
        "-V",
        "--version",
        action="version",
        version=get_version(),
        help=hlp.version,
    )
    mutex_group.add_argument(
        "--about",
        action="version",
        version=hlp.about_info,
        help=hlp.about,
    )

    # Input
    group_input = parser.add_argument_group("Input")
    group_input.add_argument(
        "input_fstrs",
        nargs="*",  # produce a list of paths
        metavar="PATH",
        help=hlp.input_fstrs,
    )
    # folder and folders
    group_input.add_argument(
        "-d",
        "--depth",
        type=get_digit,
        help=hlp.depth,
    )

    # Output
    group_output = parser.add_argument_group("Output")
    group_output.add_argument(
        "-o",
        "--output",
        dest="outfile_base",
        metavar="FILE_BASE",
        help=hlp.outfile_base,
    )
    group_output.add_argument(
        "--fix",
        choices=FIX_TYPE,
        help=hlp.pre_postfix,
    )
    # Output generation and formatting
    group_generation = parser.add_argument_group("Output generation and formatting")
    group_generation.add_argument(
        "--view",
        action=BooleanOptionalAction,
        help=hlp.view,
    )
    group_generation.add_argument(
        "-F",
        "--format",
        action="append",
        # argparse adds each occurrence of the option to the list, therefore default is
        # []
        choices=AVAILABLE_FORMATS,
        help=hlp.format,
    )
    group_generation.add_argument(
        "--show-renames",
        action=BooleanOptionalAction,
        help=hlp.show_renames,
    )
    group_generation.add_argument(
        "--scaled-percentages",
        action=BooleanOptionalAction,
        help=hlp.scaled_percentages,
    )
    group_generation.add_argument(
        "--blame-exclusions",
        choices=BLAME_EXCLUSION_CHOICES,
        help=hlp.blame_exclusions,
    )
    group_generation.add_argument(
        "--blame-skip",
        action=BooleanOptionalAction,
        help=hlp.blame_skip,
    )
    group_generation.add_argument(
        "--blame-history",
        choices=BLAME_HISTORY_CHOICES,
        help=hlp.blame_history,
    )
    group_generation.add_argument(
        "-v",
        "--verbosity",
        action="count",
        help=hlp.cli_verbosity,
    )
    group_generation.add_argument(
        "--dry-run",
        type=int,
        choices=[0, 1, 2],
        help=hlp.dry_run,
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
        help=hlp.n_files,
    )
    files_group.add_argument(
        "-f",
        "--include-files",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        dest="include_files",
        help=hlp.include_files,
    )
    group_inc_exclusions.add_argument(
        "--subfolder", type=ensure_trailing_slash, help=hlp.subfolder
    )
    group_inc_exclusions.add_argument(
        "--since", type=valid_datetime_type, help=hlp.since
    )
    group_inc_exclusions.add_argument(
        "--until", type=valid_datetime_type, help=hlp.until
    )
    group_inc_exclusions.add_argument(
        "-e",
        "--extensions",
        action=SplitAppendArgs,
        help=hlp.extensions,
    )

    # Analysis options
    # Include differences due to
    group_include_diffs = parser.add_argument_group(
        "Analysis options, include differences due to"
    )
    group_include_diffs.add_argument(
        "--deletions",
        action=BooleanOptionalAction,
        help=hlp.deletions,
    )
    group_include_diffs.add_argument(
        "--whitespace",
        action=BooleanOptionalAction,
        help=hlp.whitespace,
    )
    group_include_diffs.add_argument(
        "--empty-lines",
        action=BooleanOptionalAction,
        help=hlp.empty_lines,
    )
    group_include_diffs.add_argument(
        "--comments",
        action=BooleanOptionalAction,
        help=hlp.comments,
    )
    group_include_diffs.add_argument(
        "--copy-move",
        type=get_digit,
        metavar="N",
        help=hlp.copy_move,
    )

    # Multi-threading and multi-core
    group_general = parser.add_argument_group("Multi-threading and multi-core")
    group_general.add_argument(
        "--multi-thread",
        action=BooleanOptionalAction,
        help=hlp.multi_thread,
    )
    group_general.add_argument(
        "--multi-core",
        action=BooleanOptionalAction,
        help=hlp.multi_core,
    )

    # Exclusion options
    group_exclusions = parser.add_argument_group("Exclusion options", hlp.exclude)
    group_exclusions.add_argument(
        "--ex-files",
        "--exclude-files",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=hlp.ex_files,
    )
    group_exclusions.add_argument(
        "--ex-authors",
        "--exclude-authors",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=hlp.ex_authors,
    )
    group_exclusions.add_argument(
        "--ex-emails",
        "--exclude-emails",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=hlp.ex_emails,
    )
    group_exclusions.add_argument(
        "--ex-revisions",
        "--exclude-revisions",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=hlp.ex_revisions,
    )
    group_exclusions.add_argument(
        "--ex-messages",
        "--exclude-messages",
        action=SplitAppendArgs,
        metavar="PATTERNS",
        help=hlp.ex_messages,
    )

    # Logging
    group_cli_only = parser.add_argument_group("Logging")
    group_cli_only.add_argument(
        "--profile",
        type=get_pos_number,
        metavar="N",
        help=hlp.profile,
    )


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


def ensure_trailing_slash(subfolder):
    if len(subfolder) and (not subfolder.endswith("/")):
        subfolder += "/"
    return subfolder
