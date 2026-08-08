#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="$script_dir/../../libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp"
header_file="$script_dir/../../libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.h"
cmake_file="$script_dir/../../libraries/display-plugins/CMakeLists.txt"
controller_file="$script_dir/../../libraries/display-plugins/src/display-plugins/RefreshRateController.cpp"

require() {
    local file=$1 pattern=$2 message=$3
    grep -Eq -- "$pattern" "$file" || { printf 'FAIL: %s\n' "$message" >&2; exit 1; }
}

require "$source_file" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' 'telemetry is not phone-only'
require "$source_file" 'PHONE_PRESENT_REPORT_INTERVAL_USEC[^;]*10ULL' 'report interval is not ten seconds'
require "$source_file" 'std::chrono::steady_clock' 'present telemetry does not use a monotonic clock'
require "$source_file" 'PHONE_PRESENT_DISCONTINUITY_USEC' 'present telemetry does not reset after display inactivity'
require "$source_file" 'std::array<uint32_t, PHONE_PRESENT_INTERVAL_CAPACITY>' 'interval storage is not fixed-size'
require "$source_file" 'context->swapBuffers\(\);' 'swapBuffers call is missing'
require "$source_file" 'phonePresentTelemetry\.record\(_phonePresentHasNewFrame\);' 'successful swaps are not recorded'
require "$source_file" '__android_log_print\(ANDROID_LOG_INFO, "OvertePhoneGraphics"' 'direct Android telemetry tag is missing'
require "$source_file" 'window_seconds=%\.2f present_fps=%\.2f new_frame_fps=%\.2f inter_present_p50_ms=%\.2f inter_present_p95_ms=%\.2f inter_present_max_ms=%\.2f' 'aggregate numeric metrics are incomplete'
require "$header_file" '_phonePresentHasNewFrame' 'new-frame state is not retained without allocation'
require "$cmake_file" 'HIFI_ANDROID_APP STREQUAL "phoneInterface"' 'Android log linkage is not phone-scoped'
require "$cmake_file" 'target_link_libraries\(\$\{TARGET_NAME\} log\)' 'phone telemetry is not linked to Android liblog'
require "$controller_file" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' 'precise pacing is not phone-scoped'
require "$controller_file" 'thread->usleep' 'phone pacing still truncates its sleep to milliseconds'

if grep -Eqi -- '(__android_log_print|OvertePhoneGraphics).*(url|uri|id=|timestamp|serial|account)' "$source_file"; then
    printf 'FAIL: identifying or raw fields occur in the native telemetry log\n' >&2
    exit 1
fi

swap_line=$(grep -n -m1 'context->swapBuffers();' "$source_file" | cut -d: -f1)
record_line=$(grep -n -m1 'phonePresentTelemetry.record(_phonePresentHasNewFrame);' "$source_file" | cut -d: -f1)
(( record_line > swap_line )) || { printf 'FAIL: telemetry is emitted before swapBuffers returns\n' >&2; exit 1; }

if ! awk '
    /internalPresent\(\);/ { presented = NR }
    presented && /refreshRateController->clockEndTime\(\);/ && NR > presented { found = 1; exit }
    END { if (!found) exit 1 }
' "$source_file"; then
    printf 'FAIL: phone pacing does not include compositor-blocking swap time\n' >&2
    exit 1
fi

printf 'Phone native present telemetry static checks passed.\n'
