type Author = str
type Email = str
type FileStr = str
type FilePattern = str
type Row = list[str | int | float]

type OID = str  # Object ID = long commit SHA, 40 chars
type SHA = str  # short commit SHA, often 7 chars
type Rev = OID | SHA  # long or short commit SHA

type HtmlStr = str


# BlameStr is the output of the git blame command
type BlameStr = str

type RowsBools = tuple[list[Row], list[bool]]
