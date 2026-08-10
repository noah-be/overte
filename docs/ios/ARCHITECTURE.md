<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS port architecture decisions

## ADR-001: Qt baseline

**Decision:** Target Qt 6.11 or a newer compatible Qt 6 release. Keep Qt 5
desktop builds working while shared source is migrated.

**Reason:** The current client hard-codes Qt 5 modules, including Qt WebEngine.
An App Store build must use a current Apple SDK, so relying on the old Qt 5 iOS
toolchain would make the port depend on an unsupported compiler combination.

**Implementation rule:** New compatibility helpers use version-neutral Qt
APIs where possible. Qt target names are selected centrally; individual
libraries must not grow independent Qt-version detection.

## ADR-002: static mobile application

**Decision:** Link iOS code and Overte plug-ins statically and register required
plug-ins at build time.

**Reason:** The desktop plug-in architecture assumes shared libraries and
runtime discovery. An iOS bundle needs a closed, signed native-code graph.

The PCM and Opus codec providers implement this decision explicitly. Their
iOS targets are static, compile with `QT_STATICPLUGIN`, and are linked into
`Overte` with CMake `WHOLE_ARCHIVE` so linker dead stripping cannot discard the
generated provider entry points. `IOSStaticCodecPlugins.cpp` imports both
providers with `Q_IMPORT_PLUGIN`, and `PluginManager` enumerates
`QPluginLoader::staticInstances()` instead of scanning the signed application
bundle. The desktop shared-library and `Contents/PlugIns` copy paths are not
executed on iOS.

## ADR-003: graphics selection spike

**Decision:** Evaluate the existing Vulkan backend through MoltenVK first, then
fall back to a native Metal backend if the representative-scene gate fails.

The spike passes only if it renders the same reference frame, supports required
texture formats and synchronization, has no desktop OpenGL dependency, and
meets the frame-time and memory budgets recorded in the benchmark report.

OpenGL ES is not the long-term iOS backend. It may only be used by a diagnostic
bootstrap target and must not become a release dependency.

## ADR-004: embedded web content

**Decision:** Replace desktop Qt WebEngine surfaces with a platform web-surface
interface backed by WKWebView/Qt WebView on iOS.

Features that require Chromium-specific APIs must be feature-gated until they
have an iOS implementation. The full WebEngine module must not be linked into
the iOS target.

## ADR-005: scripts on iOS

**Decision:** Build the existing JavaScript runtime in an iOS-compatible,
non-JIT mode during the first spike. If the runtime cannot pass the script
compatibility suite without executable-memory permissions, evaluate a
non-JIT engine behind the existing script-engine interfaces.

Downloaded scripts remain data interpreted by the application. Native code,
dynamic native modules, and mechanisms that change the application's declared
features are outside the port scope.

## ADR-006: platform boundary

**Decision:** iOS-specific Objective-C++ lives below narrow C++ interfaces in
`ios/` or the owning library. Shared application logic must not import UIKit,
AVFoundation, CoreMotion, or Metal headers directly.

Platform services initially cover lifecycle, paths, audio sessions,
permissions, display metrics, safe areas, orientation, touch, and sensors.
Desktop Objective-C++ sources are not implicitly mobile services:
`AppNapDisabler.mm` remains part of the macOS Interface graph but is removed
from the iOS source glob because App Nap is a macOS-only process policy. Its
`Application.cpp` include and process-lifetime instance are also explicitly
guarded out on iOS, so no unresolved desktop implementation enters the link.
Likewise, the AppKit-backed `SpeechRecognizer.mm` and all of its Interface
registration sites are excluded on iOS; the existing macOS and Windows speech
implementations remain unchanged.
The deprecated `PlatformInfo` compatibility API identifies iOS explicitly and
returns conservative unavailable/unknown hardware values there. It must not
fall through to the macOS branches that launch `sysctl` or `system_profiler`.
The two macOS native-window mouse workarounds in `Application_Events.cpp`
(Cmd-click rewriting and right-drag focus recovery) are also explicitly
excluded from iOS, where touch/pointer events must retain Qt's mobile semantics.
The related macOS cursor-target workaround is desktop-only as well: it targets
the top-level window to compensate for a GL-widget limitation, while iOS uses
the normal primary Vulkan surface target.
The legacy `UIUtil` four-pixel title-bar correction is similarly restricted to
macOS: iPad windows do not use the affected desktop `QStyle` title-bar metric.
`UIUtil::scaleWidgetFontSizes()` treats iOS as a point-based UI platform and
therefore keeps a 1.0 scale. The legacy 0.75 compatibility scale remains
limited to the Windows/Linux 96-DPI branch.
The desktop `LogDialog` is a separate fixed-layout `QDialog` with window-on-top
and reveal-in-file-manager controls. Its toggle entry point is a no-op on iOS;
on-device diagnostics use the existing in-app/tablet log surfaces and exported
device logs instead of creating a desktop utility window.
Its now-nonfunctional desktop `Developer > Log` action and Ctrl+Shift+L
shortcut are omitted from the iOS menu as part of the same boundary.
The separate 780-pixel-minimum Entity Script Server `QDialog` follows the same
boundary: its toggle and developer-menu action are omitted on iOS, while the
HMD-friendly/in-app script log remains available.
The stand-alone JavaScript console follows that rule too: its fixed-size,
always-on-top `QDialog` and desktop keyboard-shortcut menu action are omitted on
iOS. Script execution and embedded debugging/logging services remain intact.
The legacy QWidget `DomainConnectionDialog` fallback is also desktop-only. The
iOS action uses the existing tablet timing surface when available and otherwise
does not create a dynamically sized top-level table window.
Entity/Octree statistics use the same boundary: the fixed-width,
always-on-top QWidget fallback is disabled on iOS, while the existing
`TabletEntityStatistics.qml` view remains the mobile presentation.

## ADR-007: secret-free automation

**Decision:** Pull-request CI builds and launches unsigned simulator bundles.
Device signing is a separate, explicitly approved job whose secrets are held by
the CI environment or local keychain.

No team ID, certificate, provisioning profile, keychain password, or App Store
credential may be committed.

## ADR-008: fail-closed integration graph

**Decision:** A root iOS configuration defaults to
`OVERTE_IOS_BOOTSTRAP_ONLY=ON` and returns after adding the audited native app
shell. Enabling the legacy full-client graph requires an explicit opt-out.

**Reason:** The desktop graph still contains build-host tools, dynamic plug-in
packaging, macOS bundle rules, OpenGL presentation code, and Qt 5 compatibility
paths. Allowing those into the default iOS graph would make incidental progress
look like a supported build and hide the first unsupported dependency behind a
large, nondeterministic failure surface.
