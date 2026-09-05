#!/bin/sh
set -eu

usage() { echo "usage: $0 --prepare|--preflight|--build" >&2; exit 2; }
[ "$#" -eq 1 ] || usage
mode=$1
case "$mode" in --prepare|--preflight|--build) ;; *) usage ;; esac

: "${OVERTE_ATTEMPT_ROOT:?OVERTE_ATTEMPT_ROOT must be an explicit absolute path}"
: "${OVERTE_SOURCE_CLOSURE_STORE:?OVERTE_SOURCE_CLOSURE_STORE must be an explicit absolute path}"
: "${ANDROID_SDK_ROOT:?ANDROID_SDK_ROOT must be set}"
: "${ANDROID_NDK_HOME:?ANDROID_NDK_HOME must be set}"
: "${JAVA_HOME:?JAVA_HOME must be set}"
: "${OVERTE_SOURCE_COMMIT:?OVERTE_SOURCE_COMMIT must identify the archived source}"
resume=${OVERTE_RESUME:-0}
case "$resume" in 0|1) ;; *) echo "OVERTE_RESUME must be 0 or 1" >&2; exit 2 ;; esac
case "$OVERTE_ATTEMPT_ROOT:$OVERTE_SOURCE_CLOSURE_STORE:$ANDROID_SDK_ROOT:$ANDROID_NDK_HOME:$JAVA_HOME" in
  /*:/*:/*:/*:/*) ;; *) echo "all build roots must be absolute paths" >&2; exit 2 ;; esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../../../.." && pwd)
manifest="$repo_root/android/phone/fdroid/manifests/source-closure.lock.json"
index="$repo_root/android/phone/fdroid/manifests/recipe-exports/index.json"
jobs=$(nproc)
conan_home="$OVERTE_ATTEMPT_ROOT/conan"
export CONAN_HOME="$conan_home"
export OVERTE_QT_COMPOSED_SOURCE="$OVERTE_ATTEMPT_ROOT/qt-composed"
export CMAKE_BUILD_PARALLEL_LEVEL="$jobs"
export CMAKE_GENERATOR=Ninja
export MAKEFLAGS="-j$jobs"

closure() {
  python3 "$repo_root/android/phone/fdroid/conan/source_closure_store.py" "$@" \
    --manifest "$manifest" --repo-root "$repo_root" \
    --store "$OVERTE_SOURCE_CLOSURE_STORE"
}

checkpoint() {
  name=$1; result=$2
  checkpoint_dir="$OVERTE_ATTEMPT_ROOT/checkpoints"
  mkdir -p "$checkpoint_dir"
  digest=$(sha256sum "$result" | awk '{print $1}')
  temporary="$checkpoint_dir/.$name.new"
  manifest_digest=$(sha256sum "$manifest" | awk '{print $1}')
  index_digest=$(sha256sum "$index" | awk '{print $1}')
  printf '%s\n' "attempt_root=$OVERTE_ATTEMPT_ROOT" "name=$name" \
    "source_commit=$OVERTE_SOURCE_COMMIT" "manifest_sha256=$manifest_digest" \
    "recipe_index_sha256=$index_digest" "result_sha256=$digest" \
    "jobs=$jobs" > "$temporary"
  mv "$temporary" "$checkpoint_dir/$name.COMPLETE"
}

valid_checkpoint() {
  name=$1; result=$2
  record="$OVERTE_ATTEMPT_ROOT/checkpoints/$name.COMPLETE"
  [ -f "$record" ] && [ -f "$result" ] || return 1
  digest=$(sha256sum "$result" | awk '{print $1}')
  manifest_digest=$(sha256sum "$manifest" | awk '{print $1}')
  index_digest=$(sha256sum "$index" | awk '{print $1}')
  grep -Fqx "attempt_root=$OVERTE_ATTEMPT_ROOT" "$record" &&
    grep -Fqx "name=$name" "$record" &&
    grep -Fqx "source_commit=$OVERTE_SOURCE_COMMIT" "$record" &&
    grep -Fqx "manifest_sha256=$manifest_digest" "$record" &&
    grep -Fqx "recipe_index_sha256=$index_digest" "$record" &&
    grep -Fqx "result_sha256=$digest" "$record" &&
    grep -Fqx "jobs=$jobs" "$record"
}

reset_incomplete_stage() {
  stage=$1; result=$2
  case "$stage" in
    "$OVERTE_ATTEMPT_ROOT/bootstrap"|"$OVERTE_ATTEMPT_ROOT/host-tools"|"$OVERTE_ATTEMPT_ROOT/target") ;;
    *) echo "refusing unsafe stage reset" >&2; exit 1 ;;
  esac
  rm -rf -- "$stage"
  rm -f -- "$result"
}

preflight() {
  closure verify >/dev/null
  [ -f "$OVERTE_ATTEMPT_ROOT/qt-composed/COMPOSITION.json" ] || { echo "preflight: composed Qt source is absent" >&2; exit 1; }
  [ -d "$OVERTE_ATTEMPT_ROOT/conan-source-cache/s" ] || { echo "preflight: Conan source cache is absent" >&2; exit 1; }
  [ -d "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin" ] || { echo "preflight: exact NDK is absent" >&2; exit 1; }
  [ -d "$ANDROID_SDK_ROOT/platforms/android-36" ] || { echo "preflight: SDK platform 36 is absent" >&2; exit 1; }
  [ -d "$ANDROID_SDK_ROOT/build-tools/36.0.0" ] || { echo "preflight: build-tools 36.0.0 are absent" >&2; exit 1; }
  gcc --version | head -1 | grep -Eq ' 15[.]3[.]0$'
  g++ --version | head -1 | grep -Eq ' 15[.]3[.]0$'
  "$JAVA_HOME/bin/java" -version 2>&1 | head -1 | grep -Eq 'version "17[.]'
  # Conan initializes CONAN_HOME even for a version query.  Keep that probe in
  # the container tmpfs so the qualified attempt cache remains truly empty.
  CONAN_HOME=/tmp/sh001-conan-version-probe conan --version | grep -Fx 'Conan version 2.25.2'
  cmake --version | head -1 | grep -Fx 'cmake version 3.31.6'
  ninja --version | grep -Fx '1.13.2'
  if [ "$resume" -eq 0 ]; then
    [ "$(find "$OVERTE_ATTEMPT_ROOT" -maxdepth 1 -type d \( -name bootstrap -o -name host-tools -o -name target \) | wc -l)" -eq 0 ] || { echo "preflight: stale binary output exists" >&2; exit 1; }
    [ ! -e "$conan_home" ] || [ -z "$(find "$conan_home" -mindepth 1 -print -quit)" ] || { echo "preflight: Conan cache is not empty" >&2; exit 1; }
  else
    [ -f "$OVERTE_ATTEMPT_ROOT/ACTIVE_BUILD_PROTECTED" ] || { echo "preflight: resume marker is absent" >&2; exit 1; }
  fi
  route_lines=$(wc -l < /proc/net/route)
  [ "$route_lines" -le 1 ] || { echo "preflight: network route is available" >&2; exit 1; }
  available=$(df -B1 --output=avail "$OVERTE_ATTEMPT_ROOT" | awk 'NR==2 {print $1}')
  [ "$available" -ge 85899345920 ] || { echo "preflight: less than 80 GiB free" >&2; exit 1; }
  echo "cold-build preflight: PASS (jobs=$jobs available_bytes=$available)"
}

if [ "$mode" = --prepare ]; then
  if valid_checkpoint sources "$OVERTE_ATTEMPT_ROOT/qt-composed/COMPOSITION.json"; then
    echo "source preparation checkpoint: PASS"
    exit 0
  fi
  mkdir -p "$OVERTE_ATTEMPT_ROOT"
  [ ! -e "$OVERTE_ATTEMPT_ROOT/conan-source-cache" ] || { echo "prepare: stale Conan source cache exists" >&2; exit 1; }
  closure stage-conan-cache --destination "$OVERTE_ATTEMPT_ROOT/conan-source-cache"
  closure stage-qt-store --destination "$OVERTE_ATTEMPT_ROOT/qt-source-archives"
  python3 "$repo_root/android/phone/fdroid/conan/qt_source_store.py" \
    --manifest "$repo_root/android/phone/fdroid/manifests/qt-source.lock.json" \
    --source-store "$OVERTE_ATTEMPT_ROOT/qt-source-archives" \
    --output "$OVERTE_ATTEMPT_ROOT/qt-composed"
  checkpoint sources "$OVERTE_ATTEMPT_ROOT/qt-composed/COMPOSITION.json"
  exit 0
fi

preflight
[ "$mode" = --build ] || exit 0
if [ "$resume" -eq 0 ]; then
  mkdir "$conan_home"
  conan remote remove conancenter >/dev/null
  python3 "$repo_root/android/phone/fdroid/conan/recipe_export_store.py" restore \
    --index "$index" --scanned-root "$repo_root" \
    --output "$OVERTE_ATTEMPT_ROOT/recipe-transport.tgz" --conan-home "$conan_home"
  printf '%s\n' "core.sources:download_cache=$OVERTE_ATTEMPT_ROOT/conan-source-cache" > "$conan_home/global.conf"
else
  [ -d "$conan_home" ] || { echo "build: resume cache is absent" >&2; exit 1; }
fi
[ "$(conan remote list --format=json)" = '[]' ] || { echo "build: a Conan remote is configured" >&2; exit 1; }
if [ "$resume" -eq 0 ]; then
  [ -z "$(find "$conan_home/p" -mindepth 2 -maxdepth 2 -type d -name p -print -quit 2>/dev/null)" ] || { echo "build: foreign binary package present before compilation" >&2; exit 1; }
fi

cd "$repo_root"
if ! valid_checkpoint bootstrap "$OVERTE_ATTEMPT_ROOT/bootstrap-result.json"; then
  reset_incomplete_stage "$OVERTE_ATTEMPT_ROOT/bootstrap" "$OVERTE_ATTEMPT_ROOT/bootstrap-result.json"
  conan install android/phone/fdroid/conan/bootstrap.conanfile.py -of "$OVERTE_ATTEMPT_ROOT/bootstrap" \
    -pr:h android/phone/fdroid/conan/profiles/linux-x86_64-bootstrap -pr:b android/phone/fdroid/conan/profiles/linux-x86_64-bootstrap \
    --lockfile=android/phone/fdroid/locks/bootstrap-linux-x86_64.lock --no-remote --build='*' \
    -c "tools.build:jobs=$jobs" --format=json > "$OVERTE_ATTEMPT_ROOT/bootstrap-result.json"
  checkpoint bootstrap "$OVERTE_ATTEMPT_ROOT/bootstrap-result.json"
fi

if ! valid_checkpoint host-tools "$OVERTE_ATTEMPT_ROOT/host-tools-result.json"; then
  reset_incomplete_stage "$OVERTE_ATTEMPT_ROOT/host-tools" "$OVERTE_ATTEMPT_ROOT/host-tools-result.json"
  conan install android/phone/fdroid/conan/host-tools.conanfile.py -of "$OVERTE_ATTEMPT_ROOT/host-tools" \
    -pr:h android/phone/fdroid/conan/profiles/linux-x86_64-hosttools -pr:b android/phone/fdroid/conan/profiles/linux-x86_64-bootstrap \
    --lockfile=android/phone/fdroid/locks/host-tools-linux-x86_64.lock --no-remote --build='*' \
    -c "tools.build:jobs=$jobs" --format=json > "$OVERTE_ATTEMPT_ROOT/host-tools-result.json"
  checkpoint host-tools "$OVERTE_ATTEMPT_ROOT/host-tools-result.json"
fi

if ! valid_checkpoint target "$OVERTE_ATTEMPT_ROOT/target-result.json"; then
  reset_incomplete_stage "$OVERTE_ATTEMPT_ROOT/target" "$OVERTE_ATTEMPT_ROOT/target-result.json"
  conan install android/phone/fdroid/conan/target.conanfile.py -of "$OVERTE_ATTEMPT_ROOT/target" \
    -pr:h android/phone/fdroid/conan/profiles/android-arm64-v8a-api26-16k -pr:b android/phone/fdroid/conan/profiles/linux-x86_64-hosttools \
    --lockfile=android/phone/fdroid/locks/android-arm64-v8a-api26-16k.lock --no-remote --build='*' \
    -c "tools.build:jobs=$jobs" --format=json > "$OVERTE_ATTEMPT_ROOT/target-result.json"
  checkpoint target "$OVERTE_ATTEMPT_ROOT/target-result.json"
fi

"$repo_root/android/phone/tests/verify-phone-16k-dependencies.sh" --write-sentinel \
  "$OVERTE_ATTEMPT_ROOT/target" "$OVERTE_ATTEMPT_ROOT/target" "$OVERTE_ATTEMPT_ROOT/target/.phone-16k-dependencies.ready"
echo "source-only dependency build: PASS"
