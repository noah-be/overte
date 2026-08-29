#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"

home="$repo_root/interface/resources/qml/hifi/tablet/TabletHome.qml"
button="$repo_root/interface/resources/qml/hifi/tablet/TabletButton.qml"
menu_view="$repo_root/interface/resources/qml/hifi/tablet/TabletMenuView.qml"
menu_item="$repo_root/interface/resources/qml/hifi/tablet/TabletMenuItem.qml"
shared_config="$repo_root/interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml"
shared_config_base="$repo_root/interface/resources/qml/hifi/tablet/TabletTouchConfigurationBase.qml"
touch_metrics="$repo_root/interface/resources/qml/controlsUit/TouchUiMetrics.qml"
button_control="$repo_root/interface/resources/qml/controlsUit/Button.qml"
slider_control="$repo_root/interface/resources/qml/controlsUit/Slider.qml"
switch_control="$repo_root/interface/resources/qml/controlsUit/Switch.qml"
checkbox_control="$repo_root/interface/resources/qml/controlsUit/CheckBox.qml"
text_field_control="$repo_root/interface/resources/qml/controlsUit/TextField.qml"
base_profile="$repo_root/interface/resources/qml/controlsUit/TouchUiProfileBase.qml"
phone_profile="$repo_root/interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"
preferences_dialog="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesDialog.qml"
shared_preferences_layout="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesLayout.qml"

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

require "$base_profile" 'property bool directTouch:[[:space:]]*false' \
    'desktop and VR retain their existing pointer presentation'
require "$touch_metrics" 'property bool directTouch:[[:space:]]*profile[.]directTouch' \
    'shared metrics consume the selected device profile'
require "$shared_config_base" 'readonly property bool touchOptimized:[[:space:]]*directTouch' \
    'feature presentation derives touch behavior from shared capabilities'
require "$phone_profile" 'directTouch:[[:space:]]*true' \
    'the phone selector enables touchscreen presentation'
require "$touch_metrics" 'readonly property string widthClass:' \
    'shared touch metrics derive a reusable responsive width class'
require "$shared_config_base" 'compact[[:space:]]*\?[[:space:]]*3[[:space:]]*:[[:space:]]*expanded[[:space:]]*\?[[:space:]]*6[[:space:]]*:[[:space:]]*5' \
    'the shared tablet layout adapts across compact, medium and expanded surfaces'
require "$shared_config_base" 'property int maximumButtonExtent:[[:space:]]*directTouch[[:space:]]*\?[[:space:]]*120[[:space:]]*:[[:space:]]*129' \
    'launcher cards use compact logical units before host scaling'
require "$shared_config_base" 'property int buttonSpacing:[[:space:]]*directTouch[[:space:]]*\?[[:space:]]*5[[:space:]]*:[[:space:]]*0' \
    'the compact app grid retains a clear gap between touch targets'
require "$shared_preferences_layout" 'compactFooter:[[:space:]]*profile[.]screenSpacePresentation' \
    'General Settings derives footer layout from the shared profile'
require "$base_profile" 'property bool screenSpacePresentation:[[:space:]]*false' \
    'desktop and VR retain their established General Settings footer'
require "$phone_profile" 'screenSpacePresentation:[[:space:]]*true' \
    'phone General Settings select compact footer controls'
require "$shared_preferences_layout" 'property int buttonWidth:[[:space:]]*120' \
    'phone preference buttons use unscaled logical width before host scaling'
require "$shared_preferences_layout" 'property int buttonHeight:[[:space:]]*28' \
    'phone preference buttons use unscaled logical height before host scaling'
require "$preferences_dialog" 'preferencesLayout[.]compactFooter' \
    'General Settings consumes the selector-backed footer layout'
require "$shared_config" 'TabletTouchConfigurationBase[[:space:]]*\{' \
    'desktop and VR do not gain Android-specific tablet chrome'
require "$shared_config_base" 'profile[.]screenSpacePresentation' \
    'the phone selector enables the touchscreen close control'
