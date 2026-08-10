#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
repo_root="$(cd -- "$android_root/.." && pwd)"
failures=0
checks=0

pass() {
    checks=$((checks + 1))
    printf 'PASS %s\n' "$1"
}

fail() {
    checks=$((checks + 1))
    failures=$((failures + 1))
    printf 'FAIL %s\n' "$1" >&2
}

require_file() {
    local relative_path="$1"
    if [[ -f "$android_root/$relative_path" ]]; then
        pass "file: $relative_path"
    else
        fail "missing file: $relative_path"
    fi
}

require_text() {
    local relative_path="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "$android_root/$relative_path" ]] &&
            grep -Eq -- "$pattern" "$android_root/$relative_path"; then
        pass "$description"
    else
        fail "$description"
    fi
}

reject_text() {
    local relative_path="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "$android_root/$relative_path" ]] &&
            ! grep -Eiq -- "$pattern" "$android_root/$relative_path"; then
        pass "$description"
    else
        fail "$description"
    fi
}

manifest='apps/phoneInterface/src/main/AndroidManifest.xml'
gradle='apps/phoneInterface/build.gradle'
cmake='apps/phoneInterface/CMakeLists.txt'
permissions_activity='apps/phoneInterface/src/main/java/org/overte/phone/PermissionsActivity.java'
interface_activity='apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java'
pending_url_policy='apps/phoneInterface/src/main/java/org/overte/phone/PhonePendingUrlPolicy.java'
deep_link='apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLink.java'
deep_link_normalizer='apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java'
url_handler='apps/phoneInterface/src/PhoneUrlHandler.cpp'
phone_defaults='../scripts/+android_phoneInterface/defaultScripts.js'

require_text "$gradle" 'Declare the module identity before dependency preflight failures' \
    'phone Gradle diagnostics initialize AGP identity before dependency preflight'
require_text "$cmake" '../../shared/src/OffscreenGLCanvas[.]cpp' \
    'phone native build uses the shared Android OffscreenGLCanvas override'
require_text "$gradle" '../../shared/runtime-overrides/arm64-v8a' \
    'phone packaging uses shared Android runtime overrides'
reject_text "$cmake" '(\.\./|apps/)picoInterface/' \
    'phone native build does not compile Pico-owned sources'
reject_text "$gradle" '(\.\./|apps/)picoInterface/' \
    'phone packaging does not consume Pico-owned paths'

for source_file in \
        build-phone.sh \
        phone-prebuilt-16k-deps.sh \
        build-phone.gradle \
        settings-phone.gradle \
        tests/check-phone-elf-alignment.sh \
        tests/check-phone-apk-16k.sh \
        tests/check-phone-apk-contents.py \
        tests/check-phone-apk-metadata.sh \
        tests/check-phone-apk-padding.py \
        tests/phone-apk-contents-test.sh \
        tests/phone-apk-metadata-test.sh \
        tests/phone-apk-padding-test.sh \
        tests/phone-archive-extraction-test.sh \
        tests/phone-actionbar-qml-lifetime-test.sh \
        tests/phone-audio-output-race-test.sh \
        tests/phone-device-lock-test.sh \
        tests/phone-device-smoke-mock-test.sh \
        tests/phone-elf-alignment-test.sh \
        tests/phone-offscreen-ui-mip-test.sh \
        tests/phone-prebuilt-16k-deps-test.sh \
        tests/phone-build-download-parity-test.sh \
        tests/phone-prepare-architecture-test.sh \
        tests/phone-script-payload-test.sh \
        tests/verify-phone-16k-dependencies.sh \
        phone-device-lock.sh \
        prepare-phone-16k-conan-deps.sh \
        "$gradle" \
        "$cmake" \
        "$manifest" \
        "$permissions_activity" \
        "$interface_activity" \
        "$deep_link" \
        "$url_handler" \
        "$phone_defaults"; do
    require_file "$source_file"
done

require_text tests/check-phone-apk-contents.py 'qt_dependencies[.]xml' \
    'APK completeness gate consumes the Qt runtime declaration'
require_text tests/check-phone-apk-contents.py 'bundled_in_lib' \
    'APK completeness gate covers every declared native QML/plugin runtime'
require_text tests/check-phone-apk-contents.py 'bundled_in_assets' \
    'APK completeness gate covers every declared QML module asset'
require_text tests/check-phone-apk-contents.py 'libc[+][+]_shared[.]so' \
    'APK completeness gate requires the native C++ runtime'
require_text tests/check-phone-apk-contents.py 'libQt5Core_arm64-v8a[.]so' \
    'APK completeness gate requires the Qt Core runtime'
require_text tests/check-phone-apk-contents.py 'libQt5Qml_arm64-v8a[.]so' \
    'APK completeness gate requires the Qt QML runtime'
require_text tests/check-phone-apk-contents.py 'libQt5Quick_arm64-v8a[.]so' \
    'APK completeness gate requires the Qt Quick runtime'
require_text tests/check-phone-apk-contents.py 'duplicate ZIP entry names' \
    'APK completeness gate rejects ambiguous duplicate archive entries'
require_text tests/check-phone-apk-contents.py 'outside arm64-v8a' \
    'APK completeness gate rejects native payload for unexpected ABIs'
require_text tests/check-phone-apk-contents.py 'unexpected ARM64 native entries' \
    'package completeness gate rejects undeclared ARM64 runtimes'
require_text tests/check-phone-apk-contents.py 'verify_entry_integrity' \
    'package completeness gate streams ZIP entries to verify integrity'
require_text tests/check-phone-apk-contents.py 'sorted\(raw_archive_names\)' \
    'package completeness gate verifies every packaged ZIP entry'
require_text tests/check-phone-apk-contents.py 'S_ISLNK' \
    'package completeness gate rejects ZIP symbolic links'
require_text tests/check-phone-apk-contents.py 'unsafe ZIP entry path' \
    'package completeness gate rejects unsafe paths before host extraction'
require_text tests/check-phone-apk-contents.py 'value[[:space:]]*==[[:space:]]*canonical' \
    'package completeness gate requires canonical archive paths'
require_text tests/check-phone-apk-contents.py 'character[.]isprintable' \
    'package completeness gate rejects log-unsafe archive characters'
require_text tests/check-phone-apk-contents.py 'MAX_PACKAGE_BYTES' \
    'package completeness gate bounds the package file size'
require_text tests/check-phone-apk-contents.py 'MAX_PACKAGE_ENTRIES' \
    'package completeness gate bounds the ZIP entry count'
