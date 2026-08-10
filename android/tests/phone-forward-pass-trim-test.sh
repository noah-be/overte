#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_file="$script_dir/../../libraries/render-utils/src/RenderForwardTask.cpp"
readonly fetch_file="$script_dir/../../libraries/render/src/render/RenderFetchCullSortTask.cpp"

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

awk '
    /void DrawForward::run/ { in_run = 1 }
    in_run && /const auto& inItems = inputs.get0\(\)/ { items = NR }
    in_run && /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ { phone_guard = NR }
    in_run && /if \(inItems\.empty\(\)\)/ { empty_return = NR }
    in_run && empty_return && /return;/ { returned = NR }
    in_run && returned && /#endif/ { guard_end = NR }
    in_run && /DependencyManager::get<DeferredLightingEffect>/ { lighting = NR; exit }
    END {
        exit !(items && phone_guard > items && empty_return > phone_guard && returned > empty_return &&
            guard_end > returned && lighting > guard_end)
    }
' "$source_file" || {
    echo 'FAIL: phone empty forward buckets still bind lighting resources' >&2
    exit 1
}

awk '
    /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ { guarded = 1 }
    guarded && /const auto mirrors = filteredSpatialBuckets\[MIRROR_BUCKET\]/ { passthrough = 1 }
    passthrough && /#else/ { alternate = 1 }
    alternate && /"DepthSortMirrors"/ { non_phone_sort = 1 }
    non_phone_sort && /#endif/ { closed = 1; exit }
    END { exit !(guarded && passthrough && alternate && non_phone_sort && closed) }
' "$fetch_file" || {
    echo 'FAIL: phone still depth-sorts the unrendered mirror bucket' >&2
    exit 1
}

echo 'Phone forward pass trim checks passed.'
