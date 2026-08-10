<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Qt 6 migration boundary

The iOS target selects Qt 6 centrally through `cmake/QtCompat.cmake`. Existing
desktop and Android targets remain on Qt 5 while shared source is migrated.

## Transitional compatibility

Qt Core5Compat is linked to Qt 6 targets as a temporary bridge for QRegExp,
QTextCodec, and QStringRef. The iOS-reachable animation library still uses
QStringRef in `AnimExpression.cpp/.h` and `Flow.cpp`, so the module cannot yet
leave the iOS graph. New iOS code must use QRegularExpression, QStringView, and
current text APIs.
Core5Compat is not a reason to add new Qt 5 API use.

The shared library macro treats iOS as an ARM target before applying optional
x86 SIMD flags. Although CMake reports iOS as both `APPLE` and `UNIX`, its
translation units must never inherit desktop `-mavx`, `-mavx2`, or
`-mavx512f`; desktop x86 builds retain the existing optimized-source flags.

The optional Neuron mocap plugin likewise limits its proprietary data-reader
dependency to Windows and desktop Apple builds. iOS must not download or link
that macOS SDK merely because CMake reports the target as `APPLE`; the plugin
can only be enabled there after its vendor provides an iOS-compatible SDK.

Crashpad is also disabled before dependency discovery on iOS. The current
integration links desktop Apple support libraries and copies a separate
`crashpad_handler` executable next to the target, which is not an audited
iOS-sandbox/bundle design. Desktop targets retain that integration; iOS crash
reporting stays fail-closed until an in-process supported path is provided.

## iOS audio-session lifecycle

The bootstrap UIKit host configures `AVAudioSessionCategoryPlayAndRecord` with
game-chat, speaker, and Bluetooth-HFP policy. It activates the session only when
the application becomes active, deactivates it on entry to the background with
`NotifyOthersOnDeactivation`, and only reactivates after an interruption when
iOS supplies `ShouldResume`. Activation failures are logged and never reported
as success. This AppDelegate is not linked into the Qt full-client target.

Apple's desktop `AudioHardware.h` fallback and explicit CoreAudio linkage are
excluded from iOS. The full-client path uses Qt Multimedia's `QAudioDevice`,
`QAudioSource`, and `QAudioSink`. Its permission bridge now configures and
activates PlayAndRecord/game-chat on AudioClient start and deactivates with
NotifyOthersOnDeactivation after AudioClient stop. All AVAudioSession mutations
are synchronously marshalled to the main queue; interruption telemetry records
only begin/end, ShouldResume, reactivation outcome, and numeric error code.
Full-client interruption recovery, Bluetooth routing, microphone permission,
and background behavior still require physical-device evidence.

Both the bootstrap and integrated Interface bundle use the audited iOS plist,
including `NSMicrophoneUsageDescription`. The UIKit host requests record
permission, while the Qt full client also requests it at audio startup because
Qt may own the application delegate. `AudioClient` treats both undetermined and
denied states as unavailable input and falls back to its existing silent timer;
it does not construct a `QAudioSource` until permission is explicitly granted.
Only the coarse granted/denied state is logged. Grant/denial prompts and recovery
after changing permission in Settings remain physical-device acceptance checks.

## Local-network permission and domain UDP

Both iOS bundles declare `NSLocalNetworkUsageDescription`. The production
domain path continues to use the existing `QUdpSocket`/UDT transport and lets
iOS present its local-network prompt when a private-network endpoint is first
accessed. The client neither browses nor publishes Bonjour services, so
`NSBonjourServices` is intentionally absent. DNS resolution, STUN, DomainList,
and entity packet bytes are unchanged.

iOS does not expose a reliable application-level local-network permission
status. UDP therefore remains fail-closed through the existing negative send
result and socket-error signal. iOS diagnostics record only numeric error/state
categories and whether output remains pending; they omit peer addresses and
free-form error strings that could contain private LAN endpoints. Prompt,
denial, Settings recovery, public-domain access, and private-domain access still
require physical-device evidence.

The first source audit identified these compile boundaries:

- legacy QRegExp use spread across application and shared libraries;
- Qt 5 multimedia format and device APIs in `libraries/audio-client`;
- desktop WebEngine profiles, now excluded in favor of the iOS WebView adapter;
- desktop/HMD window and OpenGL paths that must not enter the iOS target; and
- remaining Qt-5-specific deployment helpers used only by desktop packaging.

