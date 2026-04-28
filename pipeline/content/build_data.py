"""Compatibility wrapper for the unified content pipeline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import content


def main():
    if "--no-cache" in sys.argv or "--fresh" in sys.argv:
        sys.argv = [sys.argv[0], "pull", "--all"]
    else:
        sys.argv = [sys.argv[0], "build"]
    content.main()


if __name__ == "__main__":
    main()
