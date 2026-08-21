#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly security_root="$repo_root/interface/resources/qml/hifi/dialogs/security"
readonly shared_config="$security_root/SecurityTouchConfiguration.qml"
readonly base_profile="$repo_root/interface/resources/qml/controlsUit/TouchUiProfileBase.qml"
readonly security="$security_root/Security.qml"
readonly entity_allowlist="$security_root/EntityScriptQMLAllowlist.qml"
readonly script_security="$security_root/ScriptSecurity.qml"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$shared_config" 'showScriptingPlugins:[[:space:]]*profile[.]scriptingPluginsAvailable' \
    'Security derives optional features from the shared device profile'
require "$base_profile" 'property bool scriptingPluginsAvailable:[[:space:]]*true' \
    'desktop retains scripting-plugin security controls'
require "$security" 'SecurityTouchConfiguration[[:space:]]*\{' \
    'Security resolves its Phone presentation through QFileSelector'
require "$security" 'visible:[[:space:]]*touchConfiguration[.]showScriptingPlugins' \
    'Security gates the complete scripting-plugin section'
require "$security" 'if[[:space:]]*\(touchConfiguration[.]showScriptingPlugins\)' \
    'hidden Phone scripting-plugin state cannot be written during construction'
require "$entity_allowlist" 'SecuritySettings[.]normalizeAllowlist' \
    'entity/QML allowlist handles empty and malformed stored values safely'
require "$script_security" 'SecuritySettings[.]normalizeAllowlist' \
    'script allowlists share deterministic normalization'
require "$entity_allowlist" 'anchors[.]bottom:[[:space:]]*saveChanges[.]top' \
    'entity/QML allowlist editor shrinks above its touch-sized Save action'
require "$entity_allowlist" 'Component[.]onDestruction' \
    'entity/QML allowlist releases IME focus on external teardown'
require "$script_security" 'Component[.]onDestruction' \
    'script security releases IME focus on external teardown'

node --check "$security_root/SecuritySettings.js"
node "$script_dir/phone-tablet-security-normalization-test.js"
printf 'Android phone Security Settings contract checks passed.\n'
