#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly handler="$android_root/phone/apps/phoneInterface/src/PhoneUrlHandler.cpp"
readonly compat="$android_root/phone/apps/phoneInterface/src/QtInputConnectionCompat.cpp"
readonly workflow="$android_root/../.github/workflows/android-tests.yml"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$handler" 'if \(!env \|\| !value\)' 'JNI string conversion rejects null environment and value'
require "$handler" 'GetStringChars\(value, nullptr\)' 'JNI string content is acquired through the environment'
require "$handler" 'if \(!characters\)' 'pending JNI exceptions stop further string work'
require "$handler" 'GetStringLength\(value\)' 'JNI conversion preserves UTF-16 length'
require "$handler" 'ReleaseStringChars\(value, characters\)' 'acquired JNI string content is released'
require "$handler" 'if \(url\.isEmpty\(\) \|\| !application\)' 'URL bridge rejects invalid startup state'
require "$handler" 'Qt::QueuedConnection' 'URL handoff never blocks the Android UI thread'
require "$handler" 'QThread::currentThread\(\) == application->thread\(\)' 'Back avoids self-deadlock on the Qt thread'
require "$handler" 'Qt::BlockingQueuedConnection' 'cross-thread Back returns the synchronous routing result'
require "$handler" 'return invoked && consumed \? JNI_TRUE : JNI_FALSE' 'Back reports both dispatch and consumption'
require "$handler" 'PhoneInterfaceActivity_nativeUpdateTouchUiMetrics' 'JNI exports the runtime touch-metrics bridge'
require "$handler" 'TouchUiMetrics::fromUntrusted' 'JNI sanitizes runtime geometry before exposing it to Qt'
require "$handler" 'PendingTouchUiMetricsDelivery' 'native startup retains the latest accepted touch-metrics snapshot'
require "$handler" 'setTouchUiRuntimeMetrics' 'runtime metrics reach the shared Tablet/QML host boundary'
require "$compat" 'QtNativeInputConnection_finishComposingText' 'finish-composition ABI export remains present'
require "$compat" 'QtNativeInputConnection_updateCursorPosition' 'cursor-update ABI export remains present'
if ! awk '/^  fast:/{inside=1} /^  contracts:/{inside=0} inside' "$workflow" |
        grep -q 'actions/setup-java@'; then
    printf 'FAIL: fast CI must provision the mandatory JNI host-test JDK\n' >&2
    exit 1
fi
printf 'PASS: fast CI provisions a JDK for the mandatory JNI host test\n'

printf 'Phone JNI boundary contracts passed.\n'
