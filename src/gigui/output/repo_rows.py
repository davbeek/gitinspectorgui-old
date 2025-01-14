from gigui.repo_data import RepoData


class RepoRows(RepoData):
    deletions: bool
    scaled_percentages: bool

    @classmethod
    def header_authors(cls, html: bool = True) -> list[str]:
        header_prefix = ["ID", "Author"] + (["Empty", "Email"] if html else ["Email"])
        if cls.scaled_percentages:  # noqa: F821
            return (
                header_prefix
                + [
                    "Lines",
                    "Insertions",
                ]
                + (["Deletions"] if cls.deletions else [])  # noqa: F821
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
            return header_prefix + cls._header_stat()

    @classmethod
    def header_authors_files(cls, html: bool = True) -> list[str]:
        header_prefix = ["ID", "Author"] + (["Empty", "File"] if html else ["File"])
        return header_prefix + cls._header_stat()

    @classmethod
    def header_files_authors(cls, html: bool = True) -> list[str]:
        header_prefix = ["ID", "File"] + (["Empty", "Author"] if html else ["Author"])
        return header_prefix + cls._header_stat()

    @classmethod
    def header_files(cls) -> list[str]:
        return ["ID", "File"] + cls._header_stat()

    @classmethod
    def _header_stat(cls) -> list[str]:
        return (
            [
                "Lines",
                "Insertions",
            ]
            + (["Deletions"] if cls.deletions else [])  # noqa: F821
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
