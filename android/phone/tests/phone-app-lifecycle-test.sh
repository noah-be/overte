#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly events="$repo_root/interface/src/Application_Events.cpp"
readonly activity="$repo_root/android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java"
readonly address_dialog="$repo_root/interface/resources/qml/+android_phoneInterface/AddressBarDialog.qml"
readonly audio_client="$repo_root/libraries/audio-client/src/AudioClient.cpp"
readonly audio_client_header="$repo_root/libraries/audio-client/src/AudioClient.h"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

if awk '
        /case Qt::ApplicationSuspended:/ { suspended = NR }
        /case Qt::ApplicationHidden:/ { hidden = NR }
        /_isForeground = false;/ && suspended && hidden && NR > hidden { cleared = NR }
        /break;/ && cleared { exit !(suspended < hidden && hidden < cleared && cleared < NR) }
        END { if (!cleared) exit 1 }
    ' "$events"; then
    printf 'PASS: suspended and hidden application states clear foreground status\n'
else
    printf 'FAIL: suspended or hidden application state can retain foreground status\n' >&2
    exit 1
fi

if awk '
        /protected void onResume\(\)/ { in_resume = 1 }
        in_resume && /super[.]onResume\(\)/ { parent = NR }
        in_resume && /resumed = true;/ { resumed = NR }
        in_resume && /publishNativeForegroundState\(true\)/ { foreground = NR; exit }
        END { exit !(parent && resumed && foreground &&
                     parent < resumed && resumed < foreground) }
    ' "$activity"; then
    printf 'PASS: Activity resume publishes foreground state after parent startup\n'
else
    printf 'FAIL: Activity resume does not safely publish native foreground state\n' >&2
    exit 1
fi

if awk '
        /protected void onPause\(\)/ { in_pause = 1 }
        in_pause && /resumed = false;/ { paused = NR }
        in_pause && /nativeBackConsumed = false;/ { cleared = NR }
        in_pause && /removeCallbacks\(drainPendingUrlTask\)/ { callbacks = NR }
        in_pause && /publishNativeForegroundState\(false\)/ { background = NR }
        in_pause && /super[.]onPause\(\)/ { parent = NR; exit }
        END { exit !(paused && cleared && callbacks && background && parent &&
                     paused < cleared && cleared < callbacks &&
                     callbacks < background && background < parent) }
    ' "$activity"; then
    printf 'PASS: Activity pause clears transient state and publishes native background state\n'
else
    printf 'FAIL: Activity pause does not safely publish native background state\n' >&2
    exit 1
fi

require "$activity" 'private static native boolean nativeSetForegroundState\(boolean foreground\)' \
    'Activity declares the native lifecycle bridge'
require "$activity" 'private void publishNativeForegroundState\(boolean foreground\)' \
    'Activity centralizes native lifecycle publication'
require "$audio_client_header" 'bool _audioLifecycleRunning \{ false \};' \
    'audio client retains an explicit lifecycle state'

if awk '
        /void AudioClient::start\(\)/ { in_start = 1 }
        in_start && /if \(_audioLifecycleRunning\)/ { duplicate = NR }
        in_start && /_audioLifecycleRunning = true;/ { running = NR }
        in_start && /_checkDevicesTimer->start\(DEVICE_CHECK_INTERVAL_MSECS\)/ { devices = NR }
        in_start && /_checkPeakValuesTimer->start\(PEAK_VALUES_CHECK_INTERVAL_MSECS\)/ { peaks = NR }
        /void AudioClient::stop\(\)/ { exit }
        END { exit !(duplicate && running && devices && peaks &&
                     duplicate < running && running < devices && devices < peaks) }
    ' "$audio_client"; then
    printf 'PASS: audio foreground entry is idempotent and restarts monitoring\n'
else
    printf 'FAIL: audio foreground entry can duplicate or omit monitoring\n' >&2
    exit 1
fi

