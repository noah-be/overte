#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tablet_header="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.h"
tablet_source="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.cpp"
window_root="$repo_root/interface/resources/qml/hifi/tablet/WindowRoot.qml"
action_bar="$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js"
dialogs="$repo_root/interface/src/ui/DialogsManager.cpp"

require() {
    local file="$1"
    local pattern="$2"
    local message="$3"
    if ! grep -Eq "$pattern" "$file"; then
        echo "phone tablet presenter check failed: $message" >&2
        exit 1
    fi
}

require "$tablet_header" 'Q_INVOKABLE void showAndroidTablet\(int width, int height\)' \
    'screen-space presenter is not exposed to the phone script'
require "$tablet_source" 'setToolbarMode\(true\)' \
    'presenter does not reuse the established tablet window and proxy path'
require "$tablet_source" 'setPosition\(leftInset, topInset\)' \
    'tablet is not anchored inside the rounded-corner safe area'
require "$tablet_source" 'setSize\(width - leftInset - rightInset,' \
    'tablet does not follow the safe Android surface dimensions'
require "$tablet_source" 'height - topInset - bottomInset\)' \
    'tablet height does not preserve its safe Android surface inset'
require "$tablet_source" 'TABLET_HOME_SOURCE_URL' \
    'presenter does not load the established Tablet home'
require "$window_root" 'property bool screenSpaceMode: false' \
    'tablet window lacks explicit screen-space presentation state'
require "$window_root" 'frame.visible = !value' \
    'desktop window decoration is not removed in screen-space mode'
require "$window_root" 'if \(screenSpaceMode\)[[:space:]]*\{' \
    'tablet app navigation cannot restore the legacy 480x706 window size'
require "$action_bar" 'Tablet\.getTablet\("com.highfidelity.interface.tablet.system"\)' \
    'mobile action bar does not use the system TabletProxy'
require "$action_bar" 'systemTablet\.resizeAndroidTablet\(Window.innerWidth, Window.innerHeight\)' \
    'tablet is not resized after Android surface geometry changes'
require "$action_bar" 'Controller\.setVPadHidden\(tabletShown\)' \
    'world touch controls are not suspended while the tablet owns input'
require "$action_bar" 'navigationBar\.visible = !tabletShown' \
    'world action controls can remain above the full-screen tablet'
require "$dialogs" 'tablet->handleAndroidTabletBack\(\)' \
    'Android Back is not routed through tablet navigation'

if grep -Eq 'WebTablet|tablet-ui/tabletUI' "$action_bar" "$tablet_source"; then
    echo 'phone tablet presenter check failed: VR WebTablet path leaked into touchscreen integration' >&2
    exit 1
fi

echo 'phone tablet presenter checks passed'
