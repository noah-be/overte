"""Strict, bounded synthetic voice command/result contract, version 1."""
from __future__ import annotations

import base64
import hashlib
import re
from urllib.parse import urlsplit

MAX_WAV = 5 * 1024 * 1024
MAX_RESULT = 8 * 1024 * 1024


def command(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value.get("schemaVersion") != 1:
        raise ValueError("voice command requires schema version 1")
    if not isinstance(value.get("commandId"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value["commandId"]):
        raise ValueError("voice command requires a bounded commandId")
    action = value.get("action")
    if not isinstance(action, str):
        raise ValueError("voice action must be a string")
    fields = {"schemaVersion", "commandId", "action"}
    if action == "send":
        fields |= {"challenge", "muted"}
        if (not isinstance(value.get("challenge"), str) or not re.fullmatch(r"[0-9a-f]{32}", value["challenge"])
                or type(value.get("muted")) is not bool):
            raise ValueError("voice send requires a fresh challenge and boolean muted")
    elif action == "capture-start":
        fields.add("seconds")
        if type(value.get("seconds")) is not int or not 6 <= value["seconds"] <= 10:
            raise ValueError("voice capture must last 6 through 10 seconds")
    elif action == "prepare":
        fields.add("domainUrl")
        if not isinstance(value.get("domainUrl"), str):
            raise ValueError("voice domain URL must be a string")
        parsed = urlsplit(value["domainUrl"])
        try:
            valid = parsed.scheme == "hifi" and parsed.hostname and parsed.port and not (
                parsed.username or parsed.password or parsed.query or parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("voice prepare requires a controlled hifi domain URL with explicit port")
    elif action not in {"status", "capture-stop", "reset"}:
        raise ValueError("unknown voice action")
    if set(value) != fields:
        raise ValueError("voice command fields are invalid")
    return value


def result(value: object) -> dict:
    if (not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value.get("schemaVersion") != 1
            or type(value.get("ok")) is not bool
            or not isinstance(value.get("commandId"), str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value["commandId"])):
        raise ValueError("voice result envelope is invalid")
    if "wavBase64" in value:
        wav(value)
    if "frames" in value and (type(value["frames"]) is not int or not 0 <= value["frames"] <= 116160):
        raise ValueError("voice frame counter is invalid")
    if "sending" in value and type(value["sending"]) is not bool:
        raise ValueError("voice sending state is invalid")
    return value


def wav(value: dict) -> bytes:
    encoded = value.get("wavBase64")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_WAV + 2) // 3):
        raise ValueError("voice capture is missing or oversized")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError("voice capture encoding is invalid") from error
    if len(data) > MAX_WAV or hashlib.sha256(data).hexdigest() != value.get("sha256"):
        raise ValueError("voice capture digest does not match")
    return data
