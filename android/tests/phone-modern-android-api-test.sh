#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

phone_activity="$repo_root/android/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java"
permissions_activity="$repo_root/android/apps/phoneInterface/src/main/java/org/overte/phone/PermissionsActivity.java"

require() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$phone_activity" 'SDK_INT >= Build\.VERSION_CODES\.R' \
    'API 30+ uses a dedicated modern window path'
require "$phone_activity" 'setDecorFitsSystemWindows\(false\)' \
    'modern Android draws the Qt surface edge to edge'
require "$phone_activity" 'controller\.hide\(WindowInsets\.Type\.systemBars\(\)\)' \
    'modern Android hides both system bars through WindowInsets'
require "$phone_activity" 'BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE' \
    'immersive bars remain transient swipe overlays'
require "$phone_activity" 'SDK_INT >= Build\.VERSION_CODES\.P' \
    'display-cutout access is guarded by its introduction API'
require "$phone_activity" 'LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES' \
    'landscape content may safely use short-edge display cutouts'
require "$phone_activity" 'decorView\.setSystemUiVisibility\(IMMERSIVE_UI_FLAGS\)' \
    'API 26-29 retains the Qt-compatible legacy immersive path'
require "$phone_activity" 'void onConfigurationChanged\(Configuration newConfig\)' \
    'Qt surface bounds are refreshed after Android orientation changes'
require "$phone_activity" 'window\.setLayout\(' \
    'phone activity explicitly fills the complete display window'
require "$repo_root/android/apps/phoneInterface/src/main/java/org/qtproject/qt5/android/QtLayout.java" \
    'postDelayed\(\(\) -> QtNative\.setApplicationDisplayMetrics' \
    'phone reapplies real metrics after Qt replaces its fallback screen'
require "$repo_root/android/apps/phoneInterface/build.gradle" \
    "exclude 'org/qtproject/qt5/android/QtLayout.class'" \
    'phone packaging replaces only the bundled QtLayout implementation'
require "$repo_root/android/apps/phoneInterface/src/main/java/org/qtproject/qt5/android/QtLayout.java" \
    '\(applicationWidth > applicationHeight\).*\(maximumWidth > maximumHeight\)' \
    'Qt current and maximum metrics share the requested orientation'

require "$permissions_activity" 'onSaveInstanceState\(Bundle outState\)' \
    'permission launcher persists state across recreation'
require "$permissions_activity" 'STATE_PENDING_URL' \
    'validated pending deep link is persisted'
require "$permissions_activity" 'STATE_INTERFACE_LAUNCHED' \
    'native activity launch state is persisted'
require "$permissions_activity" 'A permission dialog does not provide a durable request token' \
    'permission recreation deliberately avoids a stale request token'
require "$permissions_activity" 'requestPermissions\(' \
    'missing microphone permission is requested after each safe recreation check'

printf 'Modern Android API compatibility checks passed.\n'
