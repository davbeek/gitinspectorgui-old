import json
from argparse import Namespace
from dataclasses import asdict, dataclass, field, fields
from logging import getLogger
from pathlib import Path
from typing import Any

import jsonschema
import platformdirs
from git import PathLike

from gigui import shared
from gigui._logging import log, set_logging_level_from_verbosity
from gigui.constants import (
    AUTO,
    BLAME_EXCLUSION_CHOICES,
    BLAME_EXCLUSIONS_DEFAULT,
    DEFAULT_COPY_MOVE,
    DEFAULT_EXTENSIONS,
    DEFAULT_FILE_BASE,
    DEFAULT_N_FILES,
    FILE_FORMATS,
    FIX_TYPE,
    INIT_COL_PERCENT,
    NONE,
    PREFIX,
    SUBDIR_NESTING_DEPTH,
    VIEW_OPTIONS,
)
from gigui.keys import Keys, KeysArgs
from gigui.typedefs import FileStr
from gigui.utils import to_posix_fstr, to_system_fstr, to_system_fstrs

logger = getLogger(__name__)


@dataclass
class Args:
    col_percent: int = INIT_COL_PERCENT  # Not used in CLI
    profile: int = 0  # Not used in GUI
    input_fstrs: list[FileStr] = field(default_factory=list)
    outfile_base: str = DEFAULT_FILE_BASE
    fix: str = PREFIX
    depth: int = SUBDIR_NESTING_DEPTH
    view: str = AUTO
    file_formats: list[str] = field(default_factory=lambda: ["html"])
    scaled_percentages: bool = False
    blame_exclusions: str = BLAME_EXCLUSIONS_DEFAULT
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
    copy_move: int = DEFAULT_COPY_MOVE
    verbosity: int = 0
    dryrun: int = 0
    multithread: bool = True
    multicore: bool = False
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

    # When settings are read from a settings file, cleanup the input fields.
    def normalize(self) -> None:
        settings_schema: dict[str, Any] = SettingsFile.SETTINGS_SCHEMA["properties"]
        for key, value in settings_schema.items():
            if value["type"] == "array":
                input_list: list[str] = getattr(self, key)
                clean_list: list[str] = [
                    item.strip()
                    for item in input_list  # pylint: disable=not-an-iterable
                    if item.strip()
                ]

                if key in {
                    Keys.input_fstrs,
                    Keys.ex_files,
                    Keys.include_files,
                    Keys.subfolder,
                }:
                    clean_list = [to_posix_fstr(fstr) for fstr in clean_list]
                setattr(self, key, clean_list)  # type: ignore
            elif value["type"] == "string":
                setattr(
                    self,
                    key,
                    getattr(self, key).strip(),  # pylint: disable=no-member
                )


