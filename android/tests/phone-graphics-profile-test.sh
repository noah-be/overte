#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly application="$repo_root/interface/src/Application.cpp"
readonly plugins="$repo_root/interface/src/Application_Plugins.cpp"

failures=0
checks=0

pass() {
    checks=$((checks + 1))
    printf 'PASS %s\n' "$1"
}

fail() {
    checks=$((checks + 1))
    failures=$((failures + 1))
    printf 'FAIL %s\n' "$1" >&2
}

require_pattern() {
    local file="$1" pattern="$2" description="$3"
    if grep -Eq -- "$pattern" "$file"; then
        pass "$description"
    else
        fail "$description"
    fi
}

reject_pattern() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eiq -- "$pattern" "$file"; then
        pass "$description"
    else
        fail "$description"
    fi
}

reject_diagnostic_fields() {
    local file="$1" marker="$2" description="$3"
    if awk -v marker="$marker" '
        index($0, marker) { statement = $0; collecting = 1; next }
        collecting { statement = statement " " $0 }
        collecting && /;/ {
            lowered = tolower(statement)
            forbidden = "serial|manufacturer|model|fingerprint|android_id|account|url|domain"
            exit lowered ~ forbidden
        }
        END { if (!collecting) exit 1 }
    ' "$file"; then
        pass "$description"
    else
        fail "$description"
    fi
}

for source in "$application" "$plugins"; do
    if [[ ! -f "$source" ]]; then
        printf 'FAIL missing source: %s\n' "$source" >&2
        exit 1
    fi
done

# The profile remains compile-time phone policy, with one bounded developer
# property for controlled render-scale A/B comparisons.
if awk '
    /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ { phone = 1; next }
    phone && /^#endif/ { exit found ? 0 : 1 }
    phone && /PHONE_DEFAULT_VIEWPORT_RESOLUTION_SCALE/ { scale = 1 }
    phone && /PHONE_TARGET_FPS/ { fps = 1 }
    phone && /setRenderMethod\(RenderScriptingInterface::RenderMethod::FORWARD\)/ { forward = 1 }
    phone && /setAntialiasingMode\(AntialiasingSetupConfig::Mode::NONE\)/ { aa = 1 }
    phone && /setViewportResolutionScale\(phoneViewportResolutionScale\)/ {
        found = scale && fps && forward && aa
    }
    END { if (!phone || !found) exit 1 }
' "$application"; then
    pass 'phone profile is compile-time scoped and applies its deterministic render baseline'
else
    fail 'phone profile is compile-time scoped and applies its deterministic render baseline'
fi

require_pattern "$application" \
    'PHONE_DEFAULT_VIEWPORT_RESOLUTION_SCALE[[:space:]]*\{[[:space:]]*0\.5f[[:space:]]*\}' \
    'phone render-scale override defaults to half resolution'
require_pattern "$application" \
    'PHONE_MIN_VIEWPORT_RESOLUTION_SCALE[[:space:]]*\{[[:space:]]*0\.5f[[:space:]]*\}' \
    'phone render-scale override has a 0.5 lower bound'
require_pattern "$application" \
    'PHONE_MAX_VIEWPORT_RESOLUTION_SCALE[[:space:]]*\{[[:space:]]*0\.7f[[:space:]]*\}' \
    'phone render-scale override has a 0.7 upper bound'
require_pattern "$application" \
    '__system_property_get\("debug\.overte\.phone_render_scale",[[:space:]]*phoneRenderScaleValue\)' \
    'phone render-scale A/B override uses the dedicated Android debug property'
require_pattern "$application" \
    'std::isfinite\(requestedScale\)' \
    'phone render-scale A/B override rejects non-finite values'
require_pattern "$application" \
    'requestedScale[[:space:]]*<[[:space:]]*PHONE_MIN_VIEWPORT_RESOLUTION_SCALE' \
    'phone render-scale A/B override clamps its lower bound'
require_pattern "$application" \
    'requestedScale[[:space:]]*>[[:space:]]*PHONE_MAX_VIEWPORT_RESOLUTION_SCALE' \
    'phone render-scale A/B override clamps its upper bound'
require_pattern "$application" \
    'PHONE_TARGET_FPS[[:space:]]*\{[[:space:]]*30[[:space:]]*\}' \
    'phone frame pacing targets 30 FPS'
require_pattern "$application" \
    'PHONE_FORWARD_MSAA_SAMPLES[[:space:]]*\{[[:space:]]*1[[:space:]]*\}' \
    'phone forward buffers explicitly disable multisample allocation'

for disabled_pass in \
        'setShadowsEnabled\(false\)' \
        'setBloomEnabled\(false\)' \
        'setAmbientOcclusionEnabled\(false\)' \
        'setHazeEnabled\(false\)' \
        'setLocalLightingEnabled\(false\)' \
        'setProceduralMaterialsEnabled\(false\)'; do
    require_pattern "$application" "$disabled_pass" \
        "phone graphics baseline disables ${disabled_pass}"
