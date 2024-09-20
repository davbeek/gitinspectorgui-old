import base64
import sys
from pathlib import Path

import PySimpleGUI as sg


def resource_path(relative_path=None):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # noinspection PyProtectedMember
        base_path = sys._MEIPASS  # type: ignore  # pylint: disable=E1101,W0212
    except AttributeError:
        base_path = Path(__file__).parent

    if relative_path is None:
        return base_path

    return Path(base_path) / relative_path


icon = resource_path("images/icon.png")
with open(icon, "rb") as file:
    icon = base64.b64encode(file.read())


def invalid_input(element: sg.Element):
    element.update(background_color="#FD9292")


def paths_valid(paths: list[Path], sg_input: sg.Input, colored: bool = True):
    if all(path_exists_case_sensitive(path) for path in paths):
        sg_input.update(background_color="#FFFFFF")
        return True
    else:
        if colored:
            invalid_input(sg_input)
        return False


def path_exists_case_sensitive(p: Path) -> bool:
    return p.exists() and str(p) in map(str, p.parent.iterdir())
