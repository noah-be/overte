#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
pal="$repo_root/scripts/system/pal.js"
menu_stack="$repo_root/interface/resources/qml/hifi/tablet/TabletMenuStack.qml"
menu_view="$repo_root/interface/resources/qml/hifi/tablet/TabletMenuView.qml"
menu_item="$repo_root/interface/resources/qml/hifi/tablet/TabletMenuItem.qml"
lifecycle_mock="$repo_root/android/tests/phone-tablet-people-lifecycle-mock.js"

require() {
    local file=$1
    local pattern=$2
    local description=$3
    if grep -Eq -- "$pattern" "$file"; then
        printf 'PASS: %s\n' "$description"
    else
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
}

require "$pal" 'isAndroidPhone = typeof ANDROID_PHONE_INTERFACE' \
    'People detects the Android phone runtime'
require "$pal" 'triggerMapping = isAndroidPhone [?] null' \
    'People does not construct controller mappings on Android phone'
require "$pal" 'if \(!isAndroidPhone\) \{' \
    'People gates world-input wiring behind the non-phone path'
require "$pal" 'AvatarList[.]getPalData\(\)[.]data[.]forEach\(updateAudioLevel\)' \
    'People retains tablet audio meters without world overlays'
require "$pal" 'var palRuntimeActive = false' \
    'People tracks its open runtime independently from AppUi state'
require "$pal" 'updateInterval = undefined' \
    'People releases its update interval on close'
require "$pal" 'Messages[.]unsubscribe\(CHANNEL\)' \
    'People releases its message subscription at shutdown'

require "$menu_stack" 'return tabletRoot[.]screenSpaceMode === true' \
    'Menu keeps filtering specific to the phone screen-space tablet'
if grep -Fq 'Qt.platform.os' "$menu_stack"; then
    printf 'FAIL: Menu filtering must not affect Pico merely because it also runs Android\n' >&2
    exit 1
fi
printf 'PASS: Menu filtering does not use the shared Android platform identity\n'
require "$menu_stack" 'Unavailable on Android' \
    'Menu labels unsupported actions honestly'
require "$menu_stack" 'supportedRootMenus = \["File", "View", "Navigate", "Settings"\]' \
    'Menu uses an explicit reviewed root-menu allowlist'
require "$menu_stack" 'topMenu === null.*item[.]type === MenuItemType[.]Menu' \
    'Menu applies its fail-closed policy at the root'
require "$menu_stack" '"General[.][.][.]"' \
    'Menu blocks the legacy General Settings dialog on phone screen-space'
require "$menu_stack" 'phone.s dedicated SETTINGS app remains available separately' \
    'Menu policy preserves the dedicated tablet Settings route'
require "$menu_stack" '!selectedItem[.]platformEnabled' \
    'Menu refuses to trigger unsupported Android actions'
require "$menu_view" 'item[.]enabled && phoneSupported' \
    'Menu touch targets honor Android availability'
require "$menu_item" 'property bool platformEnabled: true' \
    'Menu items expose platform availability visually'

node "$lifecycle_mock"

# Static mocks cover the People script lifecycle, but cannot validate live
# avatar/world data, actual entity overlay suppression, or server-backed user
# operations. Keep this explicit until a phone is released for the bundled run.
printf 'PENDING: People live-world/device validation (avatar data, world overlays, server actions)\n'

printf 'Android phone People/Menu checks passed.\n'
