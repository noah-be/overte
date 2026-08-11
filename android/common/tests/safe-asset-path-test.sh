#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly output="$(mktemp -d "${TMPDIR:-/tmp}/overte-safe-assets.XXXXXXXX")"
trap 'rm -rf -- "$output"' EXIT
readonly hifi_utils="$android_root/common/libraries/qt/src/main/java/io/highfidelity/utils/HifiUtils.java"
readonly java_tmp="$output/java-tmp"
mkdir -p -- "$java_tmp"

grep -q 'AssetCacheExtractor.unpack(assetManager::open, destDir)' "$hifi_utils"
grep -q 'throw new RuntimeException(e)' "$hifi_utils"

javac -d "$output" \
    "$android_root/common/libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java" \
    "$android_root/common/libraries/qt/src/main/java/io/highfidelity/utils/AssetCacheExtractor.java" \
    "$android_root/common/tests/java/io/highfidelity/utils/AssetCacheExtractorStandaloneTest.java" \
    "$android_root/common/tests/java/io/highfidelity/utils/SafeAssetPathStandaloneTest.java"
java -Djava.io.tmpdir="$java_tmp" -cp "$output" io.highfidelity.utils.SafeAssetPathStandaloneTest
java -Djava.io.tmpdir="$java_tmp" -cp "$output" io.highfidelity.utils.AssetCacheExtractorStandaloneTest
