#!/usr/bin/env python3
"""Hermetic shallow-history tests for documentation change discovery."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tests/check-documentation.py"


def git(root: Path, *arguments: str, capture: bool = False) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=capture,
        text=True,
    )
    return completed.stdout.strip() if capture else ""


spec = importlib.util.spec_from_file_location("check_documentation", CHECKER)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    source = temporary / "source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "Documentation Test")
    git(source, "config", "user.email", "documentation@example.invalid")
    (source / "README.md").write_text("initial\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-q", "-m", "base")
    base = git(source, "rev-parse", "HEAD", capture=True)

    (source / "code.txt").write_text("intermediate\n", encoding="utf-8")
    git(source, "add", "code.txt")
    git(source, "commit", "-q", "-m", "intermediate")
    (source / "README.md").write_text("updated\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-q", "-m", "documentation")

    checkout = temporary / "checkout"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", source.as_uri(), str(checkout)],
        check=True,
    )
    git(checkout, "fetch", "-q", "--no-tags", "--depth=1", "origin", base)
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"], cwd=checkout, check=False
    )
    assert merge_base.returncode != 0, "fixture must reproduce a disconnected shallow history"
    changed = checker.changed_markdown(base, checkout)
    assert changed == [checkout / "README.md"], changed

    try:
        checker.changed_markdown("0" * 40, checkout)
    except RuntimeError as error:
        assert str(error) == "the documentation comparison tree is unavailable"
    else:
        raise AssertionError("missing comparison tree was accepted")

print("documentation shallow-history contract valid")
