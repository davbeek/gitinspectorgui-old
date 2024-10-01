from dataclasses import dataclass


@dataclass
class CommentMarker:
    start: str | None
    end: str | None
    line: str | None


COMMENT_MARKER: dict[str, CommentMarker] = {
    "ada": CommentMarker(None, None, "--"),
    "adb": CommentMarker(None, None, "--"),
    "ads": CommentMarker(None, None, "--"),
    "c": CommentMarker("/*", "*/", "//"),
    "cc": CommentMarker("/*", "*/", "//"),
    "cif": CommentMarker("/*", "*/", "//"),
    "cpp": CommentMarker("/*", "*/", "//"),
    "cs": CommentMarker("/*", "*/", "//"),
    "glsl": CommentMarker("/*", "*/", "//"),
    "go": CommentMarker("/*", "*/", "//"),
    "h": CommentMarker("/*", "*/", "//"),
    "hh": CommentMarker("/*", "*/", "//"),
    "hpp": CommentMarker("/*", "*/", "//"),
    "hs": CommentMarker("{-", "-}", "--"),
    "html": CommentMarker("<!--", "-->", None),
    "ily": CommentMarker("%{", "%}", "%"),
    "java": CommentMarker("/*", "*/", "//"),
    "js": CommentMarker("/*", "*/", "//"),
    "jspx": CommentMarker("<!--", "-->", None),
    "ly": CommentMarker("%{", "%}", "%"),
    "ml": CommentMarker("(*", "*)", None),
    "mli": CommentMarker("(*", "*)", None),
    "php": CommentMarker("/*", "*/", "//"),
    "pl": CommentMarker(None, None, "#"),
    "po": CommentMarker(None, None, "#"),
    "pot": CommentMarker(None, None, "#"),
    "py": CommentMarker('"""', '"""', "#"),
    "rb": CommentMarker("=begin", "=end", "#"),
    "rlib": CommentMarker(None, None, "//"),
    "robot": CommentMarker(None, None, "#"),
    "rs": CommentMarker(None, None, "//"),
    "scala": CommentMarker("/*", "*/", "//"),
    "sql": CommentMarker("/*", "*/", "--"),
    "tex": CommentMarker("\\begin{comment}", "\\end{comment}", "%"),
    "tooldef": CommentMarker("/*", "*/", "//"),
    "xhtml": CommentMarker("<!--", "-->", None),
    "xml": CommentMarker("<!--", "-->", None),
}

COMMENT_MARKER_MUST_BE_AT_BEGINNING = {"tex"}


def get_start_marker(extension: str) -> str | None:
    if extension in COMMENT_MARKER:
        return COMMENT_MARKER[extension].start
    else:
        return None


def get_end_marker(extension: str) -> str | None:
    if extension in COMMENT_MARKER:
        return COMMENT_MARKER[extension].end
    else:
        return None


def get_line_marker(extension: str) -> str | None:
    if extension in COMMENT_MARKER:
        return COMMENT_MARKER[extension].line
    else:
        return None


def line_startswith_line_marker(extension: str, line: str) -> bool:
    line_marker = get_line_marker(extension)
    if line_marker is None:
        return False
    return line.startswith(line_marker)


def line_startswith_start_marker(extension: str, line: str) -> bool:
    start_marker = get_start_marker(extension)
    if start_marker is None:
        return False
    return line.startswith(start_marker)


def line_has_middle_start_marker(extension: str, line: str) -> bool:
    start_marker = get_start_marker(extension)
    if start_marker is None:
        return False
    return start_marker in line


def line_endswith_end_marker(extension: str, line: str) -> bool:
    end_marker = get_end_marker(extension)
    if end_marker is None:
        return False
    return line.endswith(end_marker)


def marker_must_be_at_beginning(extension: str) -> bool:
    return extension in COMMENT_MARKER_MUST_BE_AT_BEGINNING


def get_is_comment_lines(
    extension: str | None, lines: list[str], in_multiline_comment: bool
) -> tuple[list[bool], bool]:
    if extension is None:
        return [False] * len(lines), in_multiline_comment
    is_comment_lines = []
    for line in lines:
        line = line.strip()
        if not in_multiline_comment:
            if line_startswith_line_marker(extension, line):
                is_comment_lines.append(True)
            elif line_startswith_start_marker(extension, line):
                if not line_endswith_end_marker(extension, line):
                    in_multiline_comment = True
                is_comment_lines.append(True)
            elif not marker_must_be_at_beginning(
                extension
            ) and line_has_middle_start_marker(extension, line):
                in_multiline_comment = True
                is_comment_lines.append(False)
            else:
                is_comment_lines.append(False)
        else:  # in_multiline_comment
            is_comment_lines.append(True)
            if line_endswith_end_marker(extension, line):
                in_multiline_comment = False
    return is_comment_lines, in_multiline_comment
