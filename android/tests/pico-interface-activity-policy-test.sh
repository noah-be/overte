#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/pico-activity-policy.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

javac -d "$build_dir" \
    "$repo_root/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivityPolicy.java" \
    "$repo_root/apps/picoInterface/src/main/java/org/overte/pico/PicoActivityInstancePolicy.java" \
    "$repo_root/tests/java/org/overte/pico/PicoInterfaceActivityPolicyStandaloneTest.java"
java -cp "$build_dir" org.overte.pico.PicoInterfaceActivityPolicyStandaloneTest

activity="$repo_root/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivity.java"
grep -Fq 'PicoInterfaceActivityPolicy.applicationParameters(' "$activity"
grep -Fq 'PicoInterfaceActivityPolicy.canUseExactRestart(' "$activity"
grep -Fq 'INSTANCE.register(this)' "$activity"
grep -Fq 'INSTANCE.clear(this)' "$activity"
if grep -Eq 'Log\..*applicationArguments' "$activity"; then
    echo "PicoInterfaceActivity must not log restart arguments" >&2
    exit 1
fi
