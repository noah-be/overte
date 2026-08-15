#!/usr/bin/env python3
"""Create allowlist-only macOS graphics hardware evidence from system_profiler JSON."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile


class HardwareEvidenceError(RuntimeError):
    pass


RUN_RESULT_FIELDS = {
    "schema_version", "platform", "fixture_version", "fixture_mode", "profile_id",
    "run_index", "quality_score", "requested_profile", "actual_profile", "platform_info",
    "stress_entities", "warmup_to_snapshot_ms", "duration_ms", "measurement_complete",
    "sample_count", "frame_time_unit", "samples_us", "mean_frame_ms", "min_frame_ms",
    "p50_frame_ms", "p90_frame_ms", "p95_frame_ms", "p99_frame_ms", "max_frame_ms",
    "over_16_67_ms", "over_33_33_ms", "rates_hz", "stats", "lod_timings_ms",
    "fixture_features", "fixture_present_delta", "fixture_sha256",
}
DIAGNOSTIC_RENDERER_TOKENS = (
    "software", "paravirtual", "virtual", "swiftshader", "llvmpipe", "softpipe", "offscreen",
)


def clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > 256 or any(ord(character) < 32 for character in cleaned):
        return None
    return cleaned


def first_string(value: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        cleaned = clean_string(value.get(key))
        if cleaned is not None:
            return cleaned
    return None


def cpu_model_string(value: object) -> str | None:
    cleaned = clean_string(value)
    if cleaned is None or cleaned.lower() in ("unknown", "n/a", "not available"):
        return None
    return cleaned


def nonnegative_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def capacity_bytes(value: object) -> int | None:
    cleaned = clean_string(value)
    if cleaned is None:
        return None
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)", cleaned, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    factors = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    result = amount * factors[match.group(2).upper()]
    return int(result) if math.isfinite(result) and result >= 0 else None


def yes_no(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    cleaned = clean_string(value)
    if cleaned is None:
        return None
    normalized = cleaned.lower()
    if normalized in ("yes", "spdisplays_yes", "true"):
        return True
    if normalized in ("no", "spdisplays_no", "false"):
        return False
    return None


def display_dimensions(value: dict[str, object]) -> tuple[int | None, int | None, float | None]:
    text = first_string(
        value, "_spdisplays_resolution", "spdisplays_resolution", "_spdisplays_pixels",
    )
    if text is None:
        return None, None, None
    match = re.search(
        r"([0-9]+)\s*x\s*([0-9]+)(?:\s*@\s*([0-9]+(?:\.[0-9]+)?)\s*Hz)?", text,
    )
    if not match:
        return None, None, None
    refresh = float(match.group(3)) if match.group(3) is not None else None
    return int(match.group(1)), int(match.group(2)), refresh


def sanitize_display(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    width, height, refresh = display_dimensions(value)
    result = {
        "name": first_string(value, "_name"),
        "width": width,
        "height": height,
        "refresh_hz": refresh,
        "primary": yes_no(value.get("spdisplays_main")),
        "online": yes_no(value.get("spdisplays_online")),
        "connection": first_string(value, "spdisplays_connection_type"),
    }
    return result if result["name"] is not None or width is not None else None


def sanitize_gpu(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    displays = []
    raw_displays = value.get("spdisplays_ndrvs")
    if isinstance(raw_displays, list):
        displays = [display for item in raw_displays if (display := sanitize_display(item)) is not None]
    result = {
        "model": first_string(value, "sppci_model", "chipset_model", "_name"),
        "vendor": first_string(value, "spdisplays_vendor", "sppci_vendor"),
        "vram_bytes": capacity_bytes(value.get("spdisplays_vram"))
        or capacity_bytes(value.get("_spdisplays_vram")),
        "displays": displays,
    }
    return result if result["model"] is not None or displays else None


def first_object(value: object) -> dict[str, object]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def sanitize(
        payload: object, os_name: str, os_version: str, os_build: str,
        cpu_model: str | None,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise HardwareEvidenceError("system profiler input must be a JSON object")
    hardware = first_object(payload.get("SPHardwareDataType"))
    raw_gpus = payload.get("SPDisplaysDataType")
    gpus = []
    if isinstance(raw_gpus, list):
        gpus = [gpu for item in raw_gpus if (gpu := sanitize_gpu(item)) is not None]
    chip = first_string(hardware, "chip_type")
    return {
        "schema_version": 1,
        "os": {
            "name": clean_string(os_name),
            "version": clean_string(os_version),
            "build": clean_string(os_build),
        },
        "computer": {
            "model": first_string(hardware, "machine_model"),
            "name": first_string(hardware, "machine_name"),
            "chip": chip,
            "cpu_model": cpu_model_string(cpu_model)
            or cpu_model_string(first_string(hardware, "processor_name", "cpu_type"))
            or chip,
            "cpu_cores": nonnegative_integer(
                hardware.get("total_number_of_cores", hardware.get("number_processors"))
            ),
            "memory_bytes": capacity_bytes(hardware.get("physical_memory")),
        },
        "gpus": gpus,
    }


def allowlisted_object(value: object, fields: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for field in fields:
        item = value.get(field)
        if isinstance(item, str):
            cleaned = clean_string(item)
            if cleaned is not None:
                result[field] = cleaned
        elif isinstance(item, (bool, int, float)) and not (
                isinstance(item, float) and not math.isfinite(item)):
            result[field] = item
    return result


def sanitize_graphics_api(value: object) -> dict[str, object] | None:
    result = allowlisted_object(
        value, ("name", "renderer", "vendor", "version", "shadingLanguageVersion"),
    )
    return result or None


def sanitize_runtime_platform_info(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HardwareEvidenceError("profile result has no platform information")
    platform = value.get("platform")
    graphics_apis = platform.get("graphicsAPIs") if isinstance(platform, dict) else None
    sanitized_apis = []
    if isinstance(graphics_apis, list):
        sanitized_apis = [
            api for item in graphics_apis[:8] if (api := sanitize_graphics_api(item)) is not None
        ]
    gpu_value = value.get("gpu")
    gpu = None if gpu_value is None else allowlisted_object(
        gpu_value, ("model", "name", "description", "vendor", "isPrimary"),
    )
    tier = value.get("tier")
    if (isinstance(tier, bool) or not isinstance(tier, (int, float))
            or not math.isfinite(float(tier))):
        tier = None
    deferred_capable = value.get("deferred_capable")
    if not isinstance(deferred_capable, bool):
        deferred_capable = None
    return {
        "platform": {"graphicsAPIs": sanitized_apis},
        "computer": allowlisted_object(
            value.get("computer"), ("model", "vendor", "OS", "OSVersion", "profileTier"),
        ),
        "cpu": allowlisted_object(
            value.get("cpu"), ("model", "name", "vendor", "numCores", "isPrimary"),
        ),
        "gpu": gpu,
        "display": allowlisted_object(
            value.get("display"),
            (
                "modeWidth", "modeHeight", "modeRefreshrate", "width", "height",
                "refreshRate", "isPrimary",
            ),
        ),
        "tier": tier,
        "deferred_capable": deferred_capable,
    }


def sanitize_profile_result(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise HardwareEvidenceError("profile result must be a JSON object")
    result = {key: payload[key] for key in RUN_RESULT_FIELDS if key in payload}
    result["platform_info"] = sanitize_runtime_platform_info(payload.get("platform_info"))
    return result


def classify_runner(payload: object) -> str:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise HardwareEvidenceError("unsupported sanitized hardware evidence")
    gpus = payload.get("gpus")
    if not isinstance(gpus, list):
        raise HardwareEvidenceError("sanitized hardware evidence has no GPU list")
    has_gpu = any(isinstance(gpu, dict) and clean_string(gpu.get("model")) for gpu in gpus)
    has_display = any(
        isinstance(gpu, dict) and isinstance(gpu.get("displays"), list) and gpu["displays"]
        for gpu in gpus
    )
    renderer_text = json.dumps(gpus, sort_keys=True).lower()
    return "diagnostic" if (
        not has_gpu or not has_display
        or any(token in renderer_text for token in DIAGNOSTIC_RENDERER_TOKENS)
    ) else "hardware"


def atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise HardwareEvidenceError("refusing to replace a symlinked hardware evidence file")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--profile-result", type=Path)
    mode.add_argument("--classify", type=Path)
    parser.add_argument("--os-name")
    parser.add_argument("--os-version")
    parser.add_argument("--os-build")
    parser.add_argument("--cpu-model")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        if arguments.classify is not None:
            try:
                hardware = json.loads(arguments.classify.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HardwareEvidenceError("invalid sanitized hardware JSON") from error
            print(classify_runner(hardware), flush=True)
        elif arguments.profile_result is not None:
            try:
                profile = json.loads(arguments.profile_result.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HardwareEvidenceError("invalid profile-result JSON") from error
            atomic_write(arguments.profile_result, sanitize_profile_result(profile))
        else:
            if not all((arguments.os_name, arguments.os_version, arguments.os_build)):
                raise HardwareEvidenceError("OS name, version, and build are required")
            try:
                payload = json.load(sys.stdin)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HardwareEvidenceError("invalid system profiler JSON") from error
            evidence = sanitize(
                payload, arguments.os_name, arguments.os_version, arguments.os_build,
                arguments.cpu_model,
            )
            if not evidence["computer"]["model"] or not evidence["gpus"]:
                raise HardwareEvidenceError("hardware evidence is missing a computer model or GPU")
            atomic_write(arguments.output, evidence)
    except (OSError, HardwareEvidenceError) as error:
        print(f"hardware evidence sanitization failed: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
