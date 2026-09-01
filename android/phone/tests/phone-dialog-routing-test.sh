#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"

"$script_dir/phone-login-state-contract-test.sh"

dialogs="$repo_root/interface/src/ui/DialogsManager.cpp"
login="$repo_root/interface/src/ui/LoginDialog.cpp"
events="$repo_root/interface/src/Application_Events.cpp"
body="$repo_root/interface/resources/qml/LoginDialog/+android_phoneInterface/LinkAccountBody.qml"
address_body="$repo_root/interface/resources/qml/+android_phoneInterface/AddressBarDialog.qml"
tablet_home="$repo_root/interface/resources/qml/hifi/tablet/TabletHome.qml"

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
require "$address_body" 'maximumAddressLength:[[:space:]]*4096' \
    'phone Go To bounds text before the QML/C++ boundary'
require "$address_body" 'addressField[.]text[[:space:]]*=[[:space:]]*""' \
    'phone Go To starts with an empty destination instead of desktop preselection'
require "$address_body" 'addressField[.]deselect\(\)' \
    'phone Go To suppresses the Android selection action menu on open'
require "$address_body" 'DialogsManager[.]requestPhoneSoftwareKeyboard\(\)' \
    'focused phone Go To input requests Qt Android native keyboard delivery'
require "$address_body" 'y:[[:space:]]*touchMetrics[.]keyboardVisible' \
    'phone Go To moves to the upper safe area while the system IME is visible'
require "$repo_root/interface/src/ui/DialogsManager.cpp" \
    'PhoneInterfaceActivity' \
    'Phone dialog routing targets the Android activity'
require "$repo_root/interface/src/ui/DialogsManager.cpp" \
    'requestSoftwareKeyboard' \
    'Phone dialog routing bridges native keyboard requests'
require "$repo_root/interface/src/scripting/DialogsManagerScriptingInterface.cpp" \
    'requestPhoneSoftwareKeyboard' \
    'Phone keyboard requests are exposed through the QML scripting facade'
require "$repo_root/android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java" \
    'PHONE_ADDRESS_INPUT_HINTS' \
    'Phone keyboard requests preserve URL and no-composition input hints'
require "$repo_root/android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java" \
    '0, height - 1, width, 1, PHONE_ADDRESS_INPUT_HINTS, 0' \
    'Phone reports covered editor geometry so Qt preserves adjustResize behavior'
require "$repo_root/interface/src/GLCanvas.cpp" \
    'QCoreApplication::sendEvent\(focusItem, &queryEvent\)' \
    'Phone forwards Android IME state queries to the focused offscreen QML field'
require "$repo_root/interface/src/GLCanvas.cpp" \
    'Qt::ImCursorRectangle.*Qt::ImAnchorRectangle' \
    'Phone maps Android cursor and selection handles to the QML field geometry'
require "$repo_root/libraries/ui/src/OffscreenUi.cpp" \
    'abc -> abccba' \
    'Offscreen UI documents and prevents duplicate Android composition delivery'
require "$repo_root/libraries/ui/src/OffscreenUi.cpp" \
    'window && window->activeFocusItem\(\) [?] true : result' \
    'Offscreen UI consumes the original event after Android QML IME delivery'
require "$address_body" 'candidate[[:space:]]*=[[:space:]]*addressField[.]text[.]trim\(\)' \
    'phone Go To normalizes surrounding address whitespace'
require "$address_body" '\\u0000-\\u001f\\u007f' \
    'phone Go To rejects address control characters'
require "$address_body" 'addressError[.]text[[:space:]]*=[[:space:]]*qsTr' \
    'phone Go To keeps invalid input visible with a local error'
require "$address_body" 'addressDialog[.]loadAddress\(candidate\)' \
    'phone Go To passes only the validated candidate to C++'
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
require "$tablet_home" 'Math[.]max\(loginTextMetrics[.]width,[[:space:]]*presentation[.]minimumTouchTarget\)' \
    'tablet login entry exposes a touch-sized width'
require "$tablet_home" 'Math[.]max\(loginTextMetrics[.]height,[[:space:]]*presentation[.]minimumTouchTarget\)' \
    'tablet login entry exposes a touch-sized height'
if awk '
        /text:[[:space:]]*qsTr\("Cancel"\)/ { in_cancel = 1 }
        in_cancel && /enabled:[[:space:]]*!phoneLogin[.]waiting/ { disabled_while_waiting = 1 }
        in_cancel && /androidClickAction:/ { exit disabled_while_waiting }
        END { if (in_cancel) exit disabled_while_waiting }
    ' "$body"; then
    printf 'PASS: phone login can be cancelled while authentication is pending\n'
else
    printf 'FAIL: phone login disables cancellation while authentication is pending\n' >&2
    exit 1
fi
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
require "$body" 'if[[:space:]]*\(waiting[[:space:]]*\|\|[[:space:]]*closing\)' \
    'phone login rejects duplicate keyboard and touch submissions'
require "$body" 'Flickable[[:space:]]*\{' \
    'phone login remains scrollable when the IME reduces available height'
require "$body" 'contentHeight:[[:space:]]*Math[.]max\(height,[[:space:]]*panel[.]height\)' \
    'phone login only scrolls when its form no longer fits'
require "$body" 'anchors[.]leftMargin:[[:space:]]*Math[.]min\(touchMetrics[.]spacingLarge,[[:space:]]*parent[.]width[[:space:]]*/[[:space:]]*4\)' \
    'phone login keeps non-negative usable width on narrow resize'
require "$body" 'inputMethodHints:[[:space:]]*Qt[.]ImhEmailCharactersOnly' \
    'phone login requests an email-capable system keyboard for account input'
require "$body" 'Qt[.]ImhSensitiveData' \
    'phone login marks password input as sensitive to the system IME'
require "$body" 'touchMetrics[.]ensureVisible\(viewport,' \
    'phone login reveals focused fields after software-keyboard resize'
require "$address_body" 'Qt[.]ImhNoAutoUppercase' \
    'phone address entry suppresses inappropriate automatic capitalization'
require "$body" 'Component[.]onDestruction:' \
    'phone login releases IME state during external or programmatic teardown'
require "$body" 'if[[:space:]]*\(phoneLogin[.]closing\)' \
    'late authentication responses cannot revive a closing dialog'
require "$body" 'maximumCredentialLength:[[:space:]]*4096' \
    'phone login bounds credential text retained by QML'
require "$body" 'password[.]text[[:space:]]*=[[:space:]]*""' \
    'phone login clears password text during dismissal and teardown'
require "$body" 'username[.]text[[:space:]]*=[[:space:]]*""' \
    'phone login clears username text during destruction fallback'
require "$login" 'phoneLoginState[.]beginRequest\(\)' \
    'phone login rejects a competing request at the C++ boundary'
require "$login" 'phoneLoginState[.]finishRequest\(\)' \
    'terminal authentication responses release the C++ request guard'
require "$body" 'waiting:[[:space:]]*loginDialog[.]isPhoneLoginRequestPending\(\)' \
    'a reopened login waits for an older in-flight request'
require "$body" 'if[[:space:]]*\(!phoneLogin[.]requestSubmitted\)' \
    'an older failed authentication response cannot alter a newly opened dialog'

if grep -Eq -- 'WelcomeBody|AndroidHelper|openTablet|Tablet\.getTablet' "$body"; then
    printf 'FAIL: phone login body contains an HMD/tablet-only dependency\n' >&2
    exit 1
fi
printf 'PASS: phone login has no HMD/tablet completion dependency\n'
