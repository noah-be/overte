#!/bin/sh
set -eu

[ "$#" -eq 1 ] || { echo "usage: $0 ABSOLUTE_EMPTY_GRADLE_STORE" >&2; exit 2; }
store=$1
case "$store" in /*) ;; *) echo "Gradle store must be absolute" >&2; exit 2 ;; esac
[ ! -e "$store" ] || { echo "Gradle store already exists" >&2; exit 1; }
mkdir -p "$store"

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../../../.." && pwd)
project="$repo_root/android/phone/fdroid/gradle-acquisition"
wrapper="$repo_root/android/common/gradlew"

OVERTE_GRADLE_ACQUISITION_BUILD_DIR="$store/project-build" \
  GRADLE_USER_HOME="$store" "$wrapper" --no-daemon --stacktrace \
  --project-cache-dir "$store/project-cache" \
  -p "$project" resolveFdroidAcquisition
(cd "$store" && find caches/modules-2/files-2.1 wrapper/dists \
  -type f ! -name '*.lck' ! -name '*.ok' -print0 | sort -z | xargs -0 sha256sum \
  > ARTIFACT_SHA256SUMS)
(cd "$store" && sha256sum ARTIFACT_SHA256SUMS > COMPLETE)
echo "Gradle acquisition store: PASS"
