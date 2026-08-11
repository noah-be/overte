#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="$script_dir/../../../interface/src/ui/ApplicationOverlay.cpp"

require() {
    local pattern=$1 message=$2
    grep -Eq -- "$pattern" "$source_file" || { printf 'FAIL: %s\n' "$message" >&2; exit 1; }
}

require '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' 'overlay scale path is not phone-only'
require 'debug\.overte\.phone_overlay_scale' 'overlay scale property is missing'
require 'toDouble\(&parsed\)' 'overlay scale property is not parsed strictly'
require '!parsed \|\| !std::isfinite\(requested\)' 'invalid or non-finite overlay scales are not rejected'
require 'return 1\.0f;' 'safe full-resolution default is missing'
require 'std::max\(0\.5, std::min\(1\.0, requested\)\)' 'overlay scale is not clamped to 0.5..1.0'
require 'std::lround\(static_cast<double>\(logicalSize\.x\) \* overlayScale\)' 'overlay target width is not rounded from logical width'
require 'std::lround\(static_cast<double>\(logicalSize\.y\) \* overlayScale\)' 'overlay target height is not rounded from logical height'
require 'std::max\(1L, std::lround' 'overlay target dimensions are not bounded to at least one pixel'
require 'targetSize != _overlayFramebuffer->getSize\(\)' 'framebuffer recreation does not compare target size'
require 'createRenderBuffer\(DEPTH_FORMAT, width, height' 'depth target does not use scaled dimensions'
require 'createRenderBuffer\(COLOR_FORMAT, width, height' 'color target does not use scaled dimensions'
require 'overlay_logical_width=%u overlay_logical_height=%u' 'logical overlay dimensions are missing from telemetry'
require 'overlay_target_width=%u overlay_target_height=%u overlay_scale=%\.3f' 'target dimensions or effective scale are missing from telemetry'
require 'overlay_color_estimated_mib=%\.2f overlay_depth_estimated_mib=%\.2f' 'color/depth allocation estimates are missing from telemetry'
require 'std::call_once\(phoneOverlayDepthMarker' 'overlay telemetry is not one-time'

# Rendering and input must continue to consume their existing logical viewport/UI
# sizes; the experiment is limited to allocating the intermediate render target.
require 'int width = renderArgs->_viewport\.z;' 'script overlay projection no longer uses the logical render viewport'
require 'int height = renderArgs->_viewport\.w;' 'script overlay projection no longer uses the logical render viewport'
require '_uiTexture->setSize\(offscreenUI->size\(\)\.width\(\), offscreenUI->size\(\)\.height\(\)\)' 'QML texture logical sizing changed'

if grep -Eqi -- '(__android_log_print|OvertePhoneGraphics).*(url|uri|id=|timestamp|serial|account)' "$source_file"; then
    printf 'FAIL: overlay scale telemetry contains sensitive or raw identifiers\n' >&2
    exit 1
fi

printf 'Phone overlay scale static checks passed.\n'
