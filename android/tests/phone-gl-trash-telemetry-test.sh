#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$script_dir/../.." && pwd)"
header="$root/libraries/gpu-gl-common/src/gpu/gl/GLBackend.h"
backend="$root/libraries/gpu-gl-common/src/gpu/gl/GLBackend.cpp"
present="$root/libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp"

require() {
    grep -Eq -- "$2" "$1" || { printf 'FAIL: %s\n' "$3" >&2; exit 1; }
}

require_order() {
    local before after
    before="$(grep -n -m1 -E -- "$2" "$1" | cut -d: -f1)"
    after="$(grep -n -m1 -E -- "$3" "$1" | cut -d: -f1)"
    [[ -n "$before" && -n "$after" && "$before" -lt "$after" ]] || {
        printf 'FAIL: %s\n' "$4" >&2; exit 1
    }
}

require "$header" 'ANDROID_APP_PHONE_INTERFACE.*Q_OS_ANDROID' 'metrics are not phone-Android scoped'
require "$header" 'struct PhoneTrashMetrics' 'fixed snapshot type is missing'
require "$backend" 'std::atomic<uint64_t>' 'aggregate atomic counters are missing'
require "$backend" 'memory_order_relaxed' 'counters do not use relaxed atomics'
require "$backend" 'buffersEnqueued\.fetch_add' 'buffer enqueue counter is missing'
require "$backend" 'bufferBytesEnqueued\.fetch_add' 'buffer byte enqueue counter is missing'
require "$backend" 'buffersCleaned\.fetch_add' 'buffer cleanup counter is missing'
require "$backend" 'bufferBytesCleaned\.fetch_add' 'buffer byte cleanup counter is missing'
require "$backend" 'texturesEnqueued\.fetch_add' 'texture enqueue counter is missing'
require "$backend" 'externalTexturesCleaned\.fetch_add' 'external texture cleanup counter is missing'
require "$backend" 'framebuffersCleaned\.fetch_add' 'framebuffer cleanup counter is missing'
require_order "$backend" '_currentFrameTrash\.buffersTrash\.push_back' \
    'phoneTrashMetrics\.buffersEnqueued\.fetch_add' 'buffer enqueue is counted before insertion succeeds'
require_order "$backend" '_currentFrameTrash\.texturesTrash\.push_back' \
    'phoneTrashMetrics\.texturesEnqueued\.fetch_add' 'texture enqueue is counted before insertion succeeds'
require_order "$backend" '_currentFrameTrash\.externalTexturesTrash\.push_back' \
    'phoneTrashMetrics\.externalTexturesEnqueued\.fetch_add' 'external texture enqueue is counted before insertion succeeds'
require_order "$backend" '_currentFrameTrash\.framebuffersTrash\.push_back' \
    'phoneTrashMetrics\.framebuffersEnqueued\.fetch_add' 'framebuffer enqueue is counted before insertion succeeds'
require "$present" 'getPhoneTrashMetrics\(\)' 'present telemetry does not read the aggregate snapshot'
require "$present" 'record=present window_id=%llu' 'present record has no correlation ID'
require "$present" 'record=trash window_id=%llu' 'trash record has no correlation ID'
require "$present" 'record=state window_id=%llu' 'state record has no correlation ID'
require "$present" 'gl_trash_buffer_pending_mib=' 'pending buffer bytes are not reported in MiB'

if grep -Eq 'texture(Bytes|_bytes).*([Ee]nqueued|[Cc]leaned|[Pp]ending)' "$header" "$backend" "$present"; then
    echo 'FAIL: telemetry must not claim deferred texture byte accounting' >&2
    exit 1
fi
if grep -Eq '(_currentFrameTrash|_previousFrameTrashes|buffersTrash|texturesTrash).*OvertePhoneGraphics' "$present"; then
    echo 'FAIL: report path traverses trash containers' >&2
    exit 1
fi

printf 'Phone GL trash telemetry source checks passed.\n'
