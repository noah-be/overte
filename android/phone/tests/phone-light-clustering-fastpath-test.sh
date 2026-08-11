#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly header="$repo_root/libraries/render-utils/src/LightClusters.h"
readonly source="$repo_root/libraries/render-utils/src/LightClusters.cpp"

failures=0
checks=0

check() {
    local description="$1"
    shift
    checks=$((checks + 1))
    if "$@"; then
        printf 'PASS %s\n' "$description"
    else
        failures=$((failures + 1))
        printf 'FAIL %s\n' "$description" >&2
    fi
}

check "disabled cluster cache has explicit state" \
    grep -Eq '_disabledClustersInitialized[[:space:]]*\{[[:space:]]*false[[:space:]]*\}' "$header"
check "disabled cluster cache owns a genuinely empty light frame" \
    grep -Eq '_emptyLightFrame.*make_shared<LightStage::Frame>' "$header"
check "configuration invalidates cached empty clusters" \
    grep -Eq '_disabledClustersInitialized[[:space:]]*=[[:space:]]*false' "$source"

check "disabled fastpath initializes once and returns before active clustering" awk '
    /if \(!localLightingEnabled\)/ { disabled = 1 }
    disabled && /if \(!_disabledClustersInitialized\)/ { guarded = 1 }
    guarded && /updateFrustum\(/ { frustum = 1 }
    guarded && /updateLightFrame\(_emptyLightFrame, false, false\)/ { frame = 1 }
    guarded && /updateClusters\(\)/ { clusters = 1 }
    guarded && /_disabledClustersInitialized = true/ { cached = 1 }
    disabled && /return;/ { returned = guarded && frustum && frame && clusters && cached; exit returned ? 0 : 1 }
    END { if (!returned) exit 1 }
' "$source"

check "light stage remains current before disabled fastpath" awk '
    /updateLightStage\(lightStage\)/ { stage = NR }
    /if \(!localLightingEnabled\)/ { disabled = NR; exit !(stage && stage < disabled) }
    END { if (!disabled) exit 1 }
' "$source"

check "active path invalidates empty cache before normal frame update" awk '
    /_disabledClustersInitialized = false;/ { reset = NR }
    /updateLightFrame\(/ && $0 !~ /false, false/ && reset { active = NR; exit !(reset < active) }
    END { if (!active) exit 1 }
' "$source"

check "disabled metrics explicitly report no clustered local lights" awk '
    /if \(!localLightingEnabled\)/ { disabled = 1 }
    disabled && /setNumInputLights\(0\)/ { input = 1 }
    disabled && /setNumClusteredLights\(0\)/ { lights = 1 }
    disabled && /setNumClusteredLightReferences\(0\)/ { refs = 1 }
    disabled && /return;/ { exit !(input && lights && refs) }
    END { if (!disabled) exit 1 }
' "$source"

if (( failures != 0 )); then
    printf '%d/%d checks failed\n' "$failures" "$checks" >&2
    exit 1
fi

printf 'All %d phone light clustering fastpath checks passed.\n' "$checks"
