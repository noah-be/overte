#!/usr/bin/env python3
"""Best-effort external diagnostics for an unmodified macOS Overte runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import re


STOP = False
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
NODE_HOST = re.compile(r'Added "[^"]+".*?"UDP ""(\d+\.\d+\.\d+\.\d+)":\d+')
PRIVATE_IPV4 = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|127(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
MAC_ADDRESS = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
ANY_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def stop_handler(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def run_text(command: list[str], timeout: float = 10.0, limit: int = 512 * 1024) -> dict[str, object]:
    try:
        result = subprocess.run(command, text=True, errors="replace", stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return {"exit_code": result.returncode, "output": result.stdout[:limit]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"exit_code": None, "error": type(error).__name__}


def sanitize_network_text(value: str) -> str:
    value = MAC_ADDRESS.sub("<redacted-mac>", value)
    value = PRIVATE_IPV4.sub("<private-ip>", value)
    value = re.sub(r"\b(?:fe80:[0-9a-fA-F:%]+|::1)\b", "<local-ipv6>", value)
    return value


def sanitize_udp_trace(path: Path, remote_host: str | None) -> None:
    if not path.is_file():
        return
    value = path.read_text(encoding="utf-8", errors="replace")
    value = ANY_IPV4.sub(
        lambda match: match.group(0) if match.group(0) == remote_host else "local",
        value,
    )
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)


def overte_pids() -> list[int]:
    result = run_text(["pgrep", "-x", "Overte"], timeout=2, limit=4096)
    values = []
    for line in str(result.get("output", "")).splitlines():
        if line.strip().isdigit():
            values.append(int(line.strip()))
    return values


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


def capture_sample(pid: int, destination: Path) -> dict[str, object]:
    sample = shutil.which("sample")
    if not sample:
        return {"pid": pid, "succeeded": False, "reason": "sample_unavailable"}
    try:
        result = subprocess.run([sample, str(pid), "2", "1", "-file", str(destination)],
                                timeout=10, check=False)
        return {"pid": pid, "succeeded": result.returncode == 0 and destination.is_file(),
                "exit_code": result.returncode, "name": destination.name}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"pid": pid, "succeeded": False, "reason": type(error).__name__}


def stop_capture(process: subprocess.Popen[str], sudo: str | None) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if sudo:
        run_text([sudo, "-n", "kill", "-TERM", f"-{process.pid}"], timeout=3)
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            pass
    try:
        process.kill()
        process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def capture_interface(tcpdump: str) -> str | None:
    result = run_text([tcpdump, "-D"], timeout=5, limit=64 * 1024)
    interfaces = []
    for line in str(result.get("output", "")).splitlines():
        numbered = line.split(".", 1)
        if len(numbered) == 2 and numbered[0].isdigit():
            interfaces.append(numbered[1].split()[0])
    for preferred in ("pktap", "any", "en0"):
        if preferred in interfaces:
            return preferred
    return interfaces[0] if interfaces else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-runtime", type=float, required=True)
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    if args.max_runtime <= 0 or args.interval <= 0:
        parser.error("runtime and interval must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(args.output_dir, 0o700)
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    default_route = run_text(["route", "-n", "get", "default"])
    default_interface = None
    for line in str(default_route.get("output", "")).splitlines():
        if line.strip().startswith("interface:"):
            default_interface = line.split(":", 1)[1].strip()
    interfaces = run_text(["ifconfig", "-l"])
    dns = run_text(["scutil", "--dns"])
    snapshots = {
        "sw_vers": run_text(["sw_vers"]),
        "default_interface": default_interface,
        "interface_names": str(interfaces.get("output", "")).split(),
        "dns_resolver_count": str(dns.get("output", "")).count("resolver #"),
    }
    atomic_json(args.output_dir / "network-environment.json", snapshots)

    tcpdump_process = None
    tcpdump_stream = None
    tcpdump_error = None
    tcpdump = shutil.which("tcpdump")
    sudo = shutil.which("sudo")
    selected_interface = capture_interface(tcpdump) if tcpdump else None
    capture_ready = bool(
        tcpdump and sudo and selected_interface and
        run_text([sudo, "-n", "true"], timeout=3).get("exit_code") == 0
    )
    tcpdump_started = False
    remote_host = None

    started = time.monotonic()
    observations_path = args.output_dir / "runtime-observations.jsonl"
    samples: list[dict[str, object]] = []
    seen_query_at = None
    seen_server_at = None
    last_progress_change = started
    last_progress_count = 0
    sampled_reasons: set[str] = set()
    with observations_path.open("w", encoding="utf-8") as observations:
        os.chmod(observations_path, 0o600)
        while not STOP and time.monotonic() - started < args.max_runtime:
            now = time.monotonic()
            pids = overte_pids()
            log_text = ""
            try:
                if args.log.is_file():
                    log_text = args.log.read_text(encoding="utf-8", errors="replace")[-2 * 1024 * 1024:]
            except OSError:
                pass
            if remote_host is None:
                host_match = NODE_HOST.search(log_text)
                if host_match:
                    remote_host = host_match.group(1)
            if capture_ready and remote_host and not tcpdump_started:
                tcpdump_started = True
                tcpdump_stream = (args.output_dir / "udp-headers.log").open(
                    "w", encoding="utf-8", errors="replace"
                )
                try:
                    tcpdump_process = subprocess.Popen(
                        [sudo, "-n", tcpdump, "-n", "-tttt", "-q", "-l", "-i",
                         selected_interface, "udp", "and", "host", remote_host],
                        stdout=tcpdump_stream, stderr=subprocess.STDOUT, text=True,
                        start_new_session=True,
                    )
                except OSError as error:
                    tcpdump_error = type(error).__name__
            progress_count = log_text.count("OVERTE_MACOS_SMOKE online_progress")
            if progress_count != last_progress_count:
                last_progress_count = progress_count
                last_progress_change = now
            if seen_server_at is None and "OVERTE_MACOS_ENTITY_GATE entity_server_active" in log_text:
                seen_server_at = now
            if seen_query_at is None and "OVERTE_MACOS_ENTITY_GATE entity_query_sent" in log_text:
                seen_query_at = now

            ps = run_text(["ps", "-o", "pid=,ppid=,state=,%cpu=,%mem=,rss=,vsz=,etime=", "-p",
                           ",".join(map(str, pids))], timeout=3) if pids else {"exit_code": 0, "output": ""}
            sockets = {}
            for pid in pids:
                socket_result = run_text(["lsof", "-nP", "-a", "-p", str(pid), "-iUDP"], timeout=5)
                if "output" in socket_result:
                    socket_result["output"] = sanitize_network_text(str(socket_result["output"]))
                sockets[str(pid)] = socket_result
            row = {
                "elapsed_seconds": round(now - started, 3),
                "pids": pids,
                "processes": ps,
                "udp_sockets": sockets,
                "memory": run_text(["vm_stat"], timeout=3, limit=64 * 1024),
            }
            observations.write(json.dumps(row, sort_keys=True) + "\n")
            observations.flush()

            reasons = []
            if seen_server_at is not None and seen_query_at is None and now - seen_server_at >= 60:
                reasons.append("entity_server_without_query")
            if (seen_query_at is not None and "OVERTE_MACOS_ENTITY_GATE entity_data_received" not in log_text
                    and now - seen_query_at >= 60):
                reasons.append("query_without_entity_data")
            if progress_count > 0 and now - last_progress_change >= 120:
                reasons.append("online_progress_stalled")
            for reason in reasons:
                if reason not in sampled_reasons and pids and len(samples) < 4:
                    sampled_reasons.add(reason)
                    destination = args.output_dir / f"sample-{len(samples) + 1}-{reason}.txt"
                    sample_result = capture_sample(pids[-1], destination)
                    sample_result.update({"reason": reason, "elapsed_seconds": round(now - started, 3)})
                    samples.append(sample_result)

            if (tcpdump_process and (tcpdump_process.poll() is not None or
                    (args.output_dir / "udp-headers.log").stat().st_size >= MAX_CAPTURE_BYTES)):
                if tcpdump_process.poll() is None:
                    stop_capture(tcpdump_process, sudo)
                tcpdump_process = None
            deadline = time.monotonic() + args.interval
            while not STOP and time.monotonic() < deadline:
                time.sleep(min(0.25, deadline - time.monotonic()))

    if tcpdump_process and tcpdump_process.poll() is None:
        stop_capture(tcpdump_process, sudo)
    if tcpdump_stream:
        tcpdump_stream.close()
    sanitize_udp_trace(args.output_dir / "udp-headers.log", remote_host)
    atomic_json(args.output_dir / "observer-result.json", {
        "schema_version": 1,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "samples": samples,
        "sampled_reasons": sorted(sampled_reasons),
        "tcpdump_attempted": capture_ready,
        "tcpdump_started": tcpdump_started,
        "tcpdump_interface": selected_interface,
        "remote_host": remote_host,
        "tcpdump_error": tcpdump_error,
        "udp_header_bytes": (
            (args.output_dir / "udp-headers.log").stat().st_size
            if (args.output_dir / "udp-headers.log").is_file() else 0
        ),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