require_text tests/check-phone-apk-contents.py 'assets outside cache_assets[.]txt' \
    'package completeness gate rejects undeclared managed assets'
require_text tests/check-phone-apk-contents.py 'QML outside declared module roots' \
    'package completeness gate rejects undeclared QML modules'
require_text tests/check-phone-apk-contents.py 'mixes APK and Android App Bundle' \
    'package completeness gate rejects mixed archive layouts'
require_text tests/check-phone-apk-contents.py 'unexpected feature modules' \
    'package completeness gate rejects unreviewed AAB modules'
require_text tests/check-phone-apk-contents.py 'could not read Android phone package input' \
    'package completeness gate suppresses private input paths'
require_text tests/check-phone-elf-alignment.sh 'could not extract Android package' \
    'ELF gate reports archive failures without the private input path'
require_text tests/check-phone-elf-alignment.sh 'package contains no inspectable shared libraries' \
    'ELF gate reports empty inputs without the private input path'
reject_text tests/check-phone-elf-alignment.sh 'echo[[:space:]]+"\$program_headers"' \
    'ELF gate suppresses raw readelf diagnostics'
require_text tests/check-phone-apk-padding.py 'could not read APK input' \
    'APK padding gate suppresses private input paths'
require_text tests/check-phone-apk-padding.py 'archive[.]start_dir[[:space:]]*-[[:space:]]*previous_end' \
    'APK padding gate covers the gap before the central directory'
require_text tests/check-phone-apk-padding.py 'trailing_data_size' \
    'APK padding gate rejects bytes after the ZIP end record'
require_text tests/check-phone-apk-contents.py 'REQUIRED_CACHED_ASSETS' \
    'APK completeness gate identifies start-critical extracted bundles'
require_text tests/check-phone-apk-contents.py 'cache_content_digest' \
    'package completeness gate verifies the cache content digest'
require_text tests/check-phone-apk-contents.py 'asset paths are not sorted' \
    'package completeness gate requires deterministic cache ordering'
require_text tests/check-phone-apk-contents.py 'MAX_CACHE_MANIFEST_BYTES' \
    'package completeness gate bounds the cache manifest size'
require_text tests/check-phone-apk-contents.py 'MAX_CACHE_ASSET_COUNT' \
    'package completeness gate bounds the cached asset count'
require_text tests/check-phone-apk-contents.py 'MAX_CACHE_PATH_BYTES' \
    'package completeness gate bounds cached asset path lengths'
require_text tests/check-phone-apk-contents.py 'omits required extracted assets' \
    'APK completeness gate rejects bundles absent from the cache manifest'
require_text tests/check-phone-apk-contents.py 'scripts/[+]android_phoneInterface/defaultScripts[.]js' \
    'APK completeness gate requires the Phone default-script selector'
require_text tests/check-phone-apk-contents.py 'scripts/system/[+]android_phoneInterface/mobileActionBar[.]js' \
    'APK completeness gate requires the Phone action-bar runtime'
require_text tests/check-phone-apk-contents.py 'scripts/system/places/places[.]js' \
    'APK completeness gate requires an enabled shared tablet-app runtime'
require_text tests/phone-script-payload-test.sh 'APK/default startup script drift' \
    'Phone payload tests keep default scripts synchronized with the APK gate'
require_text tests/check-phone-apk-contents.py '"[.][.]" not in path[.]parts' \
    'APK completeness gate rejects traversing Qt extraction declarations'
require_text libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java \
    'getCanonicalFile\(\)' \
    'Android cached-asset extraction canonicalizes its destination root and files'
require_text libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java \
    'destination[.]getPath\(\)[.]startsWith\(rootPrefix\)' \
    'Android cached-asset extraction rejects destinations outside app cache'

require_text settings-phone.gradle \
    "include[[:space:]]+['\"]:phoneInterface['\"]" \
    'settings include the independent phoneInterface module'
require_text settings-phone.gradle \
    "project\(['\"]:phoneInterface['\"]\)\.projectDir[[:space:]]*=[[:space:]]*file\(['\"]apps/phoneInterface['\"]\)" \
    'phoneInterface resolves to apps/phoneInterface'
require_text settings-phone.gradle \
    "rootProject\.name[[:space:]]*=[[:space:]]*['\"]overte-phone['\"]" \
    'phone build has an independent Gradle root name'

require_text "$gradle" "namespace[[:space:]]+['\"]org\.overte\.phone['\"]" \
    'Gradle namespace is org.overte.phone'
require_text "$gradle" "applicationId[[:space:]]+['\"]org\.overte\.phone['\"]" \
    'application ID is org.overte.phone'
require_text "$gradle" 'minSdk[[:space:]]+26([^0-9]|$)' \
    'minimum Android API is 26'
require_text "$gradle" 'targetSdk[[:space:]]+36([^0-9]|$)' \
    'target Android API is 36'
require_text "$gradle" \
    "phoneTargetAbi = isPhoneEmulatorBuild \? ['\"]x86_64['\"] : ['\"]arm64-v8a['\"]" \
    'normal Phone APK remains restricted to ARM64'
require_text "$gradle" 'abiFilters[[:space:]]+phoneTargetAbi' \
    'selected Phone ABI controls APK packaging'
require_text "$gradle" "HIFI_ANDROID_APP=phoneInterface" \
    'native configure selects the phone application'
require_text "$gradle" "targets[[:space:]]+['\"]phoneInterface['\"]" \
    'Gradle builds the phone native target'
require_text "$gradle" 'ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON' \
    'native build opts into flexible Android page sizes'
require_text "$gradle" 'usePhone16kDependencies[[:space:]]*=[[:space:]]*phone16kReadySentinel\.isFile' \
    '16 KiB dependencies are enabled only by the verified sentinel'
require_text "$gradle" 'useLegacyPackaging[[:space:]]+true' \
    'Qt 5 phone builds extract JNI libraries required by android.app.load_local_libs'
reject_text "$gradle" 'useLegacyPackaging[[:space:]]+!usePhone16kDependencies' \
    'verified dependencies do not disable extraction required by the Qt 5 loader'
require_text "$gradle" 'check-phone-apk-16k\.sh' \
    '16 KiB builds enforce the final APK alignment gate'
require_text "$gradle" "MessageDigest[.]getInstance\\('SHA-256'\\)" \
    'Phone cache invalidation uses a content digest instead of mtimes'
require_text "$gradle" 'assetList[.]toSet\(\)[.]sort\(\)' \
    'Phone cache manifest ordering is deterministic'