The network/entity migration now uses `QRegularExpression` for address,
viewpoint, host, UUID, and octree replacement-backup matching. Explicit
`anchoredPattern` calls preserve the former `QRegExp::exactMatch` boundaries;
captured address/viewpoint fields and case-insensitive host matching remain
unchanged. This removes `AddressManager.cpp` and `OctreePersistThread.cpp` from
the Core5Compat debt inventory.

## Domain connection audit

The production `DomainHandler` hostname lookup now uses Qt 6's typed
`QHostInfo::lookupHost(name, context, member)` overload. The context remains the
handler itself, so completion still runs in its event-loop thread and is
discarded if the handler is destroyed; DNS selection and all Overte protocol
packets are unchanged. This removes the compile-time dependency on a
string-normalized `SLOT(...)` signature in the first domain connection step.

The adjacent `NodeList` path uses Qt 6-supported `QHostInfo`,
`QNetworkInterface`, queued `QMetaObject::invokeMethod`, and QObject connection
APIs. Its remaining string-based timer connection is supported by Qt 6 and is
not a current iOS compile blocker, so it is left unchanged to keep this port
semantics-neutral.

## UDT receive-path audit

The iOS UDP transport now connects `QAbstractSocket::errorOccurred` to
`NetworkSocket::onUDPSocketError` with Qt's typed connection syntax. Qt 6 no
longer exposes the former `error(...)` signal used by the string-based Android
compatibility connection. A version guard retains that legacy path for builds
older than Qt 5.15, while Qt 5.15 and Qt 6 compile-check the signal and slot
types and reliably forward UDP errors on iOS.

This change is below packet decoding: it does not touch UDT headers,
`ReceivedMessage` byte positions, message assembly, `PacketReceiver` listener
selection, or any DomainServer packet. The adjacent receive and dispatch code
uses Qt 6-supported `QByteArray`, atomics, `QPointer`, `QSharedPointer`, mutex,
and functor-based queued invocation APIs; no additional Apple-only branch is
required there.

## Entity-query receive audit

`OctreePacketProcessor` no longer includes or calls the desktop `FileLogger`
queue diagnostic on iOS. The diagnostic was already disabled on Android and is
now guarded from both Qt's `Q_OS_IOS` configuration and the early
`OVERTE_IOS` build boundary. It only reported when the processing queue was far
behind; removing it from the iOS compilation unit cannot change queueing or
entity processing.

The audited `EntityQuery` receive path otherwise retains the same packet type
registration, stats/piggyback split, version check, message rewind, erase/data
dispatch, safe-landing sequence, and EntityServer protocol bytes. Its Qt data
structures and atomics are available on Qt 6/iOS, so no further platform branch
is introduced.

## Entity-to-resource handoff audit

The ATP `ResourceManager::normalizeURL(QString)` prefix pass now uses a C++
range-based loop instead of Qt's legacy `foreach` macro. Qt 6 strict mode can
define `QT_NO_FOREACH`; the old spelling then prevents this production resource
path from compiling. The function already takes a locked snapshot of the
ordered prefix map, and the new loop iterates that same snapshot by const
reference, so matching order and `replace(0, prefix.size(), replacement)` are
unchanged.

The adjacent handoff remains real production code: `EntityTreeRenderer`
creates renderables from streamed entities, model/material resources retain
their normalized URL, and `AssetResourceRequest` resolves ATP mappings or
hashes through `AssetClient`. No URL scheme, hash expression, byte range,
cache policy, request packet, renderer selection, or EntityTree mutation was
changed by this compile fix.

The adjacent OBJ export boundary now sanitizes mesh group names with
`QRegularExpression`. The same negated ASCII character class is passed to
`QString::replace`, which still replaces every character outside letters,
digits, hyphen, and underscore with `_`. Vertex, normal, part, topology, and
index serialization are unchanged. This removes `OBJWriter.cpp` from the
Core5Compat debt inventory without broadening accepted OBJ identifiers.

The entity hyperlink tooltip's place-name gate now uses an explicitly anchored
`QRegularExpression`. The legacy expression was already bounded with `^` and
`$`; wrapping it with `anchoredPattern` makes the former `QRegExp::indexIn`
whole-string intent explicit before `match().hasMatch()`. Valid place previews,
rejected punctuation/underscore cases, and the subsequent account request are
unchanged. `Tooltip.cpp` therefore leaves the Core5Compat inventory.

The embedded web server's SSI include scanner now uses `QRegularExpression`.
Its two capture groups still distinguish `file` from `virtual` directives and
extract the include path, while matching still begins at the prior search
offset and advances by the original directive length after replacement. File
resolution, missing-file handling, and inserted content are unchanged.
`HTTPManager.cpp` therefore leaves the Core5Compat inventory.

