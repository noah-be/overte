"""Reuse device catalog suites with exact identity binding and explicit coverage gaps."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import math
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from artifacts import select_artifact
from common import HERE, ROOT, digest, json_read, write_json


def bind_result_use(ctx, directory, suite, form):
    """Copied result folders cannot stand in for independent physical runs."""
    directory = Path(directory).resolve()
    identity = json_read(directory / "result-identity.json")
    run = json_read(directory / "run-manifest.json")
    if not ctx.need(run.get("suite") == suite, "device-suite-identity",
                    "The recorded suite must match the requested suite, not only its module set."):
        return False
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    uses = getattr(ctx, "device_result_uses", {})
    ctx.device_result_uses = uses
    use = (str(directory), suite, form)
    if not ctx.need(fingerprint not in uses or uses[fingerprint] == use, "copied-device-result",
                    "Identical result evidence cannot count as a different run or form factor."):
        return False
    uses[fingerprint] = use
    return True


def verify_result(ctx, directory, suite, sha, form):
    catalog = json_read(ROOT / "tests/device/catalog.json")
    modules = [x["id"] for x in catalog["modules"] if suite in x["suites"]]
    if not ctx.need(modules, "device-suite", "Requested suite must exist in the shared catalog."):
        return False
    command = [sys.executable, ROOT / "tests/device/verify-result.py", "--result-dir", directory,
               "--expected-source-sha", ctx.revision, "--expected-artifact-sha256", sha,
               "--expected-adapter", "appium-ios", "--expected-platform", "ios", "--device-class", "physical"]
    for module in modules:
        command += ["--required-module", module]
    result = ctx.command("verify-" + suite + "-" + str(len(ctx.findings)), command)
    return result is not None and result.returncode == 0 and bind_result_use(ctx, directory, suite, form)


def run_suite(ctx, target, suite, dest, sha, *, soak=False):
    artifact = Path(target["e2eArtifact"])
    if not ctx.need(artifact.is_file() and digest(artifact) == sha, "e2e-artifact", "A hash-bound signed iOS E2E IPA is required for device execution."):
        return False
    config = Path(target["targetConfig"])
    if not ctx.need(config.is_file() and not config.is_symlink() and config.stat().st_mode & 0o077 == 0,
                    "device-config-permissions", "Appium target configuration must be a private regular file (0600)."):
        return False
    env = os.environ.copy()
    env["OVERTE_APPIUM_TARGETS"] = str(config)
    if soak:
        env.update(OVERTE_DEVICE_IDLE_SECONDS="1200", OVERTE_DEVICE_SAMPLE_SECONDS="30",
                   OVERTE_DEVICE_LIFECYCLE_CYCLES="30")
    # The private target file must expose exactly one enabled device. Harness discovery
    # rejects ambiguous targets; no UDID or selector is placed on this command line.
    argv = [sys.executable, ROOT / "tests/device/run.py", "--adapter-manifest", ROOT / "tests/device/adapters/appium/ios.json",
            "--catalog", ROOT / "tests/device/catalog.json", "--suite", suite,
            "--tablet-policy", ROOT / "tests/device/adapters/appium/ios-flat-touch-policy.json",
            "--output-dir", dest, "--require-complete", "--candidate-artifact", artifact,
            "--expected-source-sha", ctx.revision, "--expected-artifact-sha256", sha]
    if soak:
        argv.append("--keep-running")
    result = ctx.command("run-" + suite + "-" + dest.name, argv, env=env, timeout=7200)
    return result is not None and result.returncode == 0 and verify_result(ctx, dest, suite, sha, target["formFactor"])


def device(ctx, scope):
    if select_artifact(ctx) is None:
        return
    plan = json_read(HERE / "test-plan.json")
    targets = ctx.config.get("deviceTargets", [])
    if not ctx.need({x.get("formFactor") for x in targets} == {"iphone", "ipad"} and len(targets) == 2,
                    "device-form-factors", "Separate physical iPhone and iPad evidence is required."):
        return
    ctx.review("e2e-production-parity", "Review the E2E build's relationship to the production candidate and test-hook differences.", artifact=True)
    ctx.review("device-coverage", "Confirm physical iPhone/iPad identity, signing receipts, installation, controlled fixtures and private target binding.", artifact=True)
    used = set()
    coverage = []
    for target in targets:
        form = target["formFactor"]
        sha = target.get("e2eSha256", "")
        parity = ctx.config.get("reviews", {}).get("e2e-production-parity", {})
        if not ctx.need(len(sha) == 64 and sha in parity.get("e2eArtifactSha256", []), "e2e-pair-binding", "Parity review must explicitly include each E2E artifact digest."):
            continue
        if ctx.group == "long-running":
            run_soak(ctx, target, sha, plan)
            continue
        for suite in plan[ctx.group]["suites"]:
            if ctx.config.get("executeDevice"):
                dest = ctx.output / f"{form}-{suite}"
                passed = run_suite(ctx, target, suite, dest, sha)
            else:
                location = target.get("results", {}).get(suite)
                if not ctx.need(location, "missing-" + form + "-" + suite, f"Missing physical {form} evidence for {suite}."):
                    continue
                dest = Path(location).resolve()
                if not ctx.need(dest not in used, "reused-device-result", "One device result cannot stand in for multiple form factors/suites."):
                    continue
                used.add(dest)
                passed = verify_result(ctx, dest, suite, sha, form)
            coverage.append({"formFactor": form, "suite": suite, "status": "PASS" if passed else "FAIL"})
        for case in plan[ctx.group]["manualCases"]:
            review_name = f"{form}-{case['id']}"
            ctx.review(review_name, case["procedure"], artifact=True)
    ctx.inventories[ctx.group + "-coverage"] = coverage


def run_soak(ctx, target, sha, plan):
    form = target["formFactor"]
    suites = plan["long-running"]["suites"]
    minimum = plan["long-running"]["minimumSeconds"]
    if ctx.config.get("executeDevice"):
        started = time.monotonic()
        history = []
        iteration = 0
        # No retry of failed product cases. Reuse the shared runner/catalog; each
        # bounded result remains within its existing <=2h identity contract.
        while time.monotonic() - started < minimum:
            for suite in suites:
                dest = ctx.output / f"{form}-soak-{iteration:03d}-{suite}"
                if not run_suite(ctx, target, suite, dest, sha, soak=True):
                    return
                history.append({"suite": suite, "directory": str(dest)})
            iteration += 1
        write_json(ctx.output / f"{form}-soak-results.json", {"results": history})
    else:
        history = target.get("longRunningResults", [])
    if not ctx.need(bool(history), "soak-missing", f"No long-running {form} results."):
        return
    total = 0.0
    seen, observed = set(), set()
    global_seen = getattr(ctx, "soak_result_paths", set())
    ctx.soak_result_paths = global_seen
    intervals = []
    for item in history:
        directory, suite = Path(item["directory"]).resolve(), item["suite"]
        if not ctx.need(directory not in seen and directory not in global_seen and suite in suites, "soak-duplicates", "Soak results must be unique across form factors and use the required suites."):
            continue
        seen.add(directory)
        global_seen.add(directory)
        if verify_result(ctx, directory, suite, sha, form):
            run = json_read(directory / "run-manifest.json")
            intervals.append((run["startedEpochMs"], run["finishedEpochMs"]))
            total += run["durationSeconds"]
            observed.add(suite)
    intervals.sort()
    for left, right in zip(intervals, intervals[1:]):
        ctx.need(0 <= right[0] - left[1] <= 300000, "soak-continuity", "Soak results must be non-overlapping with gaps <=5 minutes.")
    ctx.need(total >= minimum and set(suites) <= observed, "soak-duration", f"At least {minimum} seconds and all soak suites are required for {form}.")
    metrics = target.get("metrics")
    if ctx.need(metrics, "soak-metrics", "Provide a private timestamped resource measurement JSON file."):
        analyze_metrics(ctx, Path(metrics), sha, form, plan["long-running"], intervals)
    for case in plan["long-running"]["manualCases"]:
        ctx.review(f"{form}-{case['id']}", case["procedure"], artifact=True)


def analyze_metrics(ctx, path, sha, form, policy, intervals):
    value = json_read(path)
    if not ctx.need(value.get("sourceRevision") == ctx.revision and value.get("artifactSha256") == sha
                    and value.get("formFactor") == form, "metrics-binding", "Metrics must bind source, E2E artifact and form factor."):
        return
    samples = value.get("samples", [])
    if not ctx.need(len(samples) >= 30, "metrics-count", "At least 30 measurements are required."):
        return
    required = ("elapsedSeconds", "rssMiB", "cpuPercent")
    if not ctx.need(all(all(isinstance(x.get(k), (int, float)) and not isinstance(x[k], bool)
                            and math.isfinite(x[k]) and x[k] >= 0 for k in required) for x in samples),
                    "metrics-values", "Resource samples must contain finite nonnegative elapsedSeconds, rssMiB and cpuPercent."):
        return
    times = [x["elapsedSeconds"] for x in samples]
    started = value.get("startedEpochMs")
    if not ctx.need(type(started) is int and bool(intervals), "metrics-clock", "Timestamped metrics must identify the measured campaign interval."):
        return
    ctx.need(abs(started + times[0] * 1000 - intervals[0][0]) <= 120000
             and abs(started + times[-1] * 1000 - intervals[-1][1]) <= 120000,
             "metrics-campaign-binding", "Resource measurements must span the same campaign timestamps as the verified suite results.")
    sessions = {x.get("processSession") for x in samples}
    ctx.need(len(sessions) == 1 and None not in sessions and "" not in sessions,
             "continuous-process", "A stable anonymized process-session identifier must prove no process restart during the soak.")
    ctx.need(times[-1] - times[0] >= policy["minimumSeconds"] and all(0 < b - a <= 120 for a, b in zip(times, times[1:])),
             "metrics-duration", "Resource samples must span the soak with <=120-second gaps.")
    rss = [x["rssMiB"] for x in samples]
    cpu = [x["cpuPercent"] for x in samples]
    quarter = max(1, len(rss) // 4)
    growth = sum(rss[-quarter:]) / quarter - sum(rss[:quarter]) / quarter
    ctx.need(max(rss) <= policy["maxRssMiB"], "memory-budget", "RSS peak exceeds the reviewed device budget.")
    ctx.need(growth <= policy["maxRssGrowthMiB"], "memory-growth", "Sustained RSS growth exceeds budget; investigate retained allocations/leaks.")
    ctx.need(sum(cpu) / len(cpu) <= policy["maxMeanCpuPercent"], "cpu-budget", "Mean CPU consumption exceeds budget.")
    optional = {"gpuPercent": (0, 100), "batteryPercent": (0, 100), "thermalState": (0, 3), "freeDiskMiB": (0, 10**9)}
    for field, (low, high) in optional.items():
        available = all(isinstance(x.get(field), (int, float)) and not isinstance(x[field], bool)
                        and math.isfinite(x[field]) and low <= x[field] <= high for x in samples)
        if not available:
            ctx.review(f"{form}-unavailable-{field}", f"{field} unavailable: record supported measurement method or justified device/API limitation.", artifact=True)
        elif field == "thermalState":
            ctx.need(max(x[field] for x in samples) < 3, "thermal-critical", "Critical thermal state observed.")
        elif field == "batteryPercent":
            ctx.need(value.get("charging") is False, "battery-charging", "Battery drain measurements must be unplugged.")
            drain = (samples[0][field] - samples[-1][field]) / ((times[-1] - times[0]) / 3600)
            ctx.need(drain <= policy["maxBatteryDrainPerHour"], "battery-budget", "Battery drain exceeds the reviewed budget.")
    ctx.inventories[f"{form}-resource-summary"] = {"samples": len(samples), "peakRssMiB": max(rss),
        "rssGrowthMiB": growth, "meanCpuPercent": sum(cpu) / len(cpu), "metricsSha256": digest(path)}
