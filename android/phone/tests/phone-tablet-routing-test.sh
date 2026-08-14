#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly tablet_header="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.h"
readonly tablet_source="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.cpp"
readonly dialogs="$repo_root/interface/src/ui/DialogsManager.cpp"
readonly action_bar="$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js"
readonly phone_defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
readonly tablet_apps="$repo_root/scripts/system/+android_phoneInterface/mobileTabletApps.js"
readonly activity="$repo_root/android/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java"
readonly native_handler="$repo_root/android/phone/apps/phoneInterface/src/PhoneUrlHandler.cpp"
readonly phone_router="$repo_root/interface/src/ui/PhoneDialogRouter.h"
readonly window_root="$repo_root/interface/resources/qml/hifi/tablet/WindowRoot.qml"
readonly phone_ui_profile="$repo_root/interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"

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
require "$phone_ui_profile" 'safeInsetLeft:[[:space:]]*25' \
    'the phone profile supplies its rounded-corner left safety inset'
require "$tablet_source" 'root->property\("screenSpaceSafeInsetLeft"\)' \
    'the native presenter reads safe-area geometry from the selected UI profile'
require "$tablet_source" '_desktopWindow->setPosition\(leftInset,[[:space:]]*topInset\)' \
    'the tablet surface starts inside the profile-provided safe area'
require "$tablet_source" 'width[[:space:]]*-[[:space:]]*leftInset[[:space:]]*-[[:space:]]*rightInset' \
    'the tablet width preserves asymmetric horizontal safety margins'
require "$tablet_source" 'height[[:space:]]*-[[:space:]]*topInset[[:space:]]*-[[:space:]]*bottomInset' \
    'the tablet height preserves asymmetric vertical safety margins'
require "$tablet_source" 'width <= leftInset \+ rightInset \|\| height <= topInset \+ bottomInset' \
    'invalid transient Android surface dimensions are ignored'
require "$tablet_source" 'else if \(_state != State::Home\)[[:space:]]*\{[[:space:]]*$' \
    'Back distinguishes app navigation from closing the tablet home'
require "$tablet_source" 'gotoHomeScreen\(\);' \
    'Back from an app replaces content without reapplying host geometry'
if awk '
    /bool TabletProxy::handleAndroidTabletBack\(\)/ { in_back = 1 }
    in_back && /showAndroidTablet\(/ { bad = 1 }
    in_back && /^}/ { exit bad }
    END { if (bad) exit 1 }
' "$tablet_source"; then
    printf 'PASS: app Back cannot compound the screen-space safety inset\n'
else
    printf 'FAIL: app Back must not resize the existing screen-space host\n' >&2
    exit 1
fi
require "$tablet_source" 'setScreenSpaceMode' \
    'the shared root is explicitly switched to screen-space presentation'
require "$window_root" 'Qt\.callLater\(alignScreenSpaceWindow\)' \
    'the frameless tablet corrects desktop visibility repositioning asynchronously'
require "$window_root" 'function alignScreenSpaceWindow\(\)' \
    'the screen-space host exposes a deterministic display-origin alignment step'
require "$window_root" 'screenSpaceSafeInsetLeft:[[:space:]]*touchUiProfile[.]safeInsetLeft' \
    'the QML host consumes the selected profile safe area'
require "$window_root" 'x[[:space:]]*=[[:space:]]*screenSpaceSafeInsetLeft' \
    'the screen-space tablet preserves its left display margin'
require "$window_root" 'y[[:space:]]*=[[:space:]]*screenSpaceSafeInsetTop' \
    'the screen-space tablet preserves its top display margin'
require "$phone_ui_profile" 'screenSpaceContentScale:[[:space:]]*2[.]5' \
    'Android tablet applications share a touch-readable 250 percent scale'
require "$window_root" 'screenSpaceContentScale:[[:space:]]*touchUiProfile[.]screenSpaceContentScale' \
    'the screen-space host obtains content scale from the device profile'
require "$window_root" 'readonly property real contentScale:[[:space:]]*tabletRoot\.screenSpaceMode' \
    'the single host scale covers every Android tablet surface'
require "$window_root" 'scale:[[:space:]]*contentScale' \
    'the common loader applies the Android scale to the complete app subtree'
require "$window_root" 'width:[[:space:]]*pane\.contentWidth[[:space:]]*/[[:space:]]*contentScale' \
    'the loader compensates logical width before anchored apps are laid out'
require "$window_root" 'height:[[:space:]]*pane\.scrollHeight[[:space:]]*/[[:space:]]*contentScale' \
    'the loader compensates logical height before anchored apps are laid out'
require "$window_root" 'loader\.item\.width[[:space:]]*=[[:space:]]*loader\.width' \
    'loaded apps inherit the already compensated parent width'
require "$window_root" 'loader\.item\.height[[:space:]]*=[[:space:]]*loader\.height' \
    'loaded apps inherit the already compensated parent height'
require "$tablet_source" 'QVariant\(TABLET_HOME_SOURCE_URL\)' \
    'opening the tablet deterministically presents its home screen'
require "$tablet_source" 'emit tabletShownChanged\(\)' \
    'world controls can react to tablet visibility changes'

