#!/usr/bin/env python3
"""Prove controlled WAV loading, decoding, and the in-client injector lifecycle."""

from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen
import uuid

from module_support import (InfrastructureError, assert_process, fail, module_main,
                            operation, process_identity, write_json)
from overte_session import OverteSession


def absolute_http_environment(name: str) -> str:
    value = os.environ.get(name, "")
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        fail(f"{name} must be an absolute HTTP(S) URL")
    return value


def tagged_url(url: str, command_id: str) -> str:
    split = urlsplit(url)
    query = parse_qs(split.query, keep_blank_values=True)
    query["e2eCommand"] = [command_id]
    return urlunsplit((split.scheme, split.netloc, split.path,
                       urlencode(query, doseq=True), split.fragment))


class FreshProbe:
    """Require universally fresh, internally ordered probe snapshots."""

    def __init__(self, session: OverteSession, initial: dict, identity: str) -> None:
        self.session = session
        self.identity = identity
        self.sequence = initial.get("sampleSequence")
        self.epoch_ms = initial["sampleEpochMs"]
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            fail("sound playback requires probe sampleSequence")

    def next(self, deadline: float) -> dict:
        while time.monotonic() < deadline:
            assert_process(self.identity, "sound playback probe sampling")
            sample = self.session.snapshot()
            sequence = sample.get("sampleSequence")
            epoch_ms = sample["sampleEpochMs"]
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                fail("sound playback requires probe sampleSequence")
            if sequence < self.sequence or epoch_ms < self.epoch_ms:
                fail("sound probe samples are inconsistent or out of order")
            if sequence == self.sequence:
                if epoch_ms != self.epoch_ms:
                    fail("sound probe changed without advancing sampleSequence")
                time.sleep(self.session.poll_seconds)
                continue
            if epoch_ms <= self.epoch_ms:
                fail("sound probe sampleEpochMs did not advance with sampleSequence")
            self.sequence = sequence
            self.epoch_ms = epoch_ms
            assert_process(self.identity, "sound playback fresh probe sample")
            return sample
        fail("timed out waiting for a fresh sound probe sample")

    def wait(self, description: str, predicate, timeout_seconds: float) -> dict:
        deadline = time.monotonic() + timeout_seconds
        last = None
        while time.monotonic() < deadline:
            last = self.next(deadline)
            sound = last.get("sound")
            if not isinstance(sound, dict):
                fail("probe does not expose the sound observation contract")
            if predicate(sound):
                return last
        if last is not None:
            write_json("last-sound-probe.json", last)
        fail(f"timed out waiting for {description}")


def request_evidence(requests_url: str, command_id: str, sound_url: str,
                     timeout_seconds: float) -> dict:
    target = urlsplit(sound_url)
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urlopen(requests_url, timeout=min(2.0, timeout_seconds)) as response:
                payload = json.load(response)
        except (OSError, HTTPError, URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.1)
            continue
        requests = payload.get("requests") if isinstance(payload, dict) else None
        if not isinstance(requests, list):
            raise InfrastructureError("fixture sound request telemetry is invalid")
        for event in requests:
            query = event.get("query", {}) if isinstance(event, dict) else {}
            if (event.get("path") == target.path
                    and query.get("e2eCommand") == [command_id]):
                if event.get("status") != 200:
                    fail(f"controlled sound request returned HTTP {event.get('status')}")
                if event.get("mimeType") != "audio/wav":
                    fail("controlled sound response did not use audio/wav")
                if (not isinstance(event.get("bytesSent"), int)
                        or isinstance(event["bytesSent"], bool) or event["bytesSent"] <= 0):
                    fail("controlled sound response did not send bytes")
                return event
        time.sleep(0.1)
    detail = f": {last_error}" if last_error else ""
    raise InfrastructureError("fixture did not report the controlled sound request" + detail)


