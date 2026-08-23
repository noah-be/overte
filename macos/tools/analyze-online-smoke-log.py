#!/usr/bin/env python3
"""Convert a macOS online-smoke log into bounded structured diagnostics."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re


TIMESTAMP = re.compile(r"\[(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})\]")
GATE = re.compile(r"OVERTE_MACOS_ENTITY_GATE ([a-z0-9_]+)")
PROGRESS = re.compile(
    r"online_progress entities=(\d+) renderables=(\d+) models=(\d+) "
    r"loaded_models=(\d+) presents=([0-9.]+) queues=(\{.*\})"
)
NODE = re.compile(
    r'(Added|Removing silent node|Killed) "([^"]+)".*?\{([0-9a-f-]+)\}.*?'
    r'"UDP ""([^" ]+)":(\d+)'
)
GL_DRAW = re.compile(r"OVERTE_MACOS_GL_(?:ARRAY_)?DRAW (begin|end)(?: gl_program=\s*(\d+))?")
APPLICATION_TICK_WATCHDOG = re.compile(
    r"OVERTE_APPLICATION_TICK_WATCHDOG "
    r"(presentation_stalled|presentation_resumed)(?: stall_ms=\s*(\d+))?"
)
LOOKUP_RETRY = re.compile(r"Retrying transient place lookup.*?in (\d+) ms, retry (\d+) of (\d+)")
API_ERROR = re.compile(r"AddressManager API error - ([^-]+) -")
DOMAIN_TARGET = re.compile(
    r'Possible domain change required to connect to "(\d+\.\d+\.\d+\.\d+)" on (\d+)'
)
REPEATED = re.compile(r"\[Previous message was repeated (\d+) times\]")
URL_HOST = re.compile(r"https?://([^/\s\"]+)")
UDP_PACKET = re.compile(
    r"IP ((?:\d+\.\d+\.\d+\.\d+)|local)\.(\d+) > "
    r"((?:\d+\.\d+\.\d+\.\d+)|local)\.(\d+):.*?length (\d+)"
)

GATE_ORDER = (
    "domain_list_connected",
    "entity_server_active",
    "entity_query_sent",
    "entity_data_received",
    "entity_tree_nonempty",
    "render_handoff",
)
MILESTONE_PATTERNS = {
    "application_init_complete": "init() complete.",
    "startup_complete": "Startup time:",
    "test_script_started": "Script Engine starting:online-smoke.js",
    "domain_change_requested": "Possible domain change required",
    "domain_connect_request": "Sending connect request",
    "domain_settings_requested": "Requesting settings from domain server",
}


def timestamp_seconds(line: str) -> int | None:
    match = TIMESTAMP.search(line)
    if not match:
        return None
    month, day, hour, minute, second = map(int, match.groups())
    return int((datetime(2000, month, day, hour, minute, second) - datetime(2000, 1, 1)).total_seconds())


def classify_issue(
    gates: dict[str, dict[str, object]], outcome: str | None, maximum_entities: int,
    domain_target: dict[str, object] | None, udp: dict[str, object],
) -> str:
    if outcome == "passed":
        return "none"
    if "domain_list_connected" not in gates:
        if domain_target:
            if udp.get("available"):
                domain_packets = dict(udp.get("nodes", {})).get("Domain Server", {})
                outbound = int(domain_packets.get("outbound_packets", 0))
                inbound = int(domain_packets.get("inbound_packets", 0))
                if outbound <= 0:
                    return "domain_connect_not_sent"
                if inbound <= 0:
                    return "domain_server_unreachable"
                return "domain_handshake_or_event_thread"
            return "domain_transport_or_event_thread"
        return "startup_directory_or_event_thread"
    if "entity_server_active" not in gates:
        return "domain_assignment"
    if "entity_query_sent" not in gates:
        return "entity_query_scheduler"
    if "entity_data_received" not in gates:
        return "entity_stream_or_server"
    if maximum_entities <= 0:
        return "entity_decode_or_tree"
    return "asset_render_or_snapshot"


def analyze(
    log_path: Path, process_path: Path | None, udp_headers_path: Path | None = None
) -> dict[str, object]:
    raw = log_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    first_timestamp = next((timestamp_seconds(line) for line in lines if timestamp_seconds(line) is not None), None)
    gates: dict[str, dict[str, object]] = {}
    gate_events: dict[str, list[dict[str, object]]] = {}
    gate_counts: Counter[str] = Counter()
    node_counts: Counter[str] = Counter()
    node_events: list[dict[str, object]] = []
    node_endpoints: dict[tuple[str, int], str] = {}
    progress: list[dict[str, object]] = []
    warning_counts: Counter[str] = Counter()
    resource_hosts: Counter[str] = Counter()
    milestones: dict[str, dict[str, object]] = {}
    lookup_retries: list[dict[str, object]] = []
    api_errors: Counter[str] = Counter()
    coalesced_lookups = 0
    domain_target: dict[str, object] | None = None
    repeated_messages = 0
    gl_error_counts: Counter[str] = Counter()
    draw_stack: dict[str, list[int]] = {}
    draw_durations: list[int] = []
    tick_watchdog_counts: Counter[str] = Counter()
    tick_watchdog_events: list[dict[str, object]] = []
    tick_watchdog_stall_ms: list[int] = []
    outcome: str | None = None
    outcome_detail: str | None = None

    def offset(value: int | None) -> int | None:
        if value is None or first_timestamp is None:
            return None
        delta = value - first_timestamp
        return delta if delta >= 0 else delta + 366 * 24 * 3600

    for line_number, line in enumerate(lines, 1):
        absolute = timestamp_seconds(line)
        elapsed = offset(absolute)
        gate_match = GATE.search(line)
        if gate_match:
            name = gate_match.group(1)
            gate_counts[name] += 1
            gate_events.setdefault(name, []).append(
                {"elapsed_seconds": elapsed, "line": line_number}
            )
        for name, pattern in MILESTONE_PATTERNS.items():
            if pattern in line:
                milestones.setdefault(name, {"elapsed_seconds": elapsed, "line": line_number})
        retry_match = LOOKUP_RETRY.search(line)
        if retry_match and len(lookup_retries) < 16:
            delay_ms, retry, maximum = map(int, retry_match.groups())
            lookup_retries.append({
                "elapsed_seconds": elapsed,
                "delay_ms": delay_ms,
                "retry": retry,
                "maximum": maximum,
            })
        api_error_match = API_ERROR.search(line)
        if api_error_match:
            api_errors[api_error_match.group(1).strip()] += 1
        if "Coalescing duplicate active place lookup" in line:
            coalesced_lookups += 1
        domain_target_match = DOMAIN_TARGET.search(line)
        if domain_target_match and domain_target is None:
            host, port = domain_target_match.groups()
            domain_target = {
                "host": host,
                "port": int(port),
                "elapsed_seconds": elapsed,
                "line": line_number,
            }
            node_endpoints[(host, int(port))] = "Domain Server"
        repeated_match = REPEATED.search(line)
        if repeated_match:
            repeated_messages += int(repeated_match.group(1))
        if "ERROR " in line:
            gl_error_match = re.search(r"ERROR ([0-9]+) in ([A-Za-z0-9_]+)", line)
            if gl_error_match:
                gl_error_counts[f"{gl_error_match.group(1)}:{gl_error_match.group(2)}"] += 1
        for host in URL_HOST.findall(line):
            resource_hosts[host.lower()] += 1
        progress_match = PROGRESS.search(line)
        if progress_match:
            try:
                queues = json.loads(progress_match.group(6))
            except json.JSONDecodeError:
                queues = {"parse_error": True}
            progress.append({
                "elapsed_seconds": elapsed,
                "entities": int(progress_match.group(1)),
                "renderables": int(progress_match.group(2)),
                "models": int(progress_match.group(3)),
                "loaded_models": int(progress_match.group(4)),
                "presents": float(progress_match.group(5)),
                "queues": queues,
            })
        node_match = NODE.search(line)
        if node_match:
            action, node_type, node_id, host, port = node_match.groups()
            key = action.lower().replace(" ", "_")
            node_counts[f"{key}:{node_type}"] += 1
            if action == "Added":
                node_endpoints[(host, int(port))] = node_type
            if len(node_events) < 256:
                node_events.append({
                    "action": key,
                    "type": node_type,
                    "id": node_id,
                    "host": host,
                    "port": int(port),
                    "elapsed_seconds": elapsed,
                })
        draw_match = GL_DRAW.search(line)
        if draw_match and elapsed is not None:
            action, program = draw_match.groups()
            program = program or "unknown"
            if action == "begin":
                draw_stack.setdefault(program, []).append(elapsed)
            elif draw_stack.get(program):
                draw_durations.append(max(0, elapsed - draw_stack[program].pop()))
        tick_watchdog_match = APPLICATION_TICK_WATCHDOG.search(line)
        if tick_watchdog_match:
            action, stall_ms = tick_watchdog_match.groups()
            tick_watchdog_counts[action] += 1
            event: dict[str, object] = {
                "action": action,
                "elapsed_seconds": elapsed,
                "line": line_number,
            }
            if stall_ms is not None:
                event["stall_ms"] = int(stall_ms)
                tick_watchdog_stall_ms.append(int(stall_ms))
            if len(tick_watchdog_events) < 256:
                tick_watchdog_events.append(event)
        if "OVERTE_MACOS_SMOKE passed" in line:
            outcome, outcome_detail = "passed", line.split("OVERTE_MACOS_SMOKE passed", 1)[1].strip()
        elif "OVERTE_MACOS_SMOKE failed" in line:
            outcome, outcome_detail = "failed", line.split("OVERTE_MACOS_SMOKE failed", 1)[1].strip()
        for level in ("CRITICAL", "WARNING"):
            if f"[{level}]" in line:
                category_match = re.search(rf"\[{level}\] \[([^]]*)\]", line)
                category = category_match.group(1) if category_match else "unknown"
                warning_counts[f"{level.lower()}:{category}"] += 1

    previous_elapsed = -1
    for name in GATE_ORDER:
        candidates = [
            event for event in gate_events.get(name, [])
            if isinstance(event["elapsed_seconds"], int) and event["elapsed_seconds"] >= previous_elapsed
        ]
        if not candidates:
            break
        gates[name] = candidates[0]
        previous_elapsed = int(candidates[0]["elapsed_seconds"])

    progress_summary: dict[str, object] = {"samples": len(progress)}
    if progress:
        present_values = [item["presents"] for item in progress]
        elapsed_values = [item["elapsed_seconds"] for item in progress if item["elapsed_seconds"] is not None]
        progress_summary.update({
            "first": progress[0],
            "last": progress[-1],
            "max_entities": max(item["entities"] for item in progress),
            "max_loaded_models": max(item["loaded_models"] for item in progress),
            "present_delta": max(present_values) - min(present_values),
            "max_sample_gap_seconds": max(
                (later - earlier for earlier, later in zip(elapsed_values, elapsed_values[1:])),
                default=0,
            ),
        })

    transitions: dict[str, int | None] = {}
    for previous, current in zip(GATE_ORDER, GATE_ORDER[1:]):
        if previous in gates and current in gates:
            earlier = gates[previous]["elapsed_seconds"]
            later = gates[current]["elapsed_seconds"]
            transitions[f"{previous}_to_{current}_seconds"] = (
                later - earlier if isinstance(earlier, int) and isinstance(later, int) else None
            )

    process = None
    if process_path and process_path.is_file():
        process = json.loads(process_path.read_text(encoding="utf-8"))
    udp_summary: dict[str, object] = {"available": False}
    if udp_headers_path and udp_headers_path.is_file():
        udp_raw = udp_headers_path.read_bytes()
        udp_lines = udp_raw.decode("utf-8", errors="replace").splitlines()
        endpoint_counts: dict[str, Counter[str]] = {
            node_type: Counter() for node_type in set(node_endpoints.values())
        }
        for line in udp_lines:
            packet_match = UDP_PACKET.search(line)
            if not packet_match:
                continue
            source_host, source_port, destination_host, destination_port, length = packet_match.groups()
            source = (source_host, int(source_port))
            destination = (destination_host, int(destination_port))
            if source in node_endpoints:
                counter = endpoint_counts[node_endpoints[source]]
                counter["inbound_packets"] += 1
                counter["inbound_bytes"] += int(length)
            if destination in node_endpoints:
                counter = endpoint_counts[node_endpoints[destination]]
                counter["outbound_packets"] += 1
                counter["outbound_bytes"] += int(length)
        udp_summary = {
            "available": True,
            "sha256": hashlib.sha256(udp_raw).hexdigest(),
            "bytes": len(udp_raw),
            "lines": len(udp_lines),
            "nodes": {name: dict(counts) for name, counts in sorted(endpoint_counts.items())},
        }
    maximum_entities = int(progress_summary.get("max_entities", 0))
    return {
        "schema_version": 1,
        "log": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "lines": len(lines),
        },
        "process": process,
        "outcome": outcome,
        "outcome_detail": outcome_detail,
        "primary_bottleneck": classify_issue(
            gates, outcome, maximum_entities, domain_target, udp_summary
        ),
        "gates": gates,
        "gate_counts": dict(sorted(gate_counts.items())),
        "pre_online_gate_counts": {
            name: gate_counts[name] - (1 if name in gates else 0)
            for name in GATE_ORDER if gate_counts[name] - (1 if name in gates else 0) > 0
        },
        "gate_transitions": transitions,
        "milestones": milestones,
        "directory": {
            "api_errors": dict(sorted(api_errors.items())),
            "retries": lookup_retries,
            "coalesced_active_lookups": coalesced_lookups,
        },
        "domain_target": domain_target,
        "progress": progress_summary,
        "nodes": {
            "counts": dict(sorted(node_counts.items())),
            "events": node_events,
        },
        "udp": udp_summary,
        "graphics": {
            "completed_draws": len(draw_durations),
            "incomplete_draws": sum(len(values) for values in draw_stack.values()),
            "maximum_draw_seconds": max(draw_durations, default=0),
            "total_draw_seconds": sum(draw_durations),
            "errors": dict(sorted(gl_error_counts.items())),
            "application_tick_watchdog": {
                "counts": dict(sorted(tick_watchdog_counts.items())),
                "events": tick_watchdog_events,
                "maximum_reported_stall_ms": max(tick_watchdog_stall_ms, default=0),
            },
        },
        "resource_host_counts": dict(resource_hosts.most_common(32)),
        "suppressed_repeated_messages": repeated_messages,
        "diagnostic_counts": dict(sorted(warning_counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--process", type=Path)
    parser.add_argument("--udp-headers", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if not args.log.is_file():
        parser.error("online log does not exist")
    payload = analyze(args.log, args.process, args.udp_headers)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.result, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
