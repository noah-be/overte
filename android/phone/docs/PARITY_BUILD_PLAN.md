# Exact-source Phone parity build

This plan builds the complete ARM64 debug application from the reviewed Phone
feature commit, without publishing, tagging, installing or starting a device.
The coordinator schedules the build and freezes the clean source worktree until
it finishes. A successful Java or desktop Qt compilation is not an APK result.

## Verified inputs, 2026-10-13

The local Phone doctor passes with no warnings using JDK 21.0.12.1, Android SDK
36, Build-Tools 36.0.0, NDK 27.3.13750724 and SDK CMake 3.31.6. Conan 2.25.2 and
Ninja 1.13.2 are present. The worktree does not yet have a verified Phone 16 KiB
generator/sentinel graph; it must be restored before application compilation.

The fork's existing `android-phone-16k-deps-v3` release exposes
`android-phone-16k-conan.tgz` (1,476,694,358 bytes). Its release digest matches the
repository dependency policy:

```text
092fde910f2dcc3eb0c2d6cff819f2e6264de4e176750ed1f7625a9a21e926be
```

The three existing `pico4-deps-v1` shared host/runtime archives also match the
policy's release digests. Existing helpers restore these separately from the
Phone target graph; shared 4 KiB libraries must never shadow the Phone packages.
The repository's content-bound sentinel and ELF gate remain mandatory.

The pinned AndroidX WebKit 1.12.1 runtime, transitive locks and matching source
archives have been acquired and resolved offline in the isolated Gradle store
`/tmp/overte-phone-web-gradle-store`. Its 724 immutable artifact files are bound
by `ARTIFACT_SHA256SUMS` and `COMPLETE`. Verify both before copying to a private
build cache. The Android Qt/JNI jar used for isolated API testing came from an
older Pico handoff; the actual application must consume the Qt jar and runtime
restored with the verified Phone dependency graph.

## Build runner and sequence

Use the local Linux host with a coordinator-assigned build resource slot and
the existing Phone worktree. The trusted Actions workflow currently accepts
only `android-phone` and approved release tags, so it cannot test this unpublished
feature commit as-is. Do not weaken that ref boundary or invent a release tag.
The existing local entry point builds the exact source directly.

From the repository root, set `PARITY_SOURCE_REVISION` to the reviewed full
Phone commit and `PARITY_BUILD_ROOT` to a new absolute directory on the large
local filesystem. Then execute these stages separately, preserving logs:

```bash
test "$(git rev-parse HEAD)" = "$PARITY_SOURCE_REVISION"
test -z "$(git status --porcelain)"
export JAVA_HOME=/usr/lib/jvm/java-21-temurin-jdk
export ANDROID_SDK_ROOT=/home/user/Android/Sdk
export PATH="$ANDROID_SDK_ROOT/cmake/3.31.6/bin:$PATH"
export CONAN_HOME="$PARITY_BUILD_ROOT/phone-conan2"
export PHONE_SHARED_CONAN_HOME="$PARITY_BUILD_ROOT/shared-conan2"
export GRADLE_USER_HOME="$PARITY_BUILD_ROOT/gradle-home"
export PHONE_PREBUILT_TMPDIR="$PARITY_BUILD_ROOT/download-tmp"
export PHONE_VERIFY_TMPDIR="$PARITY_BUILD_ROOT/verification-tmp"
export PHONE_BUILD_TMPDIR="$PARITY_BUILD_ROOT/package-tmp"
export PHONE_BUILD_JOBS=4

CONAN_HOME="$PHONE_SHARED_CONAN_HOME" conan profile detect
conan profile detect
android/phone/build.sh doctor
android/phone/build.sh deps --download
android/phone/build.sh prepare
android/common/tests/run-tests.sh host --report-dir "$PARITY_BUILD_ROOT/host-tests"
android/phone/build.sh build --stacktrace
```

Before dependency restore, the coordinator may seed the new Gradle cache from
the verified acquisition store. Keep both Conan caches private and distinct.
The two initial detections create each fresh cache's default host profile for
the doctor; dependency restoration still uses the reviewed explicit profiles.
Restore uses checksum verification and `--build=never`; missing dependencies,
stale sentinels or alignment failures stop the build. Do not enable the legacy
4 KiB override. If the pinned archive cannot satisfy the graph, report the
exact failure before scheduling the separate, bounded dependency producer.

The application build invokes `:phoneInterface:assembleDebug`, including CMake,
the common WebView adapter, Phone native Host and actual Qt Android packaging.
Monitor one active build through its supported wait or at ten-minute intervals;
do not restart it while it is running. Record the source revision, tool versions,
dependency policy digest and complete build log. Recheck the source revision and
clean state after completion.

## Artifact gate and remaining acceptance

The resulting APK is
`android/phone/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk`.
Run the repository's complete APK verifier against that exact file:

```bash
android/phone/ci/verify-phone-apk.py \
  android/phone/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk \
  --apkanalyzer "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/apkanalyzer" \
  --apksigner "$ANDROID_SDK_ROOT/build-tools/36.0.0/apksigner" \
  --expect-debuggable 1 --source-revision "$PARITY_SOURCE_REVISION" \
  --output "$PARITY_BUILD_ROOT/apk-manifest.json"
```

Retain the APK digest and verifier receipt with the source revision. This proves
complete compilation and packaging, not provider/device behavior. A later,
separately coordinated device run must qualify origin/frame/epoch bridge fences,
same- and cross-origin DOM input and IME composition, overlay clipping/insets,
chooser Activity return, provider failure recovery and user-driven embedded
video/audio. World bitmap capture does not establish hardware video support.
The independent F-Droid source-only cold build remains a separate qualification.
