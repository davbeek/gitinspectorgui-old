from git import Commit as GitCommit

type Author = str
type Email = str
type FileStr = str
type Row = list[str | int | float]
type SHAlong = str  # long commit SHA
type SHAshort = str  # short commit SHA
type Rev = SHAlong | SHAshort  # long or short commit SHA

type HTML = str

type BlameLine = str  # single line of code
type BlameLines = list[BlameLine]
# GitBlames is a list of two-element lists
# Each two-element list contains a GitCommit followed by a list of Blame lines
type GitBlames = list[list[GitCommit | BlameLines]]
