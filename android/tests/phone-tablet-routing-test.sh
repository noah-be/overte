#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly tablet_header="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.h"
readonly tablet_source="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.cpp"
readonly dialogs="$repo_root/interface/src/ui/DialogsManager.cpp"
readonly action_bar="$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js"
readonly phone_defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
readonly settings_app="$repo_root/scripts/system/settings/settings.js"

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

for method in showAndroidTablet resizeAndroidTablet hideAndroidTablet handleAndroidTabletBack; do
    require "$tablet_header" "Q_INVOKABLE .*${method}\\(" \
        "the Android presenter API exposes ${method}"
done
require "$tablet_header" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'the screen-space presenter API is restricted to the phone client'
require "$tablet_source" '_desktopWindow->setPosition\(0,[[:space:]]*0\)' \
    'the tablet surface starts at the Android viewport origin'
require "$tablet_source" '_desktopWindow->setSize\(width,[[:space:]]*height\)' \
    'the tablet surface fills the current Android viewport'
require "$tablet_source" 'width <= 0 \|\| height <= 0' \
    'invalid transient Android surface dimensions are ignored'
require "$tablet_source" 'setScreenSpaceMode' \
    'the shared root is explicitly switched to screen-space presentation'
require "$tablet_source" 'QVariant\(TABLET_HOME_SOURCE_URL\)' \
    'opening the tablet deterministically presents its home screen'
require "$tablet_source" 'emit tabletShownChanged\(\)' \
    'world controls can react to tablet visibility changes'

require "$dialogs" 'if \(offscreenUi && offscreenUi->isVisible\("LoginDialog"\)\)' \
    'Android Back gives the login modal first refusal'
require "$dialogs" 'if \(offscreenUi && offscreenUi->isVisible\("AddressBarDialog"\)\)' \
    'Android Back gives the address modal refusal before the tablet'
require "$dialogs" 'tablet->handleAndroidTabletBack\(\)' \
    'Android Back is routed into tablet navigation'
if awk '
    /bool DialogsManager::closePhoneDialog\(\)/ { in_function = 1 }
    in_function && /isVisible\("LoginDialog"\)/ { login = NR }
    in_function && /isVisible\("AddressBarDialog"\)/ { address = NR }
    in_function && /handleAndroidTabletBack\(\)/ { tablet = NR }
    in_function && /^}/ { exit !(login && address && tablet && login < address && address < tablet) }
    END { if (in_function) exit !(login && address && tablet && login < address && address < tablet) }
' "$dialogs"; then
    printf 'PASS: Android Back follows modal, address, then tablet priority\n'
else
    printf 'FAIL: Android Back routing priority changed\n' >&2
    exit 1
fi

require "$action_bar" 'tablet\.showAndroidTablet\(Window\.innerWidth,[[:space:]]*Window\.innerHeight\)' \
    'the action bar opens a viewport-sized tablet'
require "$action_bar" 'Window\.geometryChanged\.connect\(resizeTablet\)' \
    'surface changes resize an open tablet'
require "$action_bar" 'systemTablet\.tabletShownChanged\.connect\(tabletVisibilityChanged\)' \
    'the action bar observes tablet visibility'
require "$action_bar" 'Controller\.setVPadHidden\(tabletShown\)' \
    'the virtual pad cannot receive touches through the tablet'
require "$action_bar" 'Controller\.captureTouchEvents\(\)' \
    'the general touchscreen device cannot receive tablet drags as world input'
require "$action_bar" 'Controller\.releaseTouchEvents\(\)' \
    'closing the tablet releases the captured touchscreen input'
require "$action_bar" 'navigationBar\.visible[[:space:]]*=[[:space:]]*!tabletShown' \
    'navigation controls do not overlay the open tablet'
require "$action_bar" 'audioBar\.visible[[:space:]]*=[[:space:]]*!tabletShown' \
    'audio controls do not overlay the open tablet'
require "$action_bar" 'Controller\.setVPadHidden\(false\)' \
    'script shutdown restores world touch controls'
require "$action_bar" 'tabletVisibilityChanged\(\);' \
    'script startup synchronizes controls with an already-visible tablet'
require "$phone_defaults" '"system/audio[.]js"' \
    'the Android tablet registers the touch-compatible Audio app'
require "$phone_defaults" '"system/settings/settings[.]js"' \
    'the Android tablet registers the touch-compatible Settings app'

for unsupported in \
        system/tablet-ui/tabletUI.js \
        system/create/edit.js \
        system/tablet-users.js \
        system/avatarapp.js \
        system/emote.js \
        system/more/app-more.js; do
    if grep -Fq -- "$unsupported" "$phone_defaults"; then
        printf 'FAIL: unvalidated tablet app is enabled in the Android MVP: %s\n' "$unsupported" >&2
        exit 1
    fi
done
printf 'PASS: unvalidated VR, desktop, and remote-web tablet apps remain disabled\n'
require "$settings_app" 'typeof ANDROID_PHONE_INTERFACE !== "undefined" && ANDROID_PHONE_INTERFACE' \
    'Settings recognizes the Android screen-space tablet'
require "$settings_app" 'tablet[.]loadQMLSource\("hifi/tablet/TabletGeneralPreferences[.]qml"\)' \
    'General Settings stays inside the Android tablet instead of opening a desktop window'

printf 'Android tablet routing checks passed.\n'
