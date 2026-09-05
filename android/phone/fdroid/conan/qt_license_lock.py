#!/usr/bin/env python3
"""Generate and verify the closed license-file inventory for the locked Qt tree."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from qt_source_store import EXPECTED_COMPONENTS, sha256_file


class LicenseLockError(RuntimeError):
    pass


LOCK_COLUMNS = ("path", "sha256", "component", "reasons")
LICENSE_PREFIXES = ("license", "licence", "copying", "copyright")
ATTRIBUTION_NAME = "qt_attribution.json"
_SINGLE_LICENSE = re.compile(
    r'"LicenseFile"\s*:\s*"((?:\\.|[^"\\])*)"', re.DOTALL
)
_MULTIPLE_LICENSES = re.compile(
    r'"LicenseFiles"\s*:\s*\[([^\]]*)\]', re.DOTALL
)
_JSON_STRING = re.compile(r'"((?:\\.|[^"\\])*)"', re.DOTALL)


@dataclass(frozen=True)
class LicenseEntry:
    path: str
    sha256: str
    component: str
    reasons: str


def _decode_json_string(value: str, source: Path) -> str:
    try:
        decoded = json.loads(f'"{value}"')
    except ValueError as error:
        raise LicenseLockError(f"invalid license path string in {source}: {error}") from error
    if not isinstance(decoded, str) or not decoded:
        raise LicenseLockError(f"empty license path in {source}")
    return decoded


def attribution_references(path: Path) -> list[str]:
    """Read only LicenseFile(s) fields; old Qt files are not always strict JSON."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise LicenseLockError(f"unreadable attribution file {path}: {error}") from error

    singles = [
        _decode_json_string(match.group(1), path)
        for match in _SINGLE_LICENSE.finditer(text)
    ]
    multiples = []
    for array in _MULTIPLE_LICENSES.finditer(text):
        multiples.extend(
            _decode_json_string(match.group(1), path)
            for match in _JSON_STRING.finditer(array.group(1))
        )

    declared_single = len(re.findall(r'"LicenseFile"\s*:', text))
    declared_multiple = len(re.findall(r'"LicenseFiles"\s*:', text))
    if declared_single != len(singles) or declared_multiple != len(
        list(_MULTIPLE_LICENSES.finditer(text))
    ):
        raise LicenseLockError(f"unparsed LicenseFile(s) field in {path}")
    return singles + multiples


def _component_for(relative: PurePosixPath) -> str:
    candidates = []
    for identifier, destination in EXPECTED_COMPONENTS.items():
        destination_path = PurePosixPath(destination)
        if relative == destination_path or destination_path in relative.parents:
            candidates.append((len(destination_path.parts), identifier))
    if not candidates:
        raise LicenseLockError(f"file outside selected Qt components: {relative}")
    return max(candidates)[1]


def _safe_relative(root: Path, candidate: Path, source: Path) -> PurePosixPath:
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise LicenseLockError(f"missing referenced license from {source}: {candidate}") from error
    if not resolved.is_relative_to(root):
        raise LicenseLockError(f"license reference escapes Qt root from {source}: {candidate}")
    if candidate.is_symlink() or not resolved.is_file():
        raise LicenseLockError(f"license reference is not a regular file: {candidate}")
    return PurePosixPath(resolved.relative_to(root).as_posix())


def discover(source_tree: Path) -> list[LicenseEntry]:
    root = (source_tree / "qt5").resolve(strict=True)
    if not root.is_dir():
        raise LicenseLockError("source tree must contain the composed qt5 directory")

    reasons: dict[PurePosixPath, set[str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        name = path.name.casefold()
        if name.startswith(LICENSE_PREFIXES):
            reasons.setdefault(relative, set()).add("license-basename")
        if name == ATTRIBUTION_NAME:
            reasons.setdefault(relative, set()).add("qt-attribution")
            for reference in attribution_references(path):
                reference_path = PurePosixPath(reference)
                if reference_path.is_absolute():
                    raise LicenseLockError(
                        f"absolute license reference from {path}: {reference}"
                    )
                target = path.parent.joinpath(*reference_path.parts)
                target_relative = _safe_relative(root, target, path)
                reasons.setdefault(target_relative, set()).add("attribution-reference")

    entries = []
    for relative in sorted(reasons, key=str):
        path = root.joinpath(*relative.parts)
        entries.append(
            LicenseEntry(
                path=str(relative),
                sha256=sha256_file(path),
                component=_component_for(PurePosixPath("qt5") / relative),
                reasons=",".join(sorted(reasons[relative])),
            )
        )
    components = {entry.component for entry in entries}
    missing = sorted(set(EXPECTED_COMPONENTS) - components)
    if missing:
        raise LicenseLockError(f"selected Qt components lack license evidence: {missing}")
    return entries


def serialize(entries: list[LicenseEntry]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(LOCK_COLUMNS)
    for entry in entries:
        writer.writerow((entry.path, entry.sha256, entry.component, entry.reasons))
    return output.getvalue()


def load_lock(path: Path) -> list[LicenseEntry]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            if tuple(reader.fieldnames or ()) != LOCK_COLUMNS:
                raise LicenseLockError("invalid Qt license lock columns")
            entries = [LicenseEntry(**row) for row in reader]
    except OSError as error:
        raise LicenseLockError(f"unreadable Qt license lock: {error}") from error
    paths = [entry.path for entry in entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise LicenseLockError("Qt license lock paths must be sorted and unique")
    for entry in entries:
        relative = PurePosixPath(entry.path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise LicenseLockError(f"unsafe Qt license lock path: {entry.path}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry.sha256):
            raise LicenseLockError(f"invalid Qt license SHA-256: {entry.path}")
        if entry.component not in EXPECTED_COMPONENTS:
            raise LicenseLockError(f"unknown Qt component in license lock: {entry.component}")
        allowed_reasons = {
            "attribution-reference",
            "license-basename",
            "qt-attribution",
        }
        values = entry.reasons.split(",")
        if values != sorted(set(values)) or not set(values) <= allowed_reasons:
            raise LicenseLockError(f"invalid reason set: {entry.path}")
    return entries


def verify(source_tree: Path, lock_path: Path) -> list[LicenseEntry]:
    expected = discover(source_tree)
    actual = load_lock(lock_path)
    if actual != expected:
        expected_by_path = {entry.path: entry for entry in expected}
        actual_by_path = {entry.path: entry for entry in actual}
        missing = sorted(expected_by_path.keys() - actual_by_path.keys())
        extra = sorted(actual_by_path.keys() - expected_by_path.keys())
        changed = sorted(
            path
            for path in expected_by_path.keys() & actual_by_path.keys()
            if expected_by_path[path] != actual_by_path[path]
        )
        raise LicenseLockError(
            f"Qt license lock mismatch: missing={missing} extra={extra} changed={changed}"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--source-tree", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "generate":
            entries = discover(args.source_tree)
            args.lock.write_text(serialize(entries), encoding="utf-8")
        else:
            entries = verify(args.source_tree, args.lock)
    except (LicenseLockError, OSError) as error:
        parser.error(str(error))
    print(f"QT_LICENSE_LOCK=PASS files={len(entries)} components={len(EXPECTED_COMPONENTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
