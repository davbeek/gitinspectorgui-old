import dearpygui.dearpygui as dpg

def input_text(tag: str, callback, width: int = -1, default_value: str = '') -> (int | str):
    # with dpg.theme() as theme:
    #     with dpg.theme_component(dpg.mvInputText):
    #         dpg.add_theme_color(dpg.mvThemeCol_FrameBg, VALID_INPUT_RGBA_COLOR, tag=tag+"theme")

    it = dpg.add_input_text(tag=tag, default_value= default_value, width=width, callback=callback)
    # dpg.bind_item_theme(it, theme)
    return it


def checkbox(label: str, key: str, callback) -> (int | str):
    return dpg.add_checkbox(label=label, tag=key, callback=callback)

def multiline(key: str) -> None:
    with dpg.child_window(height=170, width=-1, tag=key):
        pass  # No content added, starts as an empty child window

def button(label: str, key: str, callback) -> (int | str):
    return dpg.add_button(label=label, tag=key, callback=callback)


def text(default_value):
    dpg.add_text(default_value)

def separator(label: str):
    dpg.add_separator(label=label)

def spinner(label: str, width: int, min_value: int, max_value: int, step: int, key: str, callback):
    return dpg.add_input_int(
        label=label,
        width=width,
        min_value=min_value,
        max_value=max_value,
        step=step,
        tag=key,
        callback=callback,
    )

def popup(title: str, message: str):
    with dpg.window(label=title, modal=True, tag="popup_window"):
        dpg.add_text(message)
        dpg.add_button(label="Ok", callback=lambda: dpg.delete_item("popup_window"))
