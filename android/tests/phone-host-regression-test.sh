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
deep_link='apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLink.java'
deep_link_normalizer='apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java'
url_handler='apps/phoneInterface/src/PhoneUrlHandler.cpp'
phone_defaults='../scripts/+android_phoneInterface/defaultScripts.js'

for source_file in \
        build-phone.sh \
        build-phone.gradle \
        settings-phone.gradle \
        tests/check-phone-elf-alignment.sh \
        tests/check-phone-apk-16k.sh \
        tests/verify-phone-16k-dependencies.sh \
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
require_text "$gradle" "abiFilters[[:space:]]+['\"]arm64-v8a['\"]" \
    'APK is restricted to ARM64'
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
    ' "$gradle"; then
    pass 'Qt runtime staging runs only after dependency verification'
else
    fail 'Qt runtime staging runs only after dependency verification'
fi
require_text "$gradle" "include 'libQt5PositioningQuick_arm64-v8a\.so'" \
    'phone stages the verified PositioningQuick dependency required by QtLocation'
require_text "$gradle" 'inputs\.file\(phone16kReadySentinel\)' \
    'the dependency sentinel participates in Gradle task invalidation'
require_text "$gradle" 'requirePhone16kReleaseDependencies' \
    'release packaging requires a valid 16 KiB dependency sentinel'
require_text "$gradle" 'canonicalVariantApk[[:space:]]*=[[:space:]]*output\.outputFile' \
    'the final gate checks the canonical APK output of each variant'
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
    'pendingUrl[[:space:]]*=[[:space:]]*PhoneDeepLink\.fromIntent\(intent\)' \
    'every new launcher intent replaces or clears the pending URL'
reject_text "$permissions_activity" \
    'applicationArguments.*pendingUrl|--url.*pendingUrl|intent\.setData\(' \
    'external deep links are never copied into Qt argv or duplicated as intent data'
require_text "$permissions_activity" \
    'putExtra\(PhoneDeepLink\.EXTRA_URL,[[:space:]]*pendingUrl\)' \
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
    'PHONE_VIEWPORT_RESOLUTION_SCALE[[:space:]]*\{[[:space:]]*0\.5f[[:space:]]*\}' \
    'phone profile deterministically applies a 0.5 viewport scale after the performance preset'
require_text '../interface/src/Application.cpp' \
    'setCustomRefreshRate\(RefreshRateManager::RefreshRateRegime::FOCUS_ACTIVE,[[:space:]]*PHONE_TARGET_FPS\)' \
    'phone profile configures a real active 30 FPS refresh target'
require_text '../interface/src/Application_Plugins.cpp' \
    'refreshRateManager\.updateRefreshRateController\(\)' \
    'phone frame target is applied after the display present operator is installed'
for disabled_phone_feature in \
        'setHazeEnabled\(false\)' \
        'setLocalLightingEnabled\(false\)' \
        'setProceduralMaterialsEnabled\(false\)' \
        'mirrorConfig->setProperty\("enabled",[[:space:]]*false\)'; do
    require_text '../interface/src/Application.cpp' "$disabled_phone_feature" \
        "phone MVP profile disables ${disabled_phone_feature}"
