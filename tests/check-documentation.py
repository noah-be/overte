#!/usr/bin/env python3
"""Fast, dependency-free checks for changed Markdown documentation."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def changed_markdown(base: str) -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / name for name in result.stdout.splitlines() if name.lower().endswith(".md")]


def link_target(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        return raw[1 : raw.index(">")]
    return raw.split(maxsplit=1)[0]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^(<<<<<<<|=======|>>>>>>>)", text):
        errors.append("contains an unresolved merge marker")
    for match in LINK.finditer(text):
        target = link_target(match.group(1))
        if not target or target.startswith(("#", "/")) or SCHEME.match(target):
            continue
        relative = unquote(urlsplit(target).path)
        if not relative or any(token in relative for token in ("${", "{{", "*")):
            continue
        resolved = (path.parent / relative).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            errors.append(f"link escapes the repository: {target}")
            continue
        if not resolved.exists():
            errors.append(f"local link target does not exist: {target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    failures = []
    files = changed_markdown(args.base)
    for path in files:
        for error in validate(path):
            failures.append(f"{path.relative_to(ROOT)}: {error}")
    if failures:
        print("Documentation checks failed:\n- " + "\n- ".join(failures))
        return 1
    print(f"Documentation checks passed for {len(files)} changed Markdown file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
