#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
render_dir="$script_dir/../../libraries/render-utils/src"
display_file="$script_dir/../../libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp"

require() {
    local file=$1 pattern=$2 message=$3
    grep -Eq -- "$pattern" "$file" || { printf 'FAIL: %s\n' "$message" >&2; exit 1; }
}

require "$render_dir/RenderForwardTask.cpp" 'std::mutex phoneFramebufferTelemetryMutex' 'framebuffer telemetry lacks coherent snapshot locking'
require "$render_dir/RenderForwardTask.cpp" 'std::lock_guard<std::mutex>' 'framebuffer telemetry does not lock reads and writes'
require "$render_dir/PhoneFramebufferTelemetry.h" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' 'API is not phone-only'
require "$render_dir/RenderForwardTask.cpp" 'recordPrimaryRecreate' 'primary framebuffer recreates are not recorded'
require "$render_dir/RenderForwardTask.cpp" '"MakeResolvingFramebuffer"' 'forward resolve framebuffer is missing'
require "$render_dir/RenderCommonTask.cpp" 'NewFramebuffer\(pixelFormat, false\)' 'generic framebuffers are tracked by default'
require "$render_dir/RenderCommonTask.cpp" 'if \(_trackPhoneResolveRecreates\)' 'resolve tracking is not explicitly gated'
require "$display_file" 'phone_framebuffer_telemetry::snapshot\(\)' 'present telemetry does not take a framebuffer snapshot'
require "$display_file" 'framebuffer_primary_recreate_delta=%llu framebuffer_primary_recreate_total=%llu' 'primary delta and total are missing'
require "$display_file" 'framebuffer_resolve_recreate_delta=%llu framebuffer_resolve_recreate_total=%llu' 'resolve delta and total are missing'
require "$display_file" 'framebuffer_primary_width=%u framebuffer_primary_height=%u framebuffer_primary_samples=%u' 'primary shape is missing'
require "$display_file" 'framebuffer_resolve_width=%u framebuffer_resolve_height=%u framebuffer_resolve_samples=%u framebuffer_estimated_mib=%\.2f' 'resolve shape, samples, or memory estimate is missing'

printf 'Phone framebuffer telemetry static checks passed.\n'
