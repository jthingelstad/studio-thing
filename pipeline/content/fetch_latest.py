"""Compatibility wrapper for fetching the latest Buttondown issue."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import content


def main():
    args = ["pull", "--latest"]
    if "--skip-existing" in sys.argv:
        args.append("--skip-existing")
    sys.argv = [sys.argv[0], *args]
    content.main()


if __name__ == "__main__":
    main()