`ArchiveDownloadInterface.cpp` no longer includes the removed `QTextCodec`
header. The translation unit never used that API: archive entry validation,
QuaZip extraction, temporary-directory checks, and emitted results are
unchanged. Removing the dead include therefore removes an unnecessary
Core5Compat compile dependency without changing archive decoding behavior.

The automatic asset-upload path now removes a ZIP suffix with
`QRegularExpression`. The expression remains case-sensitive, consumes `.zip`
and everything following it through the end of the final path component, and
is still applied before the `model_repo` subpath is appended. Asset mappings,
upload permissions, and entity creation are otherwise unchanged.
`Application_Assets.cpp` therefore leaves the Core5Compat inventory.

Bookmark names are now normalized with `QRegularExpression`. Leading and
trailing whitespace is still trimmed first, then every run of CR/LF pairs,
individual CR/LF characters, tabs, vertical tabs, or spaces is replaced by one
space. Empty-name rejection and bookmark persistence are unchanged.
`LocationBookmarks.cpp` therefore leaves the Core5Compat inventory.

Snapshot filenames now normalize the account username with
`QRegularExpression`. The same negated ASCII allowlist is applied globally:
letters, digits, and underscore remain valid, while every other character is
replaced by `-`. Snapshot metadata, timestamps, image formats, paths, and
upload behavior are unchanged. `Snapshot.cpp` therefore leaves the
Core5Compat inventory.

The update dialog now removes leading release-note newlines with
`QRegularExpression`. The expression remains anchored at the beginning and
matches only one or more LF characters; embedded line breaks, HTML break
removal, version ordering, and release-note concatenation are unchanged.
`UpdateDialog.cpp` therefore leaves the Core5Compat inventory.

The desktop model chooser now checks `QFileInfo::completeSuffix()` with
`QRegularExpression`. Its existing substring alternatives (`fst`, `fbx`,
`FST`, and `FBX`) and the preceding `isFile()` gate are unchanged, as are the
selected model, button label, and remembered browse location.
`ModelSelector.cpp` therefore leaves the Core5Compat inventory.

The default-script XML model now filters keys with an explicitly anchored
`QRegularExpression`. This preserves the former `exactMatch` behavior for the
`.*\\.js` pattern: only complete keys ending in lowercase `.js` create script
nodes. XML traversal, path derivation, URL normalization, and tree rebuilding
are unchanged. `ScriptsModel.cpp` therefore leaves the Core5Compat inventory.

The shared `simpleWordWrap` helper now splits whitespace runs with
`QRegularExpression`. `Qt::KeepEmptyParts` is explicit to retain the legacy
split default, while the same `\\s+` expression, line-length calculation, and
output assembly remain unchanged. Its UI license and warning-message callers
therefore receive the same wrapping behavior. `StringHelpers.cpp` leaves the
Core5Compat inventory.

Command-line configuration keys are now scanned with an explicitly anchored
`QRegularExpression`. Whole arguments must still consist of one or two leading
dashes followed by the same word-or-dash key characters; map keys still come
from capture group two. Initial lookup, next-key boundaries, `--config`
skipping, switch values, and multi-token value joining are unchanged.
`HifiConfigVariantMap.cpp` therefore leaves the Core5Compat inventory.

`AnimExpression.cpp` no longer includes the removed `QRegExp` header. The
animation expression implementation never used regular expressions: its
tokenizer remains character-driven, and parsing plus opcode evaluation are
unchanged. This removes an unnecessary Core5Compat compile dependency without
altering animation graph expressions.

The public `LogHandler.h` header no longer includes `QRegExp`, which was not
used by any declaration or inline macro in that interface. Logging option
parsing, the Qt message-handler entry point, repeated-message aggregation, and
break-on-message support remain unchanged. Consumers no longer inherit an
unnecessary Core5Compat header dependency.

Rolled log filenames are now recognized with an explicitly anchored
`QRegularExpression`. The timestamp wildcard, optional UUID session suffix,
`.txt` suffix, and former whole-filename `exactMatch` boundary are preserved.
Directory size accounting, oldest-file deletion, rolling thresholds, and log
output are unchanged. `FileLogger.cpp` therefore leaves the Core5Compat
inventory.

The entity-script URL validator now parses both allowlist sources with
`QRegularExpression`. The environment value still splits on whitespace-padded
commas; the settings value still splits on runs of commas, CR, or LF with
surrounding whitespace. Both retain `Qt::SkipEmptyParts`, and URL validation,
the built-in empty entry, settings retrieval, and validator installation are
unchanged. `Application_Graphics.cpp` therefore leaves the Core5Compat
inventory.