def main() -> None:
    session = OverteSession()
    timeout = session._float_environment(
        "OVERTE_E2E_SOUND_TIMEOUT_SECONDS", 15.0, 1.0, 120.0)
    sound_url = absolute_http_environment("OVERTE_E2E_SOUND_URL")
    requests_url = absolute_http_environment("OVERTE_E2E_SOUND_REQUESTS_URL")
    command_url = absolute_http_environment("OVERTE_E2E_SOUND_COMMAND_URL")
    command_id = "sound-" + uuid.uuid4().hex
    requested_url = tagged_url(sound_url, command_id)

    identity = process_identity()
    baseline = session.snapshot("sound-before.json")
    fresh = FreshProbe(session, baseline, identity)
    result = operation("sound.play", {
        "schemaVersion": 1,
        "commandId": command_id,
        "url": requested_url,
        "commandUrl": command_url,
    })
    write_json("sound-command.json", result)
    if result.get("requested") is not True or result.get("commandId") != command_id:
        fail("sound.play did not acknowledge the exact sound command")
    assert_process(identity, "sound command")

    command_sample = fresh.wait(
        "the probe to observe the exact sound command",
        lambda sound: sound["commandObserved"] is True
        and sound["commandId"] == command_id and sound["url"] == requested_url,
        timeout,
    )
    write_json("sound-command-observed.json", command_sample)

    request = request_evidence(requests_url, command_id, requested_url, timeout)
    write_json("sound-request.json", request)

    ready_sample = fresh.wait(
        "the controlled WAV to become decoded and usable",
        lambda sound: sound["commandId"] == command_id and sound["resourceReady"] is True,
        timeout,
    )
    ready = ready_sample["sound"]
    if ready["format"] != "wav":
        fail("sound resource did not take the WAV format path")
    try:
        expected_duration = float(os.environ.get(
            "OVERTE_E2E_SOUND_DURATION_SECONDS", "2.0"))
    except ValueError:
        fail("OVERTE_E2E_SOUND_DURATION_SECONDS must be numeric")
    if not 0.1 <= expected_duration <= 120.0:
        fail("OVERTE_E2E_SOUND_DURATION_SECONDS must be from 0.1 through 120")
    if abs(float(ready["durationSeconds"]) - expected_duration) > 0.1:
        fail("decoded sound duration does not match the controlled WAV")
    write_json("sound-resource-ready.json", ready_sample)

    if ready["finished"] is True:
        fail("audio injector ended unexpectedly before active playback was sampled")

    started_sample = (ready_sample if ready["started"] and ready["playing"] else fresh.wait(
        "the audio injector to start playing",
        lambda sound: sound["commandId"] == command_id and sound["injectorCreated"] is True
        and sound["started"] is True and sound["playing"] is True,
        timeout,
    ))
    active_samples = [started_sample]
    deadline = time.monotonic() + timeout
    while len(active_samples) < 2:
        sample = fresh.next(deadline)
        sound = sample.get("sound", {})
        if sound.get("commandId") != command_id:
            fail("sound probe switched commands during playback")
        if sound.get("finished") is True or sound.get("playing") is not True:
            fail("audio injector ended unexpectedly before two fresh active samples")
        active_samples.append(sample)
    write_json("sound-active-samples.json", active_samples)

    finished_sample = fresh.wait(
        "the audio injector to finish normally",
        lambda sound: sound["commandId"] == command_id and sound["finished"] is True
        and sound["playing"] is False,
        timeout,
    )
    reason = finished_sample["sound"]["finishReason"]
    if reason not in {"natural", "stopped"}:
        fail("audio injector ended without a regular finish or controlled stop")
    assert_process(identity, "sound playback completion")
    write_json("sound-finished.json", finished_sample)
    write_json("metrics.json", {
        "activeFreshSamples": len(active_samples),
        "commandId": command_id,
        "finishReason": reason,
        "processIdentity": identity,
        "requestedBytes": request["bytesSent"],
    })
    print("Controlled WAV was requested, decoded, and observed through a complete "
          "in-client AudioInjector lifecycle; physical audio output was not measured.")


module_main(main)
