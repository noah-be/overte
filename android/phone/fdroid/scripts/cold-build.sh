#!/usr/bin/env bash
set -euo pipefail

usage() { echo "usage: $0 --preflight|--run|--resume" >&2; exit 2; }
[[ $# == 1 ]] || usage
mode=$1
[[ $mode == --preflight || $mode == --run || $mode == --resume ]] || usage
: "${OVERTE_SOURCE_CLOSURE_STORE:?set OVERTE_SOURCE_CLOSURE_STORE}"
: "${OVERTE_ATTEMPT_ROOT:?set OVERTE_ATTEMPT_ROOT}"
: "${ANDROID_SDK_ROOT:?set ANDROID_SDK_ROOT}"
case "$OVERTE_SOURCE_CLOSURE_STORE:$OVERTE_ATTEMPT_ROOT:$ANDROID_SDK_ROOT" in
  /*:/*:/*) ;; *) echo "all roots must be absolute" >&2; exit 2 ;; esac

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/../../../.." && pwd)
image=localhost/overte-sh001-fdroid-toolchain:three-gates
ndk="$ANDROID_SDK_ROOT/ndk/27.3.13750724"

python3 "$repo_root/android/phone/fdroid/conan/toolchain_probe.py" \
  --repo-root "$repo_root" --sdk-root "$ANDROID_SDK_ROOT" \
  --lock "$repo_root/android/phone/fdroid/manifests/toolchain-provisioning.lock.json"
python3 "$repo_root/android/phone/fdroid/conan/source_closure_store.py" verify \
  --manifest "$repo_root/android/phone/fdroid/manifests/source-closure.lock.json" \
  --repo-root "$repo_root" --store "$OVERTE_SOURCE_CLOSURE_STORE"
[[ -z $(git -C "$repo_root" status --porcelain) ]] || {
  echo "cold build requires a clean committed source tree" >&2; exit 1;
}
[[ $(git -C "$repo_root" rev-parse HEAD) == "$(git -C "$repo_root" rev-parse HEAD^{commit})" ]]
available=$(df -B1 --output=avail "$(dirname -- "$OVERTE_ATTEMPT_ROOT")" | awk 'NR==2 {print $1}')
(( available >= 85899345920 )) || { echo "less than 80 GiB free" >&2; exit 1; }
source_commit=$(git -C "$repo_root" rev-parse HEAD)
if [[ $mode == --resume ]]; then
  [[ -f $OVERTE_ATTEMPT_ROOT/ACTIVE_BUILD_PROTECTED && ! -e $OVERTE_ATTEMPT_ROOT/COMPLETE ]] || {
    echo "resume requires one protected incomplete attempt" >&2; exit 1;
  }
  grep -Fqx "source_commit=$source_commit" "$OVERTE_ATTEMPT_ROOT/ACTIVE_BUILD_PROTECTED" || {
    echo "resume source lineage mismatch" >&2; exit 1;
  }
else
  [[ ! -e $OVERTE_ATTEMPT_ROOT ]] || { echo "attempt root already exists" >&2; exit 1; }
fi
echo "cold-build host preflight: PASS"
[[ $mode == --run || $mode == --resume ]] || exit 0
: "${OVERTE_GRADLE_STORE:?set OVERTE_GRADLE_STORE for build execution}"
[[ -f $OVERTE_GRADLE_STORE/COMPLETE ]] || { echo "Gradle acquisition store is incomplete" >&2; exit 1; }
(cd "$OVERTE_GRADLE_STORE" && sha256sum -c COMPLETE && sha256sum -c ARTIFACT_SHA256SUMS) >/dev/null

if [[ $mode == --run ]]; then
  mkdir -p "$OVERTE_ATTEMPT_ROOT/source" "$OVERTE_ATTEMPT_ROOT/logs"
  printf '%s\n' "source_commit=$source_commit" \
    "source_closure_sha256=$(sha256sum "$repo_root/android/phone/fdroid/manifests/source-closure.lock.json" | awk '{print $1}')" \
    "recipe_index_sha256=$(sha256sum "$repo_root/android/phone/fdroid/manifests/recipe-exports/index.json" | awk '{print $1}')" \
    "toolchain_image_id=1b2da099cf7c03f6ea4b751cf8f148784f12db71fdaabb2b6330d60ba1572dda" \
    "gradle_complete_sha256=$(sha256sum "$OVERTE_GRADLE_STORE/COMPLETE" | awk '{print $1}')" \
    > "$OVERTE_ATTEMPT_ROOT/ACTIVE_BUILD_PROTECTED.new"
  mv "$OVERTE_ATTEMPT_ROOT/ACTIVE_BUILD_PROTECTED.new" "$OVERTE_ATTEMPT_ROOT/ACTIVE_BUILD_PROTECTED"
  git -C "$repo_root" archive --format=tar HEAD | tar -xf - -C "$OVERTE_ATTEMPT_ROOT/source"
  cp -a "$OVERTE_GRADLE_STORE" "$OVERTE_ATTEMPT_ROOT/gradle-home"
  printf '%s\n' 'GPU_BUILD_ACCELERATION=NOT_APPLICABLE' > "$OVERTE_ATTEMPT_ROOT/GPU_BUILD_ACCELERATION"
fi
(cd "$OVERTE_ATTEMPT_ROOT/gradle-home" && sha256sum -c COMPLETE && sha256sum -c ARTIFACT_SHA256SUMS) >/dev/null

container_args=(
  --rm --network=none --read-only --security-opt label=disable
  --tmpfs /tmp:rw,size=4g --tmpfs /root:rw,size=128m
  --volume "$OVERTE_ATTEMPT_ROOT:/attempt:rw"
  --volume "$OVERTE_SOURCE_CLOSURE_STORE:/source-store:ro"
  --volume "$ANDROID_SDK_ROOT:/opt/android-sdk:ro"
  --env OVERTE_ATTEMPT_ROOT=/attempt
  --env OVERTE_SOURCE_CLOSURE_STORE=/source-store
  --env ANDROID_SDK_ROOT=/opt/android-sdk
  --env ANDROID_NDK_HOME=/opt/android-sdk/ndk/27.3.13750724
  --env JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
  --env "OVERTE_SOURCE_COMMIT=$source_commit"
)
[[ $mode == --resume ]] && container_args+=(--env OVERTE_RESUME=1)
inner_path='/opt/sh001/conan/bin:/usr/lib/jvm/java-17-openjdk-amd64/bin:/opt/android-sdk/build-tools/36.0.0:/opt/android-sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

monitor_pid() {
  local monitored_pid=$1
  while kill -0 "$monitored_pid" 2>/dev/null; do
    local timestamp free load mem
    timestamp=$(date --iso-8601=seconds)
    free=$(df -B1 --output=avail "$OVERTE_ATTEMPT_ROOT" | awk 'NR==2 {print $1}')
    read -r load _ < /proc/loadavg
    mem=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    printf '%s\t%s\t%s\t%s\n' "$timestamp" "$free" "$mem" "$load" >> "$OVERTE_ATTEMPT_ROOT/logs/resources.tsv"
    if (( free < 12884901888 )); then
      kill -TERM "$monitored_pid" 2>/dev/null || true
      wait "$monitored_pid" || true
      printf '%s\n' 'RESOURCE_ABORT: free space crossed 12 GiB floor' > "$OVERTE_ATTEMPT_ROOT/RESOURCE_ABORT"
      return 75
    fi
    sleep 20
  done
  wait "$monitored_pid"
}

podman run "${container_args[@]}" "$image" /bin/sh -c \
  "export PATH='$inner_path'; /attempt/source/android/phone/fdroid/scripts/build-dependencies.sh --prepare; /attempt/source/android/phone/fdroid/scripts/build-dependencies.sh --build" \
  > "$OVERTE_ATTEMPT_ROOT/logs/dependencies.log" 2>&1 &
build_pid=$!
monitor_pid "$build_pid"

podman run "${container_args[@]}" --env OVERTE_FDROID_CONAN_DIR=/attempt/target \
  --env GRADLE_USER_HOME=/attempt/gradle-home "$image" /bin/sh -c \
  "export PATH='$inner_path'; cd /attempt/source/android/common; ./gradlew --offline --no-daemon --stacktrace --settings-file /attempt/source/android/phone/settings.gradle -p /attempt/source/android/phone -PVERSION_CODE=1 -PRELEASE_NUMBER=0.1.0-fdroidproof :phoneInterface:assembleRelease --max-workers=\$(nproc)" \
  > "$OVERTE_ATTEMPT_ROOT/logs/gradle.log" 2>&1 &
gradle_pid=$!
monitor_pid "$gradle_pid"
apk="$OVERTE_ATTEMPT_ROOT/source/android/phone/apps/phoneInterface/build/outputs/apk/release/phoneInterface-release-unsigned.apk"
[[ -f $apk ]] || { echo "unsigned release APK is absent" >&2; exit 1; }
sha256sum "$apk" > "$OVERTE_ATTEMPT_ROOT/APK_SHA256"
printf '%s\n' "apk=$apk" "sha256=$(sha256sum "$apk" | awk '{print $1}')" > "$OVERTE_ATTEMPT_ROOT/COMPLETE.new"
mv "$OVERTE_ATTEMPT_ROOT/COMPLETE.new" "$OVERTE_ATTEMPT_ROOT/COMPLETE"
echo "SH-001 cold build: PASS"
