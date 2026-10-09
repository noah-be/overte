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

The metadata uses `scandelete` for unused files in F-Droid's disposable
checkout, including globbed dependency manifests and an unused Qt deployment
loader template. The maintained source archives remain hash-pinned. There is
no `scanignore` and no bypass of APK scanning. The compiler-source cleanup
removes the same declared files before native compilation (see below).

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
fdroid build --server --test io.github.noah_be.overte.phone:4
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

**Current validation boundary:** the published 0.1.3 (4) reference is tied to
`ee32aaffe5c78358b4eb1bdfb539793258e53571`. This local follow-up changes source
cleanup and is not covered by that release's full-build or device evidence.
Do not replace its tag or APK. Keep the staged recipe disabled until the new
source has been qualified and its reference-APK/version implications resolved.
The 36000-second timeout is an upper limit, not evidence of performance on the
official buildserver. No successful shared-runner/official-server test is claimed.

The work directory, Conan cache and Gradle home stay outside the checkout.
`prebuild` calls `--acquire-only`: it downloads the hash-locked archives and
Gradle inputs, prepares the dependency source caches, and expands all native
source archives into `fdroid-source-closure/` inside the checkout. The existing
1551 content-bound binary-fixture/platform-tool/wrapper exclusions are applied
before inventorying; the 264 declared `scandelete` files remain for F-Droid's
normal scanner to inspect and delete. The metadata expresses those deletions
as 20 file globs; it has no `scanignore`. F-Droid uses non-recursive globbing,
so nested npm manifests require separate patterns for their different depths.

`build` calls `--build-only` and never acquires inputs. It requires the same
prebuild commit, version, policy, manifest, Gradle distribution and inventory.
The inventory records exact deletion paths and original file hashes. After
scanning, precisely those files must be absent and every remaining source must
match; extra, modified or unexpectedly missing files stop the build. The
inventory cannot be rewritten to accept a scanner finding. Conan's actual
`post_source` hook removes the same 1551 + 264 files from the separately
extracted compiler sources, checking their original hashes before deletion.
The external archive cache cannot silently restore rejected compiler inputs.

hwloc's unused web-tool manifest is also listed as installable data in its
`contrib/hwloc-ps.www/Makefile.am` and generated `Makefile.in`. Deleting the
manifest alone causes `make all` to fail. The cleanup policy removes that one
installation-list entry from both files, checking complete input and output
hashes. The identical edits are applied before the scanner inventory and in
Conan's compiler source cleanup. The manifest stays deleted; library sources,
configure options and runtime behavior are unchanged. Conan already discards
the installed web-tool data from the dependency package.

The newly deleted files are:

- 263 `package.json`/`Cargo.toml` installation manifests. npm and Corepack
  installation are disabled. Node embeds the JavaScript files declared by
  `node.gyp`/`configure.py`, not these manifests; those JavaScript files stay.
  Other manifests belong to unused Meson Rust tests, Qt examples/tests,
  SPIRV-Tools wasm/editor tooling, hwloc web tooling and Draco npm packaging.
- Qt's `src/android/java/.../bindings/QtLoader.java`, an unused Android
  deployment template. It is installed as source by `java/java.pro`, not
  compiled into `QtAndroid.jar` by `jar/jar.pro`. The Phone Gradle project uses
  its maintained `android/common/libraries/qt` bindings, including its own
  `QtActivityLoader`, and the separate QtAndroid.jar runtime delegate. It does
  not use Qt's deployment-template source directory. The runtime Java sources
  and jar inputs remain intact. This correction supersedes the earlier
  rationale for retaining the template as a scanner exception.

`source-scan-policy.json` retains the exact archive, recipe, path, content hash
and rationale for each removal. These entries constrain the implementation;
they are not a long list of scanner exceptions in F-Droid metadata. A fresh
source scan and compiler-cleanup rehearsal validate this policy; they do not
prove a successful full build or a byte-identical reference APK.

`build.py --check` verifies source coordinates, the SDK/toolchain and isolation
without acquiring or compiling. On a host with networking it requires working
`unshare --user --map-root-user --net`. On a runner already isolated to loopback
it reuses that isolation without nested user namespaces. Both paths test a local
socket handshake for Gradle and reject any non-loopback interface. There is no
fallback to network-enabled compilation.

```sh
python3 android/phone/fdroid/submission/build.py \
  --commit "$(git rev-parse HEAD)" --version-code 4 --version-name 0.1.3 \
  --sdk "$ANDROID_SDK_ROOT" --work-dir /absolute/new/build-attempt --check
```

Use a fresh work directory for `--acquire-only`; retain it for the subsequent
F-Droid scan and `--build-only`. Do not skip the intervening scanner. The native
build retains its empty-binary-cache and `--no-remote --build='*'` checks.
A source-scan failure is useful evidence and must not be presented as a completed
buildserver qualification. The local loopback-only container probe demonstrates
the alternative isolation path, not official infrastructure compatibility.

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

Current release configuration:

- **Identity:** `Overte Mobile (Unofficial)`, application ID
  `io.github.noah_be.overte.phone`. Published version: `0.1.2` (3); disabled
  review candidate: `0.1.3` (4).
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
- **Signing:** reproducible builds against the maintainer-signed published APK,
  with `AllowedAPKSigningKeys` binding the established release certificate.
  The local Android debug key remains test-only. No keys belong in the checkout.
- **Publication:** disabled candidate, full commit binding, unsigned build output,
  ten-hour timeout ceiling and Android-specific tag update detection. The
  published 0.1.2 reference remains unchanged. Qualify the new source revision
  before requesting approval to publish a new tag, signed reference or metadata.

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
