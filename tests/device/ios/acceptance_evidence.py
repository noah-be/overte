"""Validate continuously observed physical iOS acceptance evidence."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import math
import statistics


class EvidenceError(ValueError):
    """Incomplete or contradictory physical observations cannot establish a pass."""


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def observation(document, run_id, build_version, now_ms):
    if (not isinstance(document, dict) or document.get("schemaVersion") != 1
            or document.get("runId") != run_id or document.get("error")
            or document.get("buildVersion") != build_version
            or not number(document.get("sampleEpochMs"))
            or not -1000 <= now_ms - document["sampleEpochMs"] <= 4000
            or type(document.get("sampleSequence")) is not int or document["sampleSequence"] <= 0):
        raise EvidenceError("IOS_ACCEPTANCE_STALE_OR_INVALID_OBSERVATION")
    native = document.get("nativeAudio", {})
    if (native.get("physicalDevice") is not True or native.get("iosForeground") is not True
            or any(native.get(key) is not False for key in
                   ("prepared", "measurementMode", "sourceEnabled", "sourceClockActive"))):
        raise EvidenceError("IOS_ACCEPTANCE_NATIVE_STATE_INVALID")
    render = document.get("render", {})
    if (type(render.get("frameCount")) is not int or render["frameCount"] <= 0
            or not number(render.get("lastFrameEpochMs"))
            or not -1000 <= now_ms - render["lastFrameEpochMs"] <= 4000
            or not number(render.get("drawCalls")) or render["drawCalls"] <= 0):
        raise EvidenceError("IOS_ACCEPTANCE_RENDER_NOT_ADVANCING")
    scene = document.get("scene", {})
    ids = scene.get("entityIds")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 10000
            or not all(isinstance(identifier, str) and identifier for identifier in ids)
            or len(set(ids)) != len(ids) or scene.get("entityCount") != len(ids)):
        raise EvidenceError("IOS_ACCEPTANCE_SCENE_MISSING")
    return document


def local_resume(before, after):
    native = after["nativeAudio"]
    muted, permission = native.get("nativeMuted"), native.get("iosPermission")
    capture = permission == 1 and muted is False
    expected = 3 if muted else (2 if permission == 1 else 1)
    if (before["scene"].get("protocol") != "file" or after["scene"].get("protocol") != "file"
            or before["scene"]["entityIds"] != after["scene"]["entityIds"]
            or after["sampleSequence"] <= before["sampleSequence"]
            or after["render"]["frameCount"] <= before["render"]["frameCount"]
            or type(muted) is not bool or permission not in (1, 2)
            or native.get("iosInterrupted") is not False or native.get("iosOutcome") != expected
            or native.get("audioLifecycleRunning") is not True or native.get("audioPaused") is not False
            or native.get("iosCaptureAllowed") is not capture or native.get("inputPresent") is not capture
            or (capture and (native.get("inputError") != 0 or native.get("inputState") != 0))):
        raise EvidenceError("IOS_ACCEPTANCE_LOCAL_RESUME_FAILED")
    return {"passed": True, "retainedEntityCount": after["scene"]["entityCount"],
            "renderFramesAdvanced": after["render"]["frameCount"] - before["render"]["frameCount"]}


def stability(rows, *, minimum_seconds=1800):
    if minimum_seconds < 1800:
        raise EvidenceError("IOS_STABILITY_INTERVAL_TOO_SHORT")
    if not isinstance(rows, list) or len(rows) < 61:
        raise EvidenceError("IOS_STABILITY_COVERAGE_MISSING")
    previous = None
    first = rows[0]
    for row in rows:
        if (not number(row.get("elapsedSeconds")) or row["elapsedSeconds"] < 0
                or type(row.get("processId")) is not int or row["processId"] <= 0
                or row["processId"] != first.get("processId")
                or row.get("foreground") is not True
                or type(row.get("thermalState")) is not int or row["thermalState"] not in (0, 1, 2)
                or not number(row.get("physicalFootprintBytes")) or row["physicalFootprintBytes"] <= 0
                or type(row.get("sampleSequence")) is not int or row["sampleSequence"] <= 0
                or type(row.get("renderFrameCount")) is not int or row["renderFrameCount"] <= 0):
            raise EvidenceError("IOS_STABILITY_PROCESS_THERMAL_OR_METRIC_INVALID")
        if previous and (not 0 < row["elapsedSeconds"] - previous["elapsedSeconds"] <= 45
                         or row["sampleSequence"] <= previous["sampleSequence"]
                         or row["renderFrameCount"] <= previous["renderFrameCount"]):
            raise EvidenceError("IOS_STABILITY_OBSERVATION_GAP_OR_FROZEN_RENDER")
        previous = row
    if first["elapsedSeconds"] > 5 or rows[-1]["elapsedSeconds"] < minimum_seconds:
        raise EvidenceError("IOS_STABILITY_START_OR_END_NOT_COVERED")
    # Declare this bounded-session heuristic explicitly; it does not prove an
    # absence of every leak. Reject large sustained growth after warm-up.
    start = [row["physicalFootprintBytes"] for row in rows if 300 <= row["elapsedSeconds"] <= 600]
    end = [row["physicalFootprintBytes"] for row in rows if row["elapsedSeconds"] >= minimum_seconds - 300]
    if len(start) < 5 or len(end) < 5:
        raise EvidenceError("IOS_STABILITY_MEMORY_WINDOW_MISSING")
    initial, final = statistics.median(start), statistics.median(end)
    growth = final - initial
    if growth > 128 * 1024 * 1024 or growth > initial * 0.10:
        raise EvidenceError("IOS_STABILITY_SUSTAINED_MEMORY_GROWTH")
    return {"passed": True, "durationSeconds": rows[-1]["elapsedSeconds"], "samples": len(rows),
            "maximumObservationGapSeconds": max(b["elapsedSeconds"] - a["elapsedSeconds"] for a, b in zip(rows, rows[1:])),
            "thermalStates": sorted(set(row["thermalState"] for row in rows)),
            "physicalFootprintMinimumBytes": min(row["physicalFootprintBytes"] for row in rows),
            "physicalFootprintMaximumBytes": max(row["physicalFootprintBytes"] for row in rows),
            "postWarmupMedianBytes": initial, "finalMedianBytes": final, "medianGrowthBytes": growth,
            "memoryRule": "Final 5-minute median must not exceed the 5-10-minute median by more than 128 MiB or 10%.",
            "limitations": ["One continuously observed session; not a proof of the absence of every memory leak."]}
