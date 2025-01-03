import datetime
from argparse import (  # type: ignore
    ArgumentParser,
    ArgumentTypeError,
    BooleanOptionalAction,
)

from gigui.constants import BLAME_EXCLUSION_CHOICES, BLAME_HISTORY_CHOICES, FIX_TYPE
from gigui.tiphelp import Help
from gigui.utils import get_digit, get_pos_number, get_pos_number_or_empty, get_version

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
    group_input.add_argument(
        "--subfolder",
        help=hlp.subfolder,
    )
    files_group = group_input.add_mutually_exclusive_group()
    files_group.add_argument(
        "-n",
        "--n-files",
        # Unfortunately, for an empty option string, get_pos_number_or_empty is not
        # called.
        type=get_pos_number_or_empty,
        nargs="?",  # Accept zero or one argument
        metavar="N",
        help=hlp.n_files,
    )
    files_group.add_argument(
        "-f",
        "--include-files",
        action="extend",
        nargs="*",
        metavar="PATTERNS",
        help=hlp.include_files,
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
    group_generation = parser.add_argument_group("Output generation and viewing")
    group_generation.add_argument(
        "--view",
        action=BooleanOptionalAction,
        help=hlp.view,
    )
    group_generation.add_argument(
        "-F",
        "--format",
        action="extend",
        nargs="*",
        help=hlp.format,
    )

    # Below follow the subgroups from group "Output generation and formatting". The
    # subgroups are added directly to the parser instead of to the "Output generation
    # and formatting" group, because real subgroups are not shown in the help output.

    # Statistics subgroup
    subgroup_stats = parser.add_argument_group("Statistics output")
    subgroup_stats.add_argument(
        "--show-renames",
        action=BooleanOptionalAction,
        help=hlp.show_renames,
    )
    subgroup_stats.add_argument(
        "--deletions",
        action=BooleanOptionalAction,
        help=hlp.deletions,
    )
    subgroup_stats.add_argument(
        "--scaled-percentages",
        action=BooleanOptionalAction,
        help=hlp.scaled_percentages,
    )

    # Blame subgroup
    subgroup_blame = parser.add_argument_group("Blame")
    subgroup_blame.add_argument(
        "--blame-history",
        choices=BLAME_HISTORY_CHOICES,
        help=hlp.blame_history,
    )
    subgroup_blame.add_argument(
        "--blame-exclusions",
        choices=BLAME_EXCLUSION_CHOICES,
        help=hlp.blame_exclusions,
    )
    subgroup_blame.add_argument(
        "--copy-move",
        type=get_digit,
        metavar="N",
        help=hlp.copy_move,
    )
    subgroup_blame.add_argument(
        "--blame-skip",
        action=BooleanOptionalAction,
        help=hlp.blame_skip,
    )

    # Subgroup blame inclusions
    subgroup_blame_inclusions = parser.add_argument_group("Blame inclusions")
    subgroup_blame_inclusions.add_argument(
        "--empty-lines",
        action=BooleanOptionalAction,
        help=hlp.empty_lines,
    )
    subgroup_blame_inclusions.add_argument(
        "--comments",
        action=BooleanOptionalAction,
        help=hlp.comments,
    )

    # Analysis options
    subgroup_general_options = parser.add_argument_group("General options")
    subgroup_general_options.add_argument(
        "--whitespace",
        action=BooleanOptionalAction,
        help=hlp.whitespace,
    )
    subgroup_general_options.add_argument(
        "--since", type=valid_datetime_type, help=hlp.since
    )
    subgroup_general_options.add_argument(
        "--until", type=valid_datetime_type, help=hlp.until
    )
    subgroup_general_options.add_argument(
        "-v",
        "--verbosity",
        action="count",
        help=hlp.cli_verbosity,
    )
    subgroup_general_options.add_argument(
        "--dry-run",
        type=int,
        choices=[0, 1, 2],
        help=hlp.dry_run,
    )
    subgroup_general_options.add_argument(
        "-e",
        "--extensions",
        action="extend",
        nargs="*",
        help=hlp.extensions,
    )

    # Multithread and multicore
    group_general = parser.add_argument_group("Multithread and multicore")
    group_general.add_argument(
        "--multithread",
        action=BooleanOptionalAction,
        help=hlp.multithread,
    )
    group_general.add_argument(
        "--multicore",
        action=BooleanOptionalAction,
        help=hlp.multicore,
    )

    # Exclusion patterns
    group_exclusions = parser.add_argument_group("Exclusion patterns", hlp.exclude)
    group_exclusions.add_argument(
        "--ex-files",
        "--exclude-files",
        action="extend",
        nargs="*",
        metavar="PATTERNS",
        help=hlp.ex_files,
    )
    group_exclusions.add_argument(
        "--ex-authors",
        "--exclude-authors",
        action="extend",
        nargs="*",
        metavar="PATTERNS",
        help=hlp.ex_authors,
    )
    group_exclusions.add_argument(
        "--ex-emails",
        "--exclude-emails",
        action="extend",
        nargs="*",
        metavar="PATTERNS",
        help=hlp.ex_emails,
    )
    group_exclusions.add_argument(
        "--ex-revisions",
        "--exclude-revisions",
        action="extend",
        nargs="*",
        metavar="PATTERNS",
        help=hlp.ex_revisions,
    )
    group_exclusions.add_argument(
        "--ex-messages",
        "--exclude-messages",
        action="extend",
        nargs="*",
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