reject_text "$gradle" 'youngestLastModified' \
    'Phone cache invalidation no longer depends on the newest source mtime'
require_text "$gradle" 'def escapeQrcXml = ' \
    'generated Phone QML resources centralize XML escaping'
require_text "$gradle" "[.]replace\\('&', '&amp;'\\)" \
    'generated Phone QML resources escape path metacharacters'
require_text "$gradle" 'escapeQrcXml\(qmlFile[.]absolutePath\)' \
    'generated Phone QML resources escape absolute source paths'
require_text tests/check-phone-apk-16k.sh 'check-phone-apk-padding\.py' \
    'final APK gate rejects excessive incremental ZIP padding'
require_text tests/check-phone-apk-16k.sh 'check-phone-apk-contents\.py' \
    'final APK gate rejects incomplete incremental package outputs'
require_text tests/check-phone-apk-16k.sh 'check-phone-apk-metadata[.]sh' \
    'final APK gate checks merged manifest metadata'
require_text tests/check-phone-apk-metadata.sh 'android[.]permission[.]VIBRATE' \
    'final APK metadata gate enforces the exact permission allowlist'
require_text tests/check-phone-apk-metadata.sh 'min_sdk.*26.*target_sdk.*36' \
    'final APK metadata gate enforces current SDK bounds'
require_text tests/check-phone-apk-metadata.sh 'PHONE_EXPECT_DEBUGGABLE' \
    'final APK metadata gate can enforce the expected build mode'
require_text tests/check-phone-apk-metadata.sh 'version_code.*2147483647' \
    'final APK metadata gate enforces Android version-code range'
require_text tests/check-phone-apk-metadata.sh 'version_name.*A-Za-z0-9._+' \
    'final APK metadata gate enforces portable version-name form'
require_text tests/check-phone-apk-metadata.sh 'metadata_error.*could not read APK' \
    'final APK metadata gate reports analyzer failures without raw tool detail'
require_text "$gradle" "environment 'PHONE_EXPECT_DEBUGGABLE'" \
    'Gradle final APK gate binds debuggable state to each variant'
require_text "$gradle" "exclude 'simplifiedUI/[*][*]'" \
    'phone packaging omits the unused desktop Simplified UI payload'
require_text "$gradle" "exclude 'developer/[*][*]'" \
    'phone packaging omits developer-only script fixtures'
require_text "$gradle" "exclude 'tutorials/[*][*]'" \
    'phone packaging omits tutorial-only script examples'
require_text "$gradle" "exclude 'communityScripts/[*][*]'" \
    'phone packaging omits the unreachable desktop community-app bundle'
reject_text "$phone_defaults" 'makeUserConnection' \
    'touchscreen phone defaults do not start the VR handshake service'
require_text "$gradle" "exclude 'system/assets/sounds/4beat_sweep[.]wav'" \
    'phone packaging omits the unreachable VR handshake sound payload'
require_text ../interface/src/Application_Graphics.cpp 'offscreenUi->setGenerateMips\(false\)' \
    'phone desktop UI disables its unused mip chain'
require_text "$gradle" "dependsOn tasks\.named\('verifyPhone16kDependencies'\)" \
    'Conan generator staging runs only after dependency verification'
require_text "$gradle" 'outputs\.upToDateWhen[[:space:]]*\{[[:space:]]*false[[:space:]]*\}' \
    '16 KiB dependency verification cannot be skipped as up-to-date'
require_text "$gradle" 'outputs\.cacheIf[[:space:]]*\{[[:space:]]*false[[:space:]]*\}' \
    '16 KiB dependency verification cannot be restored from the build cache'
if awk '
        /tasks\.register\('\''preparePhoneQtRuntime'\'',[[:space:]]*Sync\)/ { in_task = 1; next }
        in_task && /dependsOn tasks\.named\('\''verifyPhone16kDependencies'\''\)/ { found = 1; exit }
        in_task && /^}/ { exit }
        END { exit !found }
    ' "$android_root/$gradle"; then
    pass 'Qt runtime staging runs only after dependency verification'
else
    fail 'Qt runtime staging runs only after dependency verification'
fi
require_text "$gradle" 'include "libQt5PositioningQuick_\$\{qtAbiSuffix\}\.so"' \
    'phone stages the verified PositioningQuick dependency required by QtLocation'
require_text "$gradle" 'inputs\.file\(phone16kReadySentinel\)' \
    'the dependency sentinel participates in Gradle task invalidation'
require_text "$gradle" 'requirePhone16kReleaseDependencies' \
    'release packaging requires a valid 16 KiB dependency sentinel'
require_text "$gradle" "gradleProperty\('RELEASE_NUMBER'\)[.]orNull" \
    'release packaging requires an explicit bounded version name'
require_text "$gradle" 'canonicalVariantApk[[:space:]]*=[[:space:]]*output\.outputFile' \
    'the final gate checks the canonical APK output of each variant'
require_text "$gradle" "include '[*][*]/[*][.]aab'" \
    'release bundle gate resolves the canonical task-produced AAB'
require_text "$gradle" 'phonePackageContentsCheck[.]absolutePath' \
    'release bundle output runs through the package completeness gate'
require_text tests/check-phone-apk-contents.py 'base/manifest/AndroidManifest[.]xml' \
    'package completeness gate recognizes Android App Bundle layout'
reject_text "$gradle" "fileTree\(\"\$buildDir/outputs/apk/" \
    'the final gate never scans stale APKs with a wildcard'
require_text "$cmake" 'set\(TARGET_NAME[[:space:]]+phoneInterface\)' \
    'CMake declares the phone native target'
require_text "$cmake" 'add_subdirectory\("\$\{CMAKE_SOURCE_DIR\}/interface"' \
    'phone native target includes the main Interface client'
require_text "$cmake" 'src/PhoneUrlHandler\.cpp' \
    'CMake includes the runtime deep-link bridge'

require_text "$manifest" 'android\.hardware\.touchscreen' \
    'manifest requires a touchscreen'
require_text "$manifest" 'android:glEsVersion="0x00030002"' \
    'manifest declares the OpenGL ES requirement'
require_text "$manifest" 'android\.permission\.INTERNET' \
    'manifest allows network access'
require_text "$manifest" 'android\.permission\.RECORD_AUDIO' \
    'manifest declares microphone access'
require_text tests/phone-data-protection-test.py 'EXPECTED_PERMISSIONS' \
    'data protection gate enforces an exact phone permission allowlist'
require_text tests/phone-data-protection-test.py 'EXPECTED_ACTIVITIES' \
    'data protection gate enforces an exact exported-activity allowlist'
