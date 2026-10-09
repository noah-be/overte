"""Request a stable, fresh native UIKit geometry sample before physical input."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import base64
import json
import time
import uuid
from urllib.request import Request, urlopen

from adapters.appium.adapter import AppiumAdapter
from adapters.ios.viewport import viewport


def validate(receipt, command_id):
    if (not isinstance(receipt, dict) or set(receipt) != {
            "schemaVersion", "commandId", "observation"}
            or type(receipt["schemaVersion"]) is not int or receipt["schemaVersion"] != 1
            or receipt["commandId"] != command_id):
        raise ValueError("native geometry sample did not match this request")
    document = receipt["observation"]
    return document, viewport(document)


def capture(client, session, target, observe_process):
    before = observe_process()
    if (not isinstance(before, dict) or type(before.get("pid")) is not int
            or before["pid"] <= 0 or before.get("foregroundRunning") is not True):
        raise RuntimeError("native geometry requires the configured foreground process")
    command_id = "ios-" + uuid.uuid4().hex
    payload = {"schemaVersion": 1, "commandId": command_id,
               "action": "native-geometry-snapshot"}
    origin = target["testBuild"]["fixtureOrigin"]
    AppiumAdapter.controlled_http_url(origin, "native geometry fixture origin")
    request = Request(origin + "/e2e-client-command.json", data=json.dumps(payload).encode(),
                      method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        content = response.read(4097)
        if response.status != 200 or len(content) > 4096 or json.loads(content) != payload:
            raise RuntimeError("owned fixture did not accept the exact native geometry request")
    remote = (f"@{target['appId']}:documents/"
              f"{target['testBuild']['resultsDirectory']}/ios-ui-request-result.json")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
        try:
            document, rect = validate(json.loads(base64.b64decode(encoded, validate=True)), command_id)
        except (ValueError, UnicodeError):
            time.sleep(0.1)
            continue
        after = observe_process()
        if (not isinstance(after, dict) or type(after.get("pid")) is not int
                or after["pid"] != before["pid"] or after.get("foregroundRunning") is not True):
            raise RuntimeError("native geometry crossed process or foreground identities")
        return document, rect
    raise RuntimeError("fresh request-bound native UIKit geometry was not observed")
