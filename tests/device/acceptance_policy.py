#!/usr/bin/env python3
"""Load the versioned platform/suite promotion policy."""

from __future__ import annotations

import json
from pathlib import Path


STATES = ("implemented", "accepted", "required")


def catalog_suites(path: Path) -> set[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    modules = value.get("modules") if isinstance(value, dict) else None
    if not isinstance(modules, list):
        raise ValueError("module catalog is invalid")
    suites = {suite for module in modules for suite in module.get("suites", [])}
    if not suites or not all(isinstance(item, str) and item for item in suites):
        raise ValueError("module catalog contains invalid suite identifiers")
    return suites


def load_policy(path: Path, catalog: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {
            "schemaVersion", "contractVersion", "platforms"}:
        raise ValueError("acceptance policy fields are invalid")
    if value["schemaVersion"] != 1 or value["contractVersion"] != 1:
        raise ValueError("unsupported acceptance policy contract")
    platforms = value.get("platforms")
    if (not isinstance(platforms, dict) or not platforms
            or list(platforms) != sorted(platforms)):
        raise ValueError("acceptance policy platforms must be non-empty and sorted")
    known_suites = catalog_suites(catalog)
    for platform, profile in platforms.items():
        if (not isinstance(platform, str) or not platform
                or not isinstance(profile, dict)
                or set(profile) != {"defaultEvidence", "defaultState", "suites"}):
            raise ValueError("acceptance policy platform profile is invalid")
        if profile["defaultState"] not in STATES:
            raise ValueError(f"platform {platform} has an invalid default state")
        if (not isinstance(profile["defaultEvidence"], str)
                or (profile["defaultState"] != "implemented"
                    and not profile["defaultEvidence"])):
            raise ValueError(f"platform {platform} default promotion needs evidence")
        overrides = profile["suites"]
        if not isinstance(overrides, dict) or list(overrides) != sorted(overrides):
            raise ValueError(f"platform {platform} suite overrides must be sorted")
        unknown = sorted(set(overrides) - known_suites)
        if unknown:
            raise ValueError(f"platform {platform} references unknown suites: {', '.join(unknown)}")
        for suite, promotion in overrides.items():
            if (not isinstance(promotion, dict)
                    or set(promotion) != {"state", "evidence"}
                    or promotion.get("state") not in STATES
                    or not isinstance(promotion.get("evidence"), str)):
                raise ValueError(f"platform {platform} suite {suite} promotion is invalid")
            if promotion["state"] != "implemented" and not promotion["evidence"]:
                raise ValueError(
                    f"platform {platform} suite {suite} needs hardware acceptance evidence")
    return value


def state_for(policy: dict, platform: str, suite: str) -> str:
    if platform not in policy["platforms"]:
        raise ValueError(f"platform {platform!r} is absent from the acceptance policy")
    profile = policy["platforms"][platform]
    return profile["suites"].get(suite, {"state": profile["defaultState"]})["state"]


def gates(policy: dict, catalog: Path, minimum: str = "required") -> list[str]:
    if minimum not in STATES:
        raise ValueError("unknown acceptance lifecycle state")
    threshold = STATES.index(minimum)
    suites = sorted(catalog_suites(catalog))
    return sorted(
        f"{platform}:{suite}"
        for platform in policy["platforms"]
        for suite in suites
        if STATES.index(state_for(policy, platform, suite)) >= threshold
    )
