#!/usr/bin/env bash

set -euo pipefail

ANDROID_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ANDROID_DIR}/.." && pwd)"
GRADLE_FILE="${ANDROID_DIR}/apps/phoneInterface/build.gradle"
SERVERLESS_DIR="${REPO_ROOT}/interface/resources/serverless"

grep -q "include '\*.json'" "${GRADLE_FILE}" || {
    echo "phone packaging must restrict loose serverless assets to root JSON files" >&2
    exit 1
}

python3 - "${SERVERLESS_DIR}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
bad_references = []

def inspect(value, source, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            inspect(child, source, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            inspect(child, source, f"{path}/{index}")
    elif isinstance(value, str):
        resource_key = any(token in path.lower() for token in
                           ("url", "script", "texture", "model", "sound"))
        if resource_key and "/serverless/" in value and not value.startswith("qrc:/"):
            bad_references.append((source.name, path, value))

scenes = sorted(root.glob("*.json"))
if not scenes:
    raise SystemExit("no root serverless JSON scenes found")

for scene in scenes:
    with scene.open(encoding="utf-8") as stream:
        inspect(json.load(stream), scene)

if bad_references:
    for source, path, value in bad_references:
        print(f"{source}{path}: non-qrc packaged resource reference: {value}", file=sys.stderr)
    raise SystemExit(1)

embedded = [path for path in root.rglob("*") if path.is_file() and path.parent != root]
if not embedded:
    raise SystemExit("no embedded serverless resources found to validate")

loose_bytes = sum(path.stat().st_size for path in scenes)
embedded_bytes = sum(path.stat().st_size for path in embedded)
print(f"PASS phone serverless packaging: {len(scenes)} loose JSON scenes; "
      f"{len(embedded)} RCC-only resources avoid {embedded_bytes} duplicate bytes "
      f"({loose_bytes} loose bytes remain)")
PY
