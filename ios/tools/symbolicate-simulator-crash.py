#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Symbolicate the app frames in an Apple Simulator .ips crash report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


MAX_REPORT_BYTES = 4 * 1024 * 1024
UUID_RE = re.compile(r"\b([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\b")


def die(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def load_crash(path: Path) -> dict:
    size = path.stat().st_size
    if size <= 0 or size > MAX_REPORT_BYTES:
        die("crash report size is outside the accepted range")
    text = path.read_text(encoding="utf-8", errors="strict")
    decoder = json.JSONDecoder()
    reports: list[dict] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("{", cursor)
        if start < 0:
            break
        try:
            value, consumed = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        cursor = start + consumed
        if isinstance(value, dict) and "threads" in value and "usedImages" in value:
            reports.append(value)
    if len(reports) != 1:
        die("expected exactly one structured simulator crash report")
    return reports[0]


def run_checked(arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if completed.returncode != 0:
        die(f"symbolication command failed with status {completed.returncode}")
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("crash_report", type=Path)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if not args.crash_report.is_file():
        die("crash report does not exist")
    if not args.binary.is_file():
        die("application binary does not exist")
    if args.output.exists():
        die("output path already exists")

    report = load_crash(args.crash_report)
    images = report.get("usedImages")
    threads = report.get("threads")
    faulting_thread = report.get("faultingThread")
    if not isinstance(images, list) or not isinstance(threads, list):
        die("crash report image or thread inventory is invalid")
    if not isinstance(faulting_thread, int) or not 0 <= faulting_thread < len(threads):
        die("faulting thread index is invalid")

    matches = [
        (index, image)
        for index, image in enumerate(images)
        if isinstance(image, dict)
        and image.get("name") == args.binary.name
        and image.get("CFBundleIdentifier") == "org.overte.interface.dev"
    ]
    if len(matches) != 1:
        die("expected exactly one Overte application image")
    image_index, image = matches[0]
    base = image.get("base")
    image_uuid = str(image.get("uuid", "")).lower()
    arch = str(image.get("arch", ""))
    if not isinstance(base, int) or base <= 0 or arch != "arm64" or UUID_RE.fullmatch(image_uuid) is None:
        die("Overte image metadata is invalid")

    uuid_output = run_checked(["xcrun", "dwarfdump", "--uuid", str(args.binary)])
    uuids = [match.group(1).lower() for match in UUID_RE.finditer(uuid_output)]
    if uuids != [image_uuid]:
        die("application binary UUID does not match the crash report")

    thread = threads[faulting_thread]
    frames = thread.get("frames") if isinstance(thread, dict) else None
    if not isinstance(frames, list) or len(frames) > 256:
        die("faulting thread frame inventory is invalid")
    app_frames: list[dict[str, int]] = []
    for frame_index, frame in enumerate(frames):
        if not isinstance(frame, dict) or frame.get("imageIndex") != image_index:
            continue
        offset = frame.get("imageOffset")
        if not isinstance(offset, int) or offset < 0:
            die("application frame offset is invalid")
        app_frames.append(
            {"frameIndex": frame_index, "imageOffset": offset, "address": base + offset}
        )
    if not app_frames:
        die("faulting thread contains no Overte frames")

    address_arguments = [f"0x{frame['address']:x}" for frame in app_frames]
    symbols = run_checked(
        [
            "xcrun",
            "atos",
            "-arch",
            arch,
            "-o",
            str(args.binary),
            "-l",
            f"0x{base:x}",
            *address_arguments,
        ]
    ).splitlines()
    if len(symbols) != len(app_frames):
        die("atos returned an unexpected number of symbols")
    for frame, symbol in zip(app_frames, symbols, strict=True):
        frame["address"] = f"0x{frame['address']:x}"
        frame["imageOffset"] = f"0x{frame['imageOffset']:x}"
        frame["symbol"] = symbol.strip()

    exception = report.get("exception") if isinstance(report.get("exception"), dict) else {}
    result = {
        "schemaVersion": 1,
        "exceptionType": exception.get("type"),
        "signal": exception.get("signal"),
        "subtype": exception.get("subtype"),
        "faultingThread": faulting_thread,
        "appImage": {"arch": arch, "base": f"0x{base:x}", "uuid": image_uuid},
        "frames": app_frames,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"symbolicated {len(app_frames)} Overte crash frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
