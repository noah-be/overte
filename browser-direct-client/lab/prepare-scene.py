#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Derive a local test scene from the repository's actual historical Hub snapshot."""
from __future__ import annotations

from collections import Counter
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "build/browser-direct/lab"
SOURCE = REPO / "interface/resources/serverless/overte-hub-original.json"
SOURCE_SHA256 = "f104f22166f4a085240291bb3ac800eb510b08aee19320055a7e32a16599a509"
CENTER = (155.084, -98.5, -397.328)
HTTPS_BRIDGE_ENTITY = "{b42a2c92-2a33-400d-a6b4-30e3d3ff2282}"
HTTPS_ORIGIN = "https://127.0.0.1:46119"


def prepare() -> dict:
    original = SOURCE.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("Hub fixture changed; review and update its pinned source identity")
    snapshot = json.loads(original)
    source_entities = snapshot["Entities"]
    selected = set()
    by_id = {entity["id"]: entity for entity in source_entities}
    for entity in source_entities:
        position, size = entity.get("position", {}), entity.get("dimensions", {})
        distance = math.sqrt(sum((position.get(axis, 0) - center) ** 2
                                 for axis, center in zip("xyz", CENTER)))
        radius = math.sqrt(sum(size.get(axis, 0) ** 2 for axis in "xyz")) / 2
        if distance <= 30 + radius or entity["type"] == "Zone":
            selected.add(entity["id"])
    # Retain parent transforms and their children rather than flattening models.
    while True:
        extended = set(selected)
        for entity in source_entities:
            if entity["id"] in selected and entity.get("parentID") in by_id:
                extended.add(entity["parentID"])
            if entity.get("parentID") in selected:
                extended.add(entity["id"])
        if extended == selected:
            break
        selected = extended
    excluded = Counter()
    entities = []
    for entity in source_entities:
        if entity["id"] not in selected:
            continue
        safe = dict(entity)
        # Remote world scripts are not executed by the isolated laboratory.
        # Rendering, collision, model, texture, material and transform data remain.
        for key in ("script", "serverScripts", "scriptTimestamp", "userData"):
            if key in safe:
                excluded[key] += 1
                safe.pop(key)
        entities.append(safe)
    result = {key: value for key, value in snapshot.items() if key != "Entities"}
    result["Entities"] = entities
    payload = (json.dumps(result, separators=(",", ":")) + "\n").encode()
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    scene = ROOT / "scene/hub-subset.json"
    scene.parent.mkdir(parents=True, exist_ok=True)
    scene.write_bytes(payload)
    (scene.parent / "hub-subset.json.gz").write_bytes(gzip.compress(payload, mtime=0))
    manifest = {
        "source": str(SOURCE.relative_to(REPO)), "sourceSHA256": SOURCE_SHA256,
        "sourceLastCommit": "5ac64721763a8423bea82b744a58513ab3d7017c",
        "contentVersion": "2019-12-06_12-12-23",
        "referencePlace": "overte_hub", "historicalSnapshot": True,
        "livePublicServerTest": False, "sourceEntityCount": len(source_entities),
        "selection": {"center": list(CENTER), "radiusMetres": 30,
                      "keepIntersectingBounds": True, "keepZonesAndParentTrees": True},
        "entityCount": len(entities), "entityTypes": dict(Counter(e["type"] for e in entities)),
        "removedExecutableAndScriptData": dict(excluded),
        "sceneSHA256": hashlib.sha256(payload).hexdigest(),
        "assets": "Original HTTPS URLs, fetched into an isolated browser/native cache at runtime.",
        "assetLicenseStatus": "Not established by this fixture; CDN asset bytes remain local and are not packaged.",
        "redistribution": "No downloaded third-party asset bytes or copied Hub scene are added to Git.",
    }
    (ROOT / "scene/provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def derive_atp_scene() -> dict:
    registry = ROOT / "runtime/processes.json"
    if registry.exists() and json.loads(registry.read_text()):
        raise RuntimeError("Stop the owned domain before deriving its ATP scene")
    scene = ROOT / "scene/hub-subset.json"
    payload = scene.read_bytes()
    source_hash = hashlib.sha256(payload).hexdigest()
    assets = json.loads((ROOT / "scene/asset-provenance.json").read_text())
    if assets["sourceSceneSHA256"] != source_hash or assets.get("unavailable"):
        raise RuntimeError("The exact historical selection needs a complete verified asset closure")
    records = assets["records"]
    by_source = {record["sourceURL"]: record for record in records}
    for record in records:
        path = (ROOT / "https-assets" / record["relativePath"]).resolve()
        if not path.is_relative_to((ROOT / "https-assets").resolve()):
            raise RuntimeError("An asset manifest path leaves its owned mirror")
        data = path.read_bytes()
        stored = (ROOT / "assets/files" / record["servedSHA256"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != record["servedSHA256"] or stored != data:
            raise RuntimeError("The served asset bytes differ from their recorded import identity")
    snapshot = json.loads(payload)
    changes = []
    zone_changes = []
    for entity in snapshot["Entities"]:
        original = entity.get("modelURL")
        if original:
            record = by_source.get(original)
            if not record:
                raise RuntimeError("A selected actual Hub model has no imported asset closure")
            entity["modelURL"] = record["atpURL"]
            changes.append({"entityID": entity["id"], "sourceModelURL": original,
                            "servedModelURL": record["atpURL"]})
        if entity.get("type") == "Zone":
            for group, field in (("skybox", "url"), ("ambientLight", "ambientURL")):
                properties = entity.get(group, {})
                original = properties.get(field)
                if not original:
                    continue
                record = by_source.get(original)
                if not record:
                    raise RuntimeError("Import the complete actual Zone assets with --include-zones")
                properties[field] = record["atpURL"]
                zone_changes.append({"entityID": entity["id"], "property": f"{group}.{field}",
                                     "sourceURL": original, "servedURL": record["atpURL"]})
    # Existing native AssetServer semantics: a hidden baked mapping that points
    # at the original hash disables baking without changing geometry or pixels.
    mappings_path = ROOT / "assets/map.json"
    mappings = json.loads(mappings_path.read_text())
    disabled = []
    for record in records:
        suffix = Path(record["relativePath"]).suffix.lower()
        baked = "asset.fbx" if suffix == ".fbx" else "texture.ktx" if suffix in {
            ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga", ".tif", ".tiff", ".exr", ".hdr"
        } else None
        if not baked:
            continue
        key = f"/.baked/{record['servedSHA256']}/{baked}"
        if key in mappings and mappings[key] != record["servedSHA256"]:
            raise RuntimeError("Existing baked output must be retained as separate test evidence")
        mappings[key] = record["servedSHA256"]
        disabled.append(key)
    mappings_path.write_text(json.dumps(mappings, indent=2) + "\n")
    derived = (json.dumps(snapshot, separators=(",", ":")) + "\n").encode()
    target = scene.parent / "hub-with-atp.json"
    target.write_bytes(derived)
    target.with_suffix(".json.gz").write_bytes(gzip.compress(derived, mtime=0))
    manifest = {
        "label": "Actual historical Hub selection with locally imported ATP model and Zone URLs",
        "historicalSourceScene": scene.name, "historicalSourceSHA256": source_hash,
        "runtimeScene": target.name, "sceneSHA256": hashlib.sha256(derived).hexdigest(),
        "entityCount": len(snapshot["Entities"]), "changedModelURLs": len(changes),
        "changedZoneURLs": len(zone_changes),
        "changedEntityProperties": ["modelURL", "skybox.url", "ambientLight.ambientURL"],
        "transformsMaterialsAndQualityChanged": False,
        "models": changes, "zoneAssets": zone_changes, "assetFileCount": len(records),
        "assetManifestSHA256": hashlib.sha256((scene.parent / "asset-provenance.json").read_bytes()).hexdigest(),
        "nativeBakingDisabledMappings": len(set(disabled)),
        "nativeBakingPolicy": "Original-hash self mappings via existing AssetServer setBakingEnabled semantics",
        "assetLicenseStatus": "Not established by this fixture; CDN asset bytes remain local and are not packaged.",
        "publicServerModified": False, "livePublicServerTest": False,
    }
    (scene.parent / "atp-scene-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def derive_https_scene() -> dict:
    registry = ROOT / "runtime/processes.json"
    if registry.exists() and json.loads(registry.read_text()):
        raise RuntimeError("Stop the owned domain before deriving its mixed HTTPS scene")
    scene = ROOT / "scene/hub-with-atp.json"
    payload = scene.read_bytes()
    snapshot = json.loads(payload)
    assets_path = scene.parent / "asset-provenance.json"
    assets = json.loads(assets_path.read_text())
    base_manifest = json.loads((scene.parent / "atp-scene-provenance.json").read_text())
    if base_manifest["sceneSHA256"] != hashlib.sha256(payload).hexdigest() or \
            base_manifest["assetManifestSHA256"] != hashlib.sha256(assets_path.read_bytes()).hexdigest():
        raise RuntimeError("Prepare the exact current ATP scene before its HTTPS variant")
    entity = next(value for value in snapshot["Entities"] if value["id"] == HTTPS_BRIDGE_ENTITY)
    record = next(value for value in assets["records"] if value["atpURL"] == entity["modelURL"])
    directory = Path(record["relativePath"]).parent
    closure = [value for value in assets["records"]
               if Path(value["relativePath"]).is_relative_to(directory)]
    if not closure or any(value["sourceSHA256"] != value["servedSHA256"] for value in closure):
        raise RuntimeError("The selected HTTPS bridge needs its unchanged original relative closure")
    original = entity["modelURL"]
    entity["modelURL"] = f"{HTTPS_ORIGIN}/{record['relativePath']}"
    derived = (json.dumps(snapshot, separators=(",", ":")) + "\n").encode()
    target = scene.parent / "hub-with-atp-and-https.json"
    target.write_bytes(derived)
    target.with_suffix(".json.gz").write_bytes(gzip.compress(derived, mtime=0))
    manifest = {
        "label": "Actual Hub selection with one original-byte HTTPS bridge and native ATP assets",
        "baseScene": scene.name, "baseSceneSHA256": hashlib.sha256(payload).hexdigest(),
        "runtimeScene": target.name, "sceneSHA256": hashlib.sha256(derived).hexdigest(),
        "entityCount": len(snapshot["Entities"]), "httpsEntityID": HTTPS_BRIDGE_ENTITY,
        "baseModelURL": original, "httpsModelURL": entity["modelURL"],
        "changesFromBase": ["modelURL on the existing bridge entity"],
        "transformsMaterialsAndQualityChanged": False, "remainingATPModels": 54,
        "httpsClosure": closure, "httpsClosureUsesOriginalBytes": True,
        "assetManifestSHA256": hashlib.sha256(assets_path.read_bytes()).hexdigest(),
        "publicServerModified": False, "livePublicServerTest": False,
    }
    (scene.parent / "mixed-scene-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    remaining = []
    for selected in snapshot["Entities"]:
        fields = (("compoundShapeURL", selected.get("compoundShapeURL")),
                  ("animation.url", (selected.get("animation") or {}).get("url")))
        for field, url in fields:
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                remaining.append({"entityID": selected["id"], "field": field,
                                  "sourceURL": url, "adapted": False,
                                  "reason": "Retained original reference; no verified imported auxiliary closure"})
    audit = {"schema": 1, "sceneSHA256": manifest["sceneSHA256"],
             "remainingSourceURLFields": remaining, "compoundHullParityClaimed": False,
             "entityAnimationParityClaimed": False}
    audit_path = scene.parent / "remaining-source-urls.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    audit_path.chmod(0o600)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--with-assets", action="store_true")
    selection.add_argument("--with-https-bridge", action="store_true")
    arguments = parser.parse_args()
    if arguments.with_https_bridge:
        derive_atp_scene()
        print(json.dumps(derive_https_scene(), indent=2))
    elif arguments.with_assets:
        print(json.dumps(derive_atp_scene(), indent=2))
    else:
        print(json.dumps(prepare(), indent=2))
