import textwrap
from dataclasses import dataclass, fields

from gigui.constants import AVAILABLE_FORMATS, DEFAULT_EXTENSIONS, DEFAULT_N_FILES
from gigui.utils import get_version


# Help for GUI tooltips and for Help button
# All dataclass vars need to be declared with a type, otherwise, nothing works and var
# declarations are silently ignored.
@dataclass
class Tip:
    # IO configuration
    input_fstrs: str = "Absolute path(s) to repository, folders or URLs to be analyzed"
    outfile_base: str = (
        "Name of output file without extension, prefix or postfix (default gitinspect)"
    )
    outfile_path: str = "Full path to Output file base with optional postfix or prefix"
    out_file_option: str = (
        "Whether to add a postfix or prefix to the output file base, "
        "see result in output file path above"
    )
    postfix: str = (
        "Construct output file name by postfixing output file base with repository"
    )
    prefix: str = (
        "Construct output file name by prefixing output file base with repository"
    )
    nofix: str = "Output file name equals output file base"
    depth: str = (
        "Number of levels of subfolders of the input folder path that is "
        "searched for repositories"
    )

    # Output generation and formatting
    outputs: str = "Select output viewing and output formats to be generated"
    view: str = "View the generated output"
    html: str = "Generate html output"
    excel: str = "Generate excel output"

    # Statistics subgroup
    deletions: str = "Include deletions in addition to lines and insertions output"
    show_renames: str = (
        "Show previous file names and alternative author names and emails"
    )
    scaled_percentages: str = (
        "Show percentages that are scaled (multiplied) by the number of authors in "
        "the repository"
    )

    # Blame subgroup
    blame_history: str = (
        "Generate blame tables, "
        "static: all tables in html, "
        "dynamic: generate on demand, "
        "none: single table per file (default)"
    )
    blame_exclusions: str = (
        "Deal with: comments, empty and author lines that are excluded in html output, "
        "show: add and start by showing, "
        "hide: add and start by hiding, "
        "remove: do not add"
    )
    copy_move: str = (
        "0: Ignore copy and move of lines, "
        "1: Detect copy move within file, "
        "2: and across files in one commit (default), "
        "3: and across two commits, "
        "4: across all commits"
    )
    blame_skip: str = "Do not generate blame worksheets or blame tabs"

    # Subgroup blame inclusions
    empty_lines: str = "Include empty lines in blame calculations"
    comments: str = "Include comments in blame output"

    # Analysis options
    whitespace: str = "Include all whitespace in diffs and in copy move detection"
    verbosity: str = (
        "0: No debug output, "
        "1: Occasional output messages, "
        "2: Detailed debug output"
    )
    dry_run: str = (
        "0: normal execution, 1: fast analysis without viewer or output files, "
        "2: no analysis no output, only repo names."
    )

    # Inclusions and exclusions

    settings_file: str = "Settings file name or full path"
    file_options: str = (
        'For file selection, the file pattern for "Show files" has priority '
        'over "Show N files"'
    )
    n_files: str = (
        "For each repository generate output for the first N (default "
        f"{DEFAULT_N_FILES}) biggest files"
    )
    include_files: str = (
        "Generate output for all files matching any of the space-separated list of "
        f"specified patterns (default the {DEFAULT_N_FILES} biggest files)"
    )
    subfolder: str = "Restrict analysis to a subfolder of the repository"
    since: str = "Only show statistics for commits more recent than a specific date"
    since_box: str = "Enter a date of the form 2022-12-31 or press the dot button"
    until: str = "Only show statistics for commits older than a specific date"
    until_box: str = since_box
    extensions: str = (
        "Space-separated list of file extensions to include when computing "
        "statistics. Default extensions: " + " ".join(DEFAULT_EXTENSIONS)
    )

    # Multi-threading and multi-core
    multi_thread: str = (
        "Analyse multiple files for changes and blames per repository using multiple threads"
    )
    multi_core: str = (
        "Execute multiple repositories using multiple cores, disabled for GUI"
    )

    # Exclusion patterns
    ex_files: str = (
        "Filter out all files (or paths) containing any of the space-separated "
        "strings, e.g.: myfile.py test"
    )
    ex_authors: str = (
        "Filter out all authors containing any of the space-separated strings, "
        'e.g.: "John Smith" Mary*'
    )
    ex_emails: str = (
        "Filter out all emails containing any of the space-separated strings, "
        "e.g.: *@gmail.com john.smith@*"
    )
    ex_revisions: str = (
        "Filter out all revisions starting with any of the space-separated hash strings, "
        "e.g.: 8755fb3 123456"
    )
    ex_messages: str = (
        "Filter out all revisions containing any of the space-separated commit message "
        "strings"
    )


# Help for CLI
@dataclass
class Help(Tip):
    # Is printed using the description attribute of the ArgumentParser at the start of
    # the help output.
    help_doc: tuple[str, str, str] = (
        "For online documentation see <",
        "https://gitinspectorgui.readthedocs.io",
        ">",
    )

    # Mutually exclusive settings
    gui: str = """
        Start the GUI, taking all settings from the settings file and ignoring all
        other CLI arguments."""
    version: str = "Output version information."
    show: str = "Show the settings location and its values."
    save: str = "Save settings file."
    save_as: str = "Save settings file to PATH."
    load: str = "Load settings file from PATH and update its location."
    reset: str = (
        "Reset saved settings and location of settings file to their default values."
    )
    about: str = "Output license information."
    about_info: str = (
        f"GitinspectorGUI version {get_version()}. It utilizes the PySimpleGUI "
        "project, specifically the PyPI pysimplegui-4-foss version, which is licensed "
        "under the LGPL."
    )
    # Input
    input_fstrs: str = """
         Space-separated list of relative or absolute PATH(s) to repository, folders
         to be analyzed."""
    depth: str = """
        Number of levels of subfolders of the input folder PATH that is searched for
        repositories (default 5).
        DEPTH=0: the input folder itself must be a repository.
        DEPTH=1: only the input folder itself is searched for repository folders."""

    # Output
    pre_postfix: str = """
        Specify whether or not to add the name of the repository as
        prefix or postfix to the output file name."""

    # IO arguments
    format: str = (
        "Space-separated list of output formats. Select from "
        f"{', '.join(AVAILABLE_FORMATS)} (default html)."
    )
    # General configuration
    multi_core: str = "Execute multiple repositories using multiple cores."

    # Exclusions
    exclude_string: str = """Space-separated list of exclusion patterns describing the
file paths, revisions, revisions with certain commit messages, author names or author
emails that should be excluded from the statistics. Can be specified multiple times
separated by a space. Quotes may be used to keep spaces in names and * may be used to
specify any string."""

    # Logging
    cli_verbosity: str = "More verbose output for each v, e.g. -vv."
    profile: str = "Add profiling output to the console."

    exclude: str = "\n".join(
        textwrap.wrap(
            exclude_string,
            initial_indent=" " * 4,
            subsequent_indent=" " * 4,
            width=70,
        )
    )

    def __post_init__(self):
        for fld in fields(Tip):
            if getattr(self, fld.name) == getattr(super(), fld.name):
                setattr(self, fld.name, getattr(self, fld.name) + ".")