require_text tests/phone-data-protection-test.py 'provider.*receiver.*service' \
    'data protection gate rejects unexpected Android components'
require_text "$manifest" 'android:name="\.PermissionsActivity"' \
    'manifest declares the permission launcher activity'
require_text "$manifest" 'android\.intent\.action\.MAIN' \
    'manifest has a MAIN launcher action'
require_text "$manifest" 'android\.intent\.category\.LAUNCHER' \
    'manifest has a LAUNCHER category'
require_text "$manifest" 'android:scheme="overte"' \
    'manifest accepts overte deep links'
require_text "$manifest" 'android:scheme="hifi"' \
    'manifest accepts legacy hifi deep links'
require_text "$manifest" 'android:name="\.PhoneInterfaceActivity"' \
    'manifest declares the Qt client activity'
require_text "$manifest" 'android:screenOrientation="landscape"' \
    'manifest fixes the phone UI to landscape'
require_text apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java \
    'SCREEN_ORIENTATION_SENSOR_LANDSCAPE' \
    'phone establishes landscape before Qt creates its rendering surface'
require_text apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java \
    'WindowManager\.LayoutParams\.MATCH_PARENT' \
    'phone window always fills the Android activity bounds'
require_text apps/phoneInterface/src/main/java/org/qtproject/qt5/android/QtLayout.java \
    'postDelayed\(\(\) -> QtNative\.setApplicationDisplayMetrics' \
    'phone refreshes Qt fallback screen metrics after native startup'
require_text "$manifest" 'android\.app\.lib_name"[[:space:]]+android:value="phoneInterface"' \
    'Qt loads the phoneInterface native library'
reject_text "$manifest" 'openxr|pico|headtracking|vr\.headtracking' \
    'phone manifest contains no Pico/OpenXR feature requirement'

require_text "$permissions_activity" \
    'requestPermissions\(' \
    'launcher requests runtime permission'
require_text "$permissions_activity" \
    'Manifest\.permission\.RECORD_AUDIO' \
    'launcher requests RECORD_AUDIO specifically'
require_text "$permissions_activity" \
    'new Intent\(this,[[:space:]]*PhoneInterfaceActivity\.class\)' \
    'launcher transfers control to the Qt activity'
require_text "$permissions_activity" \
    'launchState[.]replacePendingUrl\(PhoneDeepLink[.]fromIntent\(intent\)\)' \
    'every new launcher intent replaces or clears the pending URL'
reject_text "$permissions_activity" \
    'applicationArguments.*pendingUrl|--url.*pendingUrl|intent\.setData\(' \
    'external deep links are never copied into Qt argv or duplicated as intent data'
require_text "$permissions_activity" \
    'putExtra\(PhoneDeepLink\.EXTRA_URL,[[:space:]]*launchState[.]pendingUrl\(\)\)' \
    'validated cold and warm deep links use the dedicated internal transport'
reject_text "$permissions_activity" \
    'getStringExtra\([^)]*args' \
    'exported launcher rejects arbitrary external native arguments'
reject_text "$permissions_activity" \
    'STATE_PERMISSION_REQUEST_PENDING|permissionRequestPending' \
    'launcher does not persist an unreliable in-flight permission-request token'
require_text "$interface_activity" \
    'extends[[:space:]]+QtActivity' \
    'phone activity hosts QtActivity'
require_text "$interface_activity" \
    'FLAG_KEEP_SCREEN_ON' \
    'phone activity keeps the display awake'
require_text "$interface_activity" \
    'System\.loadLibrary\("crypto"\)' \
    'phone activity preloads the OpenSSL crypto SONAME'
require_text "$interface_activity" \
    'System\.loadLibrary\("ssl"\)' \
    'phone activity preloads the OpenSSL TLS SONAME'
require_text "$interface_activity" \
    'PhoneDeepLink\.fromInternalExtra\(intent\)' \
    'warm internal deep links are recovered from their dedicated extra'
reject_text "$interface_activity" \
    'requestedParameters.*applicationArguments|APPLICATION_PARAMETERS[[:space:]]*=.*requestedParameters' \
    'Qt application arguments are not duplicated before QtActivityLoader processes them'
require_text "$interface_activity" \
    'nativeProcessUrl\(pendingUrl\)' \
    'warm deep links cross the Java/native bridge when Qt is ready'
require_text "$interface_activity" \
    'postDelayed\(drainPendingUrlTask,[[:space:]]*URL_RETRY_DELAY_MS\)' \
    'an early warm deep link remains pending until Qt is initialized'
require_text "$interface_activity" \
    'PhonePendingUrlPolicy[.]canAttempt\(pendingUrl,[[:space:]]*resumed\)' \
    'background deep links remain pending until the phone Activity resumes'
require_text "$pending_url_policy" \
    'pendingUrl != null && resumed' \
    'pending URL delivery requires both a destination and a resumed Activity'
require_text "$interface_activity" \
    'MAX_URL_RETRY_ATTEMPTS[[:space:]]*=[[:space:]]*300' \
    'native startup retries have a finite retry budget'
require_text "$interface_activity" \
    'catch[[:space:]]*\(UnsatisfiedLinkError' \
    'an early intent cannot crash before the Qt native library is loaded'
require_text "$deep_link_normalizer" \
    'MAX_URL_LENGTH[[:space:]]*=[[:space:]]*4096' \
    'external deep links have a bounded length'
require_text "$deep_link_normalizer" \
    'containsUnsafeCharacter\(value\)' \
    'external deep links reject raw whitespace and control characters'
require_text "$deep_link_normalizer" \
    'Character\.isWhitespace\(character\)' \
    'external deep links reject raw whitespace'
require_text "$deep_link_normalizer" \
    'Character\.isSpaceChar\(character\)' \
    'external deep links reject Unicode space characters'
reject_text "$deep_link_normalizer" \
    'toString\(\)\.trim\(' \
    'control and whitespace checks happen before any trimming'
require_text "$deep_link_normalizer" \
    'return[[:space:]]+"hifi"[[:space:]]*\+[[:space:]]*value\.substring' \
    'overte and hifi URLs share the native hifi representation'
require_text "$url_handler" \
    'JNI_FALSE' \
    'native handoff tells Java to retain URLs received before Qt initialization'
require_text "$url_handler" \
    'processURL\(url\)' \
    'native deep links use the existing URL processing path'
require_text "$url_handler" \
    'QMetaObject::invokeMethod\([[:space:]]*$' \
    'native deep links are queued through a Qt-owned receiver'

