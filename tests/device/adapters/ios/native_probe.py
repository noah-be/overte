"""Request one immutable client probe sample through the owned command channel."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import base64
import json
import time
import uuid
from urllib.request import Request, urlopen

from adapters.appium.adapter import AppiumAdapter


def validate(receipt, command_id):
    if (not isinstance(receipt, dict) or set(receipt) != {
            "schemaVersion", "commandId", "observation"}
            or type(receipt["schemaVersion"]) is not int or receipt["schemaVersion"] != 1
            or receipt["commandId"] != command_id):
        raise ValueError("native probe sample did not match this request")
    document = receipt["observation"]
    if isinstance(document, dict) and document.get("control", "absent") is None:
        document = {key: value for key, value in document.items() if key != "control"}
    return AppiumAdapter.validate_probe(document)


def capture(client, session, target, observe_process):
    before = observe_process()
    if (not isinstance(before, dict) or type(before.get("pid")) is not int
            or before["pid"] <= 0 or before.get("foregroundRunning") is not True):
        raise RuntimeError("native probe requires the configured foreground process")
    command_id = "ios-" + uuid.uuid4().hex
    payload = {"schemaVersion": 1, "commandId": command_id,
               "action": "native-probe-snapshot"}
    origin = target["testBuild"]["fixtureOrigin"]
    AppiumAdapter.controlled_http_url(origin, "native probe fixture origin")
    request = Request(origin + "/e2e-client-command.json", data=json.dumps(payload).encode(),
                      method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        content = response.read(4097)
        if response.status != 200 or len(content) > 4096 or json.loads(content) != payload:
            raise RuntimeError("owned fixture did not accept the exact native probe request")
    remote = (f"@{target['appId']}:documents/"
              f"{target['testBuild']['resultsDirectory']}/ios-probe-request-result.json")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
        try:
            document = validate(json.loads(base64.b64decode(encoded, validate=True)), command_id)
        except (ValueError, UnicodeError):
            time.sleep(0.1)
            continue
        after = observe_process()
        if (not isinstance(after, dict) or type(after.get("pid")) is not int
                or after["pid"] != before["pid"] or after.get("foregroundRunning") is not True):
            raise RuntimeError("native probe crossed process or foreground identities")
        return document
    raise RuntimeError("fresh request-bound native client probe was not observed")
