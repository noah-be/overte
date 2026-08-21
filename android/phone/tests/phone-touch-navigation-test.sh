#!/usr/bin/env bash
set -euo pipefail

android_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
repo_root="$(cd -- "$android_dir/.." && pwd)"
device_cpp="$repo_root/libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.cpp"
device_header="$repo_root/libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.h"
phone_mapping="$repo_root/interface/resources/controllers/touchscreenvirtualpad-phone.json"
phone_action_bar="$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js"
phone_defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
phone_tablet_apps="$repo_root/scripts/system/+android_phoneInterface/mobileTabletApps.js"
preferences_policy="$repo_root/interface/resources/qml/hifi/tablet/TabletGeneralPreferencesPolicy.qml"
phone_ui_profile="$repo_root/interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"
preferences_cpp="$repo_root/interface/src/ui/PreferencesDialog.cpp"
application_events="$repo_root/interface/src/Application_Events.cpp"
application_graphics="$repo_root/interface/src/Application_Graphics.cpp"
gl_widget="$repo_root/libraries/gl/src/gl/GLWidget.cpp"

require() {
    local file=$1 pattern=$2 message=$3
    grep -Eq -- "$pattern" "$file" || {
        printf 'FAIL: %s\n' "$message" >&2
        exit 1
    }
}

reject() {
    local file=$1 pattern=$2 message=$3
    if grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$message" >&2
        exit 1
    fi
}

python3 -m json.tool "$phone_mapping" >/dev/null
python3 - "$phone_mapping" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as mapping_file:
    channels = json.load(mapping_file)["channels"]

for axis in ("RX", "RY"):
    source = "TouchscreenVirtualPad." + axis
    channel = next((item for item in channels if item.get("from") == source), None)
    if channel is None:
        raise SystemExit("FAIL: missing phone view axis " + source)
    if "invert" in channel.get("filters", []):
        raise SystemExit("FAIL: phone view axis remains mirrored: " + source)
PY

require "$device_cpp" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'phone touch navigation is not compile-time isolated'
require "$device_cpp" 'touchscreenvirtualpad-phone[.]json' \
    'phone build does not select its touch navigation mapping'
require "$device_header" 'PINCH_OUT' 'pinch-out input channel is missing'
require "$device_header" 'PINCH_IN' 'pinch-in input channel is missing'
require "$device_cpp" 'totalScaleFactor\(\)' 'pinch scale is not consumed'
require "$device_cpp" 'settings[.]value\("android/phone/pinchZoomEnabled", false\)[.]toBool\(\)' \
    'phone pinch zoom is not read live with a disabled default'
reject "$device_cpp" 'static Setting::Handle<bool> phonePinchZoomEnabled' \
    'phone pinch gestures retain a stale startup setting cache'
require "$application_events" '#if !defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'phone gesture routing does not isolate the legacy keyboard pinch path'
require "$application_events" '_keyboardMouseDevice->touchGestureEvent\(event\)' \
    'legacy keyboard gesture routing contract is missing'
require "$preferences_cpp" '"Navigation"' \
    'phone navigation preference category is missing'
require "$preferences_cpp" 'Enable two-finger perspective zoom' \
    'phone pinch zoom preference is missing'
require "$preferences_policy" 'profile[.]navigationPreferencesAvailable' \
    'tablet settings derive Navigation availability from the device profile'
require "$phone_ui_profile" 'navigationPreferencesAvailable:[[:space:]]*true' \
    'phone tablet settings do not expose Navigation'
require "$phone_defaults" 'system/\+android_phoneInterface/mobileTabletApps[.]js' \
    'phone defaults do not load the phone tablet app registrar'
require "$phone_tablet_apps" 'SETTINGS_SOURCE.*settings/Settings[.]qml' \
    'phone tablet app registrar does not expose Settings'
reject "$phone_defaults" 'system/settings/settings[.]js' \
    'phone defaults register the Settings app twice'
require "$phone_action_bar" 'function toggleCameraMode\(\)' \
    'phone camera mode button handler is missing'
require "$phone_action_bar" 'MyAvatar[.]cameraBoomLength = 0[.]5;' \
    'phone first-person toggle does not synchronize the camera boom'
require "$phone_action_bar" 'Camera[.]mode = "first person look at";' \
    'phone camera button cannot enter first-person view'
require "$phone_action_bar" 'Camera[.]mode = "look at";' \
    'phone camera button cannot enter third-person view'
require "$phone_action_bar" 'text: "TABLET"' \
    'phone action bar lost the tablet launcher during integration'
require "$phone_action_bar" 'text: "VIEW"' \
    'phone action bar does not expose the view toggle'
reject "$phone_action_bar" 'loginButton|text: "LOGIN"' \
    'phone action bar still contains the replaced login button'
reject "$phone_action_bar" 'Camera[.]modeUpdated.*cameraButton|updateCameraButton' \
    'phone camera mode changes synchronously mutate the triggering QML button'
require "$gl_widget" '#if !defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'phone GL viewport remains permanently IME enabled'
require "$application_graphics" 'focusTextChanged.*_primaryWidget' \
    'phone GL viewport does not follow real QML text focus'
require "$application_graphics" 'WA_InputMethodEnabled, focusText' \
    'phone input-method state is not gated by text focus'

require "$phone_mapping" 'TouchscreenVirtualPad[.]LX.*Actions[.]TranslateX' \
    'virtual joystick lateral movement mapping is missing'
require "$phone_mapping" 'TouchscreenVirtualPad[.]LY.*Actions[.]TranslateZ' \
    'virtual joystick forward movement mapping is missing'
require "$phone_mapping" 'TouchscreenVirtualPad[.]RX' \
    'horizontal swipe input is missing'
require "$phone_mapping" 'Actions[.]Yaw' 'horizontal swipe yaw mapping is missing'
require "$phone_mapping" 'TouchscreenVirtualPad[.]RY' 'vertical swipe input is missing'
require "$phone_mapping" 'Actions[.]Pitch' 'vertical swipe pitch mapping is missing'
require "$phone_mapping" 'TouchscreenVirtualPad[.]PinchOut' \
    'pinch-out input mapping is missing'
require "$phone_mapping" 'Actions[.]BoomOut' 'pinch-out zoom action is missing'
require "$phone_mapping" 'TouchscreenVirtualPad[.]PinchIn' \
    'pinch-in input mapping is missing'
require "$phone_mapping" 'Actions[.]BoomIn' 'pinch-in zoom action is missing'

printf 'PASS: Android phone touch navigation contracts\n'
