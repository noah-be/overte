#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="$script_dir/../../interface/src/ui/ApplicationOverlay.cpp"

require() {
    local pattern=$1 message=$2
    grep -Eq -- "$pattern" "$source_file" || { printf 'FAIL: %s\n' "$message" >&2; exit 1; }
}

require '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' 'overlay depth A/B path is not phone-only'
require 'debug\.overte\.phone_overlay_depth' 'overlay depth property is missing'
require 'requested == "1".*requested == "on".*requested == "true".*requested == "enabled"' 'strict true parser is missing'
require 'requested == "0".*requested == "off".*requested == "false".*requested == "disabled"' 'strict false parser is missing'
parser_body=$(awk '
    /^static bool isPhoneOverlayDepthEnabled\(\) \{/ { capture=1 }
    capture { print }
    capture && /^}/ { exit }
' "$source_file")
[[ $(grep -Ec '^[[:space:]]*return false;' <<<"$parser_body") -eq 3 ]] || {
    printf 'FAIL: false, invalid, and absent properties must all disable depth\n' >&2
    exit 1
}
[[ $(grep -Ec '^[[:space:]]*return true;' <<<"$parser_body") -eq 1 ]] || {
    printf 'FAIL: only an explicitly enabled property may restore depth\n' >&2
    exit 1
}
require 'overlayDepthEnabled && !_overlayFramebuffer->getDepthStencilBuffer\(\)' 'phone depth attachment is not conditional'
require 'isPhoneOverlayDepthEnabled\(\) \? gpu::Framebuffer::BUFFER_DEPTH : 0' 'phone depth clear is not conditional'
require 'overlay_depth_enabled=%d overlay_logical_width=%u overlay_logical_height=%u' 'numeric one-time depth telemetry is incomplete'
require 'overlay_color_estimated_mib=%\.2f overlay_depth_estimated_mib=%\.2f' 'numeric allocation telemetry is incomplete'
require 'std::call_once\(phoneOverlayDepthMarker' 'overlay depth telemetry is not one-time'

if grep -Eqi -- '(__android_log_print|OvertePhoneGraphics).*(url|uri|id=|timestamp|serial|account)' "$source_file"; then
    printf 'FAIL: overlay depth telemetry contains sensitive or raw identifiers\n' >&2
    exit 1
fi

printf 'Phone overlay depth static checks passed.\n'
