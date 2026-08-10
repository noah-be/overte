#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="$script_dir/../../interface/src/ui/ApplicationOverlay.cpp"
header_file="$script_dir/../../interface/src/ui/ApplicationOverlay.h"
qml_overlay_file="$script_dir/../../interface/src/ui/overlays/QmlOverlay.h"
image_overlay_file="$script_dir/../../interface/src/ui/overlays/ImageOverlay.h"
text_overlay_file="$script_dir/../../interface/src/ui/overlays/TextOverlay.h"
rectangle_overlay_file="$script_dir/../../interface/src/ui/overlays/RectangleOverlay.h"
overlays_source="$script_dir/../../interface/src/ui/overlays/Overlays.cpp"

require_source() {
    local pattern=$1 message=$2
    grep -Eq -- "$pattern" "$source_file" || { printf 'FAIL: %s\n' "$message" >&2; exit 1; }
}

require_source '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' 'overlay cache path is not phone-only'
require_source 'debug\.overte\.phone_overlay_cache' 'overlay cache property is missing'
require_source 'requested == "1".*requested == "on".*requested == "true".*requested == "enabled"' 'strict true parser is missing'
require_source 'requested == "0".*requested == "off".*requested == "false".*requested == "disabled"' 'strict false parser is missing'
parser_body=$(awk '
    /^static bool isPhoneOverlayCacheEnabled\(\) \{/ { capture=1 }
    capture { print }
    capture && /^}/ { exit }
' "$source_file")
[[ $(grep -Ec '^[[:space:]]*return false;' <<<"$parser_body") -eq 2 ]] || {
    printf 'FAIL: explicit false and invalid properties must disable caching\n' >&2
    exit 1
}
[[ $(grep -Ec '^[[:space:]]*return true;' <<<"$parser_body") -eq 2 ]] || {
    printf 'FAIL: absent and explicitly enabled properties must enable caching\n' >&2
    exit 1
}

require_source 'const bool newQmlTexture = updatePhoneQmlTexture\(\);' 'QML texture is not fetched before the cache decision'
require_source 'cacheEnabled && _phoneOverlayCompositeValid &&' 'cache does not require an explicitly valid prior composite'
require_source '!framebufferChanged && !newQmlTexture' 'resize or new QML texture does not force a cache miss'
require_source 'if \(reuseComposite\) \{' 'cache hit does not skip the composite batch'
require_source '_phoneOverlayCompositeValid = true;' 'completed composite is not marked valid'
require_source 'overlay_cache_enabled=%d overlay_cache_samples=%u overlay_cache_hits=%u' 'aggregate cache telemetry is incomplete'
require_source 'overlay_cache_misses=%u overlay_cache_new_textures=%u overlay_cache_resizes=%u' 'cache miss cause telemetry is incomplete'

grep -Eq 'bool _phoneOverlayCompositeValid \{ false \};' "$header_file" || {
    printf 'FAIL: composite cache must start invalid\n' >&2
    exit 1
}
grep -Eq 'void render\(RenderArgs\* args\) override \{\}' "$qml_overlay_file" || {
    printf 'FAIL: phone cache safety assumption changed: QmlOverlay now renders into the legacy batch\n' >&2
    exit 1
}
for overlay_file in "$image_overlay_file" "$text_overlay_file" "$rectangle_overlay_file"; do
    grep -Eq 'class [A-Za-z]+Overlay : public QmlOverlay' "$overlay_file" || {
        printf 'FAIL: concrete 2D overlay no longer derives from QmlOverlay: %s\n' "$overlay_file" >&2
        exit 1
    }
done
[[ $(grep -Ec 'new (ImageOverlay|TextOverlay|RectangleOverlay)\(' "$overlays_source") -eq 3 ]] || {
    printf 'FAIL: the set of concrete 2D overlay factories changed; reassess cache invalidation\n' >&2
    exit 1
}

if grep -Eqi -- '(__android_log_print|OvertePhoneGraphics).*(url|uri|id=|timestamp|serial|account)' "$source_file"; then
    printf 'FAIL: overlay cache telemetry contains sensitive or raw identifiers\n' >&2
    exit 1
fi

printf 'Phone overlay cache static checks passed.\n'
