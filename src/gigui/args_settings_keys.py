import json
import logging
from argparse import Namespace
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import jsonschema
import platformdirs
from git import PathLike

from gigui import common
from gigui._logging import set_logging_level_from_verbosity
from gigui.common import log, str_split_comma
from gigui.constants import (
    AVAILABLE_FORMATS,
    DEFAULT_COPY_MOVE,
    DEFAULT_EXTENSIONS,
    DEFAULT_FILE_BASE,
    DEFAULT_N_FILES,
    SUBDIR_NESTING_DEPTH,
)

PREFIX = "prefix"
POSTFIX = "postfix"
NOFIX = "nofix"
FIXTYPE = [PREFIX, POSTFIX, NOFIX]

AUTO = "auto"
NONE = "none"
VIEWER_CHOICES = [AUTO, NONE]
VIEWER_DEFAULT = AUTO

logger = logging.getLogger(__name__)


@dataclass
class Args:
    col_percent: int = 80  # Not used in CLI
    profile: int = 0  # Not used in GUI
    input_fstrs: list[str] = field(default_factory=list)
    outfile_base: str = DEFAULT_FILE_BASE
    fix: str = PREFIX
    depth: int = SUBDIR_NESTING_DEPTH
    format: list[str] = field(default_factory=lambda: [AUTO])
    scaled_percentages: bool = False
    blame_omit_exclusions: bool = False
    blame_skip: bool = False
    subfolder: str = ""
    n_files: int = DEFAULT_N_FILES
    include_files: list[str] = field(default_factory=list)
    show_renames: bool = False
    extensions: list[str] = field(default_factory=list)
    deletions: bool = False
    whitespace: bool = False
    empty_lines: bool = False
    comments: bool = False
    viewer: str = VIEWER_DEFAULT
    copy_move: int = DEFAULT_COPY_MOVE
    verbosity: int = 0
    dry_run: int = 0
    multi_thread: bool = True
    multi_core: bool = False
    since: str = ""
    until: str = ""
    ex_files: list[str] = field(default_factory=list)
    ex_authors: list[str] = field(default_factory=list)
    ex_emails: list[str] = field(default_factory=list)
    ex_revisions: list[str] = field(default_factory=list)
    ex_messages: list[str] = field(default_factory=list)

    # Return a valid settings dict for a dict that already satisfies the schema
    @staticmethod
    def validate_format_setting(d: dict) -> dict:
        formats = d["format"]
        if len(formats) == 0 or AUTO in formats and len(formats) > 1:
            formats = [AUTO]
        return d


@dataclass
class Settings(Args):
    # Do not use a constant variable for default_settings, because it is a mutable
    # object. It can be used as a starting point of settings. Therefore for each new
    # settings, a new object should be created.

    def create_settings_file(self, settings_path: Path):
        settings_dict = asdict(self)
        with open(settings_path, "w") as f:
            d = json.dumps(settings_dict, indent=4, sort_keys=True)
            f.write(d)

    def save(self):
        settings_dict = asdict(self)
        jsonschema.validate(settings_dict, SettingsFile.SETTINGS_SCHEMA)
        try:
            settings_path = SettingsFile.get_location()
        except (
            FileNotFoundError,
            json.decoder.JSONDecodeError,
            jsonschema.ValidationError,
        ):
            settings_path = SettingsFile.create_location_file_for(
                SettingsFile.DEFAULT_LOCATION_SETTINGS
            )
        self.create_settings_file(settings_path)

    def save_as(self, pathlike: PathLike):
        settings_file_path = Path(pathlike)
        settings_dict = asdict(self)
        jsonschema.validate(settings_dict, SettingsFile.SETTINGS_SCHEMA)
        with open(settings_file_path, "w") as f:
            d = json.dumps(settings_dict, indent=4, sort_keys=True)
            f.write(d)
        SettingsFile.set_location(settings_file_path)

    def to_cli_args(self) -> "CLIArgs":
        args = CLIArgs()
        vars_args = vars(args)
        settings_dict = asdict(self)
        for key in settings_dict:
            if key in vars_args:
                setattr(args, key, settings_dict[key])
        return args

    def log(self):
        settings_dict = asdict(self)
        for key, value in settings_dict.items():
            key = key.replace("_", "-")
            log(f"{key:21}: {value}")

    @classmethod
    def create_from_settings_dict(
        cls, settings_dict: dict[str, str | int | bool | list[str]]
    ) -> "Settings":
        settings_schema = SettingsFile.SETTINGS_SCHEMA["properties"]
        settings = cls()
        for key in settings_schema:
            if key == Keys.extensions and settings_dict[key] == DEFAULT_EXTENSIONS:
                setattr(settings, key, "")
            else:
                setattr(settings, key, settings_dict[key])
        return settings

    @classmethod
    def from_values_dict(cls, values: dict[str, str | int | bool]) -> "Settings":
        settings_schema = SettingsFile.SETTINGS_SCHEMA["properties"]
        settings = cls()

        for key in settings_schema:
            if key in values:
                if settings_schema[key]["type"] == "array":
                    setattr(settings, key, str_split_comma(values[key]))  # type: ignore
                else:
                    setattr(settings, key, values[key])

        if values[Keys.prefix]:
            settings.fix = Keys.prefix
        elif values[Keys.postfix]:
            settings.fix = Keys.postfix
        elif values[Keys.nofix]:
            settings.fix = Keys.nofix

        formats = []
        for fmt in AVAILABLE_FORMATS:
            if values[fmt]:
                formats.append(fmt)
        settings.format = formats

        return settings


