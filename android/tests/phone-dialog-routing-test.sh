#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

dialogs="$repo_root/interface/src/ui/DialogsManager.cpp"
login="$repo_root/interface/src/ui/LoginDialog.cpp"
events="$repo_root/interface/src/Application_Events.cpp"
body="$repo_root/interface/resources/qml/LoginDialog/+android_phoneInterface/LinkAccountBody.qml"
address_body="$repo_root/interface/resources/qml/+android_phoneInterface/AddressBarDialog.qml"

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

require "$dialogs" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'dialog routing is restricted to the phone build'
require "$dialogs" 'AddressBarDialog::show\(\)' \
    'Go To uses the screen-space address dialog'
require "$address_body" 'objectName:[[:space:]]*"AddressBarDialog"' \
    'phone selector provides the QML object expected by OffscreenUi'
require "$address_body" 'addressDialog\.loadAddress\(' \
    'phone Go To delegates lookup to the existing AddressBarDialog model'
require "$address_body" 'androidClickAction:' \
    'phone address actions use the Android-compatible button callback'
require "$login" 'LoginDialog::show\(\)' \
    'login uses the screen-space login dialog'
require "$login" 'acquirePhoneLoginUiFocus\(\)' \
    'phone login acquires UI focus through its idempotent helper'
require "$login" 'uiFocusChanged\(false\)' \
    'phone login dismissal releases script UI focus'
require "$login" 'if \(phoneLoginOwnsUiFocus\)' \
    'phone login focus release is idempotent'
require "$login" 'if \(!phoneLoginCleanupQueued\)' \
    'phone login queues Application cleanup at most once'
require "$body" 'loginDialog\.dismissPhoneLoginDialog\(\)' \
    'all phone QML dismissal paths use the complete C++ close transaction'
if awk '
        /void LoginDialog::dismissPhoneLoginDialog\(\)/ { in_phone_dismiss = 1 }
        in_phone_dismiss && /hidePhoneDialog\(\)/ { close_transaction = 1 }
        in_phone_dismiss && /getLoginDialogPoppedUp\(\)/ { stale_startup_guard = 1 }
        in_phone_dismiss && /^}/ { exit !(close_transaction && !stale_startup_guard) }
        END { if (in_phone_dismiss) exit !(close_transaction && !stale_startup_guard) }
    ' "$login"; then
    printf 'PASS: phone dismiss handles action-bar and startup dialogs identically\n'
else
    printf 'FAIL: phone dismiss still depends on the startup-only popup flag\n' >&2
    exit 1
fi
require "$dialogs" 'LoginDialog::hidePhoneDialog\(\)' \
    'programmatic and Hardware Back closes use the complete close transaction'
require "$events" 'closePhoneDialog\(\)' \
    'Android Back offers visible phone dialogs first refusal'
if awk '
        /void Application::keyPressEvent/ { in_key_press = 1 }
        in_key_press && /closePhoneDialog\(\)/ { close_line = NR }
        in_key_press && /emitKeyPressEvent\(event\)/ { emit_line = NR; exit }
        END { exit !(close_line && emit_line && close_line < emit_line) }
    ' "$events"; then
    printf 'PASS: consumed phone Back is intercepted before script delivery\n'
else
    printf 'FAIL: consumed phone Back can leak to scripts\n' >&2
    exit 1
fi
require "$events" '_keysPressed\.remove\(event->key\(\)\)' \
    'consumed phone Back clears application key bookkeeping'
require "$events" '_phoneBackKeyConsumed[[:space:]]*=[[:space:]]*false' \
    'phone Back state is cleared if focus changes before physical release'
require "$body" 'loginDialog\.loginDomain\(' \
    'domain credentials use DomainAccountManager through LoginDialog'
require "$body" 'loginDialog\.login\(' \
    'metaverse credentials use AccountManager through LoginDialog'
require "$body" 'androidClickAction:' \
    'phone login actions use the Android-compatible button callback'
require "$body" 'event\.key[[:space:]]*===[[:space:]]*Qt\.Key_Back' \
    'phone login handles Android Back inside QML before the generic overlay handler'
require "$body" 'event\.key[[:space:]]*===[[:space:]]*Qt\.Key_Escape' \
    'phone login gives Escape the same screen-space dismissal behavior'
require "$body" 'event\.accepted[[:space:]]*=[[:space:]]*true' \
    'phone login consumes its local dismissal key'
require "$body" 'Keys\.onReleased:' \
    'phone login also consumes the matching release before Application Home handling'
require "$body" 'keyDismissPending[[:space:]]*=[[:space:]]*true' \
    'phone login remains alive until it can consume the matching key release'
require "$body" 'if[[:space:]]*\(closing\)' \
    'phone login dismissal is guarded against duplicate cleanup'

if grep -Eq -- 'WelcomeBody|AndroidHelper|openTablet|Tablet\.getTablet' "$body"; then
    printf 'FAIL: phone login body contains an HMD/tablet-only dependency\n' >&2
    exit 1
fi
printf 'PASS: phone login has no HMD/tablet completion dependency\n'
