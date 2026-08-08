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

echo 'Phone forward pass trim checks passed.'