@dataclass
class CLIArgs(Args):
    gui: bool = False
    show: bool = False
    save: bool = False
    save_as: str = ""
    load: str = ""
    reset: bool = False

    # Overwrite all settings apart from col_percent, which keeps its value
    def create_settings(self) -> Settings:
        logger.info(f"CLIself = {self}")

        settings = Settings()
        sets_dict = asdict(settings)
        args_dict = asdict(self)
        for fld in fields(Args):
            sets_dict[fld.name] = args_dict[fld.name]
        settings = Settings.create_from_settings_dict(sets_dict)
        if self.extensions != DEFAULT_EXTENSIONS:
            settings.extensions = self.extensions
        logger.info(f"GUISettings from CLIArgs: {settings}")
        return settings

    def create_args(self) -> Args:
        args = Args()
        cli_args_dict = asdict(self)
        for fld in fields(Args):
            if fld.name in cli_args_dict:
                setattr(args, fld.name, cli_args_dict[fld.name])
        return args

    def update_with_namespace(self, namespace: Namespace):
        if namespace.input_fstrs == []:
            namespace.input_fstrs = None
        nmsp_dict: dict = vars(namespace)
        nmsp_vars = nmsp_dict.keys()
        cli_args = CLIArgs()
        args_dict = asdict(cli_args)
        args_vars = args_dict.keys()
        for key in nmsp_dict:
            assert key in vars(self), f"Namespace var {key} not in CLIArgs"
            if nmsp_dict[key] is not None:
                setattr(self, key, nmsp_dict[key])
        set_logging_level_from_verbosity(self.verbosity)
        logger.info(f"CLI args - Namespace: {args_vars - nmsp_vars}")
        logger.info(f"Namespace - CLI args:  {nmsp_vars - args_vars}")


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
    blame_omit_exclusions: str = "blame_omit_exclusions"
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

    def __post_init(self):
        fldnames_args = [fld.name for fld in fields(Args)]
        fldnames_keys = [fld.name for fld in fields(self.__class__)]
        assert fldnames_args == fldnames_keys


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


