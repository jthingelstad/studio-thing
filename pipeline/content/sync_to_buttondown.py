"""Compatibility wrapper for syncing archive edits back to Buttondown."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import content


def main():
    args = ["push"]
    passthrough = {"--issue", "--dry-run", "--yes", "--force"}
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in passthrough:
            args.append(arg)
            if arg == "--issue" and i + 1 < len(sys.argv):
                args.append(sys.argv[i + 1])
                i += 1
        elif arg == "--refresh":
            pass
        i += 1
    if "--dry-run" not in args and "--yes" not in args:
        args.append("--dry-run")
    sys.argv = [sys.argv[0], *args]
    content.main()


if __name__ == "__main__":
    main()