The desktop log dialog's bold timestamp/source highlighter now scans with
`QRegularExpression`. Every formatted range still starts at the match, uses
the full match length, and resumes immediately after that range. The existing
greedy `BOLD_PATTERN`, keyword highlighting, colors, and search navigation are
unchanged. `BaseLogDialog.cpp` therefore leaves the Core5Compat inventory.

The model browser's XML key filter now uses an explicitly anchored
`QRegularExpression`. The configured `_nameFilter` still has to match the
entire key before a row is added, preserving the former `exactMatch` boundary.
XML pagination, truncation handling, locking, model rows, and download URLs
are unchanged. `ModelsBrowser.cpp` therefore leaves the Core5Compat inventory.

The JavaScript console's completion parser now captures module and property
suffixes with `QRegularExpression`. The same four-group expression remains
anchored at the cursor-side end of the input; module and property values still
come from capture groups three and four. Completer model switching, prefixes,
popup behavior, and keyboard handling are unchanged. `JSConsole.cpp`
therefore leaves the Core5Compat inventory.

`ApplicationVersion` now extracts semantic versions with
`QRegularExpression`. The expression remains an unanchored search with major,
minor, and optional patch capture groups, so surrounding version text and the
implicit zero patch retain their prior behavior. Numeric-build fallback and
all equality/order comparisons are unchanged. `ApplicationVersion.cpp`
therefore leaves the Core5Compat inventory.

CommonJS module evaluation now derives `__dirname` with
`QRegularExpression`. The same `/[^/]*$` suffix is removed from `modulePath`,
so the final slash-delimited filename component and only that component is
dropped before the read-only closure property is installed. Source evaluation,
`__filename`, and module resolution are unchanged.

Both entity-script allowlist checks in `ScriptManager` now also split their
environment and settings sources with `QRegularExpression`. Each environment
value retains whitespace-padded comma splitting; each settings value retains
comma/CR/LF runs with surrounding whitespace. All four calls keep
`Qt::SkipEmptyParts`, and allowlist toggles, domain bypass, safe built-in
schemes, and URL decisions are unchanged. `ScriptManager.cpp` therefore leaves
the Core5Compat inventory.

The Windows GPU adapter scorer now splits uppercased vendor and renderer text
with a `QRegularExpression` using the same `\\W` pattern. It still removes
empty and duplicate words before counting adapter-name matches, so adapter
selection and driver reporting are unchanged. `GPUIdent.cpp` therefore leaves
the shared Core5Compat inventory; the platform-specific branch remains
unreachable on iOS.

The script editor highlighter's complete eight-expression set now uses
`QRegularExpression`. Keyword, quote, number, boolean, single-line comment,
and multi-line comment scans retain their prior match starts, full match
lengths, and resume offsets. Multi-line block state, quoted `//` rejection,
and the preceding-alpha guard for numbers are unchanged. With
`ScriptHighlighting.cpp` and `.h` migrated, the audited `QRegExp`/`QTextCodec`
Core5Compat source inventory is empty.

The optional `nitpick` tool now discovers Widgets, compiles its binary resource
bundle, and wraps Designer UI files through the central Qt compatibility
functions. Those functions dispatch to Qt 6 for the iOS/full-client graph and
to the original Qt 5 commands on existing desktop builds. Resource paths,
no-compression options, generated headers, and target dependencies are
unchanged; `tools/nitpick/CMakeLists.txt` leaves the Qt-5-CMake debt inventory.

Windows Qt deployment now resolves the imported Core target through
`overte_get_qt_target`. The central helper selects `Qt6::Core` or `Qt5::Core`
from `OVERTE_QT_MAJOR` and fails closed if that target is unavailable. The
existing target `LOCATION` lookup, `windeployqt` discovery and options, DLL
fixup, and audio-plugin cleanup are unchanged, so desktop Qt 5 behavior is
preserved while the macro no longer hard-codes a Qt major version.

Custom Linguist translation generation now compiles its temporary TS files
through `overte_qt_add_translation`. The central wrapper selects
`qt_add_translation` for Qt 6 and the original `qt5_add_translation` for
desktop Qt 5, then propagates the generated QM list to its caller. Lupdate
inputs/options, temporary-file copying, output locations, dependencies, and
the custom macro's existing parent-scope result remain unchanged.

Linux AppImage packaging now discovers Core and resolves the imported `qmake`
executable through the central Qt compatibility helpers. Qt 6 therefore uses
its selected package/target, while desktop Qt 5 still resolves `Qt5::qmake`.
The executable `LOCATION`, `CPACK_QMAKE_EXECUTABLE` handoff, fail-closed
availability check, linuxdeploy integration, and packaging flags are
unchanged. `GenerateInstallers.cmake` no longer hard-codes Qt 5.

