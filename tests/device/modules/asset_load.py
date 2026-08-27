#!/usr/bin/env python3
"""Load one controlled texture and correlate server, resource, entity and process evidence."""

from __future__ import annotations

import json
import os
import re
import time
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen
import uuid

from module_support import (InfrastructureError, assert_foreground, assert_process,
                            fail, module_main, operation, wait_for_process, write_json)
from overte_session import OverteSession


REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        fail(f"{name} is required")
    return value


def positive_integer_environment(name: str) -> int:
    value = required_environment(name)
    if not value.isdigit() or int(value) <= 0:
        fail(f"{name} must be a positive integer")
    return int(value)


def request_url(base_url: str, request_id: str) -> str:
    if not REQUEST_ID.fullmatch(request_id):
        fail("controlled asset request ID is invalid")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.fragment:
        fail("OVERTE_E2E_ASSET_URL must be an absolute HTTP URL")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(name == "requestId" for name, _value in query):
        fail("OVERTE_E2E_ASSET_URL must not contain requestId")
    query.append(("requestId", request_id))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       urlencode(query), ""))


def read_telemetry(base_url: str, asset_id: str, request_id: str) -> dict:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        fail("OVERTE_E2E_ASSET_TELEMETRY_URL must be an absolute HTTP URL")
    separator = "&" if parsed.query else "?"
    url = base_url + separator + urlencode({"assetId": asset_id, "requestId": request_id})
    try:
        with urlopen(url, timeout=5) as response:
            value = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise InfrastructureError("controlled asset telemetry is unavailable") from error
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or value.get("assetId") != asset_id or value.get("requestId") != request_id
            or isinstance(value.get("requests"), bool)
            or not isinstance(value.get("requests"), int)
            or isinstance(value.get("completedRequests"), bool)
            or not isinstance(value.get("completedRequests"), int)
            or isinstance(value.get("bytesServed"), bool)
            or not isinstance(value.get("bytesServed"), int)):
        raise InfrastructureError("controlled asset telemetry is incomplete")
    return value


def validate_delivery(value: dict, *, asset_id: str, request_id: str,
                      asset_url: str, content_type: str, byte_count: int,
                      sha256: str) -> None:
    if value["requests"] < 1 or value["completedRequests"] < 1:
        fail("fixture server did not observe a completed asset HTTP request")
    if value["bytesServed"] < byte_count:
        fail("fixture server did not deliver all controlled asset bytes")
    latest = value.get("latestCompleted")
    if not isinstance(latest, dict):
        fail("fixture server did not retain asset request evidence")
    expected_path = urlsplit(asset_url).path
    expected = {
        "assetId": asset_id, "requestId": request_id, "method": "GET",
        "path": expected_path, "status": 200, "contentType": content_type,
        "contentLength": byte_count, "sha256": sha256,
        "cacheControl": "no-store", "completed": True,
    }
    if any(latest.get(name) != expected_value for name, expected_value in expected.items()):
        fail("fixture server asset request evidence does not match the controlled asset")


def main() -> None:
    asset_id = required_environment("OVERTE_E2E_ASSET_ID")
    asset_url = required_environment("OVERTE_E2E_ASSET_URL")
    telemetry_url = required_environment("OVERTE_E2E_ASSET_TELEMETRY_URL")
    entity_name = required_environment("OVERTE_E2E_ASSET_ENTITY_NAME")
    content_type = required_environment("OVERTE_E2E_ASSET_CONTENT_TYPE")
    sha256 = required_environment("OVERTE_E2E_ASSET_SHA256")
    byte_count = positive_integer_environment("OVERTE_E2E_ASSET_BYTES")
    width = positive_integer_environment("OVERTE_E2E_ASSET_WIDTH")
    height = positive_integer_environment("OVERTE_E2E_ASSET_HEIGHT")
    request_id = os.environ.get("OVERTE_E2E_ASSET_REQUEST_ID", uuid.uuid4().hex)
    exact_url = request_url(asset_url, request_id)

    baseline = read_telemetry(telemetry_url, asset_id, request_id)
    if baseline["requests"] != 0 or baseline["completedRequests"] != 0:
        fail("controlled asset request ID was already used")

    operation("app.launch")
    identity = wait_for_process()
    assert_foreground("asset load baseline")
    session = OverteSession()
    snapshot = session.load_asset(
        asset_id, exact_url, entity_name, width, height, identity,
    )

    deadline = time.monotonic() + session.timeout_seconds
    delivery = None
    while time.monotonic() < deadline:
        assert_process(identity, "asset delivery")
        assert_foreground("asset delivery")
        delivery = read_telemetry(telemetry_url, asset_id, request_id)
        if delivery["completedRequests"] >= 1:
            break
        time.sleep(session.poll_seconds)
    if delivery is None:
        fail("fixture server asset telemetry was never sampled")
    validate_delivery(
        delivery, asset_id=asset_id, request_id=request_id, asset_url=exact_url,
        content_type=content_type, byte_count=byte_count, sha256=sha256,
    )
    assert_process(identity, "completed asset load")
    assert_foreground("completed asset load")
    write_json("asset-delivery.json", delivery)
    write_json("metrics.json", {
        "assetId": asset_id,
        "entityId": snapshot["asset"]["entity"]["id"],
        "processIdentity": identity,
        "requestId": request_id,
    })
    print("Controlled texture bytes, ready resource state, Image entity use, and stable process were observed.")


if __name__ == "__main__":
    module_main(main)