require "$shared_config_base" 'property int closeButtonHeight:[[:space:]]*showCloseButton[[:space:]]*\?[[:space:]]*32[[:space:]]*:[[:space:]]*0' \
    'the close control uses the shared host scale'
require "$shared_config_base" 'property int closeButtonBottomMargin:[[:space:]]*showCloseButton[[:space:]]*\?[[:space:]]*28[[:space:]]*:[[:space:]]*0' \
    'the close control remains fully visible above the Android display edge'
require "$touch_metrics" 'readonly property int minimumTouchTarget:[[:space:]]*directTouch[[:space:]]*\?[[:space:]]*48[[:space:]]*:[[:space:]]*30' \
    'page controls expose touch-sized targets'
require "$touch_metrics" 'readonly property int adaptiveMinimumControlHeight:[[:space:]]*directTouch' \
    'shared controls convert rendered targets into host-local coordinates'
for adaptive_control in "$button_control" "$slider_control" "$switch_control" "$checkbox_control" "$text_field_control"; do
    require "$adaptive_control" 'touchMetrics[.]adaptiveMinimumControlHeight' \
        "$(basename "$adaptive_control") consumes the universal touch target"
done
for hover_control in "$button_control" "$slider_control" "$switch_control" "$checkbox_control"; do
    require "$hover_control" 'hoverEnabled:[[:space:]]*touchMetrics[.]hoverSupported' \
        "$(basename "$hover_control") follows the selected hover capability"
done
if grep -Eq 'property int (columns|topBarHeight|horizontalMargin|minimumTouchTarget|maximumButtonExtent|buttonSpacing)' "$phone_profile"; then
    printf 'FAIL: the phone profile must remain a capability-only adapter\n' >&2
    exit 1
fi
printf 'PASS: the phone profile remains a capability-only adapter\n'
require "$home" 'TabletTouchConfiguration[[:space:]]*\{' \
    'TabletHome consumes the selector-backed presentation settings'
require "$home" 'semanticScreenId:[[:space:]]*"tablet[.]home"' \
    'TabletHome declares the versioned semantic screen identity'
require "$home" 'objectName:[[:space:]]*"tablet"' \
    'TabletHome preserves the native C++ routing identity'
require "$home" 'objectName:[[:space:]]*tablet[.]semanticScreenId' \
    'TabletHome publishes its semantic identity through a native Accessibility marker'
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
require "$home" 'objectName:[[:space:]]*"nav[.]close"' \
    'the visible close action exposes the common semantic control identity'
require "$home" 'onClicked:[[:space:]]*tabletProxy\.hideAndroidTablet\(\)' \
    'the close control routes through the native screen-space presenter'
require "$home" 'hoverEnabled:[[:space:]]*!presentation\.touchOptimized' \
    'touch presentation does not depend on hover input'
require "$button" 'hoverEnabled:[[:space:]]*tabletButton\.hoverEnabled' \
    'tablet buttons suppress synthetic hover handling on direct touch'
require "$menu_view" 'pressDelay:[[:space:]]*touchMetrics[.]pressDelay' \
    'tablet menus share the touch scroll activation delay'
require "$menu_view" 'hoverEnabled:[[:space:]]*touchMetrics[.]hoverSupported' \
    'tablet menus retain hover only on capable hybrid devices'
require "$menu_view" 'Accessible[.]onPressAction:[[:space:]]*root[.]activateItem' \
    'tablet menu actions expose semantic activation'
require "$menu_view" 'Keys[.]onSpacePressed:[[:space:]]*root[.]activateItem' \
    'tablet menu actions support hardware-keyboard activation'
require "$menu_item" 'Math[.]max\(2 \* label[.]implicitHeight, minimumControlHeight\)' \
    'tablet menu rows consume the universal touch target'
require "$menu_item" '20 \* root[.]touchTextScale' \
    'tablet menu labels follow the bounded system font scale'

printf 'Phone tablet touchscreen QML checks passed.\n'
