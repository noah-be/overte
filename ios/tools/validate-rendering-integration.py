#!/usr/bin/env python3
"""Validate source evidence for the iOS native rendering integration audit."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "ios/rendering-integration-inventory.json"
ALLOWED_STATUS = {"implemented", "blocked", "unverified"}
REQUIRED_BLOCKERS = {"interface-display-gl-api-boundary"}


def main():
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    errors = []
    if data.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    policy = data.get("policy", {})
    if not policy.get("reuse_existing_renderer") or policy.get("renderer_reimplementation_allowed"):
        errors.append("inventory must require the existing renderer")
    if policy.get("bootstrap_geometry_is_evidence"):
        errors.append("bootstrap geometry cannot be rendering evidence")
    path = data.get("required_path", [])
    for required in ("entities-renderer", "gpu-vk", "vk", "MoltenVK::MoltenVK", "CAMetalLayer"):
        if required not in path:
            errors.append(f"required path omits {required}")

    ids = set()
    blockers = set()
    for check in data.get("checks", []):
        check_id = check.get("id")
        if not check_id or check_id in ids:
            errors.append(f"invalid or duplicate check id {check_id!r}")
        ids.add(check_id)
        status = check.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"{check_id}: invalid status {status!r}")
        if status == "blocked":
            blockers.add(check_id)
            if not check.get("barrier"):
                errors.append(f"{check_id}: blocker lacks explanation")
        subtasks = check.get("subtasks", [])
        if check_id == "hybrid-opengl-dependency":
            if not subtasks or subtasks[0].get("status") != "implemented":
                errors.append(f"{check_id}: migration must record its completed classification step")
            if status == "blocked" and not any(task.get("status") == "pending" for task in subtasks):
                errors.append(f"{check_id}: cannot be blocked without pending source tasks")
            if status == "implemented" and any(task.get("status") != "implemented" for task in subtasks):
                errors.append(f"{check_id}: implemented migration still has incomplete tasks")
            for task in subtasks:
                task_source = ROOT / task.get("source", "")
                if not task_source.is_file():
                    errors.append(f"{check_id}/{task.get('id')}: missing source")
                    continue
                task_text = task_source.read_text(encoding="utf-8", errors="replace")
                if task.get("anchor") not in task_text:
                    errors.append(f"{check_id}/{task.get('id')}: missing source anchor")
        if check_id == "interface-display-gl-api-boundary":
            if status != "blocked" or not subtasks:
                errors.append(f"{check_id}: residual GL API debt must remain fail-visible")
            for task in subtasks:
                task_source = ROOT / task.get("source", "")
                if not task_source.is_file():
                    errors.append(f"{check_id}/{task.get('id')}: missing source")
                    continue
                task_text = task_source.read_text(encoding="utf-8", errors="replace")
                if task.get("anchor") not in task_text:
                    errors.append(f"{check_id}/{task.get('id')}: missing source anchor")
        if not check.get("acceptance"):
            errors.append(f"{check_id}: missing acceptance criterion")
        source = ROOT / check.get("source", "")
        if not source.is_file():
            errors.append(f"{check_id}: missing source {check.get('source')}")
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        for anchor in check.get("anchors", []):
            if anchor not in text:
                errors.append(f"{check_id}: missing anchor {anchor!r}")

    missing_blockers = REQUIRED_BLOCKERS - blockers
    if missing_blockers:
        errors.append("known blockers no longer classified as blocked: " + ", ".join(sorted(missing_blockers)))
    if errors:
        print("rendering integration inventory invalid:\n  - " + "\n  - ".join(errors), file=sys.stderr)
        return 1
    print(f"rendering integration inventory valid: {len(ids)} checks, {len(blockers)} explicit blockers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
