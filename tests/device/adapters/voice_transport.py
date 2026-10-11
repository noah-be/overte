"""Transport only: deliver one command and collect its fresh native result."""
from __future__ import annotations

import base64
import json
import time
from urllib.request import Request, urlopen

from voice_contract import MAX_RESULT, command, result


def fixture_command(url: str, value: dict) -> None:
    payload = {"schemaVersion": 1, "commandId": value["commandId"], "action": "voice-test", "request": command(value)}
    request = Request(url, data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            accepted = json.loads(response.read(4097))
        if accepted != payload:
            raise RuntimeError("voice fixture did not acknowledge the exact command")
    except (OSError, ValueError):
        raise RuntimeError("voice fixture command transport failed") from None


def exchange(value: dict, deliver, read, check_process, *, timeout: float = 15) -> dict:
    command(value)
    check_process()
    started = time.time() * 1000
    deliver({"schemaVersion": 1, "commandId": value["commandId"], "action": "voice-test", "request": value})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_process()
        try:
            raw = read()
            if not isinstance(raw, (bytes, str)) or len(raw) > MAX_RESULT:
                raise RuntimeError("voice result exceeds its transport limit")
            observed = json.loads(raw)
        except (OSError, ValueError, RuntimeError):
            time.sleep(0.1)
            continue
        if observed.get("commandId") != value["commandId"]:
            time.sleep(0.1)
            continue
        epoch = observed.get("sampleEpochMs")
        if type(epoch) not in (int, float) or not started - 30000 <= epoch <= time.time() * 1000 + 30000:
            raise RuntimeError("voice result timestamp is stale or invalid")
        check_process()
        return result(observed)
    raise RuntimeError("voice native command was not acknowledged before its deadline")


def appium_read(client, session: str, remote: str) -> bytes:
    encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_RESULT + 2) // 3):
        raise RuntimeError("voice Appium result is invalid or oversized")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError:
        raise RuntimeError("voice Appium result is not base64") from None