require "$dialogs" 'if \(offscreenUi && offscreenUi->isVisible\("LoginDialog"\)\)' \
    'Android Back gives the login modal first refusal'
require "$dialogs" 'if \(offscreenUi && offscreenUi->isVisible\("AddressBarDialog"\)\)' \
    'Android Back gives the address modal refusal before the tablet'
require "$dialogs" 'tablet->handleAndroidTabletBack\(\)' \
    'Android edge-swipe Back is routed into tablet navigation'
require "$activity" 'private static native boolean nativeHandleBack\(\);' \
    'the Android activity exposes the native Back router'
require "$activity" 'public boolean dispatchKeyEvent\(KeyEvent event\)' \
    'the Android activity intercepts Back key events'
require "$activity" 'public void onBackPressed\(\)' \
    'the Android activity also intercepts the Qt 5 direct Back callback'
require "$activity" 'registerOnBackInvokedCallback' \
    'Android edge-swipe and predictive Back are registered with the phone router'
require "$activity" 'unregisterOnBackInvokedCallback' \
    'the predictive Back callback is released with the Activity'
require "$activity" 'private void handleSystemBack\(\)' \
    'all Android Back delivery paths share one routing function'
require "$activity" 'moveTaskToBack\(true\)' \
    'Back backgrounds Overte instead of destroying native state when no UI consumes it'
require "$activity" 'event\.getAction\(\) == KeyEvent\.ACTION_DOWN' \
    'the Activity owns the complete Back key-down sequence'
require "$activity" 'event\.getRepeatCount\(\) == 0' \
    'only the first Back key-down invokes native routing'
require "$activity" 'if \(nativeBackConsumed\)' \
    'handled Back repeat events stay out of Qt'
require "$activity" 'event\.getAction\(\) == KeyEvent\.ACTION_UP && nativeBackConsumed' \
    'the matching Back key-up is consumed with its handled key-down'
require "$native_handler" 'PhoneInterfaceActivity_nativeHandleBack' \
    'JNI implements the Android Back bridge'
require "$native_handler" 'QThread::currentThread\(\) == application->thread\(\)' \
    'the Back bridge avoids blocking when already on the Qt thread'
require "$native_handler" 'Qt::BlockingQueuedConnection' \
    'the Android thread receives the synchronous dialog-routing result'
require "$native_handler" 'phone::closeTopmostDialog\(\)' \
    'the JNI bridge reuses the minimal phone dialog router'
require "$phone_router" 'bool closeTopmostDialog\(\);' \
    'the Android entry point avoids the desktop dialog header graph'
require "$dialogs" 'bool phone::closeTopmostDialog\(\)' \
    'the minimal bridge delegates inside DialogsManager implementation'
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
require "$phone_defaults" '"system/\+android_phoneInterface/mobileTabletApps[.]js"' \
    'the Android tablet starts its dedicated touch-compatible app registrar'
require "$tablet_apps" 'text:[[:space:]]*"AUDIO"' \
    'the Android tablet registers the Audio app'
require "$tablet_apps" 'text:[[:space:]]*"SETTINGS"' \
    'the Android tablet registers the Settings app'
require "$tablet_apps" 'text:[[:space:]]*"MENU"' \
    'the Android tablet registers Pico-compatible Menu navigation'
if grep -Eq 'editProperties|HMD|WebTablet|Desktop[.]show' "$tablet_apps"; then
    printf 'FAIL: Android Tablet apps use a mutable QML proxy or desktop/VR presentation\n' >&2
    exit 1
fi
printf 'PASS: Android Tablet app buttons are immutable and screen-space only\n'

for supported in \
        system/bubble.js \
        system/pal.js \
        system/avatarapp.js \
        system/places/places.js \
        system/quickGoto.js; do
    require "$phone_defaults" "$supported" \
        "the Android tablet enables Pico app backend $supported"
done

for unsupported in \
        system/tablet-ui/tabletUI.js \
        system/tablet-users.js \
        system/more/app-more.js \
        system/tablet-position/tabletPosition.js \
        system/create/edit.js; do
    if grep -Fq -- "$unsupported" "$phone_defaults"; then
        printf 'FAIL: unvalidated tablet app is enabled in the Android MVP: %s\n' "$unsupported" >&2
        exit 1
    fi
done
printf 'PASS: VR-only and unsupported remote-web tablet apps remain disabled\n'
require "$phone_defaults" 'system/\+android_phoneInterface/phoneEmote[.]js' \
    'the Android tablet enables the native-QML phone Emote app'
if grep -Fq -- 'system/emote.js' "$phone_defaults"; then
    printf 'FAIL: phone startup enables the legacy Web/controller Emote app\n' >&2
    exit 1
fi
printf 'PASS: legacy Web/controller Emote remains disabled\n'
require "$tablet_apps" '"hifi/dialogs/GeneralPreferencesDialog[.]qml":[[:space:]]*GENERAL_SETTINGS_SOURCE' \
    'General Settings stays inside the Android tablet instead of opening a desktop window'

printf 'Android tablet routing checks passed.\n'
