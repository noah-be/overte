#!/usr/bin/env bash
set -euo pipefail

android_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(cd -- "$android_dir/.." && pwd)"
device_cpp="$repo_root/libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.cpp"
device_header="$repo_root/libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.h"
phone_mapping="$repo_root/interface/resources/controllers/touchscreenvirtualpad-phone.json"

require() {
    local file=$1 pattern=$2 message=$3
    grep -Eq -- "$pattern" "$file" || {
        printf 'FAIL: %s\n' "$message" >&2
        exit 1
    }
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