@dataclass
class Settings(Args):
    # Do not use a constant variable for default_settings, because it is a mutable
    # object. It can be used as a starting point of settings. Therefore for each new
    # settings, a new object should be created.

    gui_settings_full_path: bool = False

    def __post_init__(self):
        super().__post_init__()
        if not self.n_files >= 0:
            raise ValueError("n_files must be a non-negative integer")
        if not self.depth >= 0:
            raise ValueError("depth must be a non-negative integer")
        # Always silently change empty extensions to the default value. This is done
        # when initializing, but also when settings are loaded from a a settings file.
        # Fixing empty extensions to the default value is much easier than checking if
        # the user has set it to an empty list. A side effect of this is that an empty
        # value of the extensions field in the settings file has the exact same effect
        # as the extensions field set to the default value.
        if not self.extensions:
            self.extensions = DEFAULT_EXTENSIONS
        self.normalize()

    @classmethod
    def from_args(cls, args: Args, gui_settings_full_path: bool) -> "Settings":
        # Create a Settings object using the instance variables from Args and the given
        # gui_settings_full_path
        settings = cls(gui_settings_full_path=gui_settings_full_path, **args.__dict__)
        settings.normalize()
        return settings

    def create_settings_file(self, settings_path: Path):
        settings_dict = asdict(self)
        with open(settings_path, "w", encoding="utf-8") as f:
            d = json.dumps(settings_dict, indent=4, sort_keys=True)
            f.write(d)

    def save(self):
        self.normalize()
        settings_dict = asdict(self)
        jsonschema.validate(settings_dict, SettingsFile.SETTINGS_SCHEMA)
        try:
            settings_path = SettingsFile.get_location_path()
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
        settings_dict = asdict(self)
        jsonschema.validate(settings_dict, SettingsFile.SETTINGS_SCHEMA)
        settings_path = Path(pathlike)
        self.create_settings_file(settings_path)
        SettingsFile.set_location(settings_path)

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
            log(f"{key:22}: {value}")

    def as_system(self) -> "Settings":
        self.input_fstrs = to_system_fstrs(self.input_fstrs)
        self.ex_files = to_system_fstrs(self.ex_files)
        self.include_files = to_system_fstrs(self.include_files)
        self.subfolder = to_system_fstr(self.subfolder)
        return self

    def reset(self) -> None:
        default_settings = Settings()
        for key, value in asdict(default_settings).items():
            setattr(self, key, value)

    def load_safe_from(self, file: PathLike) -> None:
        settings = SettingsFile.load_safe_from(file)
        for key, value in asdict(settings).items():
            setattr(self, key, value)

    def from_values_dict(self, values: dict[str, str | int | bool]) -> None:
        settings_schema: dict[str, Any] = SettingsFile.SETTINGS_SCHEMA["properties"]
        settings = Settings()

        values[Keys.n_files] = (
            0 if not values[Keys.n_files] else int(values[Keys.n_files])
        )
        for key, value in settings_schema.items():
            # No normalization here, that is done at the end of this method.
            if key in values:
                if value["type"] == "array":
                    input_list = values[key].split(",")  # type: ignore
                    setattr(settings, key, input_list)  # type: ignore
                else:
                    setattr(settings, key, values[key])

        if values[Keys.prefix]:
            settings.fix = Keys.prefix
        elif values[Keys.postfix]:
            settings.fix = Keys.postfix
        elif values[Keys.nofix]:
            settings.fix = Keys.nofix

        if values[Keys.auto]:
            settings.view = Keys.auto
        elif values[Keys.dynamic_blame_history]:
            settings.view = Keys.dynamic_blame_history
        else:
            settings.view = NONE

        file_formats = []
        for fmt in FILE_FORMATS:
            if values[fmt]:
                file_formats.append(fmt)
        settings.file_formats = file_formats
        for key, value in asdict(settings).items():
            setattr(self, key, value)

        settings.normalize()

    @classmethod
    def create_from_settings_dict(
        cls, settings_dict: dict[str, str | int | bool | list[str]]
    ) -> "Settings":
        settings_schema = SettingsFile.SETTINGS_SCHEMA["properties"]
        settings = cls()
        for key in settings_schema:
            setattr(settings, key, settings_dict[key])
        return settings


