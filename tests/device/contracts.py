#!/usr/bin/env python3
"""Versioned contracts shared by the device runner and adapter verifier."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
MAX_FLY_DURATION_SECONDS = 10.0
MAX_INPUT_DURATION_SECONDS = 10.0
MAX_LOOK_COMPONENT = 1.0
MOVEMENT_DIRECTIONS = {"backward", "forward", "left", "right"}
TABLET_CONTRACT_VERSION = 1
TABLET_SNAPSHOT_SCHEMA_VERSION = 1
TABLET_POLICY_SCHEMA_VERSION = 1
TEXT_SNAPSHOT_SCHEMA_VERSION = 1
MAX_TEXT_CODEPOINTS = 128
MAX_TEXT_BACKSPACES = 32


def load_capability_registry(path: Path | None = None) -> dict[str, dict]:
    source = path or ROOT / "capabilities.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    capabilities = payload.get("capabilities")
    if payload.get("schemaVersion") != 1 or not isinstance(capabilities, dict):
        raise ValueError("unsupported capability registry schema")
    if not capabilities or list(capabilities) != sorted(capabilities):
        raise ValueError("capability registry must be non-empty and sorted")
    for name, definition in capabilities.items():
        if not IDENTIFIER.fullmatch(name) or not isinstance(definition, dict):
            raise ValueError(f"invalid capability registry entry: {name}")
        operation = definition.get("operation")
        if operation is not None and operation != name:
            raise ValueError(f"capability operation must match its name: {name}")
        if not isinstance(definition.get("result"), str) or not definition["result"]:
            raise ValueError(f"capability requires result documentation: {name}")
    return capabilities


def load_tablet_ui_contract(path: Path | None = None) -> dict:
    """Load the closed semantic-ID vocabulary shared by modules and adapters."""
    source = path or ROOT / "tablet-ui-contract.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
            "contractVersion", "schemaVersion", "controlIds", "screenIds"}:
        raise ValueError("tablet UI contract contains unsupported or missing fields")
    if (payload.get("contractVersion") != TABLET_CONTRACT_VERSION
            or payload.get("schemaVersion") != 1):
        raise ValueError("unsupported tablet UI contract version")
    for field in ("controlIds", "screenIds"):
        values = payload.get(field)
        if (not isinstance(values, list) or not values
                or values != sorted(set(values))
                or not all(isinstance(item, str) and IDENTIFIER.fullmatch(item)
                           for item in values)):
            raise ValueError(f"tablet UI contract {field} must be sorted unique identifiers")
    return payload


def _validate_tablet_id_list(value: object, label: str, known: set[str]) -> list[str]:
    if (not isinstance(value, list) or value != sorted(set(value))
            or not all(isinstance(item, str) and item in known for item in value)):
        raise ValueError(f"{label} must be sorted, unique and contain only known semantic IDs")
    return value


def validate_tablet_ui_snapshot(value: object, contract: dict | None = None) -> dict:
    """Reject ambiguous adapter observations before behavior is asserted."""
    vocabulary = contract or load_tablet_ui_contract()
    required = {"contractVersion", "schemaVersion", "screenId", "ready",
                "visibleControlIds"}
    optional = {"selectedControlIds"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ValueError("tablet snapshot contains unsupported or missing fields")
    if value.get("contractVersion") != vocabulary["contractVersion"]:
        raise ValueError("unsupported tablet UI contract version")
    if value.get("schemaVersion") != TABLET_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported tablet snapshot schema version")
    if value.get("screenId") not in vocabulary["screenIds"]:
        raise ValueError("tablet snapshot contains an unknown screen ID")
    if not isinstance(value.get("ready"), bool):
        raise ValueError("tablet snapshot ready must be boolean")
    known_controls = set(vocabulary["controlIds"])
    visible = _validate_tablet_id_list(
        value.get("visibleControlIds"), "tablet snapshot visibleControlIds", known_controls)
    if "selectedControlIds" in value:
        selected = _validate_tablet_id_list(
            value["selectedControlIds"], "tablet snapshot selectedControlIds", known_controls)
        if not set(selected) <= set(visible):
            raise ValueError("tablet snapshot selected controls must be visible")
    return value


def validate_tablet_product_policy(value: object, contract: dict | None = None) -> dict:
    """Validate product expectations independently of an adapter observation."""
    vocabulary = contract or load_tablet_ui_contract()
    if not isinstance(value, dict) or set(value) != {
            "contractVersion", "schemaVersion", "profileId", "expectations"}:
        raise ValueError("tablet product policy contains unsupported or missing fields")
    if value.get("contractVersion") != vocabulary["contractVersion"]:
        raise ValueError("unsupported tablet product policy contract version")
    if value.get("schemaVersion") != TABLET_POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported tablet product policy schema version")
    profile_id = validate_identifier(
        value.get("profileId"), "tablet product policy profileId")
    if len(profile_id) > 128:
        raise ValueError("tablet product policy profileId must not exceed 128 characters")
    expectations = value.get("expectations")
    if (not isinstance(expectations, dict)
            or list(expectations) != sorted(expectations)
            or not {"settings.home", "tablet.home"} <= set(expectations)):
        raise ValueError(
            "tablet product policy expectations must be sorted and include settings.home and tablet.home")
    known_screens = set(vocabulary["screenIds"])
    known_controls = set(vocabulary["controlIds"])
    settings_home_required: set[str] = set()
    for screen_id, expectation in expectations.items():
        if screen_id not in known_screens or not isinstance(expectation, dict):
            raise ValueError(f"tablet product policy contains unknown screen: {screen_id}")
        required_fields = {"requiredControlIds", "forbiddenControlIds"}
        optional_fields = {"entryControlId"}
        if not required_fields <= set(expectation) or set(expectation) - required_fields - optional_fields:
            raise ValueError(f"tablet product policy screen {screen_id} has invalid fields")
        required = _validate_tablet_id_list(
            expectation.get("requiredControlIds"),
            f"tablet product policy {screen_id} requiredControlIds", known_controls)
        forbidden = _validate_tablet_id_list(
            expectation.get("forbiddenControlIds"),
            f"tablet product policy {screen_id} forbiddenControlIds", known_controls)
        if set(required) & set(forbidden):
            raise ValueError(f"tablet product policy {screen_id} contradicts itself")
        entry = expectation.get("entryControlId")
        if screen_id == "tablet.home":
            if entry is not None:
                raise ValueError("tablet.home must not declare an entry control")
        elif not isinstance(entry, str) or entry not in known_controls:
            raise ValueError(f"tablet product policy {screen_id} requires a known entry control")
        if screen_id == "settings.home" and entry != "app.settings":
            raise ValueError("settings.home must be entered through app.settings")
        if screen_id == "settings.home":
            settings_home_required = set(required)
    for screen_id, expectation in expectations.items():
        if screen_id not in {"tablet.home", "settings.home"}:
            entry = expectation["entryControlId"]
            if entry not in settings_home_required:
                raise ValueError(
                    f"tablet product policy entry control {entry} must be required on settings.home")
    return value


def load_tablet_product_policy(path: Path, contract: dict | None = None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_tablet_product_policy(payload, contract)


def validate_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must use lowercase dotted identifier syntax")
    return value


def validate_capabilities(values: object, registry: dict[str, dict] | None = None) -> list[str]:
    known = registry or load_capability_registry()
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("capabilities must be a string list")
    if values != sorted(set(values)):
        raise ValueError("capabilities must be unique and use deterministic sorted order")
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ValueError("unknown capabilities: " + ", ".join(unknown))
    return values


def validate_discovered_targets(value: object) -> list[dict]:
    """Validate discovery without exposing private selector or reservation values."""
    if not isinstance(value, list):
        raise ValueError("adapter discover result must be a list")
    required = {"capabilities", "displayName", "physical", "platform", "selector"}
    allowed = required | {"reservationKey"}
    selectors: set[str] = set()
    for target in value:
        if not isinstance(target, dict) or not required <= set(target) or set(target) - allowed:
            raise ValueError("adapter target contains unsupported or missing fields")
        selector = target.get("selector")
        if not isinstance(selector, str) or not selector or selector in selectors:
            raise ValueError("target selectors must be unique non-empty strings")
        selectors.add(selector)
        if (not isinstance(target.get("displayName"), str) or not target["displayName"]
                or not isinstance(target.get("platform"), str) or not target["platform"]
                or not isinstance(target.get("physical"), bool)):
            raise ValueError("target identity fields have invalid types")
        reservation_key = target.get("reservationKey")
        if reservation_key is not None and (not isinstance(reservation_key, str)
                                            or not reservation_key
                                            or len(reservation_key) > 512):
            raise ValueError("target reservationKey must be a bounded non-empty string")
        validate_capabilities(target.get("capabilities"))
    return value


def contains_private_identity(value: object, identities: set[str]) -> bool:
    """Detect exact short identities and embedded opaque identities recursively."""
    if isinstance(value, dict):
        return any(contains_private_identity(key, identities)
                   or contains_private_identity(item, identities)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(contains_private_identity(item, identities) for item in value)
    if not isinstance(value, str):
        return False
    return any(value == identity or (len(identity) >= 8 and identity in value)
               for identity in identities)


def validate_operation_arguments(operation: str, value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("operation arguments must be an object")
    if operation in {"app.version", "collaboration.snapshot", "render.snapshot",
                     "tablet.snapshot", "text.snapshot"}:
        if value:
            raise ValueError(f"{operation} does not accept arguments")
    elif operation == "tablet.activate":
        if set(value) != {"contractVersion", "controlId"}:
            raise ValueError("tablet.activate requires only contractVersion and controlId")
        vocabulary = load_tablet_ui_contract()
        if value.get("contractVersion") != vocabulary["contractVersion"]:
            raise ValueError("tablet.activate uses an unsupported contract version")
        if value.get("controlId") not in vocabulary["controlIds"]:
            raise ValueError("tablet.activate requires a known semantic control ID")
    elif operation in {
            "app.foreground", "app.launch", "app.process", "app.stop",
            "input.jump", "input.primary", "lifecycle.background", "tablet.close", "tablet.open",
            "text.dismiss", "text.focus"}:
        if value:
            raise ValueError(f"{operation} does not accept arguments")
    elif operation == "app.crash":
        if value != {"mode": "abort"}:
            raise ValueError("app.crash requires only mode: abort")
    elif operation == "app.install":
        if set(value) != {"path"}:
            raise ValueError("app.install requires only path")
        path = value.get("path")
        if (not isinstance(path, str) or not path or "\x00" in path
                or not Path(path).is_absolute()):
            raise ValueError("app.install path must be an absolute NUL-free path")
    elif operation == "artifact.video":
        if set(value) != {"durationSeconds"}:
            raise ValueError("artifact.video requires only durationSeconds")
        _bounded_number(value["durationSeconds"], "artifact.video durationSeconds", 1.0, 30.0)
    elif operation == "app.upgrade":
        if set(value) != {"fromVersion", "toVersion"}:
            raise ValueError("app.upgrade requires only fromVersion and toVersion")
        for field in ("fromVersion", "toVersion"):
            version = value.get(field)
            if (not isinstance(version, str) or not version or len(version) > 64
                    or any(character.isspace() for character in version)):
                raise ValueError(f"app.upgrade {field} is invalid")
        if value["fromVersion"] == value["toVersion"]:
            raise ValueError("app.upgrade versions must differ")
    elif operation == "collaboration.edit":
        if set(value) != {"entityName", "value"}:
            raise ValueError("collaboration.edit requires only entityName and value")
        if (not isinstance(value.get("entityName"), str)
                or not value["entityName"].startswith("OVERTE_E2E_SHARED_")):
            raise ValueError("collaboration.edit requires a controlled entity name")
        if (not isinstance(value.get("value"), str) or not value["value"]
                or len(value["value"]) > 64):
            raise ValueError("collaboration.edit value must be bounded and non-empty")
    elif operation in {"permission.set", "permission.snapshot"}:
        expected = {"permissionId", "state"} if operation == "permission.set" else {"permissionId"}
        if set(value) != expected or value.get("permissionId") != "microphone":
            raise ValueError(f"{operation} requires the controlled microphone permission")
        if operation == "permission.set" and value.get("state") not in {"denied", "granted"}:
            raise ValueError("permission.set state must be denied or granted")
    elif operation == "input.fly":
        if set(value) != {"durationSeconds"}:
            raise ValueError("input.fly requires only durationSeconds")
        _bounded_number(value["durationSeconds"], "input.fly durationSeconds",
                        0.1, MAX_FLY_DURATION_SECONDS)
    elif operation == "audio.mute":
        if set(value) != {"muted"} or not isinstance(value.get("muted"), bool):
            raise ValueError("audio.mute requires only muted: boolean")
    elif operation == "input.look":
        if set(value) != {"horizontal", "vertical"}:
            raise ValueError("input.look requires only horizontal and vertical")
        horizontal = _bounded_number(
            value["horizontal"], "input.look horizontal",
            -MAX_LOOK_COMPONENT, MAX_LOOK_COMPONENT)
        vertical = _bounded_number(
            value["vertical"], "input.look vertical",
            -MAX_LOOK_COMPONENT, MAX_LOOK_COMPONENT)
        if horizontal == 0.0 and vertical == 0.0:
            raise ValueError("input.look requires a non-zero component")
    elif operation == "input.move":
        if set(value) != {"direction", "durationSeconds"}:
            raise ValueError("input.move requires only direction and durationSeconds")
        if value["direction"] not in MOVEMENT_DIRECTIONS:
            raise ValueError("input.move direction is unsupported")
        _bounded_number(value["durationSeconds"], "input.move durationSeconds",
                        0.1, MAX_INPUT_DURATION_SECONDS)
    elif operation == "text.type":
        if set(value) != {"backspaceCount", "submit", "text"}:
            raise ValueError("text.type requires only text, backspaceCount and submit")
        text = value.get("text")
        backspaces = value.get("backspaceCount")
        if (not isinstance(text, str) or not text
                or len(text) > MAX_TEXT_CODEPOINTS
                or any(ord(character) < 32 or ord(character) == 127 for character in text)):
            raise ValueError("text.type text must be bounded non-control Unicode")
        if (not isinstance(backspaces, int) or isinstance(backspaces, bool)
                or not 0 <= backspaces <= min(MAX_TEXT_BACKSPACES, len(text))):
            raise ValueError("text.type backspaceCount is invalid")
        if not isinstance(value.get("submit"), bool):
            raise ValueError("text.type submit must be boolean")
    elif operation == "setting.set":
        if (set(value) != {"enabled", "settingId"}
                or value.get("settingId") != "audio.warn-when-muted"
                or not isinstance(value.get("enabled"), bool)):
            raise ValueError("setting.set requires the safe audio.warn-when-muted boolean")
    elif operation == "probe.snapshot":
        if not set(value) <= {"afterSampleSequence"}:
            raise ValueError("probe.snapshot accepts only afterSampleSequence")
        if "afterSampleSequence" in value:
            sequence = value["afterSampleSequence"]
            if (not isinstance(sequence, int) or isinstance(sequence, bool)
                    or sequence <= 0):
                raise ValueError("probe.snapshot afterSampleSequence must be a positive integer")
    elif operation in {"scene.load", "scene.reload"}:
        if set(value) != {"url"}:
            raise ValueError(f"{operation} requires only url")
        if not isinstance(value["url"], str) or "://" not in value["url"]:
            raise ValueError(f"{operation} url must be an absolute URL")
    elif operation == "navigation.enter-domain":
        if set(value) != {"url"} or not isinstance(value.get("url"), str):
            raise ValueError("navigation.enter-domain requires only a URL string")
        parsed = urlsplit(value["url"])
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("navigation.enter-domain URL has an invalid port") from error
        if (parsed.scheme != "hifi" or not parsed.hostname or port is None
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError(
                "navigation.enter-domain requires a credential-free hifi URL with explicit port")
    elif operation == "asset.load":
        if set(value) != {"assetId", "url", "entityName"}:
            raise ValueError("asset.load requires only assetId, url and entityName")
        asset_id = value["assetId"]
        url = value["url"]
        entity_name = value["entityName"]
        if not isinstance(asset_id, str) or not IDENTIFIER.fullmatch(asset_id):
            raise ValueError("asset.load assetId must be a lowercase identifier")
        if (not isinstance(entity_name, str)
                or not entity_name.startswith("OVERTE_E2E_ASSET_LOAD")):
            raise ValueError("asset.load entityName must use the controlled prefix")
        if not isinstance(url, str):
            raise ValueError("asset.load url must be an absolute HTTP URL")
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment):
            raise ValueError("asset.load url must be an absolute HTTP URL")
    elif operation == "sound.play":
        if set(value) != {"schemaVersion", "commandId", "url", "commandUrl"}:
            raise ValueError("sound.play requires only its versioned command fields")
        command_id = value.get("commandId")
        if (value.get("schemaVersion") != 1 or not isinstance(command_id, str)
                or not command_id or len(command_id) > 128
                or command_id.strip() != command_id):
            raise ValueError("sound.play requires schema version 1 and a bounded commandId")
        for field in ("url", "commandUrl"):
            url = value.get(field)
            parsed = urlsplit(url) if isinstance(url, str) else None
            if (parsed is None or parsed.scheme not in {"http", "https"}
                    or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None):
                raise ValueError(f"sound.play {field} must be an absolute HTTP(S) URL")
    return value


def _bounded_number(value: object, label: str, minimum: float, maximum: float) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not minimum <= float(value) <= maximum):
        raise ValueError(f"{label} must be from {minimum} through {maximum}")
    return float(value)


def validate_performed_result(operation: str, value: object) -> dict:
    if not isinstance(value, dict) or value.get("performed") is not True:
        raise ValueError(f"{operation} result must confirm performed: true")
    return value


def validate_operation_result(operation: str, value: object) -> dict:
    """Validate portable evidence returned by an adapter operation."""
    if not isinstance(value, dict):
        raise ValueError(f"{operation} result must be an object")
    if operation in {"audio.mute", "collaboration.edit", "input.fly", "input.jump", "input.look", "input.move", "input.primary",
                     "permission.set",
                     "tablet.activate", "tablet.close", "tablet.open", "text.dismiss",
                     "text.focus", "text.type", "setting.set"}:
        return validate_performed_result(operation, value)
    if operation == "tablet.snapshot":
        return validate_tablet_ui_snapshot(value)
    if operation == "text.snapshot":
        return validate_text_snapshot(value)
    if operation == "render.snapshot":
        return validate_render_snapshot(value)
    if operation == "app.version":
        if (set(value) != {"schemaVersion", "version"} or value.get("schemaVersion") != 1
                or not isinstance(value.get("version"), str) or not value["version"]):
            raise ValueError("app.version result is invalid")
        return value
    if operation == "collaboration.snapshot":
        if set(value) != {"actorId", "entityName", "revision", "schemaVersion", "value"}:
            raise ValueError("collaboration.snapshot result fields are invalid")
        if (value.get("schemaVersion") != 1
                or not isinstance(value.get("entityName"), str)
                or not value["entityName"].startswith("OVERTE_E2E_SHARED_")
                or not isinstance(value.get("value"), str)
                or not isinstance(value.get("actorId"), str)
                or not value["actorId"].startswith("OVERTE_E2E_ACTOR_")
                or not isinstance(value.get("revision"), int)
                or isinstance(value["revision"], bool) or value["revision"] < 0):
            raise ValueError("collaboration.snapshot result is invalid")
        return value
    if operation == "permission.snapshot":
        if (set(value) != {"permissionId", "schemaVersion", "state"}
                or value.get("schemaVersion") != 1
                or value.get("permissionId") != "microphone"
                or value.get("state") not in {"denied", "granted", "unknown"}):
            raise ValueError("permission.snapshot result is invalid")
        return value
    if operation == "app.crash":
        if value != {"crashed": True}:
            raise ValueError("app.crash result must be exactly crashed: true")
        return value
    if operation == "app.upgrade":
        if value != {"applied": True}:
            raise ValueError("app.upgrade result must be exactly applied: true")
        return value
    if operation == "app.install":
        if value != {"installed": True}:
            raise ValueError("app.install result must be exactly installed: true")
        return value
    if operation in {"artifact.screenshot", "artifact.video"}:
        if (set(value) != {"artifact"} or not isinstance(value.get("artifact"), str)
                or not value["artifact"] or "/" in value["artifact"]
                or "\\" in value["artifact"] or "\x00" in value["artifact"]):
            raise ValueError(f"{operation} result must identify one safe artifact filename")
        return value
    confirmation = {
        "app.launch": "launched",
        "app.stop": "stopped",
        "asset.load": "requested",
        "lifecycle.background": "backgrounded",
        "navigation.enter-domain": "requested",
        "scene.load": "requested",
        "scene.reload": "requested",
        "sound.play": "requested",
    }.get(operation)
    if confirmation is not None and value.get(confirmation) is not True:
        raise ValueError(f"{operation} result must confirm {confirmation}: true")
    if operation == "app.foreground" and not isinstance(value.get("foreground"), bool):
        raise ValueError("app.foreground result requires foreground: boolean")
    if operation == "app.process":
        running = value.get("running")
        identity = value.get("identity")
        if not isinstance(running, bool):
            raise ValueError("app.process result requires running: boolean")
        if running and (not isinstance(identity, str) or not identity):
            raise ValueError("running app.process result requires a non-empty identity")
        if not running and identity is not None:
            raise ValueError("stopped app.process result requires identity: null")
    return value


def validate_text_snapshot(value: object) -> dict:
    """Validate a privacy-bounded observation of the repository-owned test field."""
    if not isinstance(value, dict) or set(value) != {
            "focused", "keyboardVisible", "schemaVersion", "submittedCount", "value"}:
        raise ValueError("text.snapshot contains unsupported or missing fields")
    if value.get("schemaVersion") != TEXT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported text snapshot schema version")
    text = value.get("value")
    if (not isinstance(text, str) or len(text) > MAX_TEXT_CODEPOINTS
            or any(ord(character) < 32 or ord(character) == 127 for character in text)):
        raise ValueError("text.snapshot value must be bounded non-control Unicode")
    if not isinstance(value.get("focused"), bool):
        raise ValueError("text.snapshot focused must be boolean")
    if value.get("keyboardVisible") is not None and not isinstance(
            value["keyboardVisible"], bool):
        raise ValueError("text.snapshot keyboardVisible must be boolean or null")
    count = value.get("submittedCount")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("text.snapshot submittedCount must be non-negative")
    return value


def validate_render_snapshot(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
            "backend", "blackFrame", "frameSequence", "hardwareAccelerated",
            "schemaVersion", "surfaceVisible"}:
        raise ValueError("render.snapshot contains unsupported or missing fields")
    if (value.get("schemaVersion") != 1
            or not isinstance(value.get("backend"), str) or not value["backend"]
            or len(value["backend"]) > 64
            or not all(isinstance(value.get(field), bool) for field in (
                "blackFrame", "hardwareAccelerated", "surfaceVisible"))):
        raise ValueError("render.snapshot identity or state is invalid")
    sequence = value.get("frameSequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("render.snapshot frameSequence must be non-negative")
    return value


def validate_probe_snapshot(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 2:
        raise ValueError("probe snapshot must use schema version 2")
    root_fields = {
        "application", "asset", "avatar", "build", "domain", "input",
        "sampleEpochMs", "sampleSequence", "scene", "schemaVersion", "sound",
        "tablet", "view",
    }
    if "controller" in value:
        root_fields.add("controller")
    if "control" in value:
        root_fields.add("control")
    if "interaction" in value:
        root_fields.add("interaction")
    if "peer" in value:
        root_fields.add("peer")
    if "audio" in value:
        root_fields.add("audio")
    if "render" in value:
        root_fields.add("render")
    if "settings" in value:
        root_fields.add("settings")
    if "scriptedEntity" in value:
        root_fields.add("scriptedEntity")
    if "verticalEvents" in value:
        root_fields.add("verticalEvents")
    _require_exact_fields(value, root_fields, "probe snapshot")
    if (not isinstance(value.get("sampleEpochMs"), int)
            or isinstance(value["sampleEpochMs"], bool) or value["sampleEpochMs"] <= 0):
        raise ValueError("probe snapshot requires a positive sampleEpochMs")
    if (not isinstance(value.get("sampleSequence"), int)
            or isinstance(value["sampleSequence"], bool) or value["sampleSequence"] <= 0):
        raise ValueError("probe snapshot requires a positive sampleSequence")
    for field in ("build", "application", "domain", "input", "scene", "avatar",
                  "view", "tablet", "sound"):
        if not isinstance(value.get(field), dict):
            raise ValueError(f"probe snapshot requires object field {field}")

    build = value["build"]
    _require_exact_fields(build, {"date", "platform", "version"}, "probe build")
    if not all(isinstance(build.get(field), str) and build[field]
               for field in ("platform", "version", "date")):
        raise ValueError("probe build requires non-empty platform, version and date")

    application = value["application"]
    _require_exact_fields(application, {"foreground", "running"}, "probe application")
    if (not isinstance(application.get("running"), bool)
            or not isinstance(application.get("foreground"), bool)):
        raise ValueError("probe application requires running and foreground booleans")

    control = value.get("control")
    if control is not None:
        if not isinstance(control, dict):
            raise ValueError("probe control must be an object or null")
        _require_exact_fields(
            control, {"channel", "lastCommandId", "probe", "schemaVersion"},
            "probe control")
        if (control.get("schemaVersion") != 1
                or control.get("channel") != "android-debug-file-v1"
                or control.get("probe") != "overte_e2e_probe.js"
                or not isinstance(control.get("lastCommandId"), str)):
            raise ValueError("probe control has an invalid Android debug contract")

    domain = value["domain"]
    _require_exact_fields(
        domain, {"connected", "hostname", "id", "protocol", "serverless"},
        "probe domain")
    if (not isinstance(domain.get("connected"), bool)
            or not isinstance(domain.get("serverless"), bool)
            or not all(isinstance(domain.get(field), str)
                       for field in ("hostname", "id", "protocol"))):
        raise ValueError("probe domain requires connection, identity and protocol state")
    if domain["connected"] and (not domain["hostname"] or not domain["id"]):
        raise ValueError("connected probe domain requires hostname and id")

    input_state = value["input"]
    _require_exact_fields(
        input_state, {"advancedMovementControls", "dominantHand"}, "probe input")
    if (input_state.get("dominantHand") not in {"left", "right", "unknown"}
            or not isinstance(input_state.get("advancedMovementControls"), bool)):
        raise ValueError("probe input requires dominantHand and advancedMovementControls")

    scene = value["scene"]
    scene_fields = {
        "avatarAboveFloor", "collisionWall", "domainMarkerCount", "domainMarkers",
        "entityCount", "fixtureMarkerCount", "fixtureMarkers", "floorTopY", "ready",
        "spawnLocationObserved", "spawnValidated", "url",
    }
    if "commandId" in scene:
        scene_fields.add("commandId")
    _require_exact_fields(scene, scene_fields, "probe scene")
    entity_count = scene.get("entityCount")
    if (not isinstance(scene.get("ready"), bool) or not isinstance(entity_count, int)
            or isinstance(entity_count, bool) or entity_count < 0
            or not isinstance(scene.get("url"), str)):
        raise ValueError("probe scene requires url, ready and entityCount")
    if "commandId" in scene and not isinstance(scene["commandId"], str):
        raise ValueError("probe scene.commandId must be a string")
    _validate_marker_list(scene, "fixtureMarkerCount", "fixtureMarkers",
                          r"OVERTE_E2E_[A-Z_]+", "fixture")
    _validate_marker_list(scene, "domainMarkerCount", "domainMarkers",
                          r"OVERTE_E2E_DOMAIN_[A-Z]+", "domain")
    floor_top = scene.get("floorTopY")
    if floor_top is not None:
        _finite_number(floor_top, "probe scene.floorTopY")
    for field in ("avatarAboveFloor", "spawnLocationObserved", "spawnValidated"):
        if not isinstance(scene.get(field), bool):
            raise ValueError(f"probe scene.{field} must be boolean")
    wall = scene.get("collisionWall")
    if wall is not None:
        if not isinstance(wall, dict) or set(wall) != {"center", "dimensions", "name"}:
            raise ValueError("probe scene.collisionWall has an invalid shape")
        if wall.get("name") != "OVERTE_E2E_COLLISION_WALL":
            raise ValueError("probe scene.collisionWall has an invalid name")
        _validate_vector(wall.get("center"), "probe collision wall center")
        dimensions = _validate_vector(
            wall.get("dimensions"), "probe collision wall dimensions")
        if any(float(dimensions[axis]) <= 0.0 for axis in ("x", "y", "z")):
            raise ValueError("probe collision wall dimensions must be positive")

    avatar = value["avatar"]
    avatar_fields = {
        "bodyYawDegrees", "flying", "flyingEnabled", "inAir", "position", "velocity",
    }
    if "feetPosition" in avatar:
        avatar_fields.add("feetPosition")
    _require_exact_fields(avatar, avatar_fields, "probe avatar")
    _validate_vector(avatar.get("position"), "probe avatar.position")
    if "feetPosition" in avatar:
        _validate_vector(avatar.get("feetPosition"), "probe avatar.feetPosition")
    _validate_vector(avatar.get("velocity"), "probe avatar.velocity")
    _finite_number(avatar.get("bodyYawDegrees"), "probe avatar.bodyYawDegrees")
    for field in ("inAir", "flying", "flyingEnabled"):
        if not isinstance(avatar.get(field), bool):
            raise ValueError(f"probe avatar.{field} must be boolean")
    if avatar["flying"] and not avatar["inAir"]:
        raise ValueError("probe avatar cannot be flying while not inAir")

    vertical_events = value.get("verticalEvents")
    if vertical_events is not None:
        if not isinstance(vertical_events, dict):
            raise ValueError("probe verticalEvents must be an object")
        _require_exact_fields(vertical_events, {
            "flightCount", "jumpCompletedCount", "jumpCount",
            "lastFlightPeakY", "lastFlightStartY", "lastJumpLandingY",
            "lastJumpPeakY", "lastJumpStartY",
        }, "probe verticalEvents")
        for field in ("jumpCount", "jumpCompletedCount", "flightCount"):
            count = vertical_events.get(field)
            if (not isinstance(count, int) or isinstance(count, bool) or count < 0):
                raise ValueError(f"probe verticalEvents.{field} must be non-negative")
        if vertical_events["jumpCompletedCount"] > vertical_events["jumpCount"]:
            raise ValueError("probe completed jump count cannot exceed jump count")
        for field in ("lastJumpStartY", "lastJumpPeakY", "lastJumpLandingY",
                      "lastFlightStartY", "lastFlightPeakY"):
            if vertical_events.get(field) is not None:
                _finite_number(vertical_events[field], f"probe verticalEvents.{field}")
        if vertical_events["jumpCount"] == 0:
            if any(vertical_events[field] is not None for field in (
                    "lastJumpStartY", "lastJumpPeakY", "lastJumpLandingY")):
                raise ValueError("probe without jumps cannot contain jump heights")
        elif (vertical_events["lastJumpStartY"] is None
              or vertical_events["lastJumpPeakY"] is None
              or vertical_events["lastJumpPeakY"]
              < vertical_events["lastJumpStartY"]):
            raise ValueError("probe jump event requires ordered start and peak heights")
        if (vertical_events["jumpCount"] > 0
                and vertical_events["jumpCompletedCount"]
                == vertical_events["jumpCount"]
                and vertical_events["lastJumpLandingY"] is None):
            raise ValueError("probe completed jump requires a landing height")
        if vertical_events["flightCount"] == 0:
            if any(vertical_events[field] is not None for field in (
                    "lastFlightStartY", "lastFlightPeakY")):
                raise ValueError("probe without flights cannot contain flight heights")
        elif (vertical_events["lastFlightStartY"] is None
              or vertical_events["lastFlightPeakY"] is None
              or vertical_events["lastFlightPeakY"]
              < vertical_events["lastFlightStartY"]):
            raise ValueError("probe flight event requires ordered start and peak heights")
    view = value["view"]
    view_fields = {"orientation"}
    if "orientationHistory" in view:
        view_fields.add("orientationHistory")
    _require_exact_fields(view, view_fields, "probe view")
    _validate_vector(view.get("orientation"), "probe view.orientation")
    orientation_history = view.get("orientationHistory")
    if orientation_history is not None:
        if not isinstance(orientation_history, list) or len(orientation_history) > 48:
            raise ValueError("probe view.orientationHistory must be a bounded list")
        previous_sequence = 0
        for index, observation in enumerate(orientation_history):
            if not isinstance(observation, dict):
                raise ValueError("probe view orientation history entry must be an object")
            _require_exact_fields(
                observation, {"orientation", "sampleSequence"},
                f"probe view orientation history entry {index}")
            sequence = observation.get("sampleSequence")
            if (not isinstance(sequence, int) or isinstance(sequence, bool)
                    or sequence <= previous_sequence or sequence > value["sampleSequence"]):
                raise ValueError("probe view orientation history sequence is invalid")
            _validate_vector(
                observation.get("orientation"),
                f"probe view orientation history entry {index}.orientation")
            previous_sequence = sequence
    _require_exact_fields(value["tablet"], {"home", "open", "toolbarMode"}, "probe tablet")
    for field in ("open", "home", "toolbarMode"):
        if not isinstance(value["tablet"].get(field), bool):
            raise ValueError(f"probe tablet.{field} must be boolean")

    interaction = value.get("interaction")
    if interaction is not None:
        if not isinstance(interaction, dict):
            raise ValueError("probe interaction must be an object")
        _require_exact_fields(interaction, {
            "lastEntityName", "lastPointerId", "pressCount", "targetAvailable",
        }, "probe interaction")
        count = interaction.get("pressCount")
        pointer_id = interaction.get("lastPointerId")
        if (not isinstance(interaction.get("targetAvailable"), bool)
                or not isinstance(count, int) or isinstance(count, bool) or count < 0
                or not isinstance(interaction.get("lastEntityName"), str)):
            raise ValueError("probe interaction requires target state and a non-negative count")
        if (pointer_id is not None and (not isinstance(pointer_id, int)
                                       or isinstance(pointer_id, bool) or pointer_id < 0)):
            raise ValueError("probe interaction lastPointerId must be null or non-negative")
        if count == 0 and (interaction["lastEntityName"] or pointer_id is not None):
            raise ValueError("probe interaction without presses cannot contain last-event state")
        if count > 0 and interaction["lastEntityName"] != "OVERTE_E2E_INTERACTABLE":
            raise ValueError("probe interaction press must identify the controlled target")

    scripted = value.get("scriptedEntity")
    if scripted is not None:
        if not isinstance(scripted, dict):
            raise ValueError("probe scriptedEntity must be an object")
        _require_exact_fields(scripted, {
            "activationCount", "color", "loaded", "scriptUrl", "state",
            "targetAvailable",
        }, "probe scriptedEntity")
        count = scripted.get("activationCount")
        if (not isinstance(scripted.get("targetAvailable"), bool)
                or not isinstance(scripted.get("loaded"), bool)
                or not isinstance(scripted.get("scriptUrl"), str)
                or scripted.get("state") not in {"active", "idle", "unavailable"}
                or not isinstance(count, int) or isinstance(count, bool) or count < 0):
            raise ValueError("probe scriptedEntity state is invalid")
        color = scripted.get("color")
        if color is not None:
            if (not isinstance(color, dict) or set(color) != {"blue", "green", "red"}
                    or not all(isinstance(color[channel], int)
                               and not isinstance(color[channel], bool)
                               and 0 <= color[channel] <= 255
                               for channel in ("red", "green", "blue"))):
                raise ValueError("probe scriptedEntity color is invalid")
        if not scripted["targetAvailable"]:
            if scripted["loaded"] or scripted["scriptUrl"] or count != 0 \
                    or scripted["state"] != "unavailable" or color is not None:
                raise ValueError("unavailable scriptedEntity cannot contain observed state")
        elif scripted["loaded"] and not scripted["scriptUrl"]:
            raise ValueError("loaded scriptedEntity requires a script URL")
        if scripted["loaded"]:
            expected_state = "active" if count % 2 else "idle"
            expected_color = ({"red": 40, "green": 220, "blue": 100}
                              if expected_state == "active" else
                              {"red": 255, "green": 150, "blue": 40})
            if scripted["state"] != expected_state or color != expected_color:
                raise ValueError("probe scriptedEntity state does not match its activation count")

    peer = value.get("peer")
    if peer is not None:
        if not isinstance(peer, dict):
            raise ValueError("probe peer must be an object")
        _require_exact_fields(peer, {
            "displayName", "movementDistanceMeters", "observationCount", "position",
            "present", "sessionId",
        }, "probe peer")
        observations = peer.get("observationCount")
        distance = peer.get("movementDistanceMeters")
        if (not isinstance(peer.get("present"), bool)
                or not isinstance(peer.get("sessionId"), str)
                or not isinstance(peer.get("displayName"), str)
                or not isinstance(observations, int) or isinstance(observations, bool)
                or observations < 0):
            raise ValueError("probe peer identity or observation count is invalid")
        _finite_number(distance, "probe peer.movementDistanceMeters")
        if distance < 0.0:
            raise ValueError("probe peer movement distance must be non-negative")
        if peer["present"]:
            if (not peer["sessionId"] or peer["displayName"] != "OVERTE_E2E_PEER"
                    or peer["position"] is None or observations <= 0):
                raise ValueError("present probe peer requires controlled identity and position")
            _validate_vector(peer["position"], "probe peer.position")
        elif peer["sessionId"] or peer["displayName"] or peer["position"] is not None:
            raise ValueError("absent probe peer cannot contain current identity or position")

    audio = value.get("audio")
    if audio is not None:
        if not isinstance(audio, dict) or set(audio) != {"muted"} \
                or not isinstance(audio.get("muted"), bool):
            raise ValueError("probe audio requires exactly muted: boolean")
    settings = value.get("settings")
    if settings is not None:
        if (not isinstance(settings, dict)
                or set(settings) != {"audioWarnWhenMuted"}
                or not isinstance(settings.get("audioWarnWhenMuted"), bool)):
            raise ValueError("probe settings requires the safe audio warning boolean")
    render = value.get("render")
    if render is not None:
        if not isinstance(render, dict) or set(render) != {"frameCount", "lastFrameEpochMs"}:
            raise ValueError("probe render contains unsupported or missing fields")
        for field in ("frameCount", "lastFrameEpochMs"):
            number = render.get(field)
            if (not isinstance(number, int) or isinstance(number, bool) or number < 0):
                raise ValueError(f"probe render.{field} must be non-negative")
        if render["frameCount"] > 0 and render["lastFrameEpochMs"] <= 0:
            raise ValueError("probe rendered frames require a positive lastFrameEpochMs")

    controller = value.get("controller")
    if controller is not None:
        if not isinstance(controller, dict):
            raise ValueError("probe controller must be an object")
        axes = controller.get("axes")
        buttons = controller.get("buttons")
        poses = controller.get("poses")
        route = controller.get("route")
        axis_names = (
            "lx", "ly", "rx", "ry", "leftTrigger", "rightTrigger",
            "leftGrip", "rightGrip",
        )
        if not isinstance(axes, dict) or not all(
                isinstance(axes.get(name), (int, float))
                and not isinstance(axes.get(name), bool)
                and math.isfinite(float(axes[name]))
                for name in axis_names):
            raise ValueError("probe controller.axes requires finite standard input values")
        button_names = (
            "menu", "leftPrimary", "leftSecondary", "leftThumbstick", "leftTrigger",
            "rightPrimary", "rightSecondary", "rightThumbstick", "rightTrigger",
        )
        if not isinstance(buttons, dict) or not all(
                isinstance(buttons.get(name), bool) for name in button_names):
            raise ValueError("probe controller.buttons requires boolean standard input values")
        if not isinstance(poses, dict):
            raise ValueError("probe controller.poses must be an object")
        if route is not None:
            if not isinstance(route, dict):
                raise ValueError("probe controller.route must be an object")
            openxr_axes = route.get("openxrAxes")
            if openxr_axes is not None and (not isinstance(openxr_axes, dict) or not all(
                    isinstance(openxr_axes.get(axis), (int, float))
                    and not isinstance(openxr_axes.get(axis), bool)
                    and math.isfinite(float(openxr_axes[axis]))
                    for axis in ("lx", "ly", "rx", "ry"))):
                raise ValueError("probe controller.route openxrAxes must be finite or null")
            for name in ("standardLy", "translateZAction", "rawTranslateZDriveKey"):
                item = route.get(name)
                if (not isinstance(item, (int, float)) or isinstance(item, bool)
                        or not math.isfinite(float(item))):
                    raise ValueError(f"probe controller.route {name} must be finite")
            if not isinstance(route.get("translateZDriveKeyDisabled"), bool):
                raise ValueError("probe controller.route drive-key state must be boolean")
            vertical_names = ("translateYAction", "rawTranslateYDriveKey")
            if any(name in route for name in (*vertical_names, "translateYDriveKeyDisabled")):
                if not all(isinstance(route.get(name), (int, float))
                           and not isinstance(route[name], bool)
                           and math.isfinite(float(route[name])) for name in vertical_names):
                    raise ValueError("probe controller.route vertical drive state must be finite")
                if not isinstance(route.get("translateYDriveKeyDisabled"), bool):
                    raise ValueError("probe controller.route vertical drive-key state must be boolean")
        for hand in ("left", "right"):
            pose = poses.get(hand)
            if not isinstance(pose, dict) or not isinstance(pose.get("valid"), bool):
                raise ValueError(f"probe controller pose {hand} requires valid")
            if not pose["valid"]:
                if pose.get("translation") is not None or pose.get("rotation") is not None:
                    raise ValueError(f"probe invalid controller pose {hand} must be null")
                continue
            translation = pose.get("translation")
            rotation = pose.get("rotation")
            if not isinstance(translation, dict) or not all(
                    isinstance(translation.get(axis), (int, float))
                    and not isinstance(translation.get(axis), bool)
                    and math.isfinite(float(translation[axis]))
                    for axis in ("x", "y", "z")):
                raise ValueError(f"probe controller pose {hand} requires finite translation")
            if not isinstance(rotation, dict) or not all(
                    isinstance(rotation.get(axis), (int, float))
                    and not isinstance(rotation.get(axis), bool)
                    and math.isfinite(float(rotation[axis]))
                    for axis in ("x", "y", "z", "w")):
                raise ValueError(f"probe controller pose {hand} requires finite rotation")
    asset = value["asset"]
    if asset is not None:
        if not isinstance(asset, dict):
            raise ValueError("probe asset must be an object or null")
        asset_id = asset.get("assetId")
        resource = asset.get("resource")
        entity = asset.get("entity")
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("probe asset requires a non-empty assetId")
        if not isinstance(resource, dict):
            raise ValueError("probe asset requires resource evidence")
        if not isinstance(entity, dict):
            raise ValueError("probe asset requires entity evidence")
        _require_exact_fields(asset, {"assetId", "entity", "resource"}, "probe asset")
        _require_exact_fields(resource, {"state", "url"}, "probe asset resource")
        resource_url = resource.get("url")
        if not isinstance(resource_url, str) or "://" not in resource_url:
            raise ValueError("probe asset resource requires an absolute URL")
        if resource.get("state") not in {"queued", "loading", "loaded", "finished", "failed"}:
            raise ValueError("probe asset resource has an invalid state")
        _require_exact_fields(
            entity, {"id", "imageURL", "name", "naturalDimensions", "type"},
            "probe asset entity")
        if (not isinstance(entity.get("id"), str) or not entity["id"]
                or not isinstance(entity.get("name"), str) or not entity["name"]
                or entity.get("type") != "Image"):
            raise ValueError("probe asset entity requires id, name and Image type")
        image_url = entity.get("imageURL")
        if not isinstance(image_url, str) or image_url != resource_url:
            raise ValueError("probe asset entity imageURL must match the resource URL")
        dimensions = entity.get("naturalDimensions")
        if not isinstance(dimensions, dict) or not all(
                isinstance(dimensions.get(axis), (int, float))
                and not isinstance(dimensions.get(axis), bool)
                and math.isfinite(float(dimensions[axis]))
                for axis in ("x", "y", "z")):
            raise ValueError("probe asset entity requires finite naturalDimensions")
    sound = value["sound"]
    _require_exact_fields(sound, {
        "commandId", "commandObserved", "durationSeconds", "finishReason", "finished",
        "format", "injectorCreated", "playing", "resourceReady", "started", "url",
    }, "probe sound")
    boolean_fields = ("commandObserved", "resourceReady", "injectorCreated",
                      "started", "playing", "finished")
    if not all(isinstance(sound.get(field), bool) for field in boolean_fields):
        raise ValueError("probe sound state flags must be boolean")
    if (not isinstance(sound.get("commandId"), str)
            or not isinstance(sound.get("url"), str)
            or sound.get("format") not in {"unknown", "wav"}
            or sound.get("finishReason") not in {"none", "natural", "stopped"}):
        raise ValueError("probe sound identifiers or enums are invalid")
    duration = sound.get("durationSeconds")
    if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
            or not math.isfinite(float(duration)) or duration < 0.0):
        raise ValueError("probe sound durationSeconds must be finite and non-negative")
    if sound["commandObserved"] and (not sound["commandId"] or "://" not in sound["url"]):
        raise ValueError("probe sound observed command requires an ID and absolute URL")
    if sound["resourceReady"] and duration <= 0.0:
        raise ValueError("probe sound ready resource requires a positive duration")
    if sound["injectorCreated"] and not sound["resourceReady"]:
        raise ValueError("probe sound injector requires a ready resource")
    if sound["playing"] and (not sound["injectorCreated"] or not sound["started"]):
        raise ValueError("probe sound playing state requires a started injector")
    if sound["finished"] and (sound["playing"] or not sound["started"]
                              or sound["finishReason"] == "none"):
        raise ValueError("probe sound finished state is inconsistent")
    if not sound["finished"] and sound["finishReason"] != "none":
        raise ValueError("probe sound unfinished state cannot have a finish reason")
    return value


def _finite_number(value: object, label: str) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value))):
        raise ValueError(f"{label} must be finite numeric")
    return float(value)


def _require_exact_fields(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} contains unsupported or missing fields")


def _validate_vector(value: object, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError(f"{label} requires exactly numeric x/y/z")
    for axis in ("x", "y", "z"):
        _finite_number(value[axis], f"{label}.{axis}")
    return value


def _validate_marker_list(scene: dict, count_field: str, list_field: str,
                          pattern: str, label: str) -> None:
    count = scene.get(count_field)
    markers = scene.get(list_field)
    if (not isinstance(count, int) or isinstance(count, bool) or count < 0
            or not isinstance(markers, list) or markers != sorted(set(markers))
            or not all(isinstance(item, str) and re.fullmatch(pattern, item)
                       for item in markers)
            or count != len(markers)):
        raise ValueError(f"probe scene {list_field} must match {count_field}")
