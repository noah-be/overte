#!/usr/bin/env python3
"""Summarize an Overte Android Phone world-loading report."""
from __future__ import annotations

import csv
import re
import statistics
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return 0.0


def display_bytes(value: float) -> str:
    return f"{value / (1024 * 1024):.2f} MiB"


def relative_spread(values: list[float]) -> float:
    """Return population standard deviation as a percentage of the mean."""
    mean = statistics.fmean(values) if values else 0.0
    return statistics.pstdev(values) * 100.0 / mean if len(values) > 1 and mean else 0.0


def linear_slope_per_minute(rows: list[dict[str, str]], field: str) -> float:
    """Return an ordinary-least-squares slope using elapsed_ms as the clock."""
    points = [(number(row, "elapsed_ms") / 60000.0, number(row, field)) for row in rows]
    if len(points) < 2:
        return 0.0
    mean_x = statistics.fmean(point[0] for point in points)
    mean_y = statistics.fmean(point[1] for point in points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


def phase_rows(rows: list[dict[str, str]], start_seconds: int, end_seconds: int) -> list[dict[str, str]]:
    return [
        row for row in rows
        if start_seconds * 1000 <= number(row, "elapsed_ms") <= end_seconds * 1000
    ]


def elapsed_seconds(row: dict[str, str], start_epoch_ms: float) -> float:
    return max(0.0, (number(row, "sample_epoch_ms") - start_epoch_ms) / 1000.0)


def first_sustained_idle(rows: list[dict[str, str]]) -> dict[str, str] | None:
    """Return the first queue-idle status after which the queue stays idle."""
    candidate = None
    for row in reversed(rows):
        if number(row, "active_downloads") or number(row, "pending_downloads"):
            break
        candidate = row
    return candidate


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} REPORT_DIR", file=sys.stderr)
        return 2
    report = Path(sys.argv[1])
    runs_file = report / "runs.csv"
    if not runs_file.is_file():
        print(f"missing report file: {runs_file}", file=sys.stderr)
        return 2
    with runs_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("report contains no runs", file=sys.stderr)
        return 1
    print("Overte Android Phone world-loading performance")
    print(f"runs: {len(rows)}")
    for row in rows:
        print(
            f"run {row['run']}: CPU mean/max {number(row, 'mean_cpu_percent'):.1f}%/"
            f"{number(row, 'max_cpu_percent'):.1f}%, max PSS {number(row, 'max_pss_kb') / 1024:.1f} MiB, "
            f"network down/up {display_bytes(number(row, 'rx_delta_bytes'))}/"
            f"{display_bytes(number(row, 'tx_delta_bytes'))}, jank {number(row, 'janky_percent'):.1f}%, "
            f"thermal {int(number(row, 'max_thermal_status'))}"
        )
    print("medians:")
    fields = (
        ("CPU mean", "mean_cpu_percent", "%"),
        ("CPU max", "max_cpu_percent", "%"),
        ("PSS max", "max_pss_kb", " KiB"),
        ("download", "rx_delta_bytes", " bytes"),
        ("upload", "tx_delta_bytes", " bytes"),
        ("janky frames", "janky_percent", "%"),
    )
    for label, field, suffix in fields:
        values = [number(row, field) for row in rows]
        spread = f", relative spread {relative_spread(values):.1f}%" if len(values) > 1 else ""
        print(f"  {label}: {statistics.median(values):.2f}{suffix}{spread}")
    native_pattern = re.compile(
        r"present_fps=(?P<fps>[0-9.]+).*new_frame_fps=(?P<new>[0-9.]+).*"
        r"inter_present_p95_ms=(?P<p95>[0-9.]+).*inter_present_max_ms=(?P<maximum>[0-9.]+).*"
        r"gpu_texture_resident_mib=(?P<resident>[0-9.]+).*texture_resource_mib=(?P<resource>[0-9.]+)"
    )
    gpu_pattern = re.compile(r"render_gpu_ms=(?P<gpu>[0-9.]+).*render_batch_ms=(?P<batch>[0-9.]+)")
    native_windows: list[dict[str, float]] = []
    gpu_samples: list[dict[str, float]] = []
    for row in rows:
        logcat = report / f"run-{row['run']}" / "logcat.txt"
        if not logcat.is_file():
            continue
        for line in logcat.read_text(encoding="utf-8", errors="replace").splitlines():
            if match := native_pattern.search(line):
                native_windows.append({key: float(value) for key, value in match.groupdict().items()})
            if match := gpu_pattern.search(line):
                gpu_samples.append({key: float(value) for key, value in match.groupdict().items()})
    if native_windows:
        print("native Phone renderer:")
        print(f"  present FPS median: {statistics.median(item['fps'] for item in native_windows):.2f}")
        print(f"  new-frame FPS median: {statistics.median(item['new'] for item in native_windows):.2f}")
        print(f"  inter-present p95 median: {statistics.median(item['p95'] for item in native_windows):.2f} ms")
        print(f"  worst inter-present maximum: {max(item['maximum'] for item in native_windows):.2f} ms")
        print(f"  peak resident texture memory: {max(item['resident'] for item in native_windows):.2f} MiB")
        print(f"  peak resource texture memory: {max(item['resource'] for item in native_windows):.2f} MiB")
    if gpu_samples:
        print(f"  GPU frame time median/max: {statistics.median(item['gpu'] for item in gpu_samples):.2f}/{max(item['gpu'] for item in gpu_samples):.2f} ms")
        print(f"  batch time median/max: {statistics.median(item['batch'] for item in gpu_samples):.2f}/{max(item['batch'] for item in gpu_samples):.2f} ms")
    world_errors: list[str] = []
    measurement_errors: list[str] = []
    device_file = report / "device.csv"
    expected_place = ""
    expected_position: tuple[float, float, float] | None = None
    if device_file.is_file():
        with device_file.open(newline="", encoding="utf-8") as handle:
            device_rows = list(csv.DictReader(handle))
        if device_rows:
            device = device_rows[0]
            target = urlparse(device_rows[0].get("target", ""))
            expected_place = target.hostname or ""
            print(
                "measurement setup: "
                f"ADB={device.get('adb_transport', 'unknown')}, "
                f"brightness={device.get('fixed_brightness') or device.get('screen_brightness_start', 'unknown')}, "
                f"automatic brightness={'on' if device.get('screen_brightness_mode_start') == '1' else 'off'}, "
                f"Perfetto={'on' if device.get('perfetto') == '1' else 'off'}"
            )
            try:
                coordinates = target.path.lstrip("/").split("/", 1)[0].split(",")
                expected_position = tuple(float(value) for value in coordinates)  # type: ignore[assignment]
                if len(expected_position) != 3:
                    expected_position = None
            except ValueError:
                expected_position = None
            required_columns = {
                "epoch_ms", "elapsed_ms", "cpu_percent", "pss_kb", "rss_kb", "swap_pss_kb",
                "private_dirty_kb", "private_clean_kb", "rss_anon_kb", "rss_file_kb", "rss_shmem_kb",
                "vm_swap_kb", "rx_bytes", "tx_bytes", "thermal_status", "battery_level", "battery_status",
                "battery_current_uA", "battery_voltage_uV", "battery_charge_uAh", "cpu_temp_mC", "gpu_temp_mC",
                "battery_powered", "battery_ac_powered", "battery_usb_powered", "battery_wireless_powered",
                "battery_dock_powered", "battery_charging_state", "max_charging_current_uA", "max_charging_voltage_uV",
                "battery_temp_mC", "skin_temp_mC", "screen_brightness", "screen_brightness_mode",
                "display_brightness", "wifi_rssi_dbm", "wifi_link_speed_mbps", "wifi_tx_link_speed_mbps",
                "wifi_rx_link_speed_mbps", "wifi_frequency_mhz",
            }
            duration_ms = int(number(device, "duration_seconds") * 1000)
            for run_row in rows:
                run_id = run_row["run"]
                run_dir = report / f"run-{run_id}"
                samples_file = run_dir / "samples.csv"
                if not samples_file.is_file():
                    measurement_errors.append(f"run {run_id}: samples.csv missing")
                    continue
                with samples_file.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    samples = list(reader)
                    missing = required_columns - set(reader.fieldnames or ())
                if missing:
                    measurement_errors.append(f"run {run_id}: sample columns missing: {', '.join(sorted(missing))}")
                    continue
                if not samples:
                    measurement_errors.append(f"run {run_id}: no samples")
                    continue
                if duration_ms and number(samples[-1], "elapsed_ms") < duration_ms - 2500:
                    measurement_errors.append(f"run {run_id}: sample timeline ends too early")
                checks = {
                    "PSS": max(number(item, "pss_kb") for item in samples),
                    "RSS": max(number(item, "rss_kb") for item in samples),
                    "battery voltage": max(number(item, "battery_voltage_uV") for item in samples),
                    "CPU temperature": max(number(item, "cpu_temp_mC") for item in samples),
                    "GPU temperature": max(number(item, "gpu_temp_mC") for item in samples),
                    "battery temperature": max(number(item, "battery_temp_mC") for item in samples),
                    "skin temperature": max(number(item, "skin_temp_mC") for item in samples),
                    "display brightness": max(number(item, "display_brightness") for item in samples),
                    "Wi-Fi link speed": max(number(item, "wifi_link_speed_mbps") for item in samples),
                    "Wi-Fi frequency": max(number(item, "wifi_frequency_mhz") for item in samples),
                }
                for label, value in checks.items():
                    if value <= 0:
                        measurement_errors.append(f"run {run_id}: {label} unavailable")
                modes = {int(number(item, "screen_brightness_mode")) for item in samples}
                if not modes or not modes <= {0, 1}:
                    measurement_errors.append(f"run {run_id}: invalid automatic-brightness mode")
                if min(number(item, "wifi_rssi_dbm") for item in samples) >= 0:
                    measurement_errors.append(f"run {run_id}: Wi-Fi RSSI unavailable")
                expected_brightness = number(device, "fixed_brightness") or number(samples[0], "screen_brightness")
                if expected_brightness > 0 and any(
                    number(item, "screen_brightness") != expected_brightness for item in samples
                ):
                    measurement_errors.append(f"run {run_id}: fixed brightness drifted during measurement")
                if duration_ms >= 300000:
                    print(f"run {run_id} five-minute phases:")
                    for start_seconds in range(0, duration_ms // 1000, 300):
                        end_seconds = min(start_seconds + 300, duration_ms // 1000)
                        phase = phase_rows(samples, start_seconds, end_seconds)
                        if len(phase) < 2:
                            measurement_errors.append(
                                f"run {run_id}: phase {start_seconds//60}–{end_seconds//60} min has insufficient samples"
                            )
                            continue
                        pss_delta_mib = (number(phase[-1], "pss_kb") - number(phase[0], "pss_kb")) / 1024
                        rx_delta_mib = (number(phase[-1], "rx_bytes") - number(phase[0], "rx_bytes")) / 1048576
                        tx_delta_mib = (number(phase[-1], "tx_bytes") - number(phase[0], "tx_bytes")) / 1048576
                        print(
                            f"  {start_seconds//60}–{end_seconds//60} min: CPU mean "
                            f"{statistics.fmean(number(item, 'cpu_percent') for item in phase):.1f}%, "
                            f"PSS {pss_delta_mib:+.1f} MiB "
                            f"({linear_slope_per_minute(phase, 'pss_kb')/1024:+.2f} MiB/min), "
                            f"network down/up {rx_delta_mib:.2f}/{tx_delta_mib:.2f} MiB, "
                            f"CPU/GPU temp max "
                            f"{max(number(item, 'cpu_temp_mC') for item in phase)/1000:.1f}/"
                            f"{max(number(item, 'gpu_temp_mC') for item in phase)/1000:.1f} °C"
                        )
                logcat = run_dir / "logcat.txt"
                log_text = logcat.read_text(encoding="utf-8", errors="replace") if logcat.is_file() else ""
                if not log_text:
                    measurement_errors.append(f"run {run_id}: Logcat missing")
                if "OvertePhoneGraphics" not in log_text:
                    measurement_errors.append(f"run {run_id}: native renderer telemetry missing")
                if "swapBuffers() called without corresponding makeCurrent()" in log_text:
                    measurement_errors.append(f"run {run_id}: OpenGL context error in Logcat")
                if re.search(r"Failed to load .*\.exr.*Invalid Format", log_text, re.IGNORECASE):
                    measurement_errors.append(f"run {run_id}: OpenEXR texture decode failure in Logcat")
                if re.search(r"\bW Interface:\s*$", log_text, re.MULTILINE):
                    measurement_errors.append(f"run {run_id}: empty Interface warnings in Logcat")
                trace = run_dir / "trace.perfetto-trace"
                if device.get("perfetto") == "1" and (not trace.is_file() or trace.stat().st_size == 0):
                    measurement_errors.append(f"run {run_id}: Perfetto trace missing or empty")
                print(
                    f"run {run_id} sensors: brightness {min(number(item, 'screen_brightness') for item in samples):.0f}–"
                    f"{max(number(item, 'screen_brightness') for item in samples):.0f}, auto={sorted(modes)}, "
                    f"display {min(number(item, 'display_brightness') for item in samples):.6f}–"
                    f"{max(number(item, 'display_brightness') for item in samples):.6f}, "
                    f"CPU/GPU temp max {checks['CPU temperature']/1000:.1f}/{checks['GPU temperature']/1000:.1f} °C, "
                    f"Wi-Fi RSSI {min(number(item, 'wifi_rssi_dbm') for item in samples):.0f} dBm"
                )
                power_sources = [
                    label for label, field in (
                        ("AC", "battery_ac_powered"), ("USB", "battery_usb_powered"),
                        ("wireless", "battery_wireless_powered"), ("dock", "battery_dock_powered"),
                    ) if any(number(item, field) == 1 for item in samples)
                ]
                print(
                    f"run {run_id} charging: powered={'yes' if any(number(item, 'battery_powered') == 1 for item in samples) else 'no'}, "
                    f"sources={'+'.join(power_sources) if power_sources else 'none'}, "
                    f"states={sorted({int(number(item, 'battery_charging_state')) for item in samples})}, "
                    f"current {min(number(item, 'battery_current_uA') for item in samples)/1000:.0f}–"
                    f"{max(number(item, 'battery_current_uA') for item in samples)/1000:.0f} mA"
                )
                detail_file = run_dir / "memory-detail.csv"
                if not detail_file.is_file():
                    measurement_errors.append(f"run {run_id}: detailed memory attribution missing")
                else:
                    with detail_file.open(newline="", encoding="utf-8") as handle:
                        detail = list(csv.DictReader(handle))
                    if not detail:
                        measurement_errors.append(f"run {run_id}: detailed memory attribution empty")
                    else:
                        categories = (
                            ("Dalvik", "dalvik_pss_kb"), ("native allocator", "native_pss_kb"),
                            ("graphics", "graphics_pss_kb"), ("stacks", "stack_pss_kb"),
                            ("shared libraries", "shared_library_pss_kb"), ("code", "code_pss_kb"),
                            ("files", "file_pss_kb"), ("anonymous", "anonymous_pss_kb"),
                        )
                        deltas = [(label, (number(detail[-1], key) - number(detail[0], key)) / 1024) for label, key in categories]
                        dominant = max(deltas, key=lambda item: item[1])
                        print(
                            f"run {run_id} memory attribution: dominant growth {dominant[0]} {dominant[1]:+.1f} MiB; "
                            f"threads {number(detail[0], 'threads'):.0f}→{number(detail[-1], 'threads'):.0f}, "
                            f"FDs {number(detail[0], 'open_fds'):.0f}→{number(detail[-1], 'open_fds'):.0f}, "
                            f"disk cache {number(detail[0], 'cache_disk_kb')/1024:.1f}→"
                            f"{number(detail[-1], 'cache_disk_kb')/1024:.1f} MiB"
                        )
                script_file = run_dir / "script-memory.csv"
                if not script_file.is_file():
                    measurement_errors.append(f"run {run_id}: V8 script-memory telemetry missing")
                else:
                    with script_file.open(newline="", encoding="utf-8") as handle:
                        script_rows = list(csv.DictReader(handle))
                    if not script_rows:
                        measurement_errors.append(f"run {run_id}: V8 script-memory telemetry empty")
                    else:
                        scripts: dict[str, list[dict[str, str]]] = {}
                        for item in script_rows:
                            scripts.setdefault(unquote(item.get("script", "unknown")), []).append(item)
                        used_delta = sum(
                            number(items[-1], "used_heap_bytes") - number(items[0], "used_heap_bytes")
                            for items in scripts.values()
                        )
                        total_delta = sum(
                            number(items[-1], "total_heap_bytes") - number(items[0], "total_heap_bytes")
                            for items in scripts.values()
                        )
                        print(
                            f"run {run_id} V8: {len(scripts)} scripts, used heap delta "
                            f"{used_delta/1048576:+.2f} MiB, reserved heap delta {total_delta/1048576:+.2f} MiB"
                        )
    if device_file.is_file():
        print("client-reported world:")
        for row in rows:
            world_file = report / f"run-{row['run']}" / "world-status.csv"
            statuses: list[dict[str, str]] = []
            if world_file.is_file():
                with world_file.open(newline="", encoding="utf-8") as handle:
                    statuses = list(csv.DictReader(handle))
            if not statuses:
                world_errors.append(row["run"])
                print(f"  run {row['run']}: unavailable")
                continue
            final_world = statuses[-1]
            final_place = final_world.get("place", "")
            position = tuple(number(final_world, key) for key in ("x", "y", "z"))
            start_epoch_ms = number(row, "start_epoch_ms") or number(statuses[0], "sample_epoch_ms")
            connected_status = next((item for item in statuses if item.get("connected") == "1"), None)
            correct_spawn_status = None
            if expected_position is not None:
                correct_spawn_status = next((
                    item for item in statuses
                    if item.get("connected") == "1" and all(
                        abs(number(item, key) - expected) <= 5.0
                        for key, expected in zip(("x", "y", "z"), expected_position)
                    )
                ), None)
            first_idle_status = next((
                item for item in statuses
                if number(item, "active_downloads") == 0 and number(item, "pending_downloads") == 0
            ), None)
            sustained_idle_status = first_sustained_idle(statuses)
            print(
                f"  run {row['run']}: connected={final_world.get('connected', '0')} "
                f"place={final_place or 'unknown'} domain={final_world.get('domain_id', '') or 'unknown'} "
                f"position={position[0]:.3f},{position[1]:.3f},{position[2]:.3f} "
                f"entity_server={final_world.get('entity_server', 'unknown')} "
                f"entities={final_world.get('entity_count', 'unknown')} "
                f"asset_server={final_world.get('asset_server', 'unknown')} "
                f"downloads={final_world.get('active_downloads', 'unknown')} active/"
                f"{final_world.get('pending_downloads', 'unknown')} pending"
            )
            milestones = (
                ("connected", connected_status), ("correct spawn", correct_spawn_status),
                ("first queue idle", first_idle_status), ("sustained queue idle", sustained_idle_status),
            )
            print(
                "    milestones: " + ", ".join(
                    f"{label}={elapsed_seconds(item, start_epoch_ms):.1f}s" if item else f"{label}=unreached"
                    for label, item in milestones
                )
            )
            wrong_place = expected_place and not expected_place.replace("_", "-").lower() == final_place.replace("_", "-").lower()
            wrong_position = expected_position is not None and any(
                abs(actual - expected) > 5.0 for actual, expected in zip(position, expected_position)
            )
            downloads_incomplete = number(final_world, "active_downloads") > 0 or number(final_world, "pending_downloads") > 0
            if final_world.get("connected") != "1" or wrong_place or wrong_position or downloads_incomplete:
                world_errors.append(row["run"])
    unstable = [row["run"] for row in rows if row.get("process_stable") != "1"]
    connection_errors = [row["run"] for row in rows if row.get("connection_error_dialog") == "1"]
    screenshot_errors = [row["run"] for row in rows if row.get("screenshot_valid") == "0"]
    if unstable:
        print(f"warning: process restarted during runs {', '.join(unstable)}")
    if connection_errors:
        print(f"error: connection failure dialog during runs {', '.join(connection_errors)}")
    if screenshot_errors:
        print(f"error: missing, invalid, or black final screenshot during runs {', '.join(screenshot_errors)}")
    if world_errors:
        print(f"error: missing or unexpected final client world during runs {', '.join(world_errors)}")
    for error in measurement_errors:
        print(f"error: {error}")
    if unstable or connection_errors or screenshot_errors or world_errors or measurement_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
