#!/usr/bin/env bash
set -euo pipefail
phone_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
android_api="${PHONE_ANDROID_API_JAR:-${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/home/user/Android/Sdk}}/platforms/android-26/android.jar}"
[[ -f "$android_api" ]] || { echo 'Android API 26 jar is required for focused compilation' >&2; exit 2; }
scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$scratch/classes" "$scratch/data"
javac -proc:none -cp "$android_api" -d "$scratch/classes" \
    "$phone_root/apps/phoneInterface/src/main/java/org/overte/phone/SecureAccountStore.java" \
    "$phone_root/apps/phoneInterface/src/main/java/org/overte/phone/RedactingDiagnostics.java" \
    "$phone_root/../../security/redaction/java/org/overte/security/SafeDiagnostics.java" \
    "$phone_root/tests/security/SecureAccountStoreHostTest.java"
java -cp "$scratch/classes:$android_api" \
    org.overte.phone.SecureAccountStoreHostTest "$scratch/data"
