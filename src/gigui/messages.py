import platform


def close_tab_key():
    return "⌘W" if platform.system() == "Darwin" else "Ctrl+W"


def close_browser_key():
    match platform.system():
        case "Darwin":
            return "⌘Q"
        case "Linux":
            return "Ctrl+Q"
        case "Windows":
            return "Alt+F4"
        case _:
            return "Ctrl+Q"


CLOSE_OUTPUT_VIEWERS_MSG = (
    f"When you are done with the output, please close the browser window ({close_browser_key()}) or browser "
    f"tab(s) ({close_tab_key()}), but not before the pages have fully loaded. "
)

CONTROL_C = (
    "If necessary, use Ctrl+C"
    + (" (or Ctrl+Pause or Ctrl+Break)" if platform.system() == "Windows" else "")
    + " on the command line."
)

CLOSE_OUTPUT_VIEWERS_CLI_MSG = CLOSE_OUTPUT_VIEWERS_MSG + CONTROL_C
