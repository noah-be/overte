#!/usr/bin/env python3
"""Create content-addressed qualification evidence for an exact parent commit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / ".github/sync-test-reuse.json"
SHA_RE = re.compile(r"[0-9a-f]{40}")


class QualificationError(ValueError):
    """The requested qualification cannot be bound safely."""


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def git(*args: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    return result.stdout.strip()


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(document.get("qualified_inputs"), list):
        raise QualificationError("unsupported sync-test-reuse configuration")
    return document


def selected(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def tree_entries(commit: str, patterns: list[str], cwd: Path = ROOT) -> list[dict[str, str]]:
    if not SHA_RE.fullmatch(commit):
        raise QualificationError("commit must be a full lowercase SHA")
    raw = subprocess.run(
        ["git", "ls-tree", "-rz", "--full-tree", commit], cwd=cwd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    entries: list[dict[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        mode, object_type, sha = metadata.decode("ascii").split(" ")
        path = encoded_path.decode("utf-8", errors="strict")
        if object_type == "blob" and selected(path, patterns):
            entries.append({"path": path, "mode": mode, "type": object_type, "sha": sha})
    entries.sort(key=lambda item: item["path"])
    return entries


def entries_digest(entries: list[dict[str, str]]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(entries)).hexdigest()


def create_evidence(args: argparse.Namespace) -> dict:
    config = load_config(args.config)
    if args.repository != config["repository"] or args.repository_id != config["repository_id"]:
        raise QualificationError("repository identity does not match the trusted configuration")
    if args.parent_branch not in config["parents"]:
        raise QualificationError("branch is not a qualifying parent")
    if not SHA_RE.fullmatch(args.commit):
        raise QualificationError("parent commit must be a full lowercase SHA")
    if git("rev-parse", "HEAD") != args.commit:
        raise QualificationError("checked-out HEAD does not match the requested parent commit")
    branch_sha = git("rev-parse", f"refs/remotes/origin/{args.parent_branch}")
    if branch_sha != args.commit:
        raise QualificationError("remote parent ref does not match the requested commit")
    entries = tree_entries(args.commit, config["qualified_inputs"])
    found = {entry["path"] for entry in entries}
    missing = sorted(set(config["required_qualified_inputs"]) - found)
    if missing:
        raise QualificationError("required qualification inputs are missing: " + ", ".join(missing))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = now + timedelta(hours=int(config["evidence_max_age_hours"]))
    workflow = config["qualification_workflow"]
    workflow_entry = next(entry for entry in entries if entry["path"] == workflow)
    evidence = {
        "schema": 1,
        "repository": args.repository,
        "repository_id": args.repository_id,
        "parent_branch": args.parent_branch,
        "parent_commit": args.commit,
        "parent_tree": git("show", "-s", "--format=%T", args.commit),
        "qualified_inputs": entries,
        "qualified_inputs_digest": entries_digest(entries),
        "workflow": {
            "path": workflow,
            "blob_sha": workflow_entry["sha"],
            "ref": f"refs/heads/{args.parent_branch}",
            "run_id": args.run_id,
            "run_attempt": args.run_attempt,
            "event": "push",
            "trusted_app_id": config["trusted_actions_app_id"],
        },
        "results": {
            "conclusion": "success",
            "suites": ["project-quick", "device-control-plane-full"],
        },
        "qualified_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    evidence["evidence_digest"] = "sha256:" + hashlib.sha256(canonical_json(evidence)).hexdigest()
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--parent-branch", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        evidence = create_evidence(args)
    except (QualificationError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"qualification error: {error}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(evidence))
    print(evidence["evidence_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
