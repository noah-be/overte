#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly tablet_header="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.h"
readonly tablet_source="$repo_root/libraries/ui/src/ui/TabletScriptingInterface.cpp"
readonly tablet_root="$repo_root/interface/resources/qml/hifi/tablet/TabletRoot.qml"
readonly tablet_home="$repo_root/interface/resources/qml/hifi/tablet/TabletHome.qml"
readonly application="$repo_root/interface/src/Application.cpp"
readonly interface_cmake="$repo_root/interface/CMakeLists.txt"
readonly phone_gradle="$repo_root/android/phone/apps/phoneInterface/build.gradle"

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

require "$tablet_header" 'Q_INVOKABLE TabletProxy\* getTablet\(' \
    'the established Tablet.getTablet API remains available'
require "$tablet_header" 'Q_INVOKABLE TabletButtonProxy\* addButton\(' \
    'tablet applications can register home-screen buttons'
require "$tablet_header" 'Q_INVOKABLE void gotoHomeScreen\(' \
    'the presenter can return the proxy to its home screen'
require "$tablet_header" 'Q_INVOKABLE void loadQMLSource\(' \
    'existing QML tablet applications remain supported'
require "$tablet_header" 'Q_INVOKABLE void gotoWebScreen\(' \
    'existing web tablet applications remain supported'
require "$tablet_header" 'Q_INVOKABLE bool pushOntoStack\(' \
    'existing tablet applications retain stack navigation'
require "$tablet_header" 'Q_PROPERTY\(bool tabletShown' \
    'the screen-space presenter can expose tablet visibility to scripts'

require "$tablet_source" 'TabletScriptingInterface::QML[[:space:]]*=[[:space:]]*"hifi/tablet/TabletRoot.qml"' \
    'the system tablet still uses the shared TabletRoot QML'
require "$application" 'registerGlobalObject\([^,]+,[[:space:]]*"Tablet"' \
    'the Tablet scripting global is registered by Interface'
require "$tablet_root" 'objectName:[[:space:]]*"tabletRoot"' \
    'TabletRoot keeps the object identity used by C++ routing'
require "$tablet_root" 'signal screenChanged\(var type, var url\)' \
    'TabletRoot reports navigation changes to TabletProxy'
require "$tablet_root" 'function closeDialog\(\)' \
    'TabletRoot provides the first stage of Android Back handling'
require "$tablet_root" 'function returnToPreviousApp\(\)' \
    'TabletRoot provides application-stack Back handling'
require "$tablet_root" 'anchors.fill:[[:space:]]*parent' \
    'the shared loader follows its screen-space host dimensions'
require "$tablet_home" 'Tablet.getTablet\("com.highfidelity.interface.tablet.system"\)' \
    'TabletHome binds to the established system tablet proxy'
require "$tablet_home" 'SwipeView[[:space:]]*\{' \
    'TabletHome retains touch-page navigation support'

require "$phone_gradle" 'inputs.dir\(file\("[$]\{projectDir\}/../../../../interface/resources"\)\)' \
    'tablet QML resources participate in Android package invalidation'
require "$interface_cmake" 'file\(GLOB_RECURSE QML_SRC CONFIGURE_DEPENDS' \
    'new tablet QML selector files trigger incremental CMake regeneration'
require "$phone_gradle" 'inputs.dir\(file\("[$]\{projectDir\}/../../../../scripts"\)\)' \
    'tablet script QML and selectors participate in Android package invalidation'
require "$phone_gradle" 'from new File\(projectDir, '\''../../../../scripts'\''\)' \
    'Settings QML and its Android selector are copied into phone assets'
if grep -Eq "exclude .*android_phoneInterface|exclude .*settings" "$phone_gradle"; then
    printf 'FAIL: Android selector or Settings assets are excluded from phone packaging\n' >&2
    exit 1
fi
require "$phone_gradle" "include '[*][*]/android/phone/apps/phoneInterface/libraries/interface/resources[.]rcc'" \
    'the phone package includes the native Interface resource collection'

printf 'Android tablet core contract checks passed.\n'