done

if awk '
    /setupPerformancePresetSettings/ { preset = NR }
    /setViewportResolutionScale\(phoneViewportResolutionScale\)/ { scale = NR }
    /setRefreshRateProfile\(RefreshRateManager::RefreshRateProfile::CUSTOM\)/ { profile = NR }
    /PHONE_GRAPHICS_PROFILE/ { diagnostic = NR }
    END { exit !(preset && scale && profile && diagnostic && preset < scale && scale < profile && profile < diagnostic) }
' "$application"; then
    pass 'phone overrides the desktop preset before reporting the effective profile'
else
    fail 'phone overrides the desktop preset before reporting the effective profile'
fi

for regime in FOCUS_ACTIVE FOCUS_INACTIVE STARTUP; do
    require_pattern "$application" \
        "setCustomRefreshRate\(RefreshRateManager::RefreshRateRegime::${regime},[[:space:]]*PHONE_TARGET_FPS\)" \
        "phone applies its FPS target to ${regime}"
done

require_pattern "$application" \
    'QStringList viewNames[[:space:]]*\{[[:space:]]*"RenderMainView",[[:space:]]*"RenderSecondView"[[:space:]]*\}' \
    'phone graphics configuration covers primary and secondary render graphs'
require_pattern "$application" \
    'viewName[[:space:]]*\+[[:space:]]*"\.RenderForwardTask\.PreparePrimaryBufferForward"' \
    'phone resolves the forward framebuffer config in both render graphs'
require_pattern "$application" \
    'setProperty\("numSamples",[[:space:]]*PHONE_FORWARD_MSAA_SAMPLES\)' \
    'phone applies the one-sample invariant to both forward framebuffers'
require_pattern "$application" \
    'PHONE_LIGHT_CLUSTER_GRID_DIMENSION[[:space:]]*\{[[:space:]]*1[[:space:]]*\}' \
    'phone uses a minimal one-cell light-clustering grid'
require_pattern "$application" \
    'viewName[[:space:]]*\+[[:space:]]*"\.RenderForwardTask\.LightClustering"' \
    'phone resolves light clustering in both forward render graphs'
for cluster_dimension in dimX dimY dimZ; do
    require_pattern "$application" \
        "setProperty\(\"${cluster_dimension}\",[[:space:]]*PHONE_LIGHT_CLUSTER_GRID_DIMENSION\)" \
        "phone constrains light-clustering ${cluster_dimension} to one cell"
done
require_pattern "$application" \
    'MIRROR_VIEWS_PER_LEVEL[[:space:]]*\{[[:space:]]*3[[:space:]]*\}' \
    'phone mirror suppression covers every configured mirror view'
require_pattern "$application" \
    '<<[[:space:]]*"forwardMsaaSamples"[[:space:]]*<<[[:space:]]*PHONE_FORWARD_MSAA_SAMPLES' \
    'phone diagnostic reports only the aggregate forward sample target'
require_pattern "$application" \
    '<<[[:space:]]*"configuredForwardBuffers"[[:space:]]*<<[[:space:]]*configuredForwardBuffers' \
    'phone diagnostic reports only the aggregate configured-buffer count'
require_pattern "$application" \
    '<<[[:space:]]*"lightClusterGridDimension"[[:space:]]*<<[[:space:]]*PHONE_LIGHT_CLUSTER_GRID_DIMENSION' \
    'phone diagnostic reports only the aggregate light-cluster dimension'
require_pattern "$application" \
    '<<[[:space:]]*"configuredLightClusterGrids"[[:space:]]*<<[[:space:]]*configuredLightClusterGrids' \
    'phone diagnostic reports only the aggregate configured light-cluster count'

if awk '
    /setRefreshRateOperator\(/ { operator = NR }
    /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ && operator { phone = NR }
    /updateRefreshRateController\(\)/ && phone { update = NR }
    /PHONE_FRAME_PACING/ && update { diagnostic = NR }
    END { exit !(operator && phone && update && diagnostic && operator < phone && phone < update && update < diagnostic) }
' "$plugins"; then
    pass 'phone activates frame pacing only after installing the display present operator'
else
    fail 'phone activates frame pacing only after installing the display present operator'
fi

# Graphics diagnostics may contain aggregate tuning values, but never stable
# hardware identifiers, raw display dumps, or user-controlled paths.
reject_diagnostic_fields "$application" 'PHONE_GRAPHICS_PROFILE' \
    'phone graphics diagnostic contains no device or user identifier'
reject_diagnostic_fields "$plugins" 'PHONE_FRAME_PACING' \
    'phone frame-pacing diagnostic contains no device or user identifier'

printf 'Checks: %s total, %s failed\n' "$checks" "$failures"
(( failures == 0 ))
