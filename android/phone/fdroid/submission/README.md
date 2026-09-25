# Android Phone F-Droid packaging draft

This directory prepares the `noah-be/overte` Android Phone fork for the official
F-Droid build process. It does not publish, sign, push, tag, or submit anything.
The generated build is deliberately disabled until its **public commit** and
complete F-Droid buildserver execution have been qualified. Passing metadata
lint or a local APK test is not F-Droid admission.

See [the local qualification record](VALIDATION.md) for completed checks,
their limits, and the remaining publication decisions.

## What is reused

`build.py` calls the existing source-closure acquisition/composition scripts,
exact Conan recipe exports and three locked source-only graphs. It does not
change the normal Phone, Pico, iOS, or shared Overte implementation. The existing
`build.sh fdroid build` contract remains deferred; this is a separate F-Droid
manual-build entry point.

The installed Gradle wrapper cannot be relied on: F-Droid's source scanner
removes `gradlew`, `gradlew.bat`, and `gradle-wrapper.jar`. This adapter instead
acquires the same Gradle 8.13 distribution, checks the existing SHA-256, and runs
its executable directly. No wrapper scan exception is required.

The metadata's eight `scandelete` entries came from the actual F-Droid source
scan. They delete only unused test data or npm package manifests in F-Droid's
**disposable checkout**. They do not delete JavaScript implementations, icons,
fonts, runtime media, or license notices from the maintained repository. There
is no blanket `scanignore`, no bypass of APK scanning, and no per-asset license
certificate requirement.

## Stage a reviewable submission

Commit the intended packaging changes locally first. From the repository root:

```sh
python3 android/phone/fdroid/submission/stage.py \
  --commit HEAD --output /absolute/new/fdroid-draft
```

The command reads both the recipe and store text from that exact commit, writes
`metadata/io.github.noah_be.overte.phone.yml` and `metadata/io.github.noah_be.overte.phone/en-US/`, and refuses
to overwrite an existing directory. An old commit without the build adapter is
rejected. This does not make an unpublished commit publicly fetchable.

Use a disposable local checkout of `fdroiddata` for the actual F-Droid commands;
its `config/` supplies current category definitions and their icons. Copy the
staged metadata directory into that checkout, then run:

```sh
fdroid readmeta
fdroid lint --format io.github.noah_be.overte.phone
fdroid rewritemeta io.github.noah_be.overte.phone  # if formatting changes are reported
```

Do not treat a disabled build being skipped as a successful build. After the
source commit is public and buildserver prerequisites are verified, remove the
build's `disable` field in the submission copy and run:

```sh
fdroid build --server --test io.github.noah_be.overte.phone:1
```

This requires a configured local F-Droid buildserver VM; metadata lint alone does
not provision one. `--test` produces a test build, not a published repository.
No F-Droid upstream write or merge request is authorized by these instructions.

## Build phases and prerequisites

The metadata installs standard Debian trixie packages inline in F-Droid's
`sudo` stage, from `/tmp`. No source repository script runs as root. There is
no Debian snapshot, unstable repository, exact distro package pin or
`update-alternatives` override. Conan 2.25.2 is installed in the build user's
virtual environment during `prebuild`, without sudo. The optional `provision.sh`
helper is only for a disposable local VM and is not called by the metadata.

The submission adapter uses GCC/G++ 14, OpenJDK 21, system CMake 3.31 or newer
within major 3, and Ninja 1.12 or newer within major 1. Debian patch updates are
accepted, with actual versions printed in the preflight log. These bounds match
the trixie packages; they are not claims about minimum application requirements.
`OVERTE_FDROID_STANDARD_TOOLCHAIN=1`, set by the adapter, selects this check and
explicit GCC 14 settings for both Linux Conan contexts. The Android host context
retains NDK Clang 18. Shared Phone/Pico profiles and the historical local
qualification image/locks are unchanged; their checks remain on the legacy path.

The metadata acquires SDK 36, Build-Tools 35.0.0 (the AGP default) and 36.0.0
(the explicit aapt2 override), Command-line Tools 22.0 (`apkanalyzer`),
SDK CMake 3.31.6 and NDK 27.3.13750724 through F-Droid's SDK tooling.
Dependency source versions, recipe locks and archive hashes remain unchanged.
Source-built Conan build tools remain locked too; this changes the host's
Debian tools, not the dependency graph's source identity.

**Validation boundary:** the successful GCC 15/OpenJDK 17 builds do not qualify
this new toolchain. Run a clean source build before enabling the generated draft.
Reproducible APK comparison and the signing/reference-APK workflow are separate
follow-up work. Keep the existing public `android-phone-v0.1.0+1` tag unchanged.

The recipe targets ARM64 only, Android 8.0+ (API 26), versionCode 1/versionName
0.1.0. The new workspace, Conan cache and Gradle home are isolated from developer
caches. The metadata places the work directory beside the checkout: recipe
transport archives must stay outside the scanned source tree. Acquired dependencies come from the existing public, version/hash-locked
source closure and locked Gradle project.

