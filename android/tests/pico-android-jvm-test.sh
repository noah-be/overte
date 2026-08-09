#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JDK="${PICO_JAVA_HOME:-}"
if [[ -z "$JDK" ]]; then
    JDK_JAVA="$(find "${XDG_DATA_HOME:-$HOME/.local/share}/jdks" -maxdepth 3 -type f \
        -path '*/bin/java' -print 2>/dev/null | sort | grep -m1 '/jdk-17' || true)"
    [[ -z "$JDK_JAVA" ]] || JDK="$(cd -- "$(dirname -- "$JDK_JAVA")/.." && pwd)"
fi
[[ -x "$JDK/bin/java" ]] || {
    echo "error: JDK 17 not found; set PICO_JAVA_HOME" >&2
    exit 2
}
[[ -d "$SDK/platforms/android-36" ]] || {
    echo "error: Android SDK platform 36 not found below $SDK" >&2
    exit 2
}

cd -- "$ROOT/android"
JAVA_HOME="$JDK" PATH="$JDK/bin:$PATH" ANDROID_HOME="$SDK" ANDROID_SDK_ROOT="$SDK" \
    ./gradlew --no-daemon --console=plain \
    --settings-file settings-pico.gradle :picoInterface:testDebugUnitTest
