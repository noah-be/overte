# Exact-source Phone parity build

This plan describes the complete ARM64 application build from the reviewed
Phone feature commit, without publishing, tagging, installing or starting a device.
The coordinator schedules the build and freezes the clean source worktree until
it finishes. A successful Java or desktop Qt compilation is not an APK result.

## Verified inputs, 2026-10-13

The local Phone doctor passes with no warnings using JDK 21.0.12.1, Android SDK
36, Build-Tools 36.0.0, NDK 27.3.13750724 and SDK CMake 3.31.6. Conan 2.25.2 and
Ninja 1.13.2 are present. The worktree does not yet have a verified Phone 16 KiB
generator/sentinel graph satisfying its current dependency recipe.

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

The three relevant Qt recipe identities are distinct. The approved Phone
prebuilt graph uses `4fc772a2dbcd84731eb6ff9904e6e358`; the Android/Pico
source-only producer uses `d75aeab99c3d3426df7ec9b39bc73aa8`; this Phone
branch's updated source-only producer uses `4fd1f62ee1914f2f3ec4fe298a07c283`
and OpenEXR 3.2.12. A successful prebuilt restore is not qualification of either
source-only producer. Do not replace one pin with another to satisfy a check.

The coordinator completed the original Phone archive download, SHA256 check
and actual Conan restore. The subsequent offline graph fails: the archived
Node 22 recipe revision `261cd4344c058c7f08a0fb892519880a` requires OpenSSL
1.1.1q, while the current shared recipe forces OpenSSL 3.5.8. The archive does
not contain that recipe. This is a dependency graph failure, not an incomplete
download. Preserve the restored cache and original archive; do not repeat the
download or lower the OpenSSL requirement.

The historical Android/Pico source graph contains OpenSSL 3.5.8 revision
`e2ab566b1c764e543d69c8a6fa0def5b`, Node 22 revision
`a76ae5683eb20fbde3f88e16d8bea96e` and Qt revision `d75aeab99c3d3426df7ec9b39bc73aa8`.
These are genuine separately produced identities. They do not qualify the
current Phone source graph: Phone uses Qt `4fd1f62ee1914f2f3ec4fe298a07c283`,
libpng 1.6.58, OpenEXR 3.2.12 and Node Release, whereas the historical target
uses libpng 1.6.44, OpenEXR 3.1.9 and Node Debug. A package transport receipt
does not turn those historical packages into a current Phone producer receipt.
No fully qualified producer for the current Phone graph has been demonstrated.

The following original prebuilt preparation commands therefore currently fail
closed on OpenSSL and must not be presented as a ready application lane. They
remain the diagnostic consumer sequence if matching prebuilt dependencies are
independently produced and qualified later:

```bash
conan install android/common/conan/conanfile-pico.py \
  -of android/common/conan/phone-16k-debug \
  -pr:h android/common/conan/profiles/phone-arm64-16k \
  -pr:b android/common/conan/profiles/phone-prebuilt-linux-x86_64 \
  --no-remote --build=never
conan install android/common/conan/conanfile-pico.py \
  -of android/common/conan/phone-nonqt-16k-debug \
  -pr:h android/common/conan/profiles/phone-nonqt-arm64-16k \
  -pr:b android/common/conan/profiles/phone-prebuilt-linux-x86_64 \
  --no-remote --build=never
android/phone/finalize-phone-16k-deps.sh
android/phone/build.sh prepare
```

Save these new invocation logs with the final source SHA and retain the original
archive/producer identities. Phone preparation selects Draco from its exact
prepared CMakeDeps package binding; another ARM64 cache package is rejected.
The content sentinel, complete package ELF gate and original archive checksum
remain required. This is a current consumer of prebuilt dependencies, not a new
dependency Build receipt or source-only cold build.

## Prebuilt application runner, currently blocked

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
The current world path uses private VirtualDisplay/Presentation hardware
composition and SurfaceTexture/EGL readback; moving MP4 pixels still require
the real-device test rather than a player clock or host scenegraph fixture.
## Current source producer and complete application route

The executable current-source route is
`android/phone/fdroid/scripts/cold-build.sh`, not
`android/phone/fdroid/scripts/build-release.sh build`: the latter deliberately
returns `DEFERRED_SHARED_BINDING` and does not compile an application.

The cold route verifies the current source closure, recipe exports, lock files,
SDK and toolchain bindings. It starts an empty private Conan cache, builds the
bootstrap, Linux host tools and Android target with `--no-remote --build='*'`,
stages the actual host tools, and writes the Phone sentinel only after the
complete dependency ELF checks. It then sets `OVERTE_FDROID_CONAN_DIR` to that
new target graph and runs the full `:phoneInterface:assembleRelease` task in the
same network-isolated runner. This route intentionally cannot reuse the
historical 62-package transport as a purported cold build.

The pinned Podman image is
`1b2da099cf7c03f6ea4b751cf8f148784f12db71fdaabb2b6330d60ba1572dda`.
Actual coordinator probes report GCC 15.3.0, Java 17.0.20.1, CMake 3.31.6 and
Conan 2.25.2. The local host GCC 16.2.1 must not be reported as that producer's
GCC 15. The current Phone closure's recipe/index/lock/toolchain identities
validate, but its complete archived source bytes and new producer invocations
still require their own checks.

After the coordinator schedules this separate producer and freezes the final
clean Phone revision, assign an existing verified complete source store to
`PARITY_SOURCE_STORE` and a new absolute attempt path to `PARITY_ATTEMPT_ROOT`.
From the frozen repository root, preserve the output of each stage separately:

```bash
test "$(git rev-parse HEAD)" = "$PARITY_SOURCE_REVISION"
test -z "$(git status --porcelain)"
export ANDROID_SDK_ROOT=/home/user/Android/Sdk
export OVERTE_SOURCE_CLOSURE_STORE="$PARITY_SOURCE_STORE"
export OVERTE_ATTEMPT_ROOT="$PARITY_ATTEMPT_ROOT"
export OVERTE_GRADLE_STORE=/tmp/overte-phone-web-gradle-store
android/phone/fdroid/scripts/cold-build.sh --preflight
android/phone/fdroid/scripts/cold-build.sh --run
```

Preflight verifies the actual store's source bytes; a missing or outdated store
stops before production. The run copies only the frozen committed source and
the hash-verified Gradle store into the new attempt. It preserves the source
revision and original identities, resource monitoring and protected attempt
marker. An interrupted active attempt must be observed, not restarted; use
`--resume` only for the same protected incomplete source revision.

The expected artifact is
`$PARITY_ATTEMPT_ROOT/source/android/phone/apps/phoneInterface/build/outputs/apk/release/phoneInterface-release-unsigned.apk`.
The helper records its SHA256 only after the complete Gradle task succeeds;
there is no signing, publishing or installation step. Its proof version code
and version name do not authorize a distribution release. Native application
production and device acceptance remain unexecuted at this checkpoint.
