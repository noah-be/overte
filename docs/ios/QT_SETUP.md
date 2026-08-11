<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Qt setup for the iOS port

The native bootstrap application deliberately does not depend on Qt. This
separates Xcode, signing, bundle, lifecycle, and Metal failures from the Qt and
Overte migrations.

The integrated client is pinned to Qt 6.11.1 for iOS. Host tools and target
libraries must have exactly the same version. Install them through a Qt
distribution channel permitted by the applicable Qt license, or build them
from source with Xcode. The repository does not accept licenses, store Qt
credentials, or download Qt on a developer's behalf.

Point the build at the target installation, not a desktop Qt installation:

```bash
export OVERTE_IOS_QT_ROOT=/absolute/path/to/Qt/6.11.1/ios
export OVERTE_IOS_QT_HOST_ROOT=/absolute/path/to/Qt/6.11.1/macos
./ios/tools/prepare-qt-ios.sh validate
./ios/build-ios.sh doctor --platform simulator --require-qt
```

The directory must contain:

```text
bin/qt-cmake
lib/cmake/Qt6/Qt6Config.cmake
lib/cmake/Qt6/qt.toolchain.cmake
```

## Conan chainloading

The integrated client has two cross-compilation inputs, but only Qt's iOS
toolchain may be the primary `CMAKE_TOOLCHAIN_FILE`. `configure --client-graph`
therefore invokes the target installation's `bin/qt-cmake` and passes Conans
generated file through:

```text
-DQT_CHAINLOAD_TOOLCHAIN_FILE=<build>/conan/conan_toolchain.cmake
```

`qt-cmake` selects `lib/cmake/Qt6/qt.toolchain.cmake`; that file then includes
the Conan toolchain through Qt's supported chainload hook. The CLI must never
also pass `-DCMAKE_TOOLCHAIN_FILE=...conan_toolchain.cmake`, because doing so
would bypass Qt's iOS platform initialization. Conan continues to provide the
audited dependency paths, architecture, SDK, deployment target, and build
configuration. Run `deps` for the same platform and build directory before
`configure --client-graph`; a missing Conan file fails closed.

## Reproducible preparation on a macOS runner

`prepare-qt-ios.sh` is the license-neutral boundary between repository CI and
the Qt distribution. Its manifest exposes the pinned official component IDs:

```bash
./ios/tools/prepare-qt-ios.sh manifest
```

Given an already downloaded official Qt Online Installer, it prints an
interactive installation command:

```bash
./ios/tools/prepare-qt-ios.sh installer-command \
  /path/to/qt-online-installer-mac-x64-online.app/Contents/MacOS/qt-online-installer-mac-x64-online \
  /absolute/path/to/Qt
```

The command deliberately omits credentials and all options that accept
licenses or prompts. A person or an organization-controlled provisioning job
must authenticate, inspect the offered packages, and accept the applicable Qt
license. After provisioning, cache the resulting `6.11.1/macos` and
`6.11.1/ios` directories in a private cache whose access and redistribution
terms comply with that license. The ordinary build job should restore that
cache and run `validate`; it should never contain a Qt password or silently
accept a license.

The validator checks the exact host and target versions, target CMake
toolchain, required target modules, and the host-side `moc`, `rcc`,
`qmlcachegen`, and `qsb` executables. The default target module contract is
`Core`, `Gui`, `Network`, `Qml`, `Quick`, `Multimedia`, `Svg`, `WebChannel`,
`WebSockets`, `WebView`, `Core5Compat`, and `ShaderTools`. It can be extended
for an experiment with `OVERTE_IOS_QT_REQUIRED_MODULES`, but required
production modules must not be removed from the default.

Qt 6 source installations place internal build helpers such as `moc`, `rcc`,
and `qmlcachegen` in the host prefix's `libexec` directory, while packaged Qt
installations may expose them from `bin`; `qsb` is commonly installed in
`bin`. Validation accepts an executable from either canonical directory for
each required tool and still fails closed when a tool is absent from both.

The public macOS repository exposes the host package as
`qt.qt6.6111.clang_64`. No public `qt.qt6.6111.ios` binary component has been
verified, so the preparation script intentionally does not invent or request
one. The target must come from an organization-provisioned, license-compliant
cache when entitlement permits it, or from the official Qt 6.11.1 source
archive.

The manifest pins the official source URL and SHA-256. Downloading is kept
separate so CI policy can select an approved mirror and record license notices:

```bash
curl --fail --location --output qt-everywhere-src-6.11.1.tar.xz \
  "$(./ios/tools/prepare-qt-ios.sh manifest | sed -n 's/^QT_SOURCE_URL=//p')"
./ios/tools/prepare-qt-ios.sh verify-source qt-everywhere-src-6.11.1.tar.xz
```

