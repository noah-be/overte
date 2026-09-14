#!/usr/bin/env python3
"""Structured, fork-bound issue intake. Uses gh without a shell; stdlib only."""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

REPOSITORY = "noah-be/overte"
API = f"repos/{REPOSITORY}"
ROOT = Path(__file__).resolve().parents[2]
MARKER = re.compile(r"<!-- overte-issue:v1 request:([0-9a-f-]{36}) -->")
COMMENT_MARKER = "<!-- overte-issue-validator:v1 -->"
EMPTY = {"", "tbd", "todo", "...", "n/a", "none", "unknown", "not yet known", "_no response_"}


class IntakeError(Exception):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def gh(path, method="GET", data=None):
    if not (path == API or path.startswith(API + "/")):
        raise IntakeError("API path is outside noah-be/overte")
    args = ["gh", "api", "--hostname", "github.com", "--method", method, path]
    if data is not None:
        args += ["--input", "-"]
    try:
        result = subprocess.run(args, input=json.dumps(data) if data is not None else None,
                                text=True, capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise IntakeError("GitHub request did not complete. For a write, inspect the saved issue before retrying.") from exc
    if result.returncode:
        # Do not print raw API error payloads, draft content, or credentials.
        raise IntakeError(f"GitHub {method} request failed ({result.returncode}); no success is claimed. Check authentication/access and read back before retrying a write.")
    return json.loads(result.stdout) if result.stdout.strip() else None


class Client:
    def __init__(self, transport=gh):
        self.api = transport

    def verify_repository(self):
        repo = self.api(API)
        if repo.get("full_name") != REPOSITORY or repo.get("default_branch") != "main":
            raise IntakeError("Repository identity/default branch mismatch")
        return repo

    def issue(self, number):
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise IntakeError("Issue number must be a positive integer")
        issue = self.api(f"{API}/issues/{number}")
        if (issue.get("repository_url") != f"https://api.github.com/{API}"
                or issue.get("html_url") != f"https://github.com/{REPOSITORY}/issues/{number}"
                or issue.get("number") != number or "pull_request" in issue):
            raise IntakeError("Issue ownership mismatch or pull request supplied")
        return issue

    def pages(self, endpoint):
        items = []
        for page in range(1, 1001):
            sep = "&" if "?" in endpoint else "?"
            batch = self.api(f"{API}/{endpoint}{sep}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise IntakeError("Invalid paginated GitHub response")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise IntakeError("Pagination limit exceeded; result is incomplete")

    def issues(self, state="open"):
        return [x for x in self.pages(f"issues?state={state}") if "pull_request" not in x]

    def write(self, path, method, data, number=None):
        self.verify_repository()  # Resolve the actual owner immediately before every mutation.
        if number is not None:
            self.issue(number)
        return self.api(path, method, data)


def load_policy(client=None, path=None):
    if path:
        policy = json.loads(Path(path).read_text())
    else:
        client.verify_repository()
        content = client.api(f"{API}/contents/.github/issue-policy.json?ref=main")
        policy = json.loads(base64.b64decode(content["content"]))
    if policy.get("repository") != REPOSITORY or policy.get("schema") != 1 or policy.get("minimum_tool_revision", 1) > 1:
        raise IntakeError("Unsupported issue policy; update the installed tool instead of bypassing validation")
    return policy


def labels(issue):
    return {x["name"] if isinstance(x, dict) else x for x in issue.get("labels", [])}


def snapshot(issue):
    return digest({k: issue.get(k) for k in
                   ("number", "title", "body", "labels", "milestone", "state", "state_reason", "updated_at")})


def validate(draft, policy, state="inbox", completion=False, not_planned=False):
    errors = []
    if not isinstance(draft, dict):
        return ["Draft must be a JSON object"]
    allowed = {"title", "kind", "platforms", "fields", "milestone", "request_id", "extra_labels"}
    if set(draft) - allowed:
        errors.append("Unknown draft keys: " + ", ".join(sorted(set(draft) - allowed)))
    title = draft.get("title")
    if not isinstance(title, str) or not title.strip() or "\n" in title or len(title) > policy["title_max_length"]:
        errors.append(f"title: use one nonempty line, at most {policy['title_max_length']} characters")
    if draft.get("kind") not in policy["kinds"]:
        errors.append("kind: choose bug, idea, task, or acceptance")
    platforms = draft.get("platforms")
    if not isinstance(platforms, list) or any(not isinstance(x, str) or x not in policy["platforms"] for x in platforms) or len(set(platforms)) != len(platforms):
        errors.append("platforms: use unique documented platform labels; [] is allowed for repository-only work")
    milestone = draft.get("milestone")
    if milestone is not None and (not isinstance(milestone, int) or isinstance(milestone, bool) or milestone <= 0):
        errors.append("milestone: use the native milestone number or null")
    if draft.get("kind") == "acceptance" and (not platforms or milestone is None):
        errors.append("acceptance: requires at least one platform and a native milestone")
    try:
        if str(uuid.UUID(draft.get("request_id", ""))) != draft.get("request_id"):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        errors.append("request_id: use the UUID generated by the example command; preserve it when retrying")
    extras = draft.get("extra_labels", [])
    managed = set(policy["kinds"].values()) | set(policy["platforms"]) | set(policy["validation_labels"].values()) | {"system: reference"}
    if not isinstance(extras, list) or any(not isinstance(x, str) or x in managed or x.startswith("workflow:") for x in extras):
        errors.append("extra_labels: only supplementary repository labels are allowed")
    fields = draft.get("fields")
    if not isinstance(fields, dict):
        return errors + ["fields: must be an object"]
    if set(fields) - set(policy["fields"]):
        errors.append("Unknown fields: " + ", ".join(sorted(set(fields) - set(policy["fields"]))))
    if state not in policy["states"]:
        errors.append("Unknown workflow state")
    required = set(policy["required"].get(draft.get("kind"), []))
    if state in ("ready", "active"):
        required.update(policy["ready_fields"])
        if draft.get("kind") == "idea":
            errors.append("idea: refine into a concrete task before Ready/Active; retain the original proposal through a link")
    if state == "blocked":
        required.update(("blocker", "unblock_condition"))
    if completion:
        required.update(("outcome", "done_criteria", "required_checks", "evidence"))
    if not_planned:
        required.add("outcome")
    for key, value in fields.items():
        if key in policy["list_fields"]:
            if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() or "\n" in x for x in value):
                errors.append(f"{key}: use a list of nonempty single-line strings")
        elif not isinstance(value, str):
            errors.append(f"{key}: use text")
        values = value if isinstance(value, list) else [value]
        for text in values:
            if isinstance(text, str) and re.search(r"(?m)^##\s|<!-- overte-issue:|<!-- overte-issue-validator:|Prepared with AI assistance;", text):
                errors.append(f"{key}: reserved section/metadata syntax is not allowed")
    for key in sorted(required):
        value = fields.get(key)
        if key == "dependencies" and value == []:
            continue
        values = value if isinstance(value, list) else [value]
        if not value or any(not isinstance(x, str) or x.strip().lower() in EMPTY for x in values):
            if state == "inbox" and not completion and key in policy["unknown_allowed_inbox"] and isinstance(value, str) and value.strip().lower() in ("unknown", "not yet known"):
                continue
            errors.append(f"{key}: provide a meaningful value")
    if isinstance(fields.get("summary"), str) and len(fields["summary"]) > policy["summary_max_length"]:
        errors.append("summary: keep the current overview within 1000 characters; put history in comments/evidence")
    if isinstance(fields.get("next_action"), str) and "\n" in fields["next_action"].strip():
        errors.append("next_action: state one concrete action on one line")
    if len(json.dumps(fields)) > policy["body_max_length"]:
        errors.append("Description is too long; link detailed evidence instead")
    return errors


def require_valid(draft, policy, state="inbox", completion=False, not_planned=False):
    errors = validate(draft, policy, state, completion, not_planned)
    if errors:
        raise IntakeError("Draft rejected before writing:\n- " + "\n- ".join(errors))


def render(draft, policy):
    sections = [("Issue type", draft["kind"]), ("Platforms", ", ".join(draft["platforms"]) or "Repository / other")]
    for key, heading in policy["fields"].items():
        if key not in draft["fields"]:
            continue
        value = draft["fields"][key]
        if isinstance(value, list):
            value = "\n".join("- " + x for x in value) or "None"
        sections.append((heading, value))
    return (f"<!-- overte-issue:v1 request:{draft['request_id']} -->\n\n"
            + "\n\n".join(f"## {heading}\n\n{value}" for heading, value in sections)
            + "\n\n---\nPrepared with AI assistance; factual claims and evidence require review.\n")


def parse(issue, policy):
    body = issue.get("body") or ""
    markers = MARKER.findall(body)
    if len(markers) != 1:
        raise IntakeError("Missing or duplicated structured issue marker; use the intake tool to prepare/migrate this issue")
    body = body.split("\n\n---\nPrepared with AI assistance;", 1)[0]
    pairs = re.findall(r"(?ms)^## ([^\n]+)\n(.*?)(?=^## |\Z)", body)
    sections = {}
    headings = {"Issue type", "Platforms"} | set(policy["fields"].values())
    for heading, content in pairs:
        if heading not in headings or heading in sections:
            raise IntakeError("Unknown or duplicate section: " + heading)
        sections[heading] = content.strip()
    fields = {}
    for key, heading in policy["fields"].items():
        if heading not in sections:
            continue
        value = sections[heading]
        if key in policy["list_fields"]:
            if value == "None":
                value = []
            elif all(line.startswith("- ") for line in value.splitlines()) and value:
                value = [line[2:] for line in value.splitlines()]
            else:
                raise IntakeError(f"{heading}: expected a bullet list")
        fields[key] = value
    platform_text = sections.get("Platforms", "")
    platforms = [] if platform_text == "Repository / other" else platform_text.split(", ")
    draft = {"title": issue["title"], "kind": sections.get("Issue type"), "platforms": platforms,
            "fields": fields, "request_id": markers[0],
            "milestone": issue["milestone"]["number"] if issue.get("milestone") else None}
    if render(draft, policy).strip() != (issue.get("body") or "").strip():
        raise IntakeError("Description contains unstructured text or formatting; preserve it in the draft before normalizing")
    return draft


def expected_labels(draft, policy, state="inbox", existing=()):
    managed = set(policy["kinds"].values()) | set(policy["platforms"]) | set(policy["validation_labels"].values())
    preserved = {x for x in existing if x not in managed and not x.startswith("workflow:")}
    result = preserved | {policy["kinds"][draft["kind"]], policy["validation_labels"]["passed"]} | set(draft["platforms"]) | set(draft.get("extra_labels", []))
    if state:
        result.add("workflow: " + state)
    return sorted(result)


def check_remote(client, draft, policy, desired_labels, state="inbox", exclude=None):
    client.verify_repository()
    known = {x["name"] for x in client.pages("labels")}
    missing = set(desired_labels) - known
    if missing:
        raise IntakeError("Repository labels missing: " + ", ".join(sorted(missing)))
    if draft.get("milestone"):
        milestone = client.api(f"{API}/milestones/{draft['milestone']}")
        if milestone.get("state") != "open" or not milestone.get("url", "").startswith(f"https://api.github.com/{API}/milestones/"):
            raise IntakeError("Milestone is closed or belongs to another repository")
    if state in policy["wip_limits"]:
        count = sum(x["number"] != exclude and "workflow: " + state in labels(x) for x in client.issues())
        if count >= policy["wip_limits"][state]:
            raise IntakeError(f"{state} is full ({count}); retain existing work and choose another state")


def verify_saved(client, number, payload):
    saved = client.issue(number)
    for key in ("title", "body", "state", "state_reason"):
        if key in payload and saved.get(key) != payload[key]:
            raise IntakeError(f"Saved {key} differs; inspect issue #{number} before any retry")
    if "labels" in payload and labels(saved) != set(payload["labels"]):
        raise IntakeError(f"Saved labels differ; inspect issue #{number}")
    if "milestone" in payload and (saved["milestone"]["number"] if saved.get("milestone") else None) != payload["milestone"]:
        raise IntakeError(f"Saved milestone differs; inspect issue #{number}")
    return {"number": number, "url": saved["html_url"], "labels": sorted(labels(saved)), "snapshot": snapshot(saved), "verified": True}


def create(client, draft, policy):
    require_valid(draft, policy)
    desired = expected_labels(draft, policy)
    check_remote(client, draft, policy, desired)
    marker = f"<!-- overte-issue:v1 request:{draft['request_id']} -->"
    matches = [x for x in client.issues("all") if marker in (x.get("body") or "")]
    payload = {"title": draft["title"], "body": render(draft, policy), "labels": desired, "milestone": draft.get("milestone")}
    if matches:
        if len(matches) != 1:
            raise IntakeError("Request ID appears on several issues; resolve the duplicate instead of creating another")
        return verify_saved(client, matches[0]["number"], payload)
    created = client.write(f"{API}/issues", "POST", payload)
    # Never automatically repeat POST after a timeout or ambiguous result.
    return verify_saved(client, created["number"], payload)


def update(client, number, draft, policy, expected_snapshot, state=None, close_reason=None):
    original = client.issue(number)
    if "system: reference" in labels(original):
        raise IntakeError("Operating references are not task issues")
    if snapshot(original) != expected_snapshot:
        raise IntakeError("Issue changed since show; read it again and preserve concurrent edits")
    workflow = [x.removeprefix("workflow: ") for x in labels(original) if x.startswith("workflow:")]
    if len(workflow) > 1 and state is None:
        raise IntakeError("Resolve ambiguous workflow explicitly")
    state = state or (workflow[0] if workflow else "inbox")
    if original["state"] == "closed" and close_reason is None:
        raise IntakeError("Closed issues are preserved; explicitly reopen through GitHub before editing")
    require_valid(draft, policy, state, completion=close_reason == "completed", not_planned=close_reason == "not_planned")
    old_marker = MARKER.search(original.get("body") or "")
    if old_marker and old_marker[1] != draft["request_id"]:
        raise IntakeError("Preserve the existing request_id")
    desired = expected_labels(draft, policy, None if close_reason else state, labels(original))
    check_remote(client, draft, policy, desired, state if not close_reason else "inbox", number)
    payload = {"title": draft["title"], "body": render(draft, policy), "labels": desired, "milestone": draft.get("milestone")}
    if close_reason:
        payload.update(state="closed", state_reason=close_reason)
    # Optimistic re-read: GitHub issue edits do not expose an atomic conditional PATCH.
    if snapshot(client.issue(number)) != expected_snapshot:
        raise IntakeError("Issue changed during validation; read again")
    client.write(f"{API}/issues/{number}", "PATCH", payload, number)
    return verify_saved(client, number, payload)


def inspect_issue(issue, policy):
    if "system: reference" in labels(issue):
        return {"number": issue["number"], "status": "reference", "errors": []}
    if not MARKER.search(issue.get("body") or ""):
        return {"number": issue["number"], "status": "legacy", "errors": []}
    try:
        draft = parse(issue, policy)
        workflows = [x.removeprefix("workflow: ") for x in labels(issue) if x.startswith("workflow:")]
        state = workflows[0] if len(workflows) == 1 else "inbox"
        errors = validate(draft, policy, state, issue["state"] == "closed" and issue.get("state_reason") == "completed", issue["state"] == "closed" and issue.get("state_reason") == "not_planned")
        if issue["state"] == "open" and len(workflows) != 1:
            errors.append("Open issues require exactly one workflow label")
        if issue["state"] == "closed" and workflows:
            errors.append("Closed issues must not retain workflow labels")
        if draft.get("kind") in policy["kinds"]:
            desired = set(expected_labels(draft, policy, state if issue["state"] == "open" else None, labels(issue)))
            # Validation labels are output, not evidence that a document is valid.
            ignored = set(policy["validation_labels"].values())
            if desired - ignored != labels(issue) - ignored:
                errors.append("Type/platform/workflow labels do not match the structured description")
        return {"number": issue["number"], "status": "invalid" if errors else "valid", "errors": errors}
    except IntakeError as exc:
        return {"number": issue["number"], "status": "invalid", "errors": [str(exc)]}


def example(kind, policy):
    fields = {x: ([] if x in policy["list_fields"] else "") for x in policy["required"][kind]}
    return {"request_id": str(uuid.uuid4()), "title": "", "kind": kind,
            "platforms": [], "milestone": None, "fields": fields}


@contextlib.contextmanager
def local_lock():
    directory = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "overte-issue-intake"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "write.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", help="Explicit local policy for development/installation; normal sessions read main")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("policy")
    p = sub.add_parser("example"); p.add_argument("kind", choices=("bug", "idea", "task", "acceptance"))
    p = sub.add_parser("validate"); p.add_argument("file"); p.add_argument("--state", default="inbox"); p.add_argument("--render", action="store_true")
    p = sub.add_parser("search"); p.add_argument("terms", nargs="+")
    p = sub.add_parser("show"); p.add_argument("number", type=int)
    p = sub.add_parser("create"); p.add_argument("file"); p.add_argument("--apply", action="store_true")
    p = sub.add_parser("update"); p.add_argument("number", type=int); p.add_argument("file"); p.add_argument("--snapshot", required=True); p.add_argument("--state"); p.add_argument("--close", choices=("completed", "not_planned")); p.add_argument("--apply", action="store_true")
    sub.add_parser("audit")
    args = parser.parse_args()
    client = Client()
    policy = load_policy(client, args.policy)
    if args.command == "policy":
        result = policy
    elif args.command == "example":
        result = example(args.kind, policy)
    elif args.command == "search":
        result = [{"number": x["number"], "title": x["title"], "state": x["state"], "url": x["html_url"], "labels": sorted(labels(x))}
                  for x in client.issues("all") if any(t.casefold() in (x["title"] + "\n" + (x.get("body") or "")).casefold() for t in args.terms)]
    elif args.command == "show":
        issue = client.issue(args.number)
        result = {"snapshot": snapshot(issue), "issue": issue, "validation": inspect_issue(issue, policy)}
        if MARKER.search(issue.get("body") or ""):
            result["draft"] = parse(issue, policy)
    elif args.command == "audit":
        result = [inspect_issue(x, policy) for x in client.issues()]
    else:
        draft = json.loads(Path(args.file).read_text())
        require_valid(draft, policy, getattr(args, "state", None) or "inbox", getattr(args, "close", None) == "completed", getattr(args, "close", None) == "not_planned")
        if args.command == "validate" and args.render:
            print(render(draft, policy)); return 0
        if args.command == "validate" or not args.apply:
            result = {"valid": True, "write_performed": False, "body": render(draft, policy)}
        else:
            with local_lock():
                result = create(client, draft, policy) if args.command == "create" else update(client, args.number, draft, policy, args.snapshot, args.state, args.close)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (IntakeError, ValueError, KeyError, OSError) as error:
        print(f"Issue intake: {error}", file=sys.stderr)
        raise SystemExit(2)
