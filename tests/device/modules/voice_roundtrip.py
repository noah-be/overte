#!/usr/bin/env python3
"""Prove both voice directions and both mute controls using received PCM."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import secrets
import tempfile
import time

from module_support import InfrastructureError, assert_process, fail, module_main, process_identity, write_json
from module_support import contract_operation
from overte_session import OverteSession
from voice_contract import wav
from voice_peer.fixture import invoke as peer
from voice_peer.voice_signal import analyze


def exchange(action: str, **fields) -> dict:
    value = {"schemaVersion": 1, "commandId": "voice-" + secrets.token_hex(16), "action": action, **fields}
    result = contract_operation("voice.exchange", value)
    if result["commandId"] != value["commandId"]:
        raise InfrastructureError("voice transport returned another command's result")
    if not result["ok"]:
        raise InfrastructureError("native voice test hook rejected the command")
    if action != "reset" and (result.get("localEcho") is not False or result.get("serverEcho") is not False):
        raise InfrastructureError("device voice test echo must remain disabled")
    return result


def require_peer(state: Path, domain_id: str) -> dict:
    status = peer(state, "status")
    client = status.get("client") or {}
    if (not status.get("snapshotFresh") or not status.get("audioRouted")
            or not client.get("connected") or not client.get("mixerReady")
            or client.get("localEcho") or client.get("serverEcho")):
        raise InfrastructureError("owned voice partner is not ready in the device domain with echo disabled")
    if peer(state, "domain-check", domain_id=domain_id).get("sameDomain") is not True:
        raise InfrastructureError("owned voice partner is connected to another domain")
    return status


def wait_send(identity: str) -> dict:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        assert_process(identity, "voice send")
        result = exchange("status")
        if result.get("sending") is False:
            if result.get("frames") != 116160:
                fail("device did not process the complete microphone challenge")
            return result
        time.sleep(0.1)
    fail("device microphone challenge stalled")


def run_roundtrip(state: Path, identity: str, domain_id: str) -> dict:
    evidence = {"schemaVersion": 1, "legs": [], "physicalAudioHardwareTested": False}
    for muted in (False, True):
        # The receiver starts before the sender. A fresh nonce is used for every
        # leg, so previous playback or a retained capture cannot satisfy it.
        challenge = secrets.token_hex(16)
        require_peer(state, domain_id)
        exchange("capture-start", seconds=8)
        started = time.monotonic()
        sent = peer(state, "send-muted" if muted else "send", challenge=challenge)
        if sent.get("sent") is not True or sent.get("challenge") != challenge or sent.get("muted") is not muted:
            raise InfrastructureError("PC did not acknowledge the exact voice send state")
        while time.monotonic() - started < 8.25:
            assert_process(identity, "voice receive")
            time.sleep(0.1)
        captured = exchange("capture-stop")
        with tempfile.TemporaryDirectory(prefix="overte-device-voice-") as private:
            capture = Path(private) / "received.wav"
            capture.write_bytes(wav(captured))
            capture.chmod(0o600)
            measured = analyze(capture, challenge, "absent" if muted else "present")
        leg = {"direction": "pc-to-device", "muted": muted, "measurement": measured,
               "deviceVersion": captured.get("version"), "pcVersion": sent.get("build"),
               "pcBinarySha256": sent.get("clientSha256"), "pcRunnerSha256": sent.get("runnerSha256")}
        evidence["legs"].append(leg)
        write_json("voice-roundtrip.json", evidence)
        if not measured["passed"]:
            fail("PC-to-device received PCM failed the voice or mute assertion")

        challenge = secrets.token_hex(16)
        require_peer(state, domain_id)
        with ThreadPoolExecutor(max_workers=1) as workers:
            receiving = workers.submit(peer, state, "receive", challenge=challenge, seconds=8,
                                       expect="absent" if muted else "present")
            deadline = time.monotonic() + 8
            while True:
                if receiving.done():
                    receiving.result()
                    raise InfrastructureError("PC receive completed before the device send")
                status = require_peer(state, domain_id)
                if status.get("receivingChallenge") == challenge:
                    break
                if time.monotonic() > deadline:
                    raise InfrastructureError("PC receive capture did not become ready")
                time.sleep(0.1)
            sent = exchange("send", challenge=challenge, muted=muted)
            if sent.get("muted") is not muted:
                fail("device did not apply the requested microphone mute state")
            device = wait_send(identity)
            measured = receiving.result(timeout=20)
            if measured.get("challenge") != challenge or measured.get("expected") != ("absent" if muted else "present"):
                raise InfrastructureError("PC returned another challenge or expectation")
        leg = {"direction": "device-to-pc", "muted": muted, "measurement": measured,
               "deviceVersion": device.get("version")}
        evidence["legs"].append(leg)
        write_json("voice-roundtrip.json", evidence)
        if not measured.get("passed"):
            fail("device-to-PC received PCM failed the voice or mute assertion")
    return evidence


def main() -> None:
    if os.environ.get("OVERTE_E2E_VOICE_TESTS") != "1":
        raise InfrastructureError("voice suite requires an explicitly enabled test build")
    state_value = os.environ.get("OVERTE_E2E_VOICE_PEER_STATE")
    if not state_value:
        raise InfrastructureError("voice suite requires an owned PC peer fixture")
    identity = process_identity()
    failure = None
    try:
        exchange("prepare", domainUrl=os.environ["OVERTE_E2E_DOMAIN_URL"])
        deadline = time.monotonic() + 45
        expected_domain = os.environ["OVERTE_E2E_DOMAIN_ID"]
        while True:
            assert_process(identity, "voice domain join")
            device = exchange("status")
            if device.get("connected") and (OverteSession._parsed_domain_uuid(device.get("domainId"))
                    == OverteSession._domain_uuid(expected_domain, "voice fixture domain")):
                break
            if time.monotonic() > deadline:
                fail("device did not join the controlled voice domain")
            time.sleep(0.25)
        if not isinstance(device.get("version"), str) or not device["version"]:
            raise InfrastructureError("installed device version is missing from native evidence")
        position = device.get("position")
        state = Path(state_value)
        # Co-locate within one metre, avoiding attenuation from arbitrary spawn
        # points while still using ordinary spatial avatar voice.
        peer(state, "position", x=position["x"] + 0.5, y=position["y"], z=position["z"])
        write_json("voice-device-version.json", {"schemaVersion": 1, "version": device["version"]})
        run_roundtrip(state, identity, expected_domain)
        assert_process(identity, "voice roundtrip completion")
    except BaseException as error:
        failure = error
        raise
    finally:
        try:
            exchange("reset")
            write_json("voice-cleanup.json", {"schemaVersion": 1, "reset": True})
        except Exception:
            write_json("voice-cleanup.json", {"schemaVersion": 1, "reset": False})
            # Cleanup must not reclassify an observed product failure as a
            # retryable infrastructure error.
            if failure is None:
                raise
    print("PASS: received fresh voice challenges in both directions and verified both mute controls")


if __name__ == "__main__":
    raise SystemExit(module_main(main))
