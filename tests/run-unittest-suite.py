#!/usr/bin/env python3
"""Run one Python unittest directory, rejecting an empty test selection."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--pattern", default="test_*.py")
    args = parser.parse_args()
    # Match `python -m unittest`: tests may import shared helpers from the
    # repository working directory, not just the selected discovery directory.
    sys.path.insert(0, str(Path.cwd()))
    suite = unittest.defaultTestLoader.discover(str(args.directory), pattern=args.pattern)
    if not suite.countTestCases():
        print("ERROR: unittest selection contains no test cases", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
