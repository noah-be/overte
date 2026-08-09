#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly scratch="$(mktemp -d "${TMPDIR:-/tmp}/overte-mutation.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT

killed=0
survived=0

run_deep_link_mutant() {
    local name="$1"
    local expression="$2"
    local replacement="$3"
    local mutant_dir="$scratch/$name"
    mkdir -p "$mutant_dir/classes"
    sed "s@$expression@$replacement@" \
        "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java" \
        > "$mutant_dir/PhoneDeepLinkNormalizer.java"
    if cmp -s "$mutant_dir/PhoneDeepLinkNormalizer.java" \
            "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java"; then
        echo "Mutation pattern did not match: $name" >&2
        return 2
    fi
    javac -d "$mutant_dir/classes" "$mutant_dir/PhoneDeepLinkNormalizer.java" \
        "$android_root/tests/java/org/overte/phone/PhoneDeepLinkNormalizerTest.java"
    local output="$mutant_dir/test-output.txt"
    if java -cp "$mutant_dir/classes" org.overte.phone.PhoneDeepLinkNormalizerTest >"$output" 2>&1; then
        echo "SURVIVED: $name" >&2
        survived=$((survived + 1))
    elif grep -q 'AssertionError' "$output"; then
        echo "KILLED: $name"
        killed=$((killed + 1))
    else
        echo "Mutation harness failed unexpectedly: $name" >&2
        sed -n '1,20p' "$output" >&2
        return 2
    fi
}

run_asset_mutant() {
    local name="$1"
    local expression="$2"
    local replacement="$3"
    local mutant_dir="$scratch/$name"
    mkdir -p "$mutant_dir/classes"
    sed "s@$expression@$replacement@" \
        "$android_root/libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java" \
        > "$mutant_dir/SafeAssetPath.java"
    if cmp -s "$mutant_dir/SafeAssetPath.java" \
            "$android_root/libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java"; then
        echo "Mutation pattern did not match: $name" >&2
        return 2
    fi
    javac -d "$mutant_dir/classes" "$mutant_dir/SafeAssetPath.java" \
        "$android_root/tests/java/io/highfidelity/utils/SafeAssetPathStandaloneTest.java"
    local output="$mutant_dir/test-output.txt"
    if java -cp "$mutant_dir/classes" io.highfidelity.utils.SafeAssetPathStandaloneTest >"$output" 2>&1; then
        echo "SURVIVED: $name" >&2
        survived=$((survived + 1))
    elif grep -q 'AssertionError' "$output"; then
        echo "KILLED: $name"
        killed=$((killed + 1))
    else
        echo "Mutation harness failed unexpectedly: $name" >&2
        sed -n '1,20p' "$output" >&2
        return 2
    fi
}

run_deep_link_mutant "deep-link-length-boundary" \
    'value.length() > MAX_URL_LENGTH' 'value.length() < MAX_URL_LENGTH'
run_deep_link_mutant "deep-link-disable-unsafe-character-check" \
    '|| containsUnsafeCharacter(value)' '|| false'
run_deep_link_mutant "deep-link-disable-hifi-scheme" \
    '!"hifi".equalsIgnoreCase(scheme)' 'true'
run_asset_mutant "asset-disable-containment" \
    '!destination.getPath().startsWith(rootPrefix)' 'false'
run_asset_mutant "asset-allow-root-destination" \
    'destination.equals(canonicalRoot)' 'false'

echo "Critical policy mutation score: $killed/5 killed"
if (( survived != 0 )); then
    echo "$survived critical mutation(s) survived" >&2
    exit 1
fi
