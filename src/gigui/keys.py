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
    format: str = "format"
    scaled_percentages: str = "scaled_percentages"
    hide_blame_exclusions: str = "hide_blame_exclusions"
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
    viewer: str = "viewer"
    copy_move: str = "copy_move"
    verbosity: str = "verbosity"
    dry_run: str = "dry_run"
    multi_thread: str = "multi_thread"
    multi_core: str = "multi_core"
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
    debug: str = "debug"
    # Opening view
    open_webview: str = "open_webview"
    # Complete settings column
    config_column: str = "config_column"
    # Top row
    execute: str = "execute"
    clear: str = "clear"
    show: str = "show"
    save: str = "save"
    save_as: str = "save_as"
    load: str = "load"
    reset: str = "reset"
    help: str = "help"
    about: str = "about"
    exit: str = "exit"
    # IO configuration
    browse_input_fstr: str = "browse_input_fstr"
    outfile_path: str = "outfile_path"
    prefix: str = "prefix"
    postfix: str = "postfix"
    nofix: str = "nofix"
    # Output formats in table form
    auto: str = "auto"
    html: str = "html"
    excel: str = "excel"
    # General configuration
    since_box: str = "since_box"
    until_box: str = "until_box"
    # Console
    multiline: str = "multiline"