`build.py --check` verifies the commit, tool versions, SDK files and working
network namespaces without acquiring or compiling. It also checks the APK
inspection tools and runs the pinned `apkanalyzer` before the expensive build,
so a missing analyzer cannot first fail during release packaging. `--acquire-only` additionally
acquires and prepares sources/Gradle dependencies, but does not compile the app.
A direct check on an already provisioned buildserver looks like:

```sh
python3 android/phone/fdroid/submission/build.py \
  --commit "$(git rev-parse HEAD)" --version-code 1 --version-name 0.1.0 \
  --sdk "$ANDROID_SDK_ROOT" --work-dir /absolute/new/build-attempt --check
```

Remove `--check` for the complete build. The native build retains the existing
empty-cache checks and `--no-remote --build='*'` policy. Both compilation stages
run in fresh network namespaces, with loopback enabled for Gradle's local daemon
handshake and no external network interfaces. Kernel policy must allow user and
network namespaces; an unsupported host fails before acquisition. There is no
network-enabled compilation fallback.

Conan source extraction uses `tools.files.unzip:filter=data`. Archive owner IDs
are deliberately not restored in the root-mapped namespace: those foreign IDs
are unmapped, and a failed `chown` would otherwise prevent `tarfile` from applying
executable modes (reproduced with NASM's `configure`). The filter preserves the
required executable bits while retaining archive path/link safety checks. Do not
repair this by granting blanket executable permissions to downloaded sources.

The only optional reuse is `--source-store /absolute/verified-source-archives`:
it still validates every input against the public source manifest and cannot
supply compiled Conan packages. The submitted recipe does not use this option.

The output is an unsigned release APK and `result.json` with its hash. Keep the
work directory and logs as build evidence. A previous clean build took about
103 minutes on the local worker; allow several hours for a cold F-Droid build.
A locally successful build that reused compiled dependencies is not evidence
that this complete recipe passed a cold build.

## Store presentation and decisions

English text lives under `android/phone/fastlane/metadata/android/en-US/` and is
copied into the submission by the staging helper. The store icon is a 512-pixel
rendering of the [maintainer-supplied Navy artwork](../../branding/README.md),
matching the Phone launcher and splash drawable, with metadata stripped.
Only the approved author name and public profile are included; no private
contact details or private device screenshots are included. Two maintainer-created
Phone screenshots are included in `images/phoneScreenshots/`: the beach view
first, then the Overte sign. They were visually reviewed for private information;
EXIF metadata was removed without changing image pixels.

The maintainer approved the following release configuration:

- **Identity:** `Overte Mobile (Unofficial)`, application ID
  `io.github.noah_be.overte.phone`, versionCode `1`, versionName `0.1.0`.
  The internal Java/JNI namespace remains `org.overte.phone`; Android components
  therefore use fully qualified class names. Earlier local test APKs used a
  different application ID. They are separate installations, not upgrade inputs.
- **Store:** categories `Internet`, `Social Network`, `Voice & Video Chat`;
  license field `Apache-2.0`; author `Noah Frank`; author website
  `https://github.com/noah-be`. Source and issue links target `noah-be/overte`.
  No separate project website, public email or donation links are configured.
  Store description and initial changelog use the approved unofficial name;
  the description requires OpenGL ES 3.2 and does not list jumping separately.
- **Device support:** API 26 minimum, target/compile API 36, ARM64 and OpenGL ES
  3.2. SDK/NDK/CMake versions and the existing eight scanner deletions remain
  unchanged. The supplied Navy artwork and two maintainer-created Phone
  screenshots are included.
- **Signing:** normal F-Droid signing for the F-Droid release. The local Android
  debug key remains test-only. Signing for any separate distribution channel
  must be planned separately.
- **Publication:** disabled draft, full commit binding, unsigned release APK,
  twelve-hour build timeout and Android-specific tag update detection. The
  current submission and existing tag use the earlier qualified toolchain.
  Publish a newly validated source revision before updating that submission.

The [earlier qualification record](VALIDATION.md) documents the old test identity
and is historical evidence, not validation of the renamed APK. On 2026-09-21,
the new identity passed incremental release assembly, APK content and 16-KiB
checks, installation, and restart smoke testing. The first foreground check
encountered the microphone permission dialog, as confirmed by the maintainer;
the subsequent restart passed. This reused compiled dependencies and does not
replace cold qualification of the final revision.

The local F-Droid controller and VM configurations have passed configuration
validation and metadata lint. A complete clean `--server --test --scan-binary` build passed on 2026-09-22
for local commit `24075d829f6d3b5bdb694cf13b6494979689be85`; see VALIDATION.md
for its APK hash and qualification limits. The exact tested commit was later
fetched from the public fork after the maintainer authorized source publication.
These are technical checks, not owner attestations. Nothing here publishes,
merges, tags, deletes branches or updates private device-lab configuration.

## Regression checks

```sh
python3 -B -m unittest discover -s android/phone/fdroid/submission -p 'test_*.py' -v
sh -n android/phone/fdroid/submission/provision.sh
```

Tests cover commit/version validation, source-bound staging, dirty-text isolation,
refusal to overwrite state, corrupted Gradle downloads, ZIP traversal, developer
environment isolation, wrapper-independent release commands and store limits.
Actual `fdroid readmeta`, `fdroid lint`, source scanning and APK scanning must also
be run; unit tests are not replacements for them.

### Standard-toolchain preparation (2026-09-22)

The submission tests (18) and cold-build executor tests (8) passed. A disposable
container based on the actual CI buildserver image, digest
`sha256:9cb68105642ca4e7b295f0ceab10f069f5b3247dc18fa7c36046e9d81aa469a8`,
installed the unpinned standard packages successfully. Its toolchain check passed
with GCC/G++ 14.2.0, CMake 3.31.6, Ninja 1.12.1, OpenJDK 21.0.12.1 and Conan
2.25.2. Real `conan profile show` confirmed GCC 14 in both Linux contexts and
Clang 18 in the Android context. No full APK build or reproducibility claim is
part of this preparation. The online submission still references the previously
tested source until the new revision is qualified and published.

## Primary references

- [F-Droid submission guide](https://f-droid.org/docs/Submitting_to_F-Droid_Quick_Start_Guide/)
- [Build metadata reference](https://f-droid.org/docs/Build_Metadata_Reference/)
- [Current F-Droid categories](https://gitlab.com/fdroid/fdroiddata/-/blob/master/config/categories.yml)
- [Debian trixie GCC package](https://packages.debian.org/trixie/gcc)
- [Debian trixie OpenJDK package](https://packages.debian.org/trixie/openjdk-21-jdk-headless)

## Reproducibility findings and corrections

Independent standard-toolchain jobs `16664209585` and `16666614920` both passed
build and APK checks, but their unsigned APKs differed. The ZIP entry order was
identical. Differences were concentrated in native libraries and Qt resources:

- Native diagnostic strings and DWARF-derived build IDs contained random Conan
  cache paths. The submission-only Conan hook adds `-ffile-prefix-map` for the
  package's source/build roots and dependency headers. The app receives the same
  recorded mappings through a generated CMake include. Compilers are unmodified.
- OpenSSL included the wall-clock build date. The adapter now derives
  `SOURCE_DATE_EPOCH` from the exact source commit and fixes the locale/timezone.
  OpenSSL receives no additional path-bearing flags because its build-info string
  would embed them; the observed OpenSSL difference was the date.
- Both standalone RCC files had identical data regions; only the resource tree
  metadata differed. Qt's source-date override fixes those timestamps, including
  resources generated during compilation. Cache-manifest hashes are regenerated
  from the resulting assets, as before.
- Node embeds `config.gypi` in `process.config`, including random build and
  dependency paths. A guarded build-hook adjustment to `tools/js2c.cc` normalizes
  only that informational embedded copy. Actual GYP include/link paths remain
  unchanged. The hook rejects an unexpected generator implementation.
- The next full pair differed only in `libshaders.so`: Scribe inserted wall-clock
  dates into generated shader comments. The isolated hook binds `_SCRIBE_DATE`
  to the same commit epoch before compiling Scribe. Shader instructions and
  copyright comments are preserved; unexpected Scribe implementations fail.

The hook is installed only in the new, isolated submission Conan home. It does
not modify global Conan configuration, recipes in the source export store,
application features, assets, or sibling-platform builds. The source commit binds
these additional build instructions. Original failed comparisons are retained;
comparison after these corrections must still pass before claiming reproducibility.

Tests cover prefix-map context selection, all Qt build variants, OpenSSL's
build-info exception, and actual C++ compilation of the Node normalization.
A real Conan/GCC test built the same small library in two distinct caches and
obtained byte-identical output, including the build ID. Full Android rebuilds are
still required; this small regression is not the release reproducibility proof.

The first corrected full build (`16668521593`) passed but still contained random
paths in Qt and CMake-built Android dependencies. A real NDK/CMake regression
reproduced the problem: NDK initialization discarded Conan's initial compiler
flags. The hook now also emits directory compile options after toolchain
generation. Qt receives the flags in its late `default_post.prf` feature, after
mkspec initialization. Node's embedded paths were already normalized correctly.
The redundant comparison pipeline was stopped after this concrete evidence.

Both corrections passed two-build regressions using the actual NDK and Qt5/qmake,
respectively. They can be repeated in a disposable standard buildserver:

```sh
# Requires Conan 2.25.2, GCC 14, CMake, Ninja and the declared Android NDK.
export ANDROID_NDK_HOME="$ANDROID_SDK_ROOT/ndk/27.3.13750724"
python3 android/phone/fdroid/submission/verify_reproducible_ndk.py
# Requires Qt5 qmake, GCC/G++ and make; override QMAKE if necessary.
QMAKE=/usr/lib/qt5/bin/qmake python3 android/phone/fdroid/submission/verify_reproducible_qmake.py
```

These tests use fresh temporary Conan caches/build directories, no downloads or
application assets, and compare complete ELF files. They fail on a surviving
random build path or any binary difference. Full independent APK comparison is
still the final gate.
