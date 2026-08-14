#!/usr/bin/env python3
"""Render a validated macOS performance profile into a test script."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile


PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
BOOLEAN_FIELDS = (
    "shadows",
    "haze",
    "bloom",
    "ambient_occlusion",
    "local_lighting",
    "procedural_materials",
)


class ProfileError(RuntimeError):
    pass


def load_profiles(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError(f"could not read profile set: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ProfileError("unsupported performance profile schema")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ProfileError("profiles must be a non-empty array")
    return payload


def validate_profile(profile: object) -> dict[str, object]:
    if not isinstance(profile, dict):
        raise ProfileError("profile must be an object")
    required = {
        "id", "quality_score", "render_method", "shadows", "haze", "bloom",
        "ambient_occlusion", "local_lighting", "procedural_materials",
        "antialiasing", "viewport_scale", "forward_samples",
    }
    if set(profile) != required:
        raise ProfileError("profile fields do not match the strict schema")
    identifier = profile["id"]
    if not isinstance(identifier, str) or not PROFILE_ID.fullmatch(identifier):
        raise ProfileError("profile id is invalid")
    if isinstance(profile["quality_score"], bool) or not isinstance(profile["quality_score"], int):
        raise ProfileError("quality_score must be an integer")
    if not 0 <= profile["quality_score"] <= 100:
        raise ProfileError("quality_score is outside 0..100")
    if profile["render_method"] not in (0, 1):
        raise ProfileError("render_method must be Deferred=0 or Forward=1")
    for field in BOOLEAN_FIELDS:
        if not isinstance(profile[field], bool):
            raise ProfileError(f"{field} must be boolean")
    if profile["antialiasing"] not in (0, 1, 2):
        raise ProfileError("antialiasing must be None=0, TAA=1, or FXAA=2")
    scale = profile["viewport_scale"]
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
        raise ProfileError("viewport_scale must be finite")
    if not 0.5 <= float(scale) <= 1.0:
        raise ProfileError("viewport_scale is outside the benchmark range")
    if profile["forward_samples"] not in (1, 2, 4):
        raise ProfileError("forward_samples must be 1, 2, or 4")
    return dict(profile)


def select_profile(payload: dict[str, object], identifier: str) -> dict[str, object]:
    matches = [validate_profile(item) for item in payload["profiles"] if isinstance(item, dict) and item.get("id") == identifier]
    if len(matches) != 1:
        raise ProfileError(f"expected exactly one profile named {identifier}")
    return matches[0]


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ProfileError("refusing to replace a symlinked script")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--run-index", type=int, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.run_index <= 0 or arguments.run_index > 20:
            raise ProfileError("run index is outside 1..20")
        payload = load_profiles(arguments.profiles)
        profile = select_profile(payload, arguments.profile)
        template = arguments.template.read_text(encoding="utf-8")
        injected = {
            "profile": profile,
            "fixture_version": payload.get("fixture_version"),
            "run_index": arguments.run_index,
            "trace_path": str(arguments.trace.resolve()),
        }
        prefix = "var OVERTE_MACOS_PERFORMANCE_CASE = " + json.dumps(injected, sort_keys=True) + ";\n"
        atomic_write(arguments.output, (prefix + template).encode("utf-8"))
    except (OSError, ProfileError) as error:
        print(f"performance profile generation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"profile": arguments.profile, "run_index": arguments.run_index}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