if grep -Eq -- 'extraSelectors[[:space:]]*<<[[:space:]]*"android_interface"' \
        "$repo_root/libraries/shared/src/shared/FileUtils.cpp"; then
    pass 'phone file selector falls back to the existing Android touch scripts'
else
    fail 'phone file selector falls back to the existing Android touch scripts'
fi
if grep -Eq -- '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' \
        "$repo_root/interface/src/Application_Plugins.cpp" && \
        grep -Eq -- 'setPreferredDisplayPlugins\(\{[[:space:]]*DESKTOP_DISPLAY_PLUGIN_NAME[[:space:]]*\}\)' \
        "$repo_root/interface/src/Application_Plugins.cpp"; then
    pass 'phone startup selects the 2D desktop display without a chooser'
else
    fail 'phone startup selects the 2D desktop display without a chooser'
fi
if grep -Eq -- '_window->showFullScreen\(\)' \
        "$repo_root/interface/src/Application_Setup.cpp"; then
    pass 'phone Qt window claims the Android fullscreen bounds immediately'
else
    fail 'phone Qt window claims the Android fullscreen bounds immediately'
fi
if awk '
        /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ { phone_guard = NR }
        /ResourceCache::setRequestLimit\(MAX_CONCURRENT_RESOURCE_DOWNLOADS\)/ && phone_guard { phone_default = NR }
        /if \(parser\.isSet\("concurrent-downloads"\)\)/ &&
                phone_guard < phone_default && phone_default < NR { found = 1; exit }
        END { exit !found }
    ' "$repo_root/interface/src/Application_Setup.cpp"; then
    pass 'phone resource downloads default to two while the CLI remains the later override'
else
    fail 'phone resource downloads default to two while the CLI remains the later override'
fi
require_text '../interface/src/Application.cpp' \
    'PHONE_DEFAULT_VIEWPORT_RESOLUTION_SCALE[[:space:]]*\{[[:space:]]*0\.65f[[:space:]]*\}' \
    'phone profile defaults to the measured 0.65 viewport scale after the performance preset'
require_text '../interface/src/Application.cpp' \
    'setViewportResolutionScale\(phoneViewportResolutionScale\)' \
    'phone profile applies the bounded viewport-scale selection'
require_text '../interface/src/Application.cpp' \
    'setCustomRefreshRate\(RefreshRateManager::RefreshRateRegime::FOCUS_ACTIVE,[[:space:]]*PHONE_TARGET_FPS\)' \
    'phone profile configures a real active 30 FPS refresh target'
require_text '../interface/src/Application_Plugins.cpp' \
    'refreshRateManager\.updateRefreshRateController\(\)' \
    'phone frame target is applied after the display present operator is installed'
require_text '../interface/src/Application.cpp' \
    'mirrorConfig->setProperty\("enabled",[[:space:]]*false\)' \
    'phone MVP profile disables every configured mirror view'
require_text '../interface/src/Application.cpp' \
    'setProceduralMaterialsEnabled\(false\)' \
    'phone MVP profile keeps procedural materials disabled'
require_text '../interface/src/Application.cpp' \
    'phoneBoolOverride\("debug\.overte\.phone_haze",[[:space:]]*false\)' \
    'phone MVP profile keeps haze off unless a bounded A/B test enables it'
require_text '../interface/src/Application.cpp' \
    'phoneBoolOverride\("debug\.overte\.phone_local_lights",[[:space:]]*false\)' \
    'phone MVP profile keeps local lights off unless a bounded A/B test enables them'
