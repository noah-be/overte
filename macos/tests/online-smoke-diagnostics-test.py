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
            '[08/23 10:02:01] [INFO] [default] OVERTE_MACOS_GL_DRAW end gl_program= 37',
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
    assert payload["nodes"]["counts"]["added:Entity Server"] == 1
    assert payload["progress"]["max_entities"] == 0
    assert payload["process"]["exit_code"] == 0
    assert payload["udp"]["nodes"]["Entity Server"]["outbound_packets"] == 1
    assert payload["udp"]["nodes"]["Entity Server"]["inbound_packets"] == 1

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
