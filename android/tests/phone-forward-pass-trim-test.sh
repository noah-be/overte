#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_file="$script_dir/../../libraries/render-utils/src/RenderForwardTask.cpp"

awk '
    /#if !defined\(ANDROID_APP_PHONE_INTERFACE\)/ { guarded = 1 }
    guarded && /task\.addJob<BloomEffect>/ { bloom = 1 }
    bloom && /#endif/ { closed = 1; exit }
    END { exit !(guarded && bloom && closed) }
' "$source_file" || {
    echo 'FAIL: phone forward graph still dispatches the disabled bloom task' >&2
    exit 1
}

grep -Eq 'task\.addJob<ToneMapAndResample>' "$source_file" || {
    echo 'FAIL: required phone tone-map/resample pass is missing' >&2
    exit 1
}

for job in PrepareStencil DrawMetaBounds DrawBounds DrawTransparentBounds DrawZones DrawZoneStack; do
    awk -v job="$job" '
        /#if !defined\(ANDROID_APP_PHONE_INTERFACE\)/ { guarded = 1 }
        guarded && index($0, "\"" job "\"") { found = 1 }
        found && /#endif/ { closed = 1; exit }
        END { exit !(guarded && found && closed) }
    ' "$source_file" || {
        echo "FAIL: phone forward graph still dispatches $job" >&2
        exit 1
    }
done

grep -Eq 'task\.addJob<RenderSimulateTask>\("RenderSimulation"' "$source_file" || {
    echo 'FAIL: required phone render simulation was removed' >&2
    exit 1
}

echo 'Phone forward pass trim checks passed.'
