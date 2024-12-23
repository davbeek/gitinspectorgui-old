import sys

if sys.platform == "darwin":
    # macOS, Macbook Pro 16
    MAX_COL_HEIGHT = 494  # height of settings column
    WINDOW_SIZE_Y = 720  # height of GUI window
    WINDOW_SIZE_X = 660  # width of GUI window
else:
    # Windows, Linux
    MAX_COL_HEIGHT = 526  # height op settings column
    WINDOW_SIZE_Y = 740  # height of window
    WINDOW_SIZE_X = 670  # width of window

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
AVAILABLE_FORMATS = ["html", "excel"]
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

# Constants for CLI arguments, GUI options and settings
PREFIX = "prefix"
POSTFIX = "postfix"
NOFIX = "nofix"
FIX_TYPE = [PREFIX, POSTFIX, NOFIX]

NONE = "none"
STATIC = "static"
DYNAMIC = "dynamic"
BLAME_HISTORY_CHOICES = [NONE, DYNAMIC, STATIC]
BLAME_HISTORY_DEFAULT = NONE

REMOVE = "remove"
HIDE = "hide"
SHOW = "show"
BLAME_EXCLUSION_CHOICES = [HIDE, SHOW, REMOVE]
BLAME_EXCLUSIONS_DEFAULT = HIDE
