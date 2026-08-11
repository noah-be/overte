#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly events="$repo_root/interface/src/Application_Events.cpp"
readonly activity="$repo_root/android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java"
readonly address_dialog="$repo_root/interface/resources/qml/+android_phoneInterface/AddressBarDialog.qml"

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
        /protected void onPause\(\)/ { in_pause = 1 }
        in_pause && /resumed = false;/ { paused = NR }
        in_pause && /nativeBackConsumed = false;/ { cleared = NR }
        in_pause && /removeCallbacks\(drainPendingUrlTask\)/ { callbacks = NR }
        in_pause && /super[.]onPause\(\)/ { parent = NR; exit }
        END { exit !(paused && cleared && callbacks && parent &&
                     paused < cleared && cleared < callbacks && callbacks < parent) }
    ' "$activity"; then
    printf 'PASS: Activity pause clears transient Back state before parent teardown\n'
else
    printf 'FAIL: Activity pause does not safely clear transient Back state\n' >&2
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
