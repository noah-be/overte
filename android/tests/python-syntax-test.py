#!/usr/bin/env python3
"""Parse tracked Android Python sources without creating bytecode or caches."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import tokenize


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def tracked_sources() -> list[Path]:
    output = subprocess.check_output(
        ["git", "-C", str(REPOSITORY_ROOT), "ls-files", "-z", "--",
         "android/*.py", "android/**/*.py"]
    )
    return [REPOSITORY_ROOT / os.fsdecode(name)
            for name in output.split(b"\0") if name]


def validate(path: Path) -> list[str]:
    errors = []
    if not path.is_file():
        return ["input is not a regular file"]
    text = ""
    try:
        with tokenize.open(path) as source:
            text = source.read()
        ast.parse(text, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as error:
        errors.append(str(error))
    if os.access(path, os.X_OK) and not text.startswith("#!/usr/bin/env python3\n"):
        errors.append("executable Python entry point lacks the standard python3 shebang")
    return errors


def main(arguments: list[str]) -> int:
    sources = [Path(argument).resolve() for argument in arguments] if arguments else tracked_sources()
    if not sources:
        print("FAIL: no Android Python sources were selected", file=sys.stderr)
        return 1
    failures = 0
    for source in sources:
        for error in validate(source):
            print(f"FAIL: {source}: {error}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"Python syntax contract failed with {failures} error(s)", file=sys.stderr)
        return 1
    print(f"Android Python syntax contract passed for {len(sources)} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
