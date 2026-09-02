#!/usr/bin/env python3
"""Compile a closed E2E execution plan before any target is discovered."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from acceptance_policy import STATES, catalog_suites, load_policy, state_for


PROFILE_FIELDS = {
    "artifacts", "fixture", "requiredEnvironment", "session", "tabletPolicy", "tier",
}
FIXTURE_RANK = {"none": 0, "scene": 1, "domain": 2}
FIXTURE_ENVIRONMENT = {
    "none": set(),
    "scene": {"OVERTE_E2E_SCENE_URL"},
    "domain": {
        "OVERTE_E2E_DOMAIN_CONTROL_TOKEN", "OVERTE_E2E_DOMAIN_CONTROL_URL",
        "OVERTE_E2E_DOMAIN_HOST", "OVERTE_E2E_DOMAIN_ID",
        "OVERTE_E2E_DOMAIN_MARKERS_JSON", "OVERTE_E2E_DOMAIN_URL",
        "OVERTE_E2E_SCENE_URL",
    },
}


def load_profiles(path: Path, catalog: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict)
            or set(value) != {"schemaVersion", "contractVersion", "suites"}
            or value.get("schemaVersion") != 1 or value.get("contractVersion") != 1):
        raise ValueError("unsupported execution profile contract")
    suites = value.get("suites")
    known = catalog_suites(catalog)
    if (not isinstance(suites, dict) or list(suites) != sorted(suites)
            or set(suites) != known):
        missing = sorted(known - set(suites or {})) if isinstance(suites, dict) else []
        extra = sorted(set(suites or {}) - known) if isinstance(suites, dict) else []
        raise ValueError(
            "execution profiles must cover the catalog exactly"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(extra)}" if extra else ""))
    for suite, profile in suites.items():
        if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS:
            raise ValueError(f"execution profile {suite} fields are invalid")
        if (profile["fixture"] not in FIXTURE_RANK
                or profile["session"] not in {"fresh", "reusable"}
                or profile["tier"] not in {"smoke", "extended", "soak"}
                or not isinstance(profile["tabletPolicy"], bool)):
            raise ValueError(f"execution profile {suite} values are invalid")
        for field in ("artifacts", "requiredEnvironment"):
            items = profile[field]
            if (not isinstance(items, list) or items != sorted(set(items))
                    or not all(isinstance(item, str) and item for item in items)):
                raise ValueError(f"execution profile {suite} {field} must be sorted and unique")
        if not set(profile["artifacts"]) <= {"candidate", "source"}:
            raise ValueError(f"execution profile {suite} artifact vocabulary is invalid")
        if not all(re.fullmatch(r"OVERTE_E2E_[A-Z0-9_]+", item)
                   for item in profile["requiredEnvironment"]):
            raise ValueError(f"execution profile {suite} environment vocabulary is invalid")
    return value


def module_capabilities(catalog: Path, suite: str) -> tuple[list[str], list[str]]:
    modules = json.loads(catalog.read_text(encoding="utf-8"))["modules"]
    selected = [module for module in modules if suite in module["suites"]]
    if not selected:
        raise ValueError(f"suite {suite!r} selects no modules")
    return ([module["id"] for module in selected],
            sorted({capability for module in selected for capability in module["requires"]}))


def select_suites(policy: dict, profiles: dict, platform: str,
                  suites: list[str] | None, minimum_state: str | None) -> list[str]:
    if bool(suites) == bool(minimum_state):
        raise ValueError("select explicit suites or one minimum lifecycle state")
    if suites:
        return list(dict.fromkeys(suites))
    threshold = STATES.index(minimum_state)
    selected = [suite for suite in profiles["suites"]
                if STATES.index(state_for(policy, platform, suite)) >= threshold]
    if not selected:
        raise ValueError(
            f"platform {platform} has no suites at lifecycle state {minimum_state} or higher")
    return selected


def compile_plan(policy: dict, catalog: Path, profiles: dict, platform: str,
                 suites: list[str], environment_keys: set[str], tablet_policy: bool,
                 artifacts: set[str], fixture_provider: str,
                 resources: set[str] | None = None) -> dict:
    if fixture_provider not in {"auto", "external", "none"}:
        raise ValueError("unknown fixture provider")
    selected = list(dict.fromkeys(suites))
    if not selected:
        raise ValueError("execution plan requires at least one suite")
    unknown = sorted(set(selected) - set(profiles["suites"]))
    if unknown:
        raise ValueError("execution plan references unknown suites: " + ", ".join(unknown))
    rows = []
    fixture = "none"
    missing = set()
    available_resources = resources or set()
    for suite in selected:
        profile = profiles["suites"][suite]
        modules, capabilities = module_capabilities(catalog, suite)
        if FIXTURE_RANK[profile["fixture"]] > FIXTURE_RANK[fixture]:
            fixture = profile["fixture"]
        required_environment = set(profile["requiredEnvironment"])
        missing.update(required_environment - environment_keys)
        if profile["tabletPolicy"] and not tablet_policy:
            missing.add("tablet-policy")
        missing.update(f"artifact:{item}" for item in set(profile["artifacts"]) - artifacts)
        rows.append({
            "suite": suite, "state": state_for(policy, platform, suite),
            "fixture": profile["fixture"], "session": profile["session"],
            "tier": profile["tier"], "modules": modules, "capabilities": capabilities,
        })
    fixture_requirements = FIXTURE_ENVIRONMENT[fixture]
    if fixture != "none" and fixture_provider == "none":
        missing.add(f"fixture:{fixture}")
    elif fixture_provider == "external":
        missing.update(fixture_requirements - environment_keys)
    elif fixture == "domain":
        missing.update(f"executable:{item}" for item in
                       {"assignment-client", "domain-server"} - available_resources)
    return {
        "schemaVersion": 1, "contractVersion": 1, "platform": platform,
        "fixture": fixture, "fixtureProvider": fixture_provider,
        "ready": not missing, "missingInputs": sorted(missing), "suites": rows,
    }


def environment_keys(path: Path | None, inherit: bool) -> set[str]:
    keys = set(os.environ) if inherit else set()
    if path is None:
        return keys
    value = json.loads(path.read_text(encoding="utf-8"))
    supplied = value.get("environment") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or set(value) != {"schemaVersion", "environment"}
            or not isinstance(supplied, dict)
            or not all(isinstance(key, str) and isinstance(item, str) and item
                       for key, item in supplied.items())):
        raise ValueError("fixture environment contract is invalid")
    return keys | set(supplied)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--suite", action="append")
    selection.add_argument("--minimum-state", choices=STATES)
    parser.add_argument("--fixture-provider", choices=("auto", "external", "none"),
                        default="none")
    parser.add_argument("--environment-file", type=Path)
    parser.add_argument("--inherit-environment", action="store_true")
    parser.add_argument("--tablet-policy", action="store_true")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--resource", action="append", default=[],
                        choices=("assignment-client", "domain-server"))
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    catalog = args.catalog.resolve()
    policy = load_policy(args.policy.resolve(), catalog)
    profiles = load_profiles(args.profiles.resolve(), catalog)
    suites = select_suites(policy, profiles, args.platform, args.suite, args.minimum_state)
    plan = compile_plan(policy, catalog, profiles, args.platform, suites,
                        environment_keys(args.environment_file, args.inherit_environment),
                        args.tablet_policy, set(args.artifact), args.fixture_provider,
                        set(args.resource))
    encoded = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    if args.require_ready and not plan["ready"]:
        print("error: execution plan is not ready: "
              + ", ".join(plan["missingInputs"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
