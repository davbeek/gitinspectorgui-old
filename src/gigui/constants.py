import sys

# GUI window settings
WINDOW_SIZE_X = 660  # width of window
WINDOW_SIZE_Y = 720  # height of window

if sys.platform == "darwin":
    MAX_COL_HEIGHT = 509  # macOS, Macbook
else:
    MAX_COL_HEIGHT = 565  # Windows, Linux

WINDOW_HEIGHT_CORR = 45  # height correction: height of command buttons + title bar
INIT_COL_PERCENT = 75  # ratio of other layout vs multiline, default 4 : 1
ENABLED_COLOR = ("white", "#082567")
DISABLED_COLOR = ("grey", "#082567")
OPTION_TITLE_WIDTH = 13  # width of the column of text items before the option lines

# GUI option settings
REPO_HINT = "<repo-name>"
PARENT_HINT = "<repo-parent-folder>"

# GUI and CLI defaults
DEFAULT_FILE_BASE = "gitinspect"
SUBDIR_NESTING_DEPTH = 5
AVAILABLE_FORMATS = ["auto", "html", "excel"]
DEFAULT_FORMAT = "auto"
DEFAULT_N_FILES = 5
DEFAULT_COPY_MOVE = 2
DEFAULT_EXTENSIONS = [
    "c",
    "cc",
    "cif",
    "cpp",
    "glsl",
    "h",
    "hh",
    "hpp",
    "java",
    "js",
    "py",
    "rb",
    "sql",
]

# Output settings webview viewer
WEBVIEW_WIDTH = 1400
WEBVIEW_HEIGHT = 800

# Output settings web browser
MAX_BROWSER_TABS = 10

# Output settings Excel
ABBREV_CNT = 30

# Debugging
DEBUG_SHOW_MAIN_EVENT_LOOP = False