The disabled Interface translation recipe is now Qt-major-neutral: its
commented discovery example uses `overte_find_qt`, and the custom wrapper is
named `OVERTE_CREATE_TRANSLATION_CUSTOM`. The recipe remains disabled, so
neither iOS nor desktop builds gain translation-generation work. If it is
re-enabled later, its QM/TS inputs route through the central translation
dispatcher instead of a direct Qt 5 command. `interface/CMakeLists.txt` leaves
the Qt-5-CMake debt inventory without changing generated targets.

## Model and texture upload audit

The model-buffer conversion at the graphics/GPU boundary now tests QVariant
maps with `QVariant::metaType().id()` on Qt 6. The legacy `QVariant::type()`
branch remains for desktop Qt 5 builds. Both branches compare the same
`QMetaType::QVariantMap` identity, so map-versus-list selection and every
component copied into the GPU buffer are unchanged.

The surrounding production path was audited from model and texture resource
requests through `ModelCache`, image/OpenEXR decoding, KTX descriptors, and
`gpu::Texture`. No ResourceManager URL, downloaded byte, image format, KTX
layout, sampler, texture element, mip level, or GPU payload was changed. The
port only removes a Qt 6 strict-mode compile dependency on the retired QVariant
type-enum API.

## Entity renderer to GPU audit

Compound model traversal in `RenderableModelEntityItem` now uses nested C++
range loops instead of Qt's legacy `foreach` macro. This path is reachable from
the model renderer created by `EntityRenderer::addToScene`, and Qt 6 strict
mode may define `QT_NO_FOREACH`. Both loops retain const references and iterate
the same `collisionGeometry.meshes` and `mesh.parts` order.

No mesh or part is inserted, removed, or reordered during traversal. Triangle
indices, unique convex-hull points, shape selection, render item allocation,
payload proxy, status getters, scene transaction, model resource, material,
and GPU buffer contents are therefore unchanged.

## iPad input and lifecycle audit

The production `TouchscreenVirtualPadDevice` now has an explicit Qt-version
boundary. Qt 6/iPadOS enumerates `QInputDevice` touchscreen devices, consumes
`QTouchEvent::points()`, and reads `QEventPoint::position()`. Desktop and
Android Qt 5 retain `QTouchDevice`, `QTouchEvent::TouchPoint`, `touchPoints()`,
and `pos()`. Both paths feed the same touch IDs and logical-pixel coordinates
into the existing move/view/button state machine and `UserInputMapper` axes.

The audit also followed those axes into avatar movement/view updates. No axis
scaling, pinch, button, haptic, avatar, or camera behavior was changed. This is
the full-client input plugin, not the bootstrap Metal touch demonstration.

## Productive iOS application lifecycle audit

The existing full-client mobile pause/resume boundary is now compiled for iOS
as well as Android. On the first Qt `ApplicationHidden` or
`ApplicationSuspended` transition after startup, it disables DomainServer
check-ins, resets the stale connection and octree state, stops audio, and
deactivates the active display plugin. A later `ApplicationActive` transition
starts audio, reactivates that plugin (which recreates its platform surface as
needed), and enables check-ins so the normal DomainHandler reconnect path can
run. `ApplicationInactive` deliberately remains only a refresh-rate change:
short-lived iOS interruptions and system overlays must not tear down the domain.

The transition is edge-triggered through `_isForeground`, so Qt's consecutive
hidden/suspended notifications cannot reset the network twice. Startup and
shutdown guards prevent lifecycle callbacks from touching partially constructed
or destructing dependencies. The display deactivation also tolerates the state
before any plugin has been selected. No packet, DomainHandler handshake,
entity-tree mutation, renderer payload, or bootstrap lifecycle mock was changed.

## Audio migration rule

Qt 6 replaced the legacy QAudioDeviceInfo/QAudioInput/QAudioOutput and sample
format APIs. The migration must be implemented behind the audio-client device
boundary and verified against the existing 48 kHz signed-16-bit network format.
Platform-native AVAudioSession policy remains in the iOS shell and must not be
duplicated by desktop code.

The audio gate requires device enumeration, route change, microphone consent,
interruption recovery, Bluetooth behavior, mono input, stereo output, and
resampling tests on physical hardware.

## Enforcement

The iOS build is not allowed to restore Qt WebEngine, QDesktopWidget, QGLWidget,
or a desktop Qt installation to work around a migration error. A temporary
compatibility use must be centralized, documented here, and covered by a host
contract.
