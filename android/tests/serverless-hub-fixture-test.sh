#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ORIGINAL="$ROOT_DIR/world-copies/overte-hub-original.json"
OPTIMIZED="$ROOT_DIR/world-copies/overte-hub-pico4-optimized.json"
ORIGINAL_SPAWN="$ROOT_DIR/world-copies/overte-hub-original-spawn.json"
OPTIMIZED_SPAWN="$ROOT_DIR/world-copies/overte-hub-pico4-optimized-spawn.json"

command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }
for file in "$ORIGINAL" "$OPTIMIZED" "$ORIGINAL_SPAWN" "$OPTIMIZED_SPAWN"; do
    jq -e 'type == "object" and .DataVersion == 3 and (.Entities | type == "array") and (.Paths["/"] | type == "string")' "$file" >/dev/null
done

original_count="$(jq '.Entities | length' "$ORIGINAL")"
optimized_count="$(jq '.Entities | length' "$OPTIMIZED")"
[[ "$original_count" == "$optimized_count" ]] || { echo "entity count changed" >&2; exit 1; }

original_ids="$(jq -r '.Entities[].id' "$ORIGINAL" | sort)"
optimized_ids="$(jq -r '.Entities[].id' "$OPTIMIZED" | sort)"
[[ "$original_ids" == "$optimized_ids" ]] || { echo "entity IDs changed" >&2; exit 1; }

remaining_bad="$(jq '[.Entities[] | select((.script // "") | test("sitClient\\.js|script_server_crasher_client_console"; "i"))] | length' "$OPTIMIZED")"
[[ "$remaining_bad" == 0 ]] || { echo "optimized fixture still contains measured startup scripts" >&2; exit 1; }

removed_scripts="$(jq '[.Entities[] | select((.script // "") | test("sitClient\\.js|script_server_crasher_client_console"; "i"))] | length' "$ORIGINAL")"
[[ "$removed_scripts" -gt 0 ]] || { echo "no measured scripts removed" >&2; exit 1; }

spawn_original_count="$(jq '.Entities | length' "$ORIGINAL_SPAWN")"
spawn_optimized_count="$(jq '.Entities | length' "$OPTIMIZED_SPAWN")"
[[ "$spawn_original_count" == "$original_count" && "$spawn_optimized_count" == "$optimized_count" ]] || {
    echo "spawn fixture entity counts diverged" >&2; exit 1;
}

echo "PASS serverless fixture schema/entities/scripts (entities=$original_count removed_scripts=$removed_scripts)"
