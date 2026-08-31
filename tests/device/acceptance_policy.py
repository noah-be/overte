#!/usr/bin/env python3
"""Load the versioned platform/suite promotion policy."""

from __future__ import annotations

import json
from pathlib import Path
import re


STATES = ("implemented", "accepted", "required")
EVIDENCE_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,95}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
RECORDED_AT = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def catalog_suites(path: Path) -> set[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    modules = value.get("modules") if isinstance(value, dict) else None
    if not isinstance(modules, list):
        raise ValueError("module catalog is invalid")
    suites = {suite for module in modules for suite in module.get("suites", [])}
    if not suites or not all(isinstance(item, str) and item for item in suites):
        raise ValueError("module catalog contains invalid suite identifiers")
    return suites


def load_evidence(path: Path, known_suites: set[str]) -> dict[str, dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value.get("evidence") if isinstance(value, dict) else None
    if (not isinstance(value, dict)
            or set(value) != {"schemaVersion", "contractVersion", "evidence"}
            or value.get("schemaVersion") != 1 or value.get("contractVersion") != 1
            or not isinstance(records, list)):
        raise ValueError("acceptance evidence registry is invalid")
    expected = {"id", "platform", "suite", "outcome", "targetClass",
                "resultArtifact", "resultSha256", "runnerRevision", "recordedAt"}
    by_id: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != expected:
            raise ValueError("acceptance evidence record fields are invalid")
        identifier = record.get("id")
        if (not isinstance(identifier, str) or not EVIDENCE_ID.fullmatch(identifier)
                or identifier in by_id or record.get("suite") not in known_suites
                or record.get("outcome") != "passed"
                or record.get("targetClass") not in {"hardware-gpu", "physical-device"}
                or not isinstance(record.get("resultArtifact"), str)
                or not record["resultArtifact"].startswith(
                    ("local-lab://", "local-jenkins://"))
                or not isinstance(record.get("resultSha256"), str)
                or not SHA256.fullmatch(record["resultSha256"])
                or not isinstance(record.get("runnerRevision"), str)
                or not REVISION.fullmatch(record["runnerRevision"])
                or not isinstance(record.get("recordedAt"), str)
                or not RECORDED_AT.fullmatch(record["recordedAt"])):
            raise ValueError("acceptance evidence record is invalid")
        by_id[identifier] = record
    if list(by_id) != sorted(by_id):
        raise ValueError("acceptance evidence records must be sorted by ID")
    return by_id


def load_policy(path: Path, catalog: Path, evidence_path: Path | None = None) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {
            "schemaVersion", "contractVersion", "platforms"}:
        raise ValueError("acceptance policy fields are invalid")
    if value["schemaVersion"] != 2 or value["contractVersion"] != 1:
        raise ValueError("unsupported acceptance policy contract")
    platforms = value.get("platforms")
    if (not isinstance(platforms, dict) or not platforms
            or list(platforms) != sorted(platforms)):
        raise ValueError("acceptance policy platforms must be non-empty and sorted")
    known_suites = catalog_suites(catalog)
    evidence = load_evidence(
        evidence_path or path.with_name("acceptance-evidence.json"), known_suites)

    def validate_promotion(platform: str, suite: str, state: str,
                           references: object) -> None:
        if (not isinstance(references, list)
                or not all(isinstance(item, str) for item in references)
                or references != sorted(set(references))):
            raise ValueError(f"platform {platform} suite {suite} evidence must be sorted and unique")
        minimum = 0 if state == "implemented" else 1 if state == "accepted" else 3
        if len(references) < minimum:
            raise ValueError(
                f"platform {platform} suite {suite} needs {minimum} successful real runs")
        for identifier in references:
            record = evidence.get(identifier)
            if (record is None or record["platform"] != platform or record["suite"] != suite):
                raise ValueError(
                    f"platform {platform} suite {suite} has mismatched acceptance evidence")

    for platform, profile in platforms.items():
        if (not isinstance(platform, str) or not platform
                or not isinstance(profile, dict)
                or set(profile) != {"defaultEvidence", "defaultState", "suites"}):
            raise ValueError("acceptance policy platform profile is invalid")
        if profile["defaultState"] not in STATES:
            raise ValueError(f"platform {platform} has an invalid default state")
        validate_promotion(platform, "*", profile["defaultState"],
                           profile["defaultEvidence"])
        overrides = profile["suites"]
        if not isinstance(overrides, dict) or list(overrides) != sorted(overrides):
            raise ValueError(f"platform {platform} suite overrides must be sorted")
        unknown = sorted(set(overrides) - known_suites)
        if unknown:
            raise ValueError(f"platform {platform} references unknown suites: {', '.join(unknown)}")
        for suite, promotion in overrides.items():
            if (not isinstance(promotion, dict)
                    or set(promotion) != {"state", "evidence"}
                    or promotion.get("state") not in STATES):
                raise ValueError(f"platform {platform} suite {suite} promotion is invalid")
            validate_promotion(platform, suite, promotion["state"], promotion["evidence"])
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
