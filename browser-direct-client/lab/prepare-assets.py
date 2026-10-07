#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Import actual historical Hub model closures into this stopped, private lab.

The downloaded files are ephemeral, with original/served hashes recorded.
Only absolute same-CDN references in textual manifests change to ATP; image and
geometry bytes, relative paths, material values and quality remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urldefrag, urljoin, urlsplit
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "build/browser-direct/lab"
SOURCE_HOSTS = {"content.overte.org", "files.thingvellir.net"}
PREFIX = "/hub"
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
ASSET = re.compile(r"\.(?:fst|fbx|obj|gltf|glb|json|png|jpe?g|webp|gif|bmp|svg|ktx2?|exr|hdr|bin)(?:[?#].*)?$", re.I)


def canonical(url: str) -> str:
    result = urldefrag(url)[0]
    parsed = urlsplit(result)
    if parsed.scheme != "https" or parsed.netloc not in SOURCE_HOSTS or parsed.username:
        raise ValueError("Only the two declared actual historical Hub asset origins are imported")
    return result


def native_path(url: str) -> str:
    parsed = urlsplit(url)
    prefix = PREFIX if parsed.netloc == "content.overte.org" else "/hub-external/" + parsed.netloc
    path = prefix + unquote(parsed.path)
    if "\0" in path or ".." in Path(path).parts:
        raise ValueError("Invalid native asset path")
    return path


def references(url: str, data: bytes) -> list[str]:
    extension = urlsplit(url).path.lower()
    found = []
    if extension.endswith(".fst"):
        text = data.decode("utf-8")
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if not separator:
                continue
            if key.strip() == "filename":
                found.append(value.strip())
            elif key.strip() == "materialMap":
                walk = [json.loads(value)]
                while walk:
                    item = walk.pop()
                    if isinstance(item, dict):
                        walk.extend(item.values())
                    elif isinstance(item, list):
                        walk.extend(item)
                    elif isinstance(item, str) and ASSET.search(item):
                        found.append(item)
    elif extension.endswith((".json", ".gltf")):
        walk = [json.loads(data)]
        while walk:
            item = walk.pop()
            if isinstance(item, dict):
                # Preserve the complete actual metadata closure. The browser
                # reads the original images; native visitors may select the
                # original compressed KTX variant for their hardware format.
                walk.extend(item.values())
            elif isinstance(item, list):
                walk.extend(item)
            elif isinstance(item, str) and ASSET.search(item):
                found.append(item)
    return [canonical(urljoin(url, item)) for item in found if not item.startswith(("data:", "atp:"))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-models", action="store_true")
    parser.add_argument("--include-zones", action="store_true",
                        help="include actual skybox and ambient image closures from the same historical scene")
    args = parser.parse_args()
    registry = STATE / "runtime/processes.json"
    if registry.exists() and json.loads(registry.read_text()):
        raise RuntimeError("Stop this lab's domain and assignments before changing its asset storage")
    scene = json.loads((STATE / "scene/hub-subset.json").read_text())
    initial = sorted({canonical(entity["modelURL"]) for entity in scene["Entities"]
                      if entity.get("modelURL") and (args.all_models or "lounge-chair-1d" in entity["modelURL"])})
    zone_assets = sorted({canonical(url) for entity in scene["Entities"] if entity.get("type") == "Zone"
                          for url in (entity.get("skybox", {}).get("url"), entity.get("ambientLight", {}).get("ambientURL"))
                          if url}) if args.include_zones else []
    queue = deque([*initial, *zone_assets])
    original = STATE / "downloaded-assets"
    mirror = STATE / "https-assets"
    files = STATE / "assets/files"
    for directory in (original, mirror, files):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    seen, records, errors, mappings = set(), [], [], {}
    total = 0
    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        if len(seen) >= 512:
            raise RuntimeError("The declared model closure exceeds 512 files")
        seen.add(url)
        try:
            path = native_path(url)
            cached = original / hashlib.sha256(url.encode()).hexdigest()
            if cached.exists():
                data = cached.read_bytes()
                content_type = "cached; see path extension"
            else:
                with urlopen(url, timeout=20) as response:
                    data = response.read(MAX_FILE + 1)
                    content_type = response.headers.get("Content-Type", "")
                if len(data) > MAX_FILE:
                    raise RuntimeError("Actual asset exceeds the 64 MiB browser limit")
                cached.write_bytes(data)
            total += len(data)
            if total > MAX_TOTAL:
                raise RuntimeError("The declared model closure exceeds 512 MiB")
            queue.extend(references(url, data))
            source_hash = hashlib.sha256(data).hexdigest()
            served = data
            textual = urlsplit(url).path.lower().endswith((".fst", ".json", ".gltf"))
            if textual:
                for host in sorted(SOURCE_HOSTS):
                    prefix = PREFIX if host == "content.overte.org" else "/hub-external/" + host
                    served = served.replace(("https://" + host + "/").encode(), ("atp:" + prefix + "/").encode())
            served_hash = hashlib.sha256(served).hexdigest()
            (files / served_hash).write_bytes(served)
            target = mirror / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(served)
            if path in mappings and mappings[path] != served_hash:
                raise RuntimeError("Different actual content maps to the same native path")
            mappings[path] = served_hash
            records.append({"sourceURL": url, "relativePath": path.lstrip("/"),
                            "atpURL": "atp:" + path, "sourceSHA256": source_hash,
                            "servedSHA256": served_hash, "sourceBytes": len(data),
                            "servedBytes": len(served), "contentType": content_type,
                            "referenceOnlyAdaptation": served != data})
            print(f"Imported {len(records)} actual files ({total} source bytes)", flush=True)
        except Exception as error:
            errors.append({"sourceURL": url, "error": str(error)})
            print(f"Unavailable actual asset: {urlsplit(url).path}: {error}", flush=True)
    (STATE / "assets/map.json").write_text(json.dumps(mappings, indent=2) + "\n")
    manifest = {"schema": 1, "createdUTC": datetime.now(timezone.utc).isoformat(),
                "sourceSceneSHA256": hashlib.sha256((STATE / "scene/hub-subset.json").read_bytes()).hexdigest(),
                "initialModels": initial, "initialZoneAssets": zone_assets,
                "allowedSourceHosts": sorted(SOURCE_HOSTS), "source": "actual historical overte_hub asset URLs",
                "publicServerModified": False, "generatedVisualAssets": False,
                "sourceByteTotal": total, "records": records, "unavailable": errors,
                "storage": "ignored private lab only; no third-party asset bytes redistributed in Git"}
    (STATE / "scene/asset-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if errors:
        raise SystemExit("Some actual Hub assets are unavailable; retain failures as acceptance evidence")


if __name__ == "__main__":
    main()