class SettingsFile:
    SETTINGS_FILE_NAME = "gitinspectorgui.json"
    SETTINGS_LOCATION_FILE_NAME: str = "gitinspectorgui-location.json"

    SETTINGS_DIR = platformdirs.user_config_dir("gitinspectorgui", ensure_exists=True)
    SETTINGS_LOCATION_PATH = Path(SETTINGS_DIR) / SETTINGS_LOCATION_FILE_NAME
    INITIAL_SETTINGS_PATH = Path(SETTINGS_DIR) / SETTINGS_FILE_NAME

    SETTINGS_LOCATION_SCHEMA: dict = {
        "type": "object",
        "properties": {
            "settings_location": {"type": "string"},
        },
        "additionalProperties": False,
        "minProperties": 1,
    }
    DEFAULT_LOCATION_SETTINGS: dict[str, str] = {
        "settings_location": INITIAL_SETTINGS_PATH.as_posix(),
    }

    SETTINGS_SCHEMA: dict = {
        "type": "object",
        "properties": {
            "col_percent": {"type": "integer"},  # Not used in CLI
            "profile": {"type": "integer"},  # Not used in GUI
            "input_fstrs": {"type": "array", "items": {"type": "string"}},
            "format": {
                "type": "array",
                "items": {"type": "string", "enum": AVAILABLE_FORMATS},
            },
            "extensions": {"type": "array", "items": {"type": "string"}},
            "fix": {"type": "string", "enum": FIXTYPE},
            "outfile_base": {"type": "string"},
            "depth": {"type": "integer"},
            "scaled_percentages": {"type": "boolean"},
            "n_files": {"type": "integer"},
            "include_files": {"type": "array", "items": {"type": "string"}},
            "blame_omit_exclusions": {"type": "boolean"},
            "blame_skip": {"type": "boolean"},
            "show_renames": {"type": "boolean"},
            "subfolder": {"type": "string"},
            "deletions": {"type": "boolean"},
            "whitespace": {"type": "boolean"},
            "empty_lines": {"type": "boolean"},
            "comments": {"type": "boolean"},
            "viewer": {"type": "string"},
            "copy_move": {"type": "integer"},
            "verbosity": {"type": "integer"},
            "dry_run": {"type": "integer"},
            "multi_thread": {"type": "boolean"},
            "multi_core": {"type": "boolean"},
            "since": {"type": "string"},
            "until": {"type": "string"},
            "ex_authors": {"type": "array", "items": {"type": "string"}},
            "ex_emails": {"type": "array", "items": {"type": "string"}},
            "ex_files": {"type": "array", "items": {"type": "string"}},
            "ex_messages": {"type": "array", "items": {"type": "string"}},
            "ex_revisions": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
        "minProperties": 32,
    }

    # Create file that contains the location of the settings file and return this
    # settings file location.
    @classmethod
    def create_location_file_for(cls, location_settings: dict[str, str]) -> Path:
        jsonschema.validate(location_settings, cls.SETTINGS_LOCATION_SCHEMA)
        d = json.dumps(location_settings, indent=4)
        with open(cls.SETTINGS_LOCATION_PATH, "w") as f:
            f.write(d)
        return Path(location_settings["settings_location"])

    @classmethod
    def get_location(cls) -> Path:
        try:
            with open(cls.SETTINGS_LOCATION_PATH, "r") as f:
                s = f.read()
            settings_location_dict = json.loads(s)
            jsonschema.validate(settings_location_dict, cls.SETTINGS_LOCATION_SCHEMA)
            return Path(settings_location_dict["settings_location"])
        except (
            FileNotFoundError,
            json.decoder.JSONDecodeError,
            jsonschema.ValidationError,
        ):
            cls.create_location_file_for(cls.DEFAULT_LOCATION_SETTINGS)
            return cls.get_location()

    @classmethod
    def show(cls):
        path = cls.get_location()
        log(f"Settings file location: {path}")
        settings, error = cls.load()
        if not common.gui:
            settings.log()

    @classmethod
    def load(cls) -> tuple[Settings, str]:
        return cls.load_from(cls.get_location())

    @classmethod
    def load_from(cls, file: PathLike) -> tuple[Settings, str]:
        try:
            path = Path(file)
            if path.suffix != ".json":
                raise ValueError(f"File {str(path)} does not have a .json extension")
            with open(file, "r") as f:
                s = f.read()
                settings_dict = json.loads(s)
                jsonschema.validate(settings_dict, cls.SETTINGS_SCHEMA)
                settings_dict = Settings.validate_format_setting(settings_dict)
                return Settings(**settings_dict), ""
        except (
            ValueError,
            FileNotFoundError,
            json.decoder.JSONDecodeError,
            jsonschema.ValidationError,
        ) as e:
            return Settings(), str(e)

    @classmethod
    def reset(cls) -> Settings:
        cls.create_location_file_for(cls.DEFAULT_LOCATION_SETTINGS)
        settings = Settings()
        settings.save()
        return settings

    @classmethod
    def get_settings_file(cls) -> str:
        try:
            return cls.get_location().as_posix()
        except (
            FileNotFoundError,
            json.decoder.JSONDecodeError,
            jsonschema.ValidationError,
        ):
            cls.create_location_file_for(cls.DEFAULT_LOCATION_SETTINGS)
            return cls.get_location().as_posix()

    @classmethod
    def set_location(cls, location: PathLike):
        # Creating a new file or overwriting the existing file is both done using the
        # same "with open( ..., "w") as f" statement.
        cls.create_location_file_for({"settings_location": str(location)})
