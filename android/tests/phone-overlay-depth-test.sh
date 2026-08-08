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
default_false_count=$(grep -Ec '^[[:space:]]*return false;' "$source_file")
(( default_false_count >= 2 )) || { printf 'FAIL: invalid or absent properties do not disable depth by default\n' >&2; exit 1; }
require 'overlayDepthEnabled && !_overlayFramebuffer->getDepthStencilBuffer\(\)' 'phone depth attachment is not conditional'
require 'isPhoneOverlayDepthEnabled\(\) \? gpu::Framebuffer::BUFFER_DEPTH : 0' 'phone depth clear is not conditional'
require 'overlay_depth_enabled=%d overlay_width=%u overlay_height=%u overlay_depth_estimated_mib=%\.2f' 'numeric one-time telemetry is incomplete'
require 'std::call_once\(phoneOverlayDepthMarker' 'overlay depth telemetry is not one-time'

if grep -Eqi -- '(__android_log_print|OvertePhoneGraphics).*(url|uri|id=|timestamp|serial|account)' "$source_file"; then
    printf 'FAIL: overlay depth telemetry contains sensitive or raw identifiers\n' >&2
    exit 1
fi

printf 'Phone overlay depth static checks passed.\n'
