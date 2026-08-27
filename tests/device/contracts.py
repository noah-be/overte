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


def validate_operation_arguments(operation: str, value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("operation arguments must be an object")
    if operation == "input.jump" and value:
        raise ValueError("input.jump does not accept arguments")
    if operation == "input.fly":
        if set(value) != {"durationSeconds"}:
            raise ValueError("input.fly requires only durationSeconds")
        duration = value["durationSeconds"]
        if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                or not math.isfinite(float(duration))
                or not 0.1 <= float(duration) <= MAX_FLY_DURATION_SECONDS):
            raise ValueError(
                f"input.fly durationSeconds must be from 0.1 through "
                f"{MAX_FLY_DURATION_SECONDS}")
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


def validate_performed_result(operation: str, value: object) -> dict:
    if not isinstance(value, dict) or value.get("performed") is not True:
        raise ValueError(f"{operation} result must confirm performed: true")
    return value


def validate_probe_snapshot(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise ValueError("probe snapshot must use schema version 1")
    if (not isinstance(value.get("sampleEpochMs"), int)
            or isinstance(value["sampleEpochMs"], bool) or value["sampleEpochMs"] <= 0):
        raise ValueError("probe snapshot requires a positive sampleEpochMs")
    sample_sequence = value.get("sampleSequence")
    if sample_sequence is not None and (
            not isinstance(sample_sequence, int) or isinstance(sample_sequence, bool)
            or sample_sequence <= 0):
        raise ValueError("probe snapshot sampleSequence must be a positive integer")
    required_objects = ("build", "application", "scene", "avatar", "view", "tablet")
    for field in required_objects:
        if not isinstance(value.get(field), dict):
            raise ValueError(f"probe snapshot requires object field {field}")
    build = value["build"]
    if not all(isinstance(build.get(field), str) and build[field]
               for field in ("platform", "version", "date")):
        raise ValueError("probe build requires non-empty platform, version and date")
    application = value["application"]
    if not isinstance(application.get("running"), bool):
        raise ValueError("probe application.running must be boolean")
    domain = value.get("domain")
    if domain is not None:
        if (not isinstance(domain, dict)
                or not isinstance(domain.get("connected"), bool)
                or not isinstance(domain.get("serverless"), bool)
                or not all(isinstance(domain.get(field), str)
                           for field in ("hostname", "id", "protocol"))):
            raise ValueError("probe domain requires connection, identity and protocol state")
        if domain["connected"] and (not domain["hostname"] or not domain["id"]):
            raise ValueError("connected probe domain requires hostname and id")
    input_state = value.get("input")
    if input_state is not None:
        if (not isinstance(input_state, dict)
                or input_state.get("dominantHand") not in {"left", "right"}
                or not isinstance(input_state.get("advancedMovementControls"), bool)):
            raise ValueError("probe input requires dominantHand and advancedMovementControls")
    scene = value["scene"]
    entity_count = scene.get("entityCount")
    if (not isinstance(scene.get("ready"), bool) or not isinstance(entity_count, int)
            or isinstance(entity_count, bool) or entity_count < 0):
        raise ValueError("probe scene requires ready and entityCount")
    domain_marker_count = scene.get("domainMarkerCount")
    if domain_marker_count is not None and (
            not isinstance(domain_marker_count, int)
            or isinstance(domain_marker_count, bool) or domain_marker_count < 0):
        raise ValueError("probe scene domainMarkerCount must be a non-negative integer")
    domain_markers = scene.get("domainMarkers")
    if domain_markers is not None and (
            not isinstance(domain_markers, list)
            or domain_markers != sorted(set(domain_markers))
            or not all(isinstance(item, str) and re.fullmatch(
                r"OVERTE_E2E_DOMAIN_[A-Z]+", item) for item in domain_markers)
            or domain_marker_count != len(domain_markers)):
        raise ValueError("probe scene domainMarkers must match domainMarkerCount")
    for owner, field in ((value["avatar"], "position"), (value["view"], "orientation")):
        vector = owner.get(field)
        if not isinstance(vector, dict) or not all(
                isinstance(vector.get(axis), (int, float)) and not isinstance(vector.get(axis), bool)
                and math.isfinite(float(vector[axis]))
                for axis in ("x", "y", "z")):
            raise ValueError(f"probe {field} requires numeric x/y/z")
    avatar = value["avatar"]
    for field in ("inAir", "flying", "flyingEnabled"):
        if not isinstance(avatar.get(field), bool):
            raise ValueError(f"probe avatar.{field} must be boolean")
    if avatar["flying"] and not avatar["inAir"]:
        raise ValueError("probe avatar cannot be flying while not inAir")
    if not isinstance(value["tablet"].get("open"), bool):
        raise ValueError("probe tablet.open must be boolean")
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
    asset = value.get("asset")
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
        resource_url = resource.get("url")
        if not isinstance(resource_url, str) or "://" not in resource_url:
            raise ValueError("probe asset resource requires an absolute URL")
        if resource.get("state") not in {"queued", "loading", "loaded", "finished", "failed"}:
            raise ValueError("probe asset resource has an invalid state")
        if not isinstance(entity, dict):
            raise ValueError("probe asset requires entity evidence")
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
    sound = value.get("sound")
    if sound is not None:
        if not isinstance(sound, dict):
            raise ValueError("probe sound must be an object")
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