done
if awk '
        /#if defined\(ANDROID_APP_PHONE_INTERFACE\)/ { phone_guard = NR }
        /qWarning\(\) << "Avatar bookmarks JSON parse error:"/ { phone_log = NR }
        /#else/ && phone_log && !desktop_branch { desktop_branch = NR }
        /OffscreenUi::asyncWarning\("Avatar Bookmarks Error"/ { desktop_dialog = NR }
        END {
            exit !(phone_guard && phone_guard < phone_log &&
                   phone_log < desktop_branch && desktop_branch < desktop_dialog)
        }
    ' "$repo_root/interface/src/Application.cpp"; then
    pass 'phone startup logs avatar bookmark parse errors without opening the desktop warning dialog'
else
    fail 'phone startup logs avatar bookmark parse errors without opening the desktop warning dialog'
fi
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
        grep -Eq -- 'DialogsManager\.showLoginDialog\(\)' \
        "$repo_root/scripts/system/+android_phoneInterface/mobileActionBar.js"; then
    pass 'phone action bar exposes address and login dialogs'
else
    fail 'phone action bar exposes address and login dialogs'
fi

require_text build-phone.sh \
    ':phoneInterface:assembleDebug' \
    'wrapper builds the phone debug variant'
require_text build-phone.sh \
    'phoneInterface-debug\.apk' \
    'wrapper installs the documented APK path'
require_text build-phone.sh 'select_phone_serial' \
    'wrapper explicitly selects a non-VR phone before installation'
require_text build-phone.sh 'PHONE_ALLOW_LEGACY_4K_DEPS' \
    'legacy 4 KiB dependency use requires an explicit override'
require_text apps/phoneInterface/build.gradle \
    "System\.getenv\('PHONE_ALLOW_LEGACY_4K_DEPS'\) == '1'" \
    'Gradle phone builds fail closed without a verified sentinel'
require_file finalize-phone-16k-deps.sh
require_file phone-build-resource-guard.sh
require_file tests/phone-build-resource-guard-test.sh
require_text phone-build-resource-guard.sh 'OVERTE_PHONE_MIN_SWAP_BYTES=32000000000' \
    'dependency builds require at least 32 GB decimal swap'
require_text phone-build-resource-guard.sh "OVERTE_PHONE_MEMORY_MAX_PROPERTY='20000000000'" \
    'dependency builds request an exact 20 GB decimal systemd memory ceiling'
require_text phone-build-resource-guard.sh 'systemd-run --user --scope' \
    'dependency resource limit uses a systemd user scope'
reject_text phone-build-resource-guard.sh 'ulimit' \
    'dependency resource guard has no unenforceable ulimit fallback'
require_text finalize-phone-16k-deps.sh '--write-sentinel' \
    'completed dependency outputs can be finalized without rebuilding'
require_text tests/phone-device-test.sh 'logcat -d -v threadtime --pid=' \
    'device reports restrict logcat to the phone app process'
require_text tests/phone-device-test.sh 'require_stable_pid "launch" "\$pid" 30' \
    'device test requires one stable process for thirty seconds after launch'
require_text tests/phone-device-test.sh 'mResumedActivity.*PhoneInterfaceActivity' \
    'device test requires the Qt phone activity to be visibly resumed'
require_text tests/phone-device-test.sh 'reason=\[\[:space:\]\]\*\(4\|5\)' \
    'device test recognizes Android numeric Java and native crash exit reasons'
reject_text tests/phone-device-test.sh \
    'serial=%s|model=%s|dumpsys window|SurfaceFlinger' \
    'device reports omit serial, model, and global display diagnostics'
require_text tests/phone-device-test.sh 'readonly TEST_DEEP_LINK="overte://localhost"' \
    'device test uses a fixed neutral local deep link'
reject_text tests/phone-device-test.sh \
    'PHONE_DEEP_LINK|launch\.txt|deep-link\.txt|foreground\.txt|logcat\.txt|exit-info\.txt|app-log\.txt|crashes\.txt|page-size-mismatch\.txt' \
    'device reports never persist caller URIs or raw Android diagnostics'
require_text tests/phone-device-test.sh 'crash_log_matches=%s\\nexit_crash_matches=%s\\npage_size_mismatch_matches=%s' \
    'device reports retain only aggregate crash and page-size counters'
for command_name in doctor prepare build install all deploy setup; do
    require_text build-phone.sh \
        "(^|[[:space:]])${command_name}\)" \
        "wrapper exposes the ${command_name} command"
done
reject_text build-phone.sh \
    'curl|wget|git[[:space:]]+(clone|fetch|pull)' \
    'normal phone wrapper contains no implicit network or Git command'
require_text prepare-phone-16k-conan-deps.sh \
    'rm -f -- "\$ready_sentinel"' \
    'dependency rebuild invalidates any stale ready sentinel first'
require_text prepare-phone-16k-conan-deps.sh \
    'finalize-phone-16k-deps\.sh' \
    'dependency rebuild verifies the complete package set'
require_text prepare-phone-16k-conan-deps.sh \
    "--build='~qt/\\*'" \
    'non-Qt dependency rebuild explicitly excludes Qt source builds'
require_text conan/profiles/phone-nonqt-arm64-16k \
    '^tools\.build:jobs=16$' \
    'non-Qt dependency rebuild uses 16 parallel build jobs'
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
