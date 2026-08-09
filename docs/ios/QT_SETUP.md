<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Qt setup for the iOS port

The native bootstrap application deliberately does not depend on Qt. This
separates Xcode, signing, bundle, lifecycle, and Metal failures from the Qt and
Overte migrations.

The integrated client targets Qt 6.11 or a newer compatible Qt 6 release for
iOS. Install it through a Qt distribution channel permitted by the applicable
Qt license, or build it from source with Xcode. The repository does not accept
licenses or download Qt on a developer's behalf.

Point the build at the target installation, not a desktop Qt installation:

```bash
export OVERTE_IOS_QT_ROOT=/absolute/path/to/Qt/6.11.0/ios
./ios/build-ios.sh doctor --platform simulator --require-qt
```

The directory must contain:

```text
bin/qt-cmake
lib/cmake/Qt6/Qt6Config.cmake
```

The Qt host tools used for cross-compilation must match the target Qt release.
Device and simulator slices must share the same Qt configuration and deployment
target. The build must not locate a Homebrew desktop Qt through an incidental
`CMAKE_PREFIX_PATH`.

Qt WebEngine is intentionally excluded from the iOS component set. Embedded
web content uses Qt WebView/WKWebView through the platform web-surface adapter.

