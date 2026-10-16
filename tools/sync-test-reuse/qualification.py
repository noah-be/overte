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
import sys

TRUSTED_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TRUSTED_ROOT / "tools/test-evidence"))
import execution
import inputs


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
        if object_type in {"blob", "commit"} and selected(path, patterns):
            entries.append({"path": path, "mode": mode, "type": object_type, "sha": sha})
    entries.sort(key=lambda item: item["path"])
    return entries


def entries_digest(entries: list[dict[str, str]]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(entries)).hexdigest()


def create_evidence(args: argparse.Namespace) -> dict:
    config = load_config(args.config)
    candidate = Path(getattr(args, "candidate", None) or Path.cwd()).resolve()
    receipt_path = getattr(args, "execution_receipt", None)
    if receipt_path is None:
        raise QualificationError("qualification requires a trusted execution receipt")
    registry = inputs.load_registry(TRUSTED_ROOT / ".github/test-suites.json")
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"), object_pairs_hook=inputs._unique_object)
    if args.repository != config["repository"] or args.repository_id != config["repository_id"]:
        raise QualificationError("repository identity does not match the trusted configuration")
    if args.parent_branch not in config["parents"]:
        raise QualificationError("branch is not a qualifying parent")
    if not SHA_RE.fullmatch(args.commit):
        raise QualificationError("parent commit must be a full lowercase SHA")
    if git("rev-parse", "HEAD", cwd=candidate) != args.commit:
        raise QualificationError("checked-out HEAD does not match the requested parent commit")
    branch_sha = git("rev-parse", f"refs/remotes/origin/{args.parent_branch}", cwd=candidate)
    if branch_sha != args.commit:
        raise QualificationError("remote parent ref does not match the requested commit")
    entries = tree_entries(args.commit, config["qualified_inputs"], cwd=candidate)
    found = {entry["path"] for entry in entries}
    missing = sorted(set(config["required_qualified_inputs"]) - found)
    if missing:
        raise QualificationError("required qualification inputs are missing: " + ", ".join(missing))
    full_tree = inputs.full_tree(candidate, args.commit)
    source_tree = git("show", "-s", "--format=%T", args.commit, cwd=candidate)
    if execution.checkout_identity(candidate) != (args.commit, source_tree):
        raise QualificationError("qualification checkout changed or is dirty")
    if receipt.get("candidate_commit") != args.commit or receipt.get("candidate_tree") != source_tree:
        raise QualificationError("execution receipt is bound to another candidate")
    try:
        observed = execution.validate_receipt(receipt, registry, full_tree, require_all=True)
    except (execution.ExecutionError, inputs.InputError) as error:
        raise QualificationError("execution receipt does not establish actual shared qualification") from error
    if type(args.run_id) is not int or args.run_id <= 0 or type(args.run_attempt) is not int or args.run_attempt <= 0:
        raise QualificationError("workflow run and attempt must be positive integers")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = now + timedelta(hours=int(config["evidence_max_age_hours"]))
    workflow = config["qualification_workflow"]
    workflow_entry = next(entry for entry in entries if entry["path"] == workflow)
    evidence = {
        "schema": 2,
        "reusable": receipt["reusable"],
        "environment": receipt["environment"],
        "execution_receipt_digest": receipt["receipt_digest"],
        "repository": args.repository,
        "repository_id": args.repository_id,
        "parent_branch": args.parent_branch,
        "parent_commit": args.commit,
        "parent_tree": source_tree,
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
            "suites": observed,
        },
        "qualified_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    evidence["evidence_digest"] = "sha256:" + hashlib.sha256(canonical_json(evidence)).hexdigest()
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--candidate", type=Path, default=Path.cwd())
    parser.add_argument("--execution-receipt", type=Path, required=True)
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
    except (QualificationError, execution.ExecutionError, inputs.InputError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"qualification error: {error}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(evidence))
    print(evidence["evidence_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
