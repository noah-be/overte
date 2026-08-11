#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly action_bar="$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js"
readonly button_qml="$repo_root/interface/resources/qml/hifi/+android_interface/button.qml"

grep -Fq 'property bool bindToAudioMute: false' "$button_qml"
grep -Fq 'value: AudioScriptingInterface.muted' "$button_qml"
grep -Fq 'value: AudioScriptingInterface.muted ? "UNMUTE" : "MUTE"' "$button_qml"
if [[ "$(grep -Fc 'when: button.bindToAudioMute' "$button_qml")" -ne 2 ]]; then
    echo 'FAIL: microphone state bindings are not both opt-in' >&2
    exit 1
fi

grep -Fq 'bindToAudioMute: true' "$action_bar"
grep -Fq 'isActive: Audio.muted' "$action_bar"
grep -Fq 'Audio.muted = !Audio.muted;' "$action_bar"
if grep -Eq 'mutedChanged[.](connect|disconnect)|microphoneButton[.](isActive|text)[[:space:]]*=' "$action_bar"; then
    echo 'FAIL: script thread still writes microphone QML state asynchronously' >&2
    exit 1
fi

grep -Fq 'Script.clearTimeout(deferredLayoutTimer)' "$action_bar"
grep -Fq 'if (shuttingDown || width <= 0 || height <= 0)' "$action_bar"
grep -Fq 'applyBarGeometry(navigationBar' "$action_bar"

node --check "$action_bar"
node "$script_dir/phone-actionbar-lifecycle-mock.js"

printf 'Phone action-bar QML lifetime checks passed.\n'
