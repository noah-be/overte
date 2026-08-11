#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ORIGINAL="$ROOT_DIR/world-copies/overte-hub-original.json"
OPTIMIZED="$ROOT_DIR/world-copies/overte-hub-pico4-optimized.json"
SPAWN_OPTIMIZED="$ROOT_DIR/world-copies/overte-hub-pico4-spawn-optimized.json"
ORIGINAL_SPAWN="$ROOT_DIR/world-copies/overte-hub-original-spawn.json"
OPTIMIZED_SPAWN="$ROOT_DIR/world-copies/overte-hub-pico4-optimized-spawn.json"
AGGRESSIVE="$ROOT_DIR/world-copies/overte-hub-pico4-aggressive.json"
ULTRA="$ROOT_DIR/world-copies/overte-hub-pico4-ultra.json"

command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }
for file in "$ORIGINAL" "$OPTIMIZED" "$SPAWN_OPTIMIZED" "$ORIGINAL_SPAWN" "$OPTIMIZED_SPAWN" "$AGGRESSIVE" "$ULTRA"; do
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

spawn_remaining_bad="$(jq '[.Entities[] | select((.script // "") | test("sitClient\\.js|script_server_crasher_client_console"; "i"))] | length' "$SPAWN_OPTIMIZED")"
[[ "$spawn_remaining_bad" -lt "$removed_scripts" ]] || { echo "spawn optimized fixture did not reduce measured startup scripts" >&2; exit 1; }

aggressive_waves="$(jq '[.Entities[] | select((.modelURL // "") | test("waves3600"; "i"))] | length' "$AGGRESSIVE")"
[[ "$aggressive_waves" == 0 ]] || { echo "aggressive fixture still contains waves3600" >&2; exit 1; }

ultra_waves="$(jq '[.Entities[] | select((.modelURL // "") | test("waves3600"; "i"))] | length' "$ULTRA")"
ultra_hdr="$(jq '[.Entities[] | select(.type == "Zone") | (.skybox.url // ""), (.ambientLight.ambientURL // "")] | map(select(test("https?://"))) | length' "$ULTRA")"
[[ "$ultra_waves" == 0 && "$ultra_hdr" == 4 ]] || { echo "ultra fixture retained unexpected heavy startup resources" >&2; exit 1; }

spawn_original_count="$(jq '.Entities | length' "$ORIGINAL_SPAWN")"
spawn_optimized_count="$(jq '.Entities | length' "$OPTIMIZED_SPAWN")"
[[ "$spawn_original_count" == "$original_count" && "$spawn_optimized_count" == "$optimized_count" ]] || {
    echo "spawn fixture entity counts diverged" >&2; exit 1;
}

echo "PASS serverless fixture schema/entities/scripts (entities=$original_count removed_scripts=$removed_scripts aggressive_waves=$aggressive_waves ultra_waves=$ultra_waves ultra_hdr=$ultra_hdr)"
