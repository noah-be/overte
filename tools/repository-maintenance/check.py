#!/usr/bin/env python3
"""Read-only offline maintenance snapshot; never fetch, prune, merge or delete."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "noah-be/overte"
SHA = re.compile(r"[0-9a-f]{40}")
KINDS = {"feature", "fix", "docs", "refactor", "test", "tests", "ci", "sync", "task", "promote", "reconcile"}


def git(root: Path, *args: str, allow_failure: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
                            cwd=root, capture_output=True, text=True, timeout=30,
                            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
    if result.returncode and not allow_failure:
        # Do not expose local Git configuration, URLs, or credential helper output.
        raise ValueError(f"local Git inspection failed: {args[0]}")
    return result


def instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("evidence timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("evidence timestamp must include a timezone")
    return result


def age_hours(value: str, now: datetime) -> float:
    age = (now - instant(value)).total_seconds() / 3600
    if age < 0:
        raise ValueError("evidence timestamp is in the future")
    return age


def read_document(path: Path | None) -> dict | None:
    if path is None:
        return None
    if path.stat().st_size > 5_000_000:
        raise ValueError("provided snapshot exceeds 5 MB")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate snapshot key")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError("non-finite snapshot number")
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant)
    if not isinstance(document, dict) or document.get("repository") != REPOSITORY:
        raise ValueError("provided snapshot must identify noah-be/overte")
    return document


def branch_snapshot(root: Path, branches: dict, prefix: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"refs/(?:remotes|heads)/[A-Za-z0-9_/-]+", prefix) or ".." in prefix:
        raise ValueError("invalid local reference prefix")
    heads = {}
    for name in branches:
        result = git(root, "rev-parse", "--verify", f"{prefix}/{name}^{{commit}}", allow_failure=True)
        heads[name] = result.stdout.strip() if result.returncode == 0 else None
        if heads[name] is not None and not SHA.fullmatch(heads[name]):
            raise ValueError("invalid local branch object")
    edges = []
    for child, item in branches.items():
        parent = item["parent"]
        if parent is None:
            continue
        row = {"parent": parent, "child": child, "parent_sha": heads[parent], "child_sha": heads[child]}
        if heads[parent] is None or heads[child] is None:
            row.update(status="UNKNOWN", missing_parent_commits=None)
        else:
            missing = int(git(root, "rev-list", "--count", heads[child] + ".." + heads[parent]).stdout)
            row.update(status="IN_SYNC" if missing == 0 else "DRIFT", missing_parent_commits=missing)
        edges.append(row)
    return {"source": "local_git_refs", "prefix": prefix, "remote_freshness": "UNKNOWN", "edges": edges}, heads


def parse_worktrees(raw: str) -> list[dict]:
    rows = []
    for block in raw.strip("\0").split("\0\0"):
        if not block:
            continue
        values = {}
        for field in block.split("\0"):
            key, _, value = field.partition(" ")
            values[key] = value
        if "worktree" not in values:
            raise ValueError("invalid local worktree inventory")
        rows.append(values)
    return rows


def worktree_snapshot(root: Path, branches: dict, heads: dict, holds: dict | None = None) -> dict:
    scopes = {item["scope"]: name for name, item in branches.items()}
    rows = []
    for entry in parse_worktrees(git(root, "worktree", "list", "--porcelain", "-z").stdout):
        path = Path(entry["worktree"])
        branch = entry.get("branch", "").removeprefix("refs/heads/") or None
        row = {"path": str(path), "branch": branch, "head": entry.get("HEAD"),
               "status": "RETAIN", "reasons": [], "dirty": None, "target": None,
               "fully_integrated": None, "remote_holds": "NOT_CHECKED"}
        reasons = row["reasons"]
        if path.resolve() == root.resolve():
            reasons.append("current_worktree")
        if branch in branches:
            reasons.append("permanent_branch")
        if branch in (holds or {}):
            reasons.append("explicit_policy_hold")
        if "locked" in entry:
            reasons.append("locked_for_retention")
        if "prunable" in entry:
            reasons.append("stale_registration_review")
        if not path.is_dir():
            reasons.append("missing_path_review")
        elif path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            reasons.append("symlinked_worktree_review")
        elif "locked" not in entry:
            state = git(path, "status", "--porcelain", "-z", "--untracked-files=normal",
                        "--ignore-submodules=none", allow_failure=True)
            if state.returncode:
                reasons.append("unknown_worktree_state")
            else:
                row["dirty"] = bool(state.stdout)
                if row["dirty"]:
                    reasons.append("uncommitted_work")
        parts = branch.split("/", 2) if branch else []
        target = scopes.get(parts[1]) if len(parts) == 3 and parts[0] in KINDS else None
        row["target"] = target
        if branch not in branches:
            if target is None:
                reasons.append("unmanaged_or_detached_work")
            elif heads.get(target) is None or not SHA.fullmatch(row["head"] or ""):
                reasons.append("integration_evidence_missing")
            else:
                ancestry = git(root, "merge-base", "--is-ancestor", row["head"], heads[target], allow_failure=True)
                if ancestry.returncode not in (0, 1):
                    reasons.append("integration_evidence_missing")
                else:
                    row["fully_integrated"] = ancestry.returncode == 0
                    if ancestry.returncode:
                        reasons.append("not_fully_integrated")
        if not reasons and row["fully_integrated"] and row["dirty"] is False:
            row["status"] = "REVIEW_INTEGRATED"
            reasons.append("verify_remote_holds_and_recovery_before_retirement")
        rows.append(row)
    return {"count": len(rows), "counts": dict(Counter(row["status"] for row in rows)), "items": rows}


def health_snapshot(document: dict | None, now: datetime, max_age: int, heads: dict) -> dict:
    if document is None:
        return {"status": "UNKNOWN", "reason": "no_health_snapshot", "verification": "not_requested"}
    if document.get("schema") != 2:
        return {"status": "UNKNOWN", "reason": "legacy_report_is_not_current_evidence"}
    generated_age = age_hours(document.get("generated_at", ""), now)
    mode = document.get("mode")
    if mode == "local":
        return {"status": "LOCAL_ONLY", "result": document.get("status"),
                "reason": "local_contracts_do_not_establish_live_health", "age_hours": round(generated_age, 2)}
    if mode == "freshness":
        completed = document.get("last_complete_at")
        result = document.get("last_complete_status")
        complete = document.get("status") in {"FRESH", "STALE"} and completed and result in {"PASS", "FAIL"}
        source_sha = document.get("source_sha")
    elif mode == "live":
        completed = document.get("audit_completed_at")
        result = document.get("status")
        admission = document.get("admission")
        if not isinstance(admission, dict):
            raise ValueError("invalid audit admission")
        complete = (document.get("audit_executed") is True and document.get("audit_complete") is True
                    and admission.get("accepted") is True and result in {"PASS", "FAIL"})
        source_sha = document.get("source_sha")
        if complete:
            areas = document.get("results", {})
            expected = {"branches", "issues", "labels", "task_branches", "workflows", "security", "repository_contracts"}
            admission = document["admission"]
            before_state, after_state = admission.get("before"), admission.get("after")
            if not isinstance(before_state, dict) or not isinstance(after_state, dict):
                raise ValueError("invalid complete audit admission")
            before, after = before_state.get("heads"), after_state.get("heads")
            if (not isinstance(areas, dict) or set(areas) != expected
                    or any(not isinstance(area, dict) or area.get("status") not in {"PASS", "FAIL"}
                           for area in areas.values())
                    or (result == "PASS") != all(area.get("status") == "PASS" for area in areas.values())
                    or not isinstance(before, dict) or before != after or before.get("main") != source_sha):
                raise ValueError("inconsistent complete audit snapshot")
    else:
        raise ValueError("unsupported health snapshot mode")
    if not complete:
        return {"status": "UNKNOWN", "reason": "no_complete_audit", "reported_status": document.get("status")}
    age = age_hours(completed, now)
    if instant(completed) > instant(document["generated_at"]):
        raise ValueError("audit completion is later than its report")
    if not SHA.fullmatch(source_sha or ""):
        raise ValueError("complete audit is missing its source identity")
    status = "STALE" if max(age, generated_age) > max_age else "REPORTED_" + result
    if source_sha != heads.get("main"):
        status = "STALE_SOURCE"
    return {"status": status, "last_complete_at": completed, "last_complete_status": result,
            "age_hours": round(age, 2), "source_sha": source_sha,
            "verification": "provided_snapshot_not_reauthenticated", "current_remote_health": "UNKNOWN"}


def issue_snapshot(document: dict | None, now: datetime, policy: dict) -> dict:
    if document is None:
        return {"status": "UNKNOWN", "reason": "no_issue_snapshot"}
    if document.get("schema") != 1 or not isinstance(document.get("issues"), list):
        raise ValueError("invalid issue snapshot envelope")
    if document.get("complete") is not True:
        return {"status": "UNKNOWN", "reason": "issue_snapshot_not_declared_complete"}
    age = age_hours(document.get("generated_at", ""), now)
    counts, stale_active, invalid = Counter(), [], []
    seen = set()
    for item in document["issues"]:
        if not isinstance(item, dict):
            raise ValueError("invalid issue snapshot item")
        number = item.get("number")
        if type(number) is not int or number <= 0 or number in seen:
            raise ValueError("invalid or duplicate issue identity")
        seen.add(number)
        if item.get("state") not in {"open", "closed"}:
            raise ValueError("invalid issue state")
        if item["state"] != "open":
            continue
        raw_labels = item.get("labels")
        if not isinstance(raw_labels, list):
            raise ValueError("issue labels must be an array")
        labels = []
        for label in raw_labels:
            name = label if isinstance(label, str) else label.get("name") if isinstance(label, dict) else None
            if not isinstance(name, str):
                raise ValueError("invalid issue label")
            labels.append(name)
        states = [label.removeprefix("workflow: ") for label in labels if label.startswith("workflow: ")]
        if len(states) != 1 or states[0] not in policy["states"]:
            if "system: reference" not in labels:
                invalid.append(number)
            continue
        counts[states[0]] += 1
        if states[0] == "active" and age_hours(item.get("updated_at", ""), now) > 14 * 24:
            stale_active.append(number)
    over_limit = {state: counts[state] for state, maximum in policy["wip_limits"].items() if counts[state] > maximum}
    return {"status": "STALE" if age > 30 else "ATTENTION" if invalid or over_limit or stale_active else "SNAPSHOT_OK",
            "counts": {state: counts[state] for state in policy["states"]}, "age_hours": round(age, 2),
            "invalid_workflow": invalid, "over_limit": over_limit, "review_active": stale_active,
            "verification": "provided_snapshot_not_reauthenticated"}


def propagation_effort(document: dict | None) -> dict:
    if document is None:
        return {"status": "NOT_RECORDED", "changes": 0}
    rows = document.get("changes")
    if document.get("schema") != 1 or not isinstance(rows, list):
        raise ValueError("invalid propagation effort log")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid propagation observation")
        key = row.get("commit")
        total, propagation = row.get("maintenance_minutes"), row.get("propagation_minutes")
        if (not isinstance(key, str) or not SHA.fullmatch(key) or key in seen
                or type(total) not in (int, float) or type(propagation) not in (int, float)
                or not math.isfinite(total) or not math.isfinite(propagation)
                or not 0 <= propagation <= total or not total > 0
                or type(row.get("manual_reconciliation")) is not bool):
            raise ValueError("invalid or duplicate propagation observation")
        seen.add(key)
    window = rows[-10:]
    total = sum(row["maintenance_minutes"] for row in window)
    fraction = sum(row["propagation_minutes"] for row in window) / total if total else 0
    conflicts = sum(row["manual_reconciliation"] for row in window)
    return {"status": "REVIEW_TOPOLOGY" if len(window) == 10 and (fraction > 0.2 or conflicts >= 3) else "OBSERVING",
            "changes": len(window), "manual_reconciliations": conflicts,
            "propagation_fraction": round(fraction, 3), "authority": "advisory_only"}


def snapshot(root: Path, prefix: str, health: dict | None = None, issues: dict | None = None,
             effort: dict | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    branches = json.loads((root / ".github/branch-policy.json").read_text())["branches"]
    issue_policy = json.loads((root / ".github/issue-policy.json").read_text())
    health_policy = json.loads((root / ".github/repository-health.json").read_text())
    graph, heads = branch_snapshot(root, branches, prefix)
    cleanup = json.loads((root / ".github/branch-cleanup.json").read_text())
    worktrees = worktree_snapshot(root, branches, heads, cleanup["holds"])
    health_state = health_snapshot(health, now, health_policy["freshness"]["max_age_hours"], heads)
    issues_state = issue_snapshot(issues, now, issue_policy)
    effort_state = propagation_effort(effort)
    actions = []
    for edge in graph["edges"]:
        if edge["status"] == "DRIFT":
            actions.append({"priority": 1, "area": "propagation", "action": f"Review {edge['parent']} -> {edge['child']}: {edge['missing_parent_commits']} missing parent commits."})
        elif edge["status"] == "UNKNOWN":
            actions.append({"priority": 1, "area": "propagation", "action": f"Obtain an authorized current snapshot for {edge['parent']} -> {edge['child']}; local evidence is incomplete."})
    if health_state["status"] not in {"REPORTED_PASS"}:
        actions.append({"priority": 1, "area": "health", "action": f"Review repository audit evidence ({health_state['status']}); an offline snapshot cannot establish current remote health."})
    if issues_state["status"] not in {"SNAPSHOT_OK"}:
        actions.append({"priority": 2, "area": "issues", "action": f"Review task handoff and current WIP through the existing issue workflow ({issues_state['status']})."})
    reviews = sum(row["status"] == "REVIEW_INTEGRATED" or "stale_registration_review" in row["reasons"] for row in worktrees["items"])
    if reviews:
        actions.append({"priority": 3, "area": "worktrees", "action": f"Review {reviews} integrated or stale local worktree registrations; this report authorizes no deletion."})
    if effort_state["status"] == "REVIEW_TOPOLOGY":
        actions.append({"priority": 3, "area": "structure", "action": "Review intermediate branch responsibilities using the last ten measured changes."})
    actions.sort(key=lambda row: (row["priority"], row["area"], row["action"]))
    return {"schema": 1, "repository": REPOSITORY, "mode": "offline", "generated_at": now.isoformat(),
            "status": "ATTENTION" if actions else "SNAPSHOT_OK", "remote_state": "NOT_VERIFIED",
            "branches": graph, "health": health_state, "issues": issues_state,
            "worktrees": worktrees, "propagation_effort": effort_state, "actions": actions}


def summary(report: dict, maximum: int) -> str:
    edges = report["branches"]["edges"]
    rows = [f"Offline repository maintenance: {report['status']}",
            "Remote state is not verified; this command does not fetch or change anything.",
            f"Branch edges: {sum(edge['status'] == 'IN_SYNC' for edge in edges)}/{len(edges)} contain their local parent snapshot.",
            f"Audit evidence: {report['health']['status']}; issues: {report['issues']['status']}.",
            f"Local worktrees: {report['worktrees']['count']} (retention reasons are in the JSON report).", ""]
    rows.extend(f"{index}. {item['action']}" for index, item in enumerate(report["actions"][:maximum], 1))
    if len(report["actions"]) > maximum:
        rows.append(f"{len(report['actions']) - maximum} additional actions are in the JSON report.")
    return "\n".join(rows)


def report_target(root: Path, target: Path, inputs: list[Path | None]) -> Path:
    """Refuse source/input/config overwrites before producing a report."""
    absolute = target.absolute()
    if absolute.is_symlink() or any(parent.is_symlink() for parent in absolute.parents):
        raise ValueError("report output cannot traverse symlinks")
    resolved = absolute.resolve()
    if resolved in {path.resolve() for path in inputs if path is not None}:
        raise ValueError("report output cannot overwrite an input snapshot")
    for option in ("--absolute-git-dir", "--git-common-dir"):
        directory = Path(git(root, "rev-parse", option).stdout.strip())
        if not directory.is_absolute():
            directory = root / directory
        if resolved.is_relative_to(directory.resolve()):
            raise ValueError("report output cannot overwrite Git metadata")
    if resolved.is_relative_to(root.resolve()):
        relative = resolved.relative_to(root.resolve())
        if ".git" in relative.parts:
            raise ValueError("report output cannot overwrite Git metadata")
        tracked = git(root, "ls-files", "--error-unmatch", "--", str(relative), allow_failure=True)
        if tracked.returncode == 0:
            raise ValueError("report output cannot overwrite tracked files")
    if resolved.exists():
        try:
            previous = json.loads(resolved.read_text())
        except (ValueError, OSError) as error:
            raise ValueError("existing output is not a maintenance report") from error
        if (not isinstance(previous, dict) or previous.get("schema") != 1
                or previous.get("repository") != REPOSITORY or previous.get("mode") != "offline"):
            raise ValueError("existing output is not a maintenance report")
    return resolved


def write_report(target: Path, report: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".maintenance-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
            output.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--refs-prefix", default="refs/remotes/origin")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--health-report", type=Path)
    parser.add_argument("--issues-json", type=Path)
    parser.add_argument("--effort-log", type=Path)
    parser.add_argument("--max-actions", type=int, default=5)
    parser.add_argument("--strict", action="store_true", help="fail when actionable or unknown local evidence remains")
    args = parser.parse_args()
    if not 1 <= args.max_actions <= 20:
        parser.error("--max-actions must be between 1 and 20")
    try:
        root = args.root.resolve()
        target = report_target(root, args.report, [args.health_report, args.issues_json, args.effort_log])
        report = snapshot(root, args.refs_prefix, read_document(args.health_report),
                          read_document(args.issues_json), read_document(args.effort_log))
        write_report(target, report)
        print(summary(report, args.max_actions))
        return 1 if args.strict and report["status"] != "SNAPSHOT_OK" else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Offline maintenance inspection failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
