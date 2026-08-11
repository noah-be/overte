#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_dir="$(cd -- "$script_dir/../.." && pwd)"
module_gradle="$android_dir/phone/apps/phoneInterface/build.gradle"
root_gradle="$android_dir/phone/build.gradle"
manifest="$android_dir/phone/apps/phoneInterface/src/main/AndroidManifest.xml"
gitignore="$android_dir/../.gitignore"

require_text() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
}

require_absent() {
    local file="$1" pattern="$2" description="$3"
    if grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
}

require_text "$module_gradle" 'compileSdk 36' 'phone compileSdk must remain API 36'
compile_sdk_line="$(grep -n -m1 'compileSdk 36' "$module_gradle" | cut -d: -f1)"
dependency_gate_line="$(grep -n -m1 'if (!usePhone16kDependencies' "$module_gradle" | cut -d: -f1)"
if (( compile_sdk_line >= dependency_gate_line )); then
    echo 'FAIL: compileSdk must be declared before dependency preflight errors' >&2
    exit 1
fi
require_text "$module_gradle" 'targetSdk 36' 'phone targetSdk must remain API 36'
require_text "$module_gradle" "gradleProperty\('VERSION_CODE'\)" \
    'release configuration must require an explicit versionCode'
require_text "$root_gradle" 'new BigInteger\(versionCodeProperty\)' \
    'versionCode parsing must avoid unchecked integer conversion'
require_text "$root_gradle" 'BigInteger\.valueOf\(Integer\.MAX_VALUE\)' \
    'versionCode must fit the Android signed 32-bit field'
require_text "$root_gradle" 'versionCodeProperty != null' \
    'versionCode defaults only when the property is absent'
require_absent "$root_gradle" 'VERSION_CODE.*toInteger\(|getOrElse\(.1.\)\.toInteger' \
    'versionCode parsing must not throw an unhelpful NumberFormatException'
require_text "$module_gradle" "tasks\.register\('requirePhoneReleaseVersionCode'\)" \
    'release versionCode validation must be represented by a task-graph gate'
require_text "$module_gradle" "gradleProperty\('RELEASE_NUMBER'\)" \
    'release configuration must require an explicit version name'
require_text "$module_gradle" 'portable version-name characters' \
    'release version names must use a portable character set'
require_text "$module_gradle" '\{0,99\}' \
    'release version names must be bounded to 100 characters'
require_text "$module_gradle" 'packageTask\.configure' \
    'release APK packaging must depend on the versionCode gate'
require_text "$module_gradle" 'tasks\.matching.*bundleTaskName.*configureEach' \
    'release bundle packaging must depend on the versionCode gate'
require_text "$module_gradle" 'dependsOn requirePhoneReleaseVersionCode' \
    'release artifact tasks must run versionCode validation transitively'
require_absent "$module_gradle" 'gradle\.startParameter\.taskNames' \
    'release validation must not depend on explicitly requested task names'
require_text "$module_gradle" "releaseCredential\('OVERTE_ANDROID_KEYSTORE'\)" \
    'release signing must support an externally provided keystore path'
require_text "$module_gradle" 'providers\.environmentVariable\(name\)' \
    'release credentials must support masked CI environment variables'
require_text "$module_gradle" 'if \(hasReleaseSigning\)' \
    'release signing must remain conditional'
require_absent "$module_gradle" '(storePassword|keyPassword)[[:space:]]+['\"'][^$]' \
    'release signing must not contain a literal password'
require_text "$root_gradle" "com.android.application.*8\.13\.2" \
    'phone build must keep the API 36-capable Android Gradle plugin'
require_text "$manifest" 'android:allowBackup="false"' \
    'release package must not enable Android backup'
require_text "$gitignore" '^\*\.jks$' 'Java keystores must be ignored'
require_text "$gitignore" '^\*\.keystore$' 'Android keystores must be ignored'

printf 'Phone release configuration checks passed.\n'
