from dataclasses import dataclass


# The field names of class KeysArgs are identical to those of class Args, but the values
# are all strings equal to the names.
@dataclass
class KeysArgs:
    col_percent: str = "col_percent"
    profile: str = "profile"
    input_fstrs: str = "input_fstrs"
    outfile_base: str = "outfile_base"
    fix: str = "fix"
    depth: str = "depth"
    view: str = "view"
    file_formats: str = "file_formats"
    scaled_percentages: str = "scaled_percentages"
    blame_exclusions: str = "blame_exclusions"
    blame_skip: str = "blame_skip"
    subfolder: str = "subfolder"
    n_files: str = "n_files"
    include_files: str = "include_files"
    show_renames: str = "show_renames"
    extensions: str = "extensions"
    deletions: str = "deletions"
    whitespace: str = "whitespace"
    empty_lines: str = "empty_lines"
    comments: str = "comments"
    copy_move: str = "copy_move"
    verbosity: str = "verbosity"
    dry_run: str = "dry_run"
    multithread: str = "multithread"
    multicore: str = "multicore"
    since: str = "since"
    until: str = "until"
    ex_files: str = "ex_files"
    ex_authors: str = "ex_authors"
    ex_emails: str = "ex_emails"
    ex_revisions: str = "ex_revisions"
    ex_messages: str = "ex_messages"


@dataclass
class Keys(KeysArgs):
    help_doc: str = "help_doc"

    # key to end the GUI when window is closed
    end: str = "end"

    # Logging
    log: str = "log"
    logging: str = "logging"

    # Complete settings column
    config_column: str = "config_column"

    # Top row
    run: str = "run"
    stop: str = "stop"
    enable_stop_button: str = "enable_stop_button"
    clear: str = "clear"
    show: str = "show"
    help: str = "help"
    about: str = "about"
    exit: str = "exit"

    # Settings
    settings_file: str = "settings_file"
    save: str = "save"
    save_as: str = "save_as"
    load: str = "load"
    reset: str = "reset"
    reset_file: str = "reset_file"
    toggle_settings_file: str = "toggle_settings_file"
    gui_settings_full_path: str = "gui_settings_full_path"

    # IO configuration
    browse_input_fstr: str = "browse_input_fstr"
    outfile_path: str = "outfile_path"

    # Radio buttons for prefix, postfix and no prefix or postfix
    prefix: str = "prefix"
    postfix: str = "postfix"
    nofix: str = "nofix"

    # Radio buttons for viewing: auto or dynamic blame history
    # Note that hyphens are used in "dynamic-blame-history" because it is used as option
    # value in the CLI.
    auto: str = "auto"
    dynamic_blame_history: str = "dynamic-blame-history"

    # Radio buttons for file formats
    # Note that hyphens are used in "html-blame-history" because it is used as option
    # value in the CLI.
    html: str = "html"
    html_blame_history: str = "html-blame-history"
    excel: str = "excel"

    # General configuration
    since_box: str = "since_box"
    until_box: str = "until_box"

    # Console
    multiline: str = "multiline"
