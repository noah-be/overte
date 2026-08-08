#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

home="$repo_root/interface/resources/qml/hifi/tablet/TabletHome.qml"
button="$repo_root/interface/resources/qml/hifi/tablet/TabletButton.qml"
shared_config="$repo_root/interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml"
phone_config="$repo_root/interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletTouchConfiguration.qml"
preferences_dialog="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesDialog.qml"
shared_preferences_layout="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesLayout.qml"
phone_preferences_layout="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/+android_phoneInterface/TabletPreferencesLayout.qml"

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

require "$shared_config" 'property bool touchOptimized:[[:space:]]*false' \
    'desktop and VR retain their existing pointer presentation'
require "$phone_config" 'property bool touchOptimized:[[:space:]]*true' \
    'the phone selector enables touchscreen presentation'
require "$phone_config" 'availableWidth[[:space:]]*>=[[:space:]]*availableHeight[[:space:]]*\?[[:space:]]*5[[:space:]]*:[[:space:]]*3' \
    'the phone tablet responds to landscape and transient portrait sizes'
require "$phone_config" 'property int maximumButtonExtent:[[:space:]]*120' \
    'launcher cards use compact logical units before host scaling'
require "$phone_config" 'property int buttonSpacing:[[:space:]]*5' \
    'the compact app grid retains a clear gap between touch targets'
require "$shared_preferences_layout" 'property bool compactFooter:[[:space:]]*false' \
    'desktop and VR retain their established General Settings footer'
require "$phone_preferences_layout" 'property bool compactFooter:[[:space:]]*true' \
    'phone General Settings select compact footer controls'
require "$phone_preferences_layout" 'property int buttonWidth:[[:space:]]*120' \
    'phone preference buttons use unscaled logical width before host scaling'
require "$phone_preferences_layout" 'property int buttonHeight:[[:space:]]*28' \
    'phone preference buttons use unscaled logical height before host scaling'
require "$preferences_dialog" 'preferencesLayout[.]compactFooter' \
    'General Settings consumes the selector-backed footer layout'
require "$shared_config" 'property bool showCloseButton:[[:space:]]*false' \
    'desktop and VR do not gain Android-specific tablet chrome'
require "$phone_config" 'property bool showCloseButton:[[:space:]]*true' \
    'the phone selector enables the touchscreen close control'
require "$phone_config" 'property int closeButtonHeight:[[:space:]]*32' \
    'the close control uses the shared host scale'
require "$phone_config" 'property int closeButtonBottomMargin:[[:space:]]*28' \
    'the close control remains fully visible above the Android display edge'
require "$phone_config" 'property int minimumTouchTarget:[[:space:]]*48' \
    'page controls expose touch-sized targets'
require "$home" 'TabletTouchConfiguration[[:space:]]*\{' \
    'TabletHome consumes the selector-backed presentation settings'
require "$home" 'cellWidth:[[:space:]]*width[[:space:]]*/[[:space:]]*presentation\.columns' \
    'the app grid uses the responsive column count'
require "$home" 'presentation\.columns[[:space:]]*\*[[:space:]]*\(presentation\.maximumButtonExtent[[:space:]]*\+[[:space:]]*presentation\.buttonSpacing\)' \
    'the app grid is centered as a compact group instead of spanning the display'
require "$home" 'rowCount[[:space:]]*\*[[:space:]]*\(presentation\.maximumButtonExtent[[:space:]]*\+[[:space:]]*presentation\.buttonSpacing\)' \
    'the app rows are vertically compact instead of spanning the display'
require "$home" 'width:[[:space:]]*gridView\.buttonExtent' \
    'app buttons scale inside the available landscape grid'
if grep -Eq 'iconExtent:[[:space:]]*presentation\.touchOptimized|captionPixelSize:[[:space:]]*presentation\.touchOptimized' "$home"; then
    printf 'FAIL: launcher visuals must not apply a second Android scale\n' >&2
    exit 1
fi
printf 'PASS: launcher visuals rely exclusively on the shared host scale\n'
require "$home" 'anchors\.bottom:[[:space:]]*closeTabletButton\.top' \
    'the app pages reserve bottom space and sit above the close control'
require "$home" 'objectName:[[:space:]]*"androidTabletCloseButton"' \
    'the Android tablet exposes a stable close-control identity'
require "$home" 'onClicked:[[:space:]]*tabletProxy\.hideAndroidTablet\(\)' \
    'the close control routes through the native screen-space presenter'
require "$home" 'hoverEnabled:[[:space:]]*!presentation\.touchOptimized' \
    'touch presentation does not depend on hover input'
require "$button" 'hoverEnabled:[[:space:]]*tabletButton\.hoverEnabled' \
    'tablet buttons suppress synthetic hover handling on direct touch'

printf 'Phone tablet touchscreen QML checks passed.\n'
