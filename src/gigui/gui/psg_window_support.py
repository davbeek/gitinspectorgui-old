import PySimpleGUI as sg

from gigui.constants import ENABLED_COLOR, OPTION_TITLE_WIDTH
from gigui.tiphelp import Tip

# Do NOT use None as default value for size, because that will lead to an exception:
SIZE_NONE = (None, None)

BUTTON_PADDING = (3, 2)

tip = Tip()


def button(text: str, key: str, pad=BUTTON_PADDING) -> sg.Button:
    return sg.B(
        text,
        k=key,
        pad=pad,
        button_color=ENABLED_COLOR,
    )


def name_basic(text: str, tooltip, size=SIZE_NONE, pad=None) -> sg.Text:
    return sg.Text(
        text,
        tooltip=tooltip,
        size=size,
        pad=pad,
        text_color="black",
        background_color="white",
    )


def name_header(text: str, tooltip) -> sg.Text:
    return name_basic(
        text,
        tooltip,
        pad=(0, 4),
        size=OPTION_TITLE_WIDTH,
    )


def name_choice(text: str, tooltip) -> sg.Text:
    return name_basic(text, tooltip, pad=(0, 0))


def name_input(text: str, tooltip, pad=(0, 0)) -> sg.Text:
    return name_basic(text, tooltip, pad=pad)


def input_box(
    key: str,
    disabled: bool = False,
    size=SIZE_NONE,
) -> sg.Input:
    return sg.Input(
        k=key,
        pad=((3, 2), 2),
        expand_x=True,
        enable_events=True,
        disabled=disabled,
        tooltip=getattr(tip, key),
        text_color="black",
        background_color="white",
        disabled_readonly_background_color="grey92",
        size=size,
    )


def checkbox(
    text: str,
    key: str,
    disabled=False,
) -> sg.Checkbox:
    return sg.Checkbox(
        text,
        k=key,
        tooltip=getattr(tip, key),
        pad=((0, 6), 0),
        enable_events=True,
        disabled=disabled,
        text_color="black",
        background_color="white",
    )


def spinbox(key: str, spin_range: list[int], pad=None) -> sg.Spin:
    return sg.Spin(
        spin_range,
        initial_value=1,
        k=key,
        enable_events=True,
        pad=((3, 10), None) if pad is None else pad,
        size=2,
        readonly=True,
        background_color="white",
    )


def radio(
    text: str,
    group_id: int,
    key: str,
) -> sg.Radio:
    return sg.Radio(
        text,
        group_id,
        k=key,
        default=False,
        enable_events=True,
        pad=((0, 0), 2),
        tooltip=getattr(tip, key),
        text_color="black",
        background_color="white",
    )


def frame(title: str, layout: list, pad: tuple[int, int] = (0, 0)) -> sg.Frame:
    return sg.Frame(
        layout=layout,
        title=title,
        relief=sg.RELIEF_SUNKEN,
        expand_x=True,
        pad=pad,
        title_color="black",
        background_color="white",
    )


def column(layout: list, col_height, key=None) -> sg.Column:
    return sg.Column(
        layout,
        k=key,
        vertical_scroll_only=True,
        scrollable=True,
        expand_x=True,
        size=(None, col_height),
        background_color="white",
    )


def popup(title, message) -> None:
    sg.popup(title, message, keep_on_top=True, text_color="black")