On the macOS provisioning runner, first install or build the matching 6.11.1
host Qt, then configure the verified source according to Qt's iOS instructions:

```bash
mkdir qt-ios-build
cd qt-ios-build
../qt-everywhere-src-6.11.1/configure \
  -platform macx-ios-clang \
  -release \
  -qt-host-path /absolute/path/to/Qt/6.11.1/macos \
  -prefix /absolute/path/to/Qt/6.11.1/ios \
  -nomake examples -nomake tests
cmake --build . --parallel
cmake --install .
```

The build still requires Xcode and its iOS SDK. Module selection and the
applicable LGPL, GPL, or commercial obligations must be reviewed before this
expensive source build is cached. The repository cannot perform that legal
decision or provide a Qt commercial entitlement.

## Automated source-cache provisioning

After that license review, the manual `Provision Qt iOS source cache` workflow
builds the smallest currently known full-graph source set: `qtbase`,
`qtdeclarative`, `qtmultimedia`, `qtsvg`, `qtwebchannel`, `qtwebsockets`,
`qtwebview`, `qt5compat`, and `qtshadertools`. Qt's documented comma-separated
`-submodules` form also includes their dependencies. The workflow builds
matching macOS host tools first and then the iOS SDK, validates both trees, and
downloads and verifies the pinned source archive in the ephemeral workspace,
then saves the validated `qt/macos` host prefix and validated `qt/ios` target
prefix under separate immutable keys containing Qt, Xcode, SDK, architecture,
and the build-plan hash. The large, reproducible source archive is deliberately
not cached so it cannot evict the much smaller validated install prefixes. Each
completed component is saved immediately, so a later iOS failure cannot discard
a successful host build. The integrated workflow restores both component keys
exactly and validates the pair before configuration. No prefix-matched fallback
is allowed for toolchains because mixing Xcode, SDK, architecture, or plan
revisions would be ABI-unsafe.

Host and iOS configure policies have separate plan hashes. A target-only fix,
such as explicitly skipping unsupported Qt WebEngine while retaining the native
Qt WebView/WKWebView path, does not invalidate an already validated host prefix.

Compilation uses a bounded 256 MiB `sccache` directory. A run-specific recovery entry
is saved after a normal compile failure (not after successful component publication), and the next compatible run may
restore the newest entry sharing the exact compile-plan prefix. Only the newest
recovery generation for the branch and runner architecture is retained. This cache is
only an optimization: host and target installations are accepted solely after
their normal validators pass. Partial downloads, unvalidated install prefixes,
credentials, and the complete workspace are never cached. When both validated
component caches hit, provisioning skips source restoration, extraction,
Homebrew setup, and compilation entirely. The workflow never uploads the Qt
tree as a downloadable artifact and never builds, signs, or uploads an app.

The underlying command can also be resumed on a controlled macOS machine:

```bash
ios/tools/build-qt-ios-from-source.sh \
  --work-root /absolute/volume/overte-qt-work \
  --install-root /absolute/volume/overte-qt-install/qt
```

Downloads use a `.partial` file and resume with HTTP range requests. The
archive is verified before extraction. The source, host, iOS, and full local
paths can be invoked independently with `--stage`; an unmarked source,
unvalidated prefix, or unknown CMake tree fails closed instead of being
overwritten. Preserve the work root between manual attempts if the runner or
build is interrupted.

Expect roughly a 1 GB source download, substantially more temporary disk space,
and potentially several hours of compilation. GitHub-hosted runner retention,
cache quotas, and maximum job duration remain external limits. The cache does
not change Qt's license: access, redistribution, relinking materials, source
offer, notices, and commercial-seat requirements must be handled according to
the modules and license selected by the project. The workflow intentionally
contains no license-confirmation option and no Qt account credentials.

The Qt host tools used for cross-compilation must match the target Qt release.
Device and simulator slices must share the same Qt configuration and deployment
target. The build must not locate a Homebrew desktop Qt through an incidental
`CMAKE_PREFIX_PATH`.

Qt WebEngine is intentionally excluded from the iOS component set. Embedded
web content uses Qt WebView/WKWebView through the platform web-surface adapter.

The reusable Qt source workflow exposes only its deterministic cache key. Its
job output is forwarded explicitly through the workflow output to the integrated
caller. A per-ref concurrency group serializes cache writers and does not cancel
an in-progress multi-hour build. The bootstrap and integrated workflows retain
separate concurrency groups, so invoking the reusable workflows cannot collide
with the caller's group.

The macOS shell entry points remain compatible with the system Bash 3.2 baseline;
host contracts reject associative arrays, `mapfile`/`readarray`, and Bash 4 case
conversion in those paths. Workflow YAML is additionally suitable for an
`actionlint` audit without requiring that temporary audit binary in the repo.