if awk '
        /void AudioClient::stop\(\)/ { in_stop = 1 }
        in_stop && /if \(!_audioLifecycleRunning\)/ { duplicate = NR }
        in_stop && /_audioLifecycleRunning = false;/ { stopped = NR }
        in_stop && /if \(_checkDevicesTimer\)/ { devices = NR }
        in_stop && /_checkDevicesTimer->stop\(\)/ { devices_stop = NR }
        in_stop && /if \(_checkPeakValuesTimer\)/ { peaks = NR }
        in_stop && /_checkPeakValuesTimer->stop\(\)/ { peaks_stop = NR }
        /void AudioClient::handleAudioEnvironmentDataPacket/ { exit }
        END { exit !(duplicate && stopped && devices && devices_stop && peaks && peaks_stop &&
                     duplicate < stopped && stopped < devices && devices < devices_stop &&
                     devices_stop < peaks && peaks < peaks_stop) }
    ' "$audio_client"; then
    printf 'PASS: audio background entry is idempotent and guards monitoring timers\n'
else
    printf 'FAIL: repeated audio background entry can dereference a stale timer\n' >&2
    exit 1
fi

if awk '
        /public boolean dispatchKeyEvent\(KeyEvent event\)/ { in_dispatch = 1 }
        in_dispatch && /event[.]getAction\(\) == KeyEvent[.]ACTION_DOWN/ { down = NR }
        in_dispatch && /event[.]getRepeatCount\(\) == 0/ { initial = NR }
        in_dispatch && /nativeBackConsumed = tryHandleNativeBack\(\)/ { native = NR }
        in_dispatch && /if \(nativeBackConsumed\)/ { consume = NR }
        in_dispatch && /event[.]getAction\(\) == KeyEvent[.]ACTION_UP/ { up = NR; exit }
        END { exit !(down && initial && native && consume && up &&
                     down < initial && initial < native && native < consume && consume < up) }
    ' "$activity"; then
    printf 'PASS: consumed Back owns initial, repeat, and release events\n'
else
    printf 'FAIL: consumed Back can leak repeat events into Qt\n' >&2
    exit 1
fi

if awk '
        /private void drainPendingUrl\(\)/ { in_drain = 1 }
        in_drain && /removeCallbacks\(drainPendingUrlTask\)/ { removed = NR }
        in_drain && /!PhonePendingUrlPolicy[.]canAttempt\(pendingUrl, resumed\)/ { foreground = NR }
        in_drain && /nativeProcessUrl\(pendingUrl\)/ { native = NR; exit }
        END { exit !(removed && foreground && native && removed < foreground && foreground < native) }
    ' "$activity"; then
    printf 'PASS: background deep links remain pending until Activity resume\n'
else
    printf 'FAIL: a background deep link can reach native navigation\n' >&2
    exit 1
fi

if awk '
        /protected void onDestroy\(\)/ { in_destroy = 1 }
        in_destroy && /resumed = false;/ { paused = NR }
        in_destroy && /removeCallbacks\(drainPendingUrlTask\)/ { removed = NR }
        in_destroy && /super[.]onDestroy\(\)/ { parent = NR; exit }
        END { exit !(paused && removed && parent && paused < removed && removed < parent) }
    ' "$activity"; then
    printf 'PASS: Activity destroy cancels pending deep-link callbacks\n'
else
    printf 'FAIL: Activity destroy can retain a deep-link callback\n' >&2
    exit 1
fi

require "$address_dialog" 'Component[.]onDestruction:[[:space:]]*\{' \
    'address dialog has an external teardown fallback'
require "$address_dialog" 'addressField[.]focus[[:space:]]*=[[:space:]]*false' \
    'address dialog drops stale field focus during teardown'
require "$address_dialog" 'Qt[.]inputMethod[.]hide\(\)' \
    'address dialog hides the IME during teardown'

printf 'Android phone application lifecycle checks passed.\n'
