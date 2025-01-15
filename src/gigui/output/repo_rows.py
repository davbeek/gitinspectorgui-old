from gigui.repo_data import RepoData


class RepoRows(RepoData):
    def header_authors(self, html: bool = True) -> list[str]:
        header_prefix = ["ID", "Author"] + (["Empty", "Email"] if html else ["Email"])
        if self.args.scaled_percentages:  # noqa: F821
            return (
                header_prefix
                + [
                    "Lines",
                    "Insertions",
                ]
                + (["Deletions"] if self.args.deletions else [])  # noqa: F821
                + [
                    "% Lines",
                    "% Insertions",
                    "% Scaled Lines",
                    "% Scaled Insertions",
                ]
                + [
                    "Stability",
                    "Commits",
                    "Age Y:M:D",
                ]  # noqa: F821
            )
        else:
            return header_prefix + self._header_stat()

    def header_authors_files(self, html: bool = True) -> list[str]:
        header_prefix = ["ID", "Author"] + (["Empty", "File"] if html else ["File"])
        return header_prefix + self._header_stat()

    def header_files_authors(self, html: bool = True) -> list[str]:
        header_prefix = ["ID", "File"] + (["Empty", "Author"] if html else ["Author"])
        return header_prefix + self._header_stat()

    def header_files(self) -> list[str]:
        return ["ID", "File"] + self._header_stat()

    def _header_stat(self) -> list[str]:
        return (
            [
                "Lines",
                "Insertions",
            ]
            + (["Deletions"] if self.args.deletions else [])  # noqa: F821
            + [
                "% Lines",
                "% Insertions",
            ]
            + [
                "Stability",
                "Commits",
                "Age Y:M:D",
            ]
        )  # noqa: F821
