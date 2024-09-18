from bs4 import BeautifulSoup, Tag

from gigui.common import log


class HTMLModifier:
    def __init__(self, html: str) -> None:
        self.soup = BeautifulSoup(html, "html.parser")

    def new_nav_tab(self, name: str) -> Tag:
        nav_li = self.soup.new_tag("li", attrs={"class": "nav-item"})
        nav_bt = self.soup.new_tag(
            "button",
            attrs={
                "class": "nav-link",
                "id": name + "-tab",
                "data-bs-toggle": "tab",
                "data-bs-target": "#" + name,
            },
        )
        nav_bt.string = name
        nav_li.append(nav_bt)
        return nav_li

    def new_tab_content(self, name: str) -> Tag:
        div = self.soup.new_tag(
            "div",
            attrs={
                "class": "tab-pane fade",
                "id": name,
            },
        )
        div.string = "__" + name + "__"
        return div

    def add_blame_tables_to_html(self, blames_htmls: list[tuple[str, str]]) -> str:
        nav_ul = self.soup.find("ul", {"id": "stats-tabs"})
        tab_div = self.soup.find("div", {"class": "tab-content"})
        if nav_ul and tab_div:
            for blame in blames_htmls:
                file_name, _ = blame
                nav_ul.append(self.new_nav_tab(file_name))
                tab_div.append(self.new_tab_content(file_name))

            html = str(self.soup)
            for blame in blames_htmls:
                file_name, content = blame
                html = html.replace("__" + file_name + "__", content)

            return html
        else:
            if nav_ul is None:
                log(
                    "Cannot find the component with id = 'stats-tabs'", text_color="red"
                )

            if tab_div is None:
                log(
                    "Cannot find the component with class = 'tab-content'",
                    text_color="red",
                )

        return str(self.soup)