if awk '
        /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ { phone_guard = NR }
        /qWarning\(\) << "Avatar bookmarks JSON could not be loaded"/ { phone_log = NR }
        /#else/ && phone_log && !desktop_branch { desktop_branch = NR }
        /OffscreenUi::asyncWarning\("Avatar Bookmarks Error"/ { desktop_dialog = NR }
        END {
            exit !(phone_guard && phone_guard < phone_log &&
                   phone_log < desktop_branch && desktop_branch < desktop_dialog)
        }
    ' "$repo_root/interface/src/Application.cpp"; then
    pass 'phone startup reports bookmark parse failure without logging its details or opening a desktop dialog'
else
    fail 'phone startup reports bookmark parse failure without logging its details or opening a desktop dialog'
fi
reject_text '../interface/src/Application.cpp' \
    'qWarning\(\).*bookmarksError' \
    'phone Android logs cannot include raw avatar bookmark parser details'
require_text "$phone_defaults" 'touchscreenvirtualpad\.js' \
    'phone defaults load the touchscreen virtual pad'
require_text "$phone_defaults" 'mobileActionBar\.js' \
    'phone defaults load the native-QML mobile action bar'
require_file '../scripts/system/+android_phoneInterface/mobileActionBar.js'
require_text "$phone_defaults" 'Script\.require\("/~/system/\+android_interface/androidControls\.js"\)' \
    'phone defaults load entity touch controls exactly once'
reject_text "$phone_defaults" '/modes\.js|clickWeb\.js' \
    'phone defaults avoid legacy modes and unsafe direct web opening'
reject_text "$manifest" \
    'Qt5QuickParticles' 'phone manifest does not preload an unstaged particles library'
reject_text 'apps/phoneInterface/src/main/res/values/qt_dependencies.xml' \
    'Qt5QuickParticles' 'phone Qt dependencies omit unused QuickParticles'
reject_text "$phone_defaults" '\+android_interface/actionbar\.js|openAndroidActivity' \
    'phone defaults avoid the unavailable legacy Home activity'
if grep -Eq -- 'DialogsManager\.showAddressBar\(\)' \
        "$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js" && \
        grep -Eq -- 'text:[[:space:]]*"TABLET"' \
        "$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js" && \
        grep -Eq -- 'text:[[:space:]]*"VIEW"' \
        "$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js" && \
        grep -Eq -- 'DialogsManager\.showLoginDialog\(\)' \
        "$repo_root/interface/resources/qml/hifi/tablet/TabletHome.qml"; then
    pass 'phone action bar exposes address, tablet, and view controls while Tablet Home exposes login'
else
    fail 'phone navigation surfaces expose address, tablet, view, and login controls'
fi

require_text build-phone.sh \
    ':phoneInterface:assembleDebug' \
    'wrapper builds the phone debug variant'
require_text build-phone.sh \
    'phoneInterface-debug\.apk' \
    'wrapper installs the documented APK path'
require_text build-phone.sh 'select_phone_serial' \
    'wrapper explicitly selects a non-VR phone before installation'
require_text build-phone.sh '\[SETUP\].*16 KiB dependencies are not prepared' \
    'doctor distinguishes toolchain readiness from dependency readiness'
require_text build-phone.sh 'verify-phone-16k-dependencies[.]sh' \
    'doctor verifies dependency contents before reporting readiness'
require_text build-phone.sh '\[STALE\].*contents do not match the marker' \
    'doctor rejects a stale Phone dependency marker'
require_text build-phone.sh 'ready_marker.*>/dev/null 2>&1' \
    'doctor reduces detailed dependency verifier paths to an aggregate status'
require_text build-phone.sh 'phone-device-lock[.]sh.*run' \
    'wrapper serializes phone installation with the shared device lock'
require_text build-phone.sh 'PHONE_ALLOW_LEGACY_4K_DEPS' \
    'legacy 4 KiB dependency use requires an explicit override'
require_text build-phone.sh 'phone-prebuilt-16k-deps[.]sh.*download' \
    'download setup restores the Phone-specific 16 KiB delta'
require_text phone-prebuilt-16k-deps.sh 'sha256sum --check' \
    'Phone prebuilt restore verifies its versioned checksum'
require_text phone-prebuilt-16k-deps.sh '--build=never' \
    'Phone prebuilt restore cannot silently rebuild missing packages'
require_text phone-prebuilt-16k-deps.sh 'finalize-phone-16k-deps[.]sh' \
    'Phone prebuilt restore republishes readiness only through the full verifier'
require_text phone-prebuilt-16k-deps.sh 'cache save.*--no-source' \
    'Phone prebuilt export excludes dependency sources'
require_text apps/phoneInterface/build.gradle \
    "System\.getenv\('PHONE_ALLOW_LEGACY_4K_DEPS'\) == '1'" \
    'Gradle phone builds fail closed without a verified sentinel'
require_file finalize-phone-16k-deps.sh
require_file phone-build-resource-guard.sh
require_file tests/phone-build-resource-guard-test.sh
require_text phone-device-lock.sh 'git-common-dir' \
    'phone device lock is shared across Git worktrees'
require_text phone-device-lock.sh 'DEVICE_LOCK_HELD_VARIABLE="PHONE_DEVICE_LOCK_HELD"' \
    'phone device lock configures its protected-operation marker'
require_text device-lock-core.sh 'export "\$DEVICE_LOCK_HELD_VARIABLE=1"' \
    'shared device lock core marks protected child operations'
require_text tests/phone-device-test.sh 'phone-device-lock[.]sh.*run' \
    'device smoke test automatically acquires the shared phone lock'
require_text tests/phone-device-test.sh 'ro[.]kernel[.]qemu' \
    'device smoke rejects emulator targets'
require_text tests/phone-device-test.sh 'ro[.]product[.]cpu[.]abilist' \
    'device smoke requires the APK-supported ARM64 ABI'
require_text tests/phone-device-test.sh 'android[.]hardware[.]touchscreen' \
    'device smoke requires a touchscreen target'
require_text tests/phone-device-test.sh '10#\$sdk >= 26' \
    'device smoke enforces the APK minimum Android API'
require_text tests/phone-device-test.sh '10#\$gles >= 196610' \
    'device smoke enforces the manifest OpenGL ES 3.2 requirement'
require_text tests/phone-device-test.sh 'sha256sum -- "\$APK"' \
    'device smoke test identifies the exact installed APK by content'
require_text tests/phone-device-test.sh 'APK was not found' \
    'device smoke suppresses missing APK input paths'
require_text tests/phone-device-test.sh 'could not read APK for SHA-256' \
    'device smoke suppresses local APK hashing errors'
require_text tests/phone-device-test.sh 'could not resolve device-test report directory' \
    'device smoke suppresses invalid report paths'
require_text tests/phone-device-test.sh 'manifest application-id "\$APK"' \
    'device smoke reads the local APK application ID before installation'
require_text tests/phone-device-test.sh 'APK_APPLICATION_ID.*== "\$PACKAGE"' \
    'device smoke permits only the dedicated Phone package'
require_text tests/phone-device-test.sh 'manifest min-sdk "\$APK"' \
    'device smoke reads the local APK minimum SDK before installation'
require_text tests/phone-device-test.sh 'APK_MIN_SDK.*== 26.*APK_TARGET_SDK.*== 36' \
    'device smoke requires the current Phone APK SDK contract'
require_text tests/phone-device-test.sh 'manifest permissions "\$APK"' \
    'device smoke reads permissions from the final APK before installation'
require_text tests/phone-device-test.sh 'APK_PERMISSIONS.*== "\$EXPECTED_APK_PERMISSIONS"' \
    'device smoke rejects APK permission drift'
require_text tests/phone-device-test.sh 'manifest debuggable "\$APK"' \
    'device smoke reads and validates the APK debuggable state'
require_text tests/phone-device-test.sh 'PHONE_EXPECT_DEBUGGABLE' \
    'device smoke can fail closed on debug versus release artifact mismatch'
require_text tests/phone-device-test.sh 'check-phone-apk-16k[.]sh' \
    'device smoke runs the complete Phone package gate before installation'
require_text tests/phone-device-test.sh 'PHONE_APK_PREFLIGHT' \
    'device smoke package gate is replaceable only for controlled host testing'
require_text tests/phone-device-test.sh 'PHONE_ALLOW_TEST_OVERRIDES.*!= 1' \
    'device smoke requires explicit authorization for a nonstandard package gate'
require_text tests/phone-device-test.sh 'nonstandard APK preflight requires explicit host-test override' \
    'device smoke fails clearly when a package-gate override is unguarded'
require_text tests/phone-device-test.sh 'Do not query a connected device until every host-only artifact contract' \
    'device smoke completes local APK validation before selecting a device'
require_text tests/phone-device-test.sh 'PHONE_APK_ANALYZER' \
    'device smoke supports a controlled apkanalyzer path for host testing'
require_text tests/phone-device-test.sh 'apk_sha256=%s' \
    'device smoke summary records APK provenance without a local path'
require_text tests/phone-device-test.sh 'install -r -g "\$APK"' \
    'device smoke automatically grants runtime permissions without human input'
require_text tests/phone-device-test.sh '"\$ADB" -s "\$SERIAL" "\$@" 2>/dev/null' \
    'device smoke suppresses ADB transport details that can contain identifiers'
require_text tests/phone-device-test.sh 'require_adb "APK installation"' \
    'device smoke replaces raw install errors with a generic failure'
require_text tests/phone-device-test.sh 'require_adb\(\)' \
    'device smoke labels every required mutating ADB phase'
require_text tests/phone-device-test.sh 'require_adb "launcher start"' \
    'device smoke reports Activity launch failure without raw ADB output'
require_text tests/phone-device-test.sh 'runtime_permissions_auto_granted=1' \
    'device smoke summary records its permission precondition'
require_text tests/phone-device-test.sh 'test_status=%s' \
    'device smoke summary records one explicit final result'
require_text tests/phone-device-test.sh 'trap write_final_status EXIT' \
    'device smoke records failure even on late checked exits'
require_text tests/phone-device-test.sh 'require_adb "final app cleanup".*force-stop' \
    'successful device smoke must force-stop the tested app before passing'
require_text tests/phone-device-test.sh 'PACKAGE_INSTALLED == 1.*PACKAGE_CLEANED == 0' \
    'failed device smoke performs best-effort app cleanup after installation'
require_text tests/phone-device-test.sh 'cleanup_force_stopped=1' \
    'device summary records cleanup only after its required command succeeds'
require_text tests/phone-device-test.sh 'shell pm path "\$PACKAGE"' \
    'device smoke resolves the installed base APK after installation'
require_text tests/phone-device-test.sh 'installed_apk_sha256.*== "\$APK_SHA256"' \
    'device smoke verifies installed bytes against the requested APK digest'
require_text tests/phone-device-test.sh 'could not read the installed APK for provenance verification' \
    'device smoke reports installed-package read failure without raw ADB detail'
require_text tests/phone-device-test.sh 'installed_apk_verified=1' \
    'device smoke records successful installed-package provenance verification'
reject_text tests/phone-device-test.sh 'installed_base_apk.*tee|installed_base_apk.*SUMMARY' \
    'device smoke never persists the private installed APK path'
require_text tests/phone-device-test.sh '! -e "\$SUMMARY".*! -L "\$SUMMARY"' \
    'device smoke refuses existing files and symlinks at its summary target'
require_text tests/phone-device-test.sh 'umask 077.*>"\$SUMMARY"' \
    'device smoke creates its report summary with private permissions'
require_text tests/phone-device-test.sh 'set -o noclobber' \
    'device smoke creates its summary atomically without following a raced target'
require_text tests/phone-device-test.sh 'could not update device-test summary' \
    'device smoke reports summary write failures without private paths'
require_text tests/phone-device-test.sh 'chmod 600 "\$SUMMARY"' \
    'device smoke enforces a private report summary mode'
require_text tests/phone-graphics-benchmark.sh 'phone-device-lock[.]sh.*run' \
    'graphics benchmark automatically acquires the shared phone lock'
require_text tests/phone-graphics-benchmark.sh 'adb_for shell am force-stop "\$PACKAGE"' \
    'graphics benchmark force-stops the app during exit cleanup'
require_text tests/phone-graphics-benchmark.sh 'require_adb "final Phone cleanup" shell am force-stop' \
    'successful graphics benchmark requires final app cleanup'
require_text tests/phone-graphics-benchmark.sh "printf 'cleanup_force_stopped=1" \
    'graphics benchmark records required final cleanup'
require_text tests/phone-graphics-benchmark.sh "trap 'exit 130' INT" \
    'graphics benchmark converts interruption into a terminating exit'
require_text tests/phone-graphics-benchmark.sh "trap 'exit 143' TERM" \
    'graphics benchmark converts termination into a terminating exit'
require_text tests/phone-graphics-benchmark.sh 'ro[.]kernel[.]qemu' \
    'graphics benchmark rejects emulator targets'
require_text tests/phone-graphics-benchmark.sh 'arm64-v8a' \
    'graphics benchmark requires the Phone ARM64 ABI'
require_text tests/phone-graphics-benchmark.sh 'android[.]hardware[.]touchscreen' \
    'graphics benchmark requires a touchscreen target'
require_text tests/phone-graphics-benchmark.sh '10#\$sdk >= 26' \
    'graphics benchmark enforces the Phone minimum Android API'
require_text tests/phone-graphics-benchmark.sh '10#\$gles >= 196610' \
    'graphics benchmark enforces the Phone OpenGL ES contract'
require_text tests/phone-graphics-benchmark.sh '10#\$duration <= 3600' \
    'graphics benchmark bounds unattended runtime to one hour'
require_text tests/phone-graphics-benchmark.sh '10#\$interval <= 300' \
    'graphics benchmark bounds the thermal sampling interval'
require_text phone-build-resource-guard.sh 'OVERTE_PHONE_MIN_SWAP_BYTES=32000000000' \
    'dependency builds require at least 32 GB decimal swap'
require_text phone-build-resource-guard.sh "OVERTE_PHONE_MEMORY_MAX_PROPERTY='16000000000'" \
    'dependency builds request an exact 16 GB decimal systemd memory ceiling'
require_text phone-build-resource-guard.sh 'systemd-run --user --collect --wait --pipe' \
    'dependency resource limit uses a waited systemd user service'
reject_text phone-build-resource-guard.sh 'ulimit' \
    'dependency resource guard has no unenforceable ulimit fallback'
require_text finalize-phone-16k-deps.sh '--write-sentinel' \
    'completed dependency outputs can be finalized without rebuilding'
require_text tests/phone-device-test.sh 'logcat -d -T "\$logcat_start_epoch" -v threadtime --pid=' \
    'device reports restrict logcat to the test window and phone app process'
require_text tests/phone-device-test.sh 'date [+]%s[.]%3N' \
    'device smoke obtains a precise on-device logcat cursor before launch'
require_text tests/phone-device-test.sh 'log_marker_counts="\$\(' \
    'device smoke propagates process-log query failures from command substitution'
reject_text tests/phone-device-test.sh 'exit-info "\$PACKAGE" \|\| true' \
    'device smoke never masks unavailable package exit diagnostics'
require_text tests/phone-device-test.sh 'require_stable_pid "launch" "\$pid" 30' \
    'device test requires one stable process for thirty seconds after launch'
require_text tests/phone-device-test.sh '\(mResumedActivity\|topResumedActivity\).*PhoneInterfaceActivity' \
    'device test requires the Qt phone activity to be visibly resumed'
require_text tests/phone-device-test.sh 'for lifecycle_cycle in 1 2 3' \
    'device test repeats the unattended background and foreground lifecycle'
require_text tests/phone-device-test.sh 'KEYCODE_BACK' \
    'device test exercises the phone Back-to-background lifecycle'
require_text tests/phone-device-test.sh 'phone_activity_is_backgrounded' \
    'device test verifies that Home and Back actually leave the activity backgrounded'
require_text tests/phone-device-test.sh 'back_recovery_survived=1' \
    'device test records successful process-preserving Back recovery'
require_text tests/phone-device-test.sh 'reason=\[\[:space:\]\]\*\(4\|5\)' \
    'device test recognizes Android numeric Java and native crash exit reasons'
require_text tests/phone-device-test.sh 'process exit info.*valid = 1' \
    'device test validates the dumpsys exit-info response structure'
require_text tests/phone-device-test.sh 'exit_crash_count >= 0' \
    'device test rejects exit-info counters that move backwards'
require_text tests/phone-device-test.sh 'could not read baseline package exit diagnostics' \
    'device smoke labels unavailable pre-launch exit diagnostics'
require_text tests/phone-device-test.sh 'could not read final package exit diagnostics' \
    'device smoke labels unavailable post-lifecycle exit diagnostics'
reject_text tests/phone-device-test.sh \
    'serial=%s|model=%s|dumpsys window|SurfaceFlinger' \
    'device reports omit serial, model, and global display diagnostics'
reject_text tests/phone-device-test.sh \
    'reports: \$REPORT_DIR|Device diagnostics complete: %s' \
    'device process output omits absolute private report paths'
require_text tests/phone-device-test.sh 'readonly TEST_DEEP_LINK="overte://localhost"' \
    'device test uses a fixed neutral local deep link'
reject_text tests/phone-device-test.sh \
    'PHONE_DEEP_LINK|launch\.txt|deep-link\.txt|foreground\.txt|logcat\.txt|exit-info\.txt|app-log\.txt|crashes\.txt|page-size-mismatch\.txt' \
    'device reports never persist caller URIs or raw Android diagnostics'
require_text tests/phone-device-test.sh 'crash_log_matches=%s\\nexit_crash_matches=%s\\npage_size_mismatch_matches=%s' \
    'device reports retain only aggregate crash and page-size counters'
require_text tests/phone-device-test.sh 'has_16k_size.*has_failure_context' \
    'device smoke requires error context before treating generic 16 KiB text as failure'
for command_name in doctor deps prepare build install all deploy setup; do
    require_text build-phone.sh \
        "(^|[[:space:]])${command_name}\)" \
        "wrapper exposes the ${command_name} command"
done
reject_text build-phone.sh \
    'curl|wget|git[[:space:]]+(clone|fetch|pull)' \
    'normal phone wrapper contains no implicit network or Git command'
require_text build-phone.sh \
    'is_android_arm64_draco_package' \
    'phone preparation validates the staged Draco target architecture'
require_text build-phone.sh \
    'os=Android' \
    'phone preparation rejects host Draco packages before staging'
require_text prepare-phone-16k-conan-deps.sh \
    'rm -f -- "\$ready_sentinel"' \
    'dependency rebuild invalidates any stale ready sentinel first'
require_text prepare-phone-16k-conan-deps.sh \
    'finalize-phone-16k-deps\.sh' \
    'dependency rebuild verifies the complete package set'
require_text prepare-phone-16k-conan-deps.sh \
    "--build='~qt/\\*'" \
    'non-Qt dependency rebuild explicitly excludes Qt source builds'
require_text conan/conanfile-pico.py \
    'from conan\.tools\.cmake import CMakeDeps' \
    'Phone Conan graph uses the supported CMakeDeps generator API'
require_text conan/conanfile-pico.py \
    'release_deps\.configuration = "RelWithDebInfo"' \
    'Phone Conan graph emits native release configuration metadata'
require_text conan/conanfile-pico.py \
    'super\(\)\.generate\(\)' \
    'Phone Conan graph retains the original Debug generator metadata'
require_text conan/conanfile-pico.py \
    'release_deps\.generate\(\)' \
    'Phone Conan graph publishes the additional RelWithDebInfo metadata'
require_text docs/ANDROID_PHONE_RELEASE_OPERATIONS.md \
    'require glibc 2\.38 or newer' \
    'release runner documents the cached Qt host-tool ABI floor'
require_text docs/ANDROID_PHONE_RELEASE_OPERATIONS.md \
    'digest-pinned Ubuntu' \
    'release runner requires a pinned compatible runtime image'
require_text docs/ANDROID_PHONE_RELEASE_OPERATIONS.md \
    'container-engine socket nor host' \
    'release runner container excludes control sockets and devices'
require_text conan/profiles/phone-nonqt-arm64-16k \
    '^tools\.build:jobs=4$' \
    'non-Qt dependency rebuild uses four parallel build jobs'
require_text tests/verify-phone-16k-dependencies.sh \
    'mv -f -- "\$sentinel_tmp" "\$sentinel"' \
    'dependency ready sentinel is published atomically'
require_text tests/verify-phone-16k-dependencies.sh \
    "'OpenSSL\*'.*'module-OpenSSL\*'.*'FindOpenSSL\.cmake'" \
    'sentinel covers the exact non-Qt generator overlay'
require_text tests/verify-phone-16k-dependencies.sh \
    'readlink -- "\$entry"' \
    'sentinel digest includes shared-library symlink metadata'
require_text tests/verify-phone-16k-dependencies.sh \
    "'libcrypto\.so\.1\.1'" \
    'sentinel covers the staged OpenSSL crypto library consumed by Gradle'
require_text tests/verify-phone-16k-dependencies.sh \
    "'libssl\.so\.1\.1'" \
    'sentinel covers the staged OpenSSL TLS library consumed by Gradle'
require_text tests/verify-phone-16k-dependencies.sh \
    'append_manifest_entry staged-library nonqt' \
    'staged OpenSSL contents participate in the sentinel digest'
require_text tests/verify-phone-16k-dependencies.sh \
    '"\$alignment_check" "\$staged_alignment_dir"' \
    'staged OpenSSL libraries pass the 16 KiB ELF gate'
require_text tests/verify-phone-16k-dependencies.sh \
    'contains a symlink outside its package' \
    'dependency verification rejects every package symlink that escapes its package'
require_text tests/check-phone-elf-alignment.sh \
    "-name '\*\.so\.\*'" \
    'ELF gate includes versioned shared libraries'
require_text tests/check-phone-elf-alignment.sh \
    'shared-library symlink escapes the package directory' \
    'ELF gate rejects package symlinks that escape their package'

printf 'Checks: %s total, %s failed\n' "$checks" "$failures"
(( failures == 0 ))