@dataclass
class CLIArgs(Args):
    reset_file: bool = False
    load: str = ""
    reset: bool = False
    save: bool = False
    save_as: str = ""
    show: bool = False
    gui: bool = False
    run: bool = False

    def create_settings(self) -> Settings:
        logger.debug(f"CLI self = {self}")  # type: ignore

        settings = Settings()
        sets_dict = asdict(settings)
        args_dict = asdict(self)
        for fld in fields(Args):
            sets_dict[fld.name] = args_dict[fld.name]
        settings = Settings.create_from_settings_dict(sets_dict)
        logger.debug(f"GUISettings from CLIArgs: {settings}")  # type: ignore
        return settings

    def create_args(self) -> Args:
        args = Args()
        cli_args_dict = asdict(self)
        for fld in fields(Args):
            if fld.name in cli_args_dict:
                setattr(args, fld.name, cli_args_dict[fld.name])
        return args

    def update_with_namespace(self, namespace: Namespace):
        assert not (namespace.run and namespace.input_fstrs)
        if namespace.run and not namespace.input_fstrs:
            namespace.input_fstrs = namespace.run

        # Change namespace.run from a list of FileStr to a boolean because self.run is a
        # boolean.
        namespace.run = namespace.run is not None

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
        logger.debug(f"CLI args - Namespace: {args_vars - nmsp_vars}")  # type: ignore
        logger.debug(f"Namespace - CLI args:  {nmsp_vars - args_vars}")  # type: ignore


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
    DEFAULT_LOCATION_SETTINGS: dict[str, FileStr] = {
        "settings_location": INITIAL_SETTINGS_PATH.as_posix(),
    }

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "col_percent": {"type": "integer"},  # Not used in CLI
            "profile": {"type": "integer"},  # Not used in GUI
            "input_fstrs": {"type": "array", "items": {"type": "string"}},
            "view": {"type": "string", "enum": VIEW_OPTIONS},
            "file_formats": {
                "type": "array",
                "items": {"type": "string", "enum": FILE_FORMATS},
            },
            "extensions": {"type": "array", "items": {"type": "string"}},
            "fix": {"type": "string", "enum": FIX_TYPE},
            "outfile_base": {"type": "string"},
            "depth": {"type": "integer"},
            "scaled_percentages": {"type": "boolean"},
            "n_files": {"type": "integer"},
            "include_files": {"type": "array", "items": {"type": "string"}},
            "blame_exclusions": {"type": "string", "enum": BLAME_EXCLUSION_CHOICES},
            "blame_skip": {"type": "boolean"},
            "show_renames": {"type": "boolean"},
            "gui_settings_full_path": {"type": "boolean"},
            "subfolder": {"type": "string"},
            "deletions": {"type": "boolean"},
            "whitespace": {"type": "boolean"},
            "empty_lines": {"type": "boolean"},
            "comments": {"type": "boolean"},
            "copy_move": {"type": "integer"},
            "verbosity": {"type": "integer"},
            "dryrun": {"type": "integer"},
            "multithread": {"type": "boolean"},
            "multicore": {"type": "boolean"},
            "since": {"type": "string"},
            "until": {"type": "string"},
            "ex_authors": {"type": "array", "items": {"type": "string"}},
            "ex_emails": {"type": "array", "items": {"type": "string"}},
            "ex_files": {"type": "array", "items": {"type": "string"}},
            "ex_messages": {"type": "array", "items": {"type": "string"}},
            "ex_revisions": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
        "minProperties": 33,
    }

    # Create file that contains the location of the settings file and return this
    # settings file location.
    @classmethod
    def create_location_file_for(cls, location_settings: dict[str, FileStr]) -> Path:
        jsonschema.validate(location_settings, cls.SETTINGS_LOCATION_SCHEMA)
        d = json.dumps(location_settings, indent=4)
        with open(cls.SETTINGS_LOCATION_PATH, "w", encoding="utf-8") as f:
            f.write(d)
        return Path(location_settings["settings_location"])

    @classmethod
    def get_location_path(cls) -> Path:
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
            return cls.get_location_path()

    @classmethod
    def show(cls):
        path = cls.get_location_path()
        log(f"{path}:")
        settings, error = cls.load()
        if not shared.gui:
            if error:
                log(error)
            else:
                settings.log()

    @classmethod
    def get_location_name(cls) -> str:
        return cls.get_location_path().name

    @classmethod
    def load(cls) -> tuple[Settings, str]:
        return cls.load_from(cls.get_location_path())

    @classmethod
    def load_safe(cls) -> Settings:
        settings, error = cls.load()
        if error:
            cls.show_error()
            return cls.reset()
        return settings

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
                settings.normalize()
                return settings, ""
        except (
            ValueError,
            FileNotFoundError,
            json.decoder.JSONDecodeError,
            jsonschema.ValidationError,
        ) as e:
            return Settings(), str(e)

    @classmethod
    def load_safe_from(cls, file: PathLike) -> Settings:
        settings, error = cls.load_from(file)
        if error:
            cls.show_error()
            return cls.reset()
        return settings

    @classmethod
    def show_error(cls) -> None:
        logger.warning("Cannot load settings file, loading default settings.")
        if shared.gui:
            log("Save settings to avoid this message.")
        else:
            log("Save settings (--save) to avoid this message.")

    @classmethod
    def reset(cls) -> Settings:
        cls.create_location_file_for(cls.DEFAULT_LOCATION_SETTINGS)
        settings = cls.load_safe()
        return settings

    @classmethod
    def set_location(cls, location: PathLike):
        # Creating a new file or overwriting the existing file is both done using the
        # same "with open( ..., "w") as f" statement.
        absolute_location: FileStr = Path(location).resolve().as_posix()
        cls.create_location_file_for({"settings_location": absolute_location})
