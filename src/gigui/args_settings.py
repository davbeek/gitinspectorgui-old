import json
import logging
from argparse import Namespace
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import jsonschema
import platformdirs
from git import PathLike

from gigui import utils
from gigui._logging import set_logging_level_from_verbosity
from gigui.constants import (
    AVAILABLE_FORMATS,
    DEFAULT_COPY_MOVE,
    DEFAULT_EXTENSIONS,
    DEFAULT_FILE_BASE,
    DEFAULT_N_FILES,
    SUBDIR_NESTING_DEPTH,
)
from gigui.keys import Keys, KeysArgs
from gigui.utils import log, str_split_comma

PREFIX = "prefix"
POSTFIX = "postfix"
NOFIX = "nofix"
FIX_TYPE = [PREFIX, POSTFIX, NOFIX]

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
    hide_blame_exclusions: bool = False
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

    def __post_init__(self):
        fld_names_args = {fld.name for fld in fields(Args)}
        fld_names_keys = {fld.name for fld in fields(KeysArgs)}
        assert fld_names_args == fld_names_keys, (
            f"Args - KeysArgs: {fld_names_args - fld_names_keys}\n"
            f"KeysArgs - Args: {fld_names_keys - fld_names_args}"
        )


@dataclass
class Settings(Args):
    # Do not use a constant variable for default_settings, because it is a mutable
    # object. It can be used as a starting point of settings. Therefore for each new
    # settings, a new object should be created.

    gui_settings_full_path: bool = False

    def create_settings_file(self, settings_path: Path):
        settings_dict = asdict(self)
        with open(settings_path, "w", encoding="utf-8") as f:
            d = json.dumps(settings_dict, indent=4, sort_keys=True)
            f.write(d)

    # Validate the format setting for a setting read from the settings file.
    def validate_format(self) -> None:
        if len(self.format) == 0 or AUTO in self.format and len(self.format) > 1:
            self.format = [AUTO]

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
        with open(settings_file_path, "w", encoding="utf-8") as f:
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
        settings_schema: dict[str, Any] = SettingsFile.SETTINGS_SCHEMA["properties"]
        settings = cls()

        for key, value in settings_schema.items():
            if key in values:
                if value["type"] == "array":
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
        logger.info(f"CLI self = {self}")

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

    SETTINGS_SCHEMA: dict[str, Any] = {
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
            "fix": {"type": "string", "enum": FIX_TYPE},
            "outfile_base": {"type": "string"},
            "depth": {"type": "integer"},
            "scaled_percentages": {"type": "boolean"},
            "n_files": {"type": "integer"},
            "include_files": {"type": "array", "items": {"type": "string"}},
            "hide_blame_exclusions": {"type": "boolean"},
            "blame_skip": {"type": "boolean"},
            "show_renames": {"type": "boolean"},
            "gui_settings_full_path": {"type": "boolean"},
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
        with open(cls.SETTINGS_LOCATION_PATH, "w", encoding="utf-8") as f:
            f.write(d)
        return Path(location_settings["settings_location"])

    @classmethod
    def get_location(cls) -> Path:
        try:
            with open(cls.SETTINGS_LOCATION_PATH, "r", encoding="utf-8") as f:
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
        settings, _ = cls.load()
        if not utils.gui:
            settings.log()

    @classmethod
    def get_location_name(cls) -> str:
        return cls.get_location().name

    @classmethod
    def load(cls) -> tuple[Settings, str]:
        return cls.load_from(cls.get_location())

    @classmethod
    def load_from(cls, file: PathLike) -> tuple[Settings, str]:
        try:
            path = Path(file)
            if path.suffix != ".json":
                raise ValueError(f"File {str(path)} does not have a .json extension")
            with open(file, "r", encoding="utf-8") as f:
                s = f.read()
                settings_dict = json.loads(s)
                jsonschema.validate(settings_dict, cls.SETTINGS_SCHEMA)
                settings = Settings(**settings_dict)
                settings.validate_format()
                return settings, ""
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
