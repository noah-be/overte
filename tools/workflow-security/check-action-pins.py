#!/usr/bin/env python3
"""Inventory every workflow action use and reject mutable external references."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = Path(".github/workflows")
ACTION_ROOT = Path(".github/actions")
USES_LINE = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(?P<value>.*?)\s*$")
USES_KEY = re.compile(r"(?:^|[^A-Za-z0-9_])[\"']?uses[\"']?\s*:")
EXPLICIT_USES_KEY = re.compile(
    r"^\s*(?:-\s*)?\?\s+(?:!!str\s+)?[\"']?uses[\"']?\s*(?:#.*)?$"
)
REMOTE_ACTION = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}$"
)
DIGEST_CONTAINER = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")


class PinError(ValueError):
    """A workflow or composite action contains an unsafe action reference."""


@dataclass(frozen=True)
class ActionUse:
    path: str
    line: int
    reference: str
    kind: str


def source_files(root: Path) -> tuple[Path, ...]:
    files = []
    for relative in (WORKFLOW_ROOT, ACTION_ROOT):
        directory = root / relative
        if not directory.is_dir():
            continue
        for suffix in ("*.yml", "*.yaml"):
            files.extend(directory.rglob(suffix))
    return tuple(sorted(set(files)))


def scalar(value: str, path: Path, line: int) -> str:
    value = value.strip()
    if not value:
        raise PinError(f"{path}:{line}: uses value is empty")
    if value[0] in ("'", '"'):
        quote = value[0]
        closing = value.find(quote, 1)
        trailing = value[closing + 1 :].strip() if closing >= 0 else ""
        if closing < 0 or (trailing and not trailing.startswith("#")):
            raise PinError(f"{path}:{line}: uses value is not a simple YAML scalar")
        return value[1:closing]
    value = value.split(" #", 1)[0].strip()
    if not value or any(character.isspace() for character in value):
        raise PinError(f"{path}:{line}: uses value is not a simple YAML scalar")
    return value


def classify(root: Path, reference: str, path: Path, line: int) -> str:
    if "${{" in reference:
        raise PinError(f"{path}:{line}: dynamic uses references are forbidden")
    if reference.startswith("./"):
        target = (root / reference).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as error:
            raise PinError(f"{path}:{line}: local action escapes the repository") from error
        if not target.is_dir() or not any(
            (target / manifest).is_file() for manifest in ("action.yml", "action.yaml")
        ):
            raise PinError(f"{path}:{line}: local action manifest does not exist")
        return "local"
    if DIGEST_CONTAINER.fullmatch(reference):
        return "container"
    if REMOTE_ACTION.fullmatch(reference):
        return "remote"
    raise PinError(
        f"{path}:{line}: external action must use a lowercase 40-character commit SHA"
    )


def inventory(root: Path) -> tuple[ActionUse, ...]:
    uses = []
    for path in source_files(root):
        relative = path.relative_to(root)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#") or "uses" not in line:
                continue
            if EXPLICIT_USES_KEY.fullmatch(line):
                raise PinError(f"{relative}:{number}: uses must be a block-style scalar")
            match = USES_LINE.fullmatch(line)
            if match is None:
                if USES_KEY.search(line):
                    raise PinError(f"{relative}:{number}: uses must be a block-style scalar")
                continue
            reference = scalar(match.group("value"), relative, number)
            uses.append(
                ActionUse(
                    path=relative.as_posix(),
                    line=number,
                    reference=reference,
                    kind=classify(root, reference, relative, number),
                )
            )
    if not uses:
        raise PinError("no workflow or composite-action uses entries found")
    return tuple(uses)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--format", choices=("summary", "json"), default="summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        uses = inventory(args.root.resolve())
    except (OSError, UnicodeError, PinError) as error:
        print(f"action pin audit failed: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps([asdict(item) for item in uses], indent=2, sort_keys=True))
    else:
        counts = {kind: sum(item.kind == kind for item in uses) for kind in ("remote", "local", "container")}
        print(
            "action pin audit passed: "
            f"{len(uses)} uses ({counts['remote']} remote, {counts['local']} local, "
            f"{counts['container']} container) across {len(source_files(args.root.resolve()))} files"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
