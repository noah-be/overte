#!/usr/bin/env python3
"""Reconcile new/managed issues using the same policy as the Codex intake tool."""
import argparse
import json
import os
from pathlib import Path
import sys

from intake import (API, REPOSITORY, COMMENT_MARKER, MARKER, Client, IntakeError,
                    expected_labels, labels, load_policy, managed, parse, snapshot, validate, verify_saved)


def plan(issue, policy, open_issues, event_number=None):
    if not managed(issue, policy):
        return {"number": issue["number"], "managed": False, "errors": [], "patch": {}}
    names = labels(issue)
    workflows = [x.removeprefix("workflow: ") for x in names if x.startswith("workflow:")]
    state = workflows[0] if len(workflows) == 1 and workflows[0] in policy["states"] else "inbox"
    completion = issue["state"] == "closed" and issue.get("state_reason") == "completed"
    try:
        draft = parse(issue, policy)
        errors = validate(draft, policy, state, completion, issue["state"] == "closed" and issue.get("state_reason") == "not_planned")
    except (IntakeError, KeyError) as exc:
        draft = None
        errors = [str(exc)]
    if not errors and issue["state"] == "open" and state in policy["wip_limits"]:
        occupants = sorted(x["number"] for x in open_issues if "workflow: " + state in labels(x))
        if len(occupants) > policy["wip_limits"][state]:
            rejected = event_number == issue["number"] if event_number else issue["number"] not in occupants[:policy["wip_limits"][state]]
            if rejected:
                errors.append(f"{state} limit exceeded; existing work keeps its place. Choose a next step after capacity is available.")
    patch = {}
    if errors:
        desired = {x for x in names if not x.startswith("workflow:")} - set(policy["validation_labels"].values())
        desired.add(policy["validation_labels"]["needs_info"])
        if issue["state"] == "open" or completion:
            desired.add("workflow: inbox")
        if completion:
            patch.update(state="open", state_reason=None)
    else:
        desired = set(expected_labels(draft, policy, state if issue["state"] == "open" else None, names))
    if desired != names:
        patch["labels"] = sorted(desired)
    return {"number": issue["number"], "managed": True, "errors": errors, "patch": patch}


def reconcile(client, number, policy, apply=False, event_number=None):
    issue = client.issue(number)
    result = plan(issue, policy, client.issues(), event_number)
    if not apply or not result["managed"]:
        return result
    if result["patch"]:
        if snapshot(client.issue(number)) != snapshot(issue):
            raise IntakeError(f"Issue #{number} changed during validation; retry on the next event/audit")
        client.write(f"{API}/issues/{number}", "PATCH", result["patch"], number)
        verify_saved(client, number, result["patch"])
    comments = client.pages(f"issues/{number}/comments")
    # Never edit a human comment merely because it includes our marker.
    existing = [x for x in comments if COMMENT_MARKER in x.get("body", "") and x.get("user", {}).get("login") == "github-actions[bot]"]
    if not result["errors"] and not existing:
        return result
    text = COMMENT_MARKER + "\n\n"
    if result["errors"]:
        text += "This entry is saved, but it needs these corrections before it can enter Ready or Active:\n\n"
        text += "\n".join("- " + x for x in result["errors"])
        text += ("\n\nAsk Codex to structure this issue with the Overte issue intake skill. "
                 "Preserve the observations and existing evidence. The validator checks the correction automatically. "
                 "[Issue rules](https://github.com/noah-be/overte/blob/main/docs/ISSUE_WORKFLOW.md)")
    else:
        text += "Structure and labels checked. No corrections are currently needed. This is not a product acceptance result."
    if existing and existing[0]["body"] == text:
        return result
    if existing:
        comment_id = existing[0]["id"]
        comment = client.api(f"{API}/issues/comments/{comment_id}")
        if comment.get("issue_url") != f"https://api.github.com/{API}/issues/{number}" or comment.get("user", {}).get("login") != "github-actions[bot]":
            raise IntakeError("Validator comment ownership mismatch")
        path = f"{API}/issues/comments/{comment_id}"
        client.write(path, "PATCH", {"body": text}, number)
    else:
        comment = client.write(f"{API}/issues/{number}/comments", "POST", {"body": text}, number)
        path = f"{API}/issues/comments/{comment['id']}"
    if client.api(path).get("body") != text:
        raise IntakeError(f"Validator comment read-back mismatch on #{number}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--number", type=int)
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise IntakeError("The guard runs only in noah-be/overte")
    client = Client()
    # The workflow checks out trusted main. Use that same policy/code snapshot.
    policy = load_policy(path=Path(__file__).resolve().parents[2] / ".github/issue-policy.json")
    client.verify_repository()
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()) if os.environ.get("GITHUB_EVENT_PATH") else {}
    if event.get("repository") and event["repository"].get("full_name") != REPOSITORY:
        raise IntakeError("Event repository mismatch")
    number = args.number or event.get("issue", {}).get("number")
    candidates = [number] if number else [x["number"] for x in client.issues("all") if managed(x, policy)]
    results, failures = [], []
    for item in candidates:
        try:
            results.append(reconcile(client, item, policy, args.apply, number))
        except IntakeError as exc:
            failures.append({"number": item, "error": str(exc)})
    report = {"applied": args.apply, "results": results, "operational_errors": failures}
    print(json.dumps(report, indent=2))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        pending = sum(bool(x["errors"]) for x in results)
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(f"Issue intake: {len(results)} checked, {pending} need correction, {len(failures)} operational errors.\n")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (IntakeError, ValueError, KeyError, OSError) as error:
        print(f"Issue guard: {error}", file=sys.stderr)
        raise SystemExit(2)
