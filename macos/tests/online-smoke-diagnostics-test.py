#!/usr/bin/env python3
"""Exercise build-free online runtime diagnostics."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
ANALYZER = ROOT / "macos/tools/analyze-online-smoke-log.py"
OBSERVER = ROOT / "macos/tools/observe-online-runtime.py"
spec = importlib.util.spec_from_file_location("online_diagnostics", ANALYZER)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
observer_spec = importlib.util.spec_from_file_location("online_observer", OBSERVER)
observer_module = importlib.util.module_from_spec(observer_spec)
assert observer_spec.loader is not None
observer_spec.loader.exec_module(observer_module)

observer_source = OBSERVER.read_text(encoding="utf-8")
for observer_contract in (
    "discover_remote_target(log_text)",
    '"domain_target_without_node"',
    "progress_signature != last_progress_signature",
    '"remote_host_source": remote_host_source',
    '"remote_port": remote_port',
):
    assert observer_contract in observer_source
assert "progress_count != last_progress_count" not in observer_source


with tempfile.TemporaryDirectory() as temporary_name:
    temporary = Path(temporary_name)
    log = temporary / "online.log"
    process = temporary / "online-process.json"
    result = temporary / "timeline.json"
    udp_headers = temporary / "udp-headers.log"
    log.write_text(
        "\n".join((
            '[08/23 10:00:00] [INFO] [overte.scriptengine] [online-smoke.js] Script Engine starting:online-smoke.js',
            '[08/23 10:00:01] [INFO] [default] OVERTE_MACOS_GL_DRAW begin gl_program= 37',
            '[08/23 10:00:02] [WARNING] [hifi.interface] OVERTE_APPLICATION_TICK_WATCHDOG presentation_stalled stall_ms= 301',
            '[08/23 10:02:01] [INFO] [default] OVERTE_MACOS_GL_DRAW end gl_program= 37',
            '[08/23 10:02:01] [INFO] [hifi.interface] OVERTE_APPLICATION_TICK_WATCHDOG presentation_resumed',
            '[08/23 10:02:01] [DEBUG] [hifi.networking] Possible domain change required to connect to "178.105.253.182" on 40114',
            '[08/23 10:02:02] [INFO] [default] OVERTE_MACOS_ENTITY_GATE domain_list_connected domain= x session= y',
            '[08/23 10:02:03] [DEBUG] [hifi.networking] Added "Entity Server" (o) {a0b4d799-1768-446d-b540-9824e8a42b8f}(1) "UDP ""178.105.253.182":37492',
            '[08/23 10:02:04] [INFO] [default] OVERTE_MACOS_ENTITY_GATE entity_server_active node= x',
            '[08/23 10:02:05] [INFO] [default] OVERTE_MACOS_ENTITY_GATE entity_query_sent node= x bytes= 51',
            '[08/23 10:02:06] [DEBUG] [overte.scriptengine] [online-smoke.js] OVERTE_MACOS_SMOKE online_progress entities=0 renderables=0 models=0 loaded_models=0 presents=10 queues={"downloads":0,"downloads_pending":0,"processing":0,"processing_pending":0,"texture_pending_mb":0}',
            '[08/23 10:12:05] [DEBUG] [overte.scriptengine] [online-smoke.js] OVERTE_MACOS_SMOKE failed entity_stream_stalled',
        )) + "\n",
        encoding="utf-8",
    )
    process.write_text(json.dumps({"elapsed_seconds": 725, "exit_code": 0}) + "\n", encoding="utf-8")
    udp_headers.write_text(
        "2026-08-23 10:02:05.000 IP local.50000 > 178.105.253.182.37492: UDP, length 51\n"
        "2026-08-23 10:02:05.100 IP 178.105.253.182.37492 > local.50000: UDP, length 12\n",
        encoding="utf-8",
    )
    unsanitized = temporary / "unsanitized-udp.log"
    unsanitized.write_text(
        "IP 203.0.113.9.50000 > 178.105.253.182.37492: UDP, length 51\n",
        encoding="utf-8",
    )
    observer_module.sanitize_udp_trace(unsanitized, "178.105.253.182")
    assert "203.0.113.9" not in unsanitized.read_text(encoding="utf-8")
    assert "IP local.50000 > 178.105.253.182.37492" in unsanitized.read_text(encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ANALYZER), str(log), "--process", str(process),
         "--udp-headers", str(udp_headers),
         "--result", str(result)],
        check=False, text=True, capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["primary_bottleneck"] == "entity_stream_or_server"
    assert payload["outcome_detail"] == "entity_stream_stalled"
    assert payload["gate_transitions"]["entity_server_active_to_entity_query_sent_seconds"] == 1
    assert payload["graphics"]["maximum_draw_seconds"] == 120
    assert payload["graphics"]["application_tick_watchdog"]["counts"] == {
        "presentation_resumed": 1,
        "presentation_stalled": 1,
    }
    assert payload["graphics"]["application_tick_watchdog"][
        "maximum_reported_stall_ms"
    ] == 301
    assert payload["nodes"]["counts"]["added:Entity Server"] == 1
    assert payload["progress"]["max_entities"] == 0
    assert payload["process"]["exit_code"] == 0
    assert payload["udp"]["nodes"]["Entity Server"]["outbound_packets"] == 1
    assert payload["udp"]["nodes"]["Entity Server"]["inbound_packets"] == 1
    assert payload["domain_target"]["port"] == 40114

    stalled_log = temporary / "connection-stalled.log"
    stalled_udp = temporary / "connection-stalled-udp.log"
    stalled_log.write_text(
        '\n'.join((
            '[08/23 11:00:00] [INFO] [overte.scriptengine] [online-smoke.js] Script Engine starting:online-smoke.js',
            '[08/23 11:00:01] [DEBUG] [hifi.networking] Possible domain change required to connect to "178.105.253.182" on 40114',
            '[08/23 11:00:02] [DEBUG] [hifi.networking] Coalescing duplicate active place lookup for "overte_hub"',
            '[08/23 11:10:01] [DEBUG] [overte.scriptengine] [online-smoke.js] OVERTE_MACOS_SMOKE failed connection_stalled',
        )) + '\n',
        encoding="utf-8",
    )
    stalled_udp.write_text(
        "2026-08-23 11:00:02.000 IP local.50000 > 178.105.253.182.40114: UDP, length 64\n",
        encoding="utf-8",
    )
    stalled_payload = module.analyze(stalled_log, None, stalled_udp)
    assert stalled_payload["primary_bottleneck"] == "domain_server_unreachable"
    assert stalled_payload["domain_target"]["host"] == "178.105.253.182"
    assert stalled_payload["udp"]["nodes"]["Domain Server"]["outbound_packets"] == 1
    assert stalled_payload["udp"]["nodes"]["Domain Server"].get("inbound_packets", 0) == 0
    assert stalled_payload["directory"]["coalesced_active_lookups"] == 1

    assert observer_module.discover_remote_target(stalled_log.read_text(encoding="utf-8")) == (
        "178.105.253.182", 40114, "domain_target"
    )

    observer_dir = temporary / "observer"
    observed = subprocess.run(
        [sys.executable, str(OBSERVER), "--log", str(log), "--output-dir",
         str(observer_dir), "--max-runtime", "0.05", "--interval", "0.01"],
        check=False, text=True, capture_output=True, timeout=10,
    )
    assert observed.returncode == 0, observed.stderr
    observer_result = json.loads((observer_dir / "observer-result.json").read_text(encoding="utf-8"))
    assert observer_result["schema_version"] == 1
    assert (observer_dir / "network-environment.json").is_file()
    assert (observer_dir / "runtime-observations.jsonl").is_file()

print("macOS online smoke diagnostics contract valid")
