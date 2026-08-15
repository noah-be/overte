#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Exercise fail-closed iOS world/screenshot evidence validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_VALIDATOR = ROOT / "ios/tools/validate-world-screenshot.py"
RUNTIME_VALIDATOR = ROOT / "ios/tools/validate-world-runtime.py"
SET_VALIDATOR = ROOT / "ios/tools/validate-world-evidence-set.py"
DOMAIN = "123e4567-e89b-12d3-a456-426614174000"
SESSION = "123e4567-e89b-12d3-a456-426614174001"
NODE = "123e4567-e89b-12d3-a456-426614174002"
ENTITY = "123e4567-e89b-12d3-a456-426614174003"


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def png_bytes(width: int = 400, height: int = 400, *, blank: bool = False) -> bytes:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if blank:
                rows.extend((24, 24, 24))
            else:
                rows.extend(((x * 3 + y) % 256, (y * 5 + x // 2) % 256, (x ^ y) % 256))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def run_screenshot(screenshot: Path, scenario: str, destination: str, report: Path):
    return subprocess.run(
        [
            "python3",
            str(SCREENSHOT_VALIDATOR),
            str(screenshot),
            "--scenario",
            scenario,
            "--destination",
            destination,
            "--output",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_runtime(
    log: Path,
    screenshot: Path,
    screenshot_report: Path,
    scenario: str,
    destination: str,
    output: Path,
    domain: str | None = None,
):
    command = [
        "python3",
        str(RUNTIME_VALIDATOR),
        str(log),
        "--scenario",
        scenario,
        "--destination",
        destination,
        "--screenshot",
        str(screenshot),
        "--screenshot-report",
        str(screenshot_report),
        "--output",
        str(output),
    ]
    if domain is not None:
        command.extend(("--expected-domain", domain))
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def serverless_log(scene: str = "serverless_tutorial", *, reverse: bool = False) -> str:
    gates = [
        f"Overte OVERTE_IOS_WORLD_GATE navigation_requested kind= serverless destination= serverless_tutorial",
        f"Overte OVERTE_IOS_WORLD_GATE serverless_import_committed scene= {scene}",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_tree_nonempty entity= {{{ENTITY}}}",
        f"Overte OVERTE_IOS_ENTITY_GATE render_handoff entity= {{{ENTITY}}}",
    ]
    if reverse:
        gates[2], gates[3] = gates[3], gates[2]
    return "\n".join(gates) + "\n"


def online_log(domain: str = DOMAIN) -> str:
    return "\n".join(
        (
            "Overte OVERTE_IOS_WORLD_GATE navigation_requested kind= online destination= overte_hub",
            f"Overte OVERTE_IOS_ENTITY_GATE domain_list_connected domain= {domain} session= {SESSION}",
            f"Overte OVERTE_IOS_ENTITY_GATE entity_server_active node= {NODE}",
            f"Overte OVERTE_IOS_ENTITY_GATE entity_query_sent node= {NODE} bytes= 144",
            f"Overte OVERTE_IOS_ENTITY_GATE entity_data_received node= {NODE} bytes= 1200",
            f"Overte OVERTE_IOS_ENTITY_GATE entity_tree_nonempty entity= {{{ENTITY}}}",
            f"Overte OVERTE_IOS_ENTITY_GATE render_handoff entity= {{{ENTITY}}}",
        )
    ) + "\n"


with tempfile.TemporaryDirectory(prefix="overte-ios-world-evidence-test-") as directory:
    root = Path(directory)
    screenshot = root / "world.png"
    screenshot.write_bytes(png_bytes())

    serverless_screenshot_report = root / "serverless-screenshot.json"
    result = run_screenshot(
        screenshot, "serverless", "serverless_tutorial", serverless_screenshot_report
    )
    assert result.returncode == 0, result.stderr
    screenshot_payload = json.loads(serverless_screenshot_report.read_text(encoding="utf-8"))
    assert screenshot_payload["accepted"] is True
    assert screenshot_payload["sha256"] == hashlib.sha256(screenshot.read_bytes()).hexdigest()
    assert screenshot_payload["quantizedColorBuckets"] >= 24

    blank = root / "blank.png"
    blank.write_bytes(png_bytes(blank=True))
    blank_result = run_screenshot(blank, "online", "overte_hub", root / "blank.json")
    assert blank_result.returncode == 1, blank_result.stderr
    assert "blank or lacks visible world detail" in blank_result.stderr

    corrupt = root / "corrupt.png"
    damaged = bytearray(png_bytes())
    damaged[-5] ^= 0xFF
    corrupt.write_bytes(damaged)
    corrupt_result = run_screenshot(corrupt, "online", "overte_hub", root / "corrupt.json")
    assert corrupt_result.returncode == 1, corrupt_result.stderr
    assert "CRC mismatch" in corrupt_result.stderr

    trailing = root / "trailing.png"
    trailing.write_bytes(png_bytes() + b"not-part-of-png")
    trailing_result = run_screenshot(trailing, "online", "overte_hub", root / "trailing.json")
    assert trailing_result.returncode == 1, trailing_result.stderr
    assert "incomplete" in trailing_result.stderr

    serverless_log_path = root / "serverless.log"
    serverless_log_path.write_text(serverless_log(), encoding="utf-8")
    serverless_result_path = root / "serverless-runtime.json"
    serverless_result = run_runtime(
        serverless_log_path,
        screenshot,
        serverless_screenshot_report,
        "serverless",
        "serverless_tutorial",
        serverless_result_path,
    )
    assert serverless_result.returncode == 0, serverless_result.stderr
    serverless_payload = json.loads(serverless_result_path.read_text(encoding="utf-8"))
    assert serverless_payload["accepted"] is True
    assert serverless_payload["resolvedDomainId"] is None
    assert serverless_payload["runtime"]["evidence"][0]["gate"] == "serverless_import_committed"
    assert serverless_payload["containsRawRuntimeLog"] is False

    for label, content in (
        ("wrong-scene", serverless_log("different_scene")),
        ("wrong-order", serverless_log(reverse=True)),
    ):
        invalid_log = root / f"{label}.log"
        invalid_log.write_text(content, encoding="utf-8")
        invalid = run_runtime(
            invalid_log,
            screenshot,
            serverless_screenshot_report,
            "serverless",
            "serverless_tutorial",
            root / f"{label}.json",
        )
        assert invalid.returncode == 1, (label, invalid.stderr)

    online_screenshot_report = root / "online-screenshot.json"
    online_screenshot = run_screenshot(
        screenshot, "online", "overte_hub", online_screenshot_report
    )
    assert online_screenshot.returncode == 0, online_screenshot.stderr
    online_log_path = root / "online.log"
    online_log_path.write_text(online_log(), encoding="utf-8")
    online_result_path = root / "online-runtime.json"
    online_result = run_runtime(
        online_log_path,
        screenshot,
        online_screenshot_report,
        "online",
        "overte_hub",
        online_result_path,
        DOMAIN,
    )
    assert online_result.returncode == 0, online_result.stderr
    online_payload = json.loads(online_result_path.read_text(encoding="utf-8"))
    assert online_payload["resolvedDomainId"] == DOMAIN
    assert len(online_payload["runtime"]["evidence"]) == 6

    wrong_domain = run_runtime(
        online_log_path,
        screenshot,
        online_screenshot_report,
        "online",
        "overte_hub",
        root / "wrong-domain.json",
        "223e4567-e89b-12d3-a456-426614174000",
    )
    assert wrong_domain.returncode == 1, wrong_domain.stderr
    assert "does not match" in wrong_domain.stderr

    tampered = root / "tampered.png"
    tampered.write_bytes(png_bytes(401, 400))
    tampered_result = run_runtime(
        online_log_path,
        tampered,
        online_screenshot_report,
        "online",
        "overte_hub",
        root / "tampered.json",
        DOMAIN,
    )
    assert tampered_result.returncode == 1, tampered_result.stderr
    assert "does not match the retained screenshot" in tampered_result.stderr

    candidate_dir = root / "candidate"
    candidate_dir.mkdir()
    artifact = candidate_dir / "0042-OverteIOSClient-Release-simulator.zip"
    artifact.write_bytes(b"fixture simulator candidate")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    revision = "1" * 40
    candidate_manifest = candidate_dir / "0042-OverteIOSClient-Release-simulator.json"
    candidate_manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "product": "overte-ios-integrated-client",
                "artifact": artifact.name,
                "platform": "iphonesimulator",
                "architecture": "arm64",
                "sourceRevision": revision,
                "sha256": artifact_sha,
            }
        ),
        encoding="utf-8",
    )
    evidence = root / "evidence"
    evidence.mkdir()
    for family in ("iphone", "ipad"):
        for scenario, destination, runtime_payload, color_offset in (
            ("serverless", "serverless_tutorial", serverless_payload, 0),
            ("online", "overte_hub", online_payload, 1),
        ):
            stem = f"{family}-{scenario}"
            retained = evidence / f"{stem}.png"
            retained.write_bytes(png_bytes(400 + color_offset, 400))
            retained_sha = hashlib.sha256(retained.read_bytes()).hexdigest()
            report_payload = {
                **(
                    screenshot_payload
                    if scenario == "serverless"
                    else json.loads(online_screenshot_report.read_text(encoding="utf-8"))
                ),
                "file": retained.name,
                "sha256": retained_sha,
            }
            (evidence / f"{stem}-screenshot.json").write_text(
                json.dumps(report_payload), encoding="utf-8"
            )
            bound_runtime = {**runtime_payload, "screenshot": report_payload}
            (evidence / f"{stem}-runtime.json").write_text(
                json.dumps(bound_runtime), encoding="utf-8"
            )
    aggregate = root / "world-evidence-set.json"
    set_result = subprocess.run(
        [
            "python3",
            str(SET_VALIDATOR),
            str(evidence),
            "--candidate-manifest",
            str(candidate_manifest),
            "--source-revision",
            revision,
            "--candidate-sha256",
            artifact_sha,
            "--output",
            str(aggregate),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert set_result.returncode == 0, set_result.stderr
    aggregate_payload = json.loads(aggregate.read_text(encoding="utf-8"))
    assert aggregate_payload["accepted"] is True
    assert aggregate_payload["worldsVisuallyDistinct"] is True
    assert len(aggregate_payload["cases"]) == 4

    (evidence / "raw.log").write_text("secret raw log", encoding="utf-8")
    raw_result = subprocess.run(
        [
            "python3",
            str(SET_VALIDATOR),
            str(evidence),
            "--candidate-manifest",
            str(candidate_manifest),
            "--source-revision",
            revision,
            "--candidate-sha256",
            artifact_sha,
            "--output",
            str(root / "raw-rejected.json"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert raw_result.returncode == 1
    assert "raw runtime logs" in raw_result.stderr

main_source = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
application_source = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
application_setup_source = (ROOT / "interface/src/Application_Setup.cpp").read_text(
    encoding="utf-8"
)
assert '"ios-world-evidence"' in main_source
assert '"OVERTE_IOS_WORLD_GATE navigation_requested"' in main_source
assert 'QStringLiteral("file:///~/serverless/tutorial.json")' in main_source
assert 'QStringLiteral("hifi://overte_hub")' in main_source
assert '"OVERTE_IOS_WORLD_GATE serverless_import_committed"' in application_source
assert 'QStringLiteral("serverless_tutorial")' in application_source
assert "suppressAudioForWorldEvidence" in application_setup_source
assert 'QStringLiteral("--ios-world-evidence")' in application_setup_source
assert "if (!suppressAudioForWorldEvidence)" in application_setup_source
assert "audioIO->startThread();" in application_setup_source
assert "OVERTE_IOS_WORLD_DIAGNOSTIC audio_suppressed=evidence_mode" in application_setup_source

print("PASS fail-closed iOS serverless/online world and screenshot evidence validators")
