import sys
from pathlib import Path

# Add the parent directory to the Python module search path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.github import GITool

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1].lower() not in {"gui", "cli"}:
        print("Usage: python create_app.py [gui|cli]")
        sys.exit(1)

    bundle_type = sys.argv[1].lower()
    gi_tool = GITool()
    gi_tool.create_app(bundle_type)
