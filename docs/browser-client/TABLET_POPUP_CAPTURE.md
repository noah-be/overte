# Private Controls2 popup capture

The bounded capture change is integrated; its full native/browser profile
selection acceptance remains in progress. Earlier Graphics cohorts applied
nine slider/switch changes but displayed the old closed combobox after a genuine
arrow click. A fixed passive actual Qt observer now proves that the popup opens
and its overlay is inside the selected private GUI ancestor. The callback grab
fails because that C++-created `QQuickRootItem` has no QML engine. Its strict
painted-popup oracle remains unchanged.

## Exact native boundary

The pinned native release is2026.04.1. Its packaged
`usr/lib/libQt5QuickTemplates2.so.5` SHA256 is
`00f093dc7d5e871c3145f604905398443c4aa8525df86c6dd574dfb1f92c8935`.
The exported `QQuickOverlay::overlay(QQuickWindow*)` disassembly at0xcb840
calls `QQuickWindow::contentItem()`; at0xcb880 it constructs `QQuickOverlay`
with that content item as its parent. This is the actual shipped Qt5 binary,
not a Qt6 inference. Its Templates2 metadata exports the readonly attached
Overlay pointer (SHA256
`5a499e54fefde8d3a313be0c54e69eafd1a9892de8f37a659b8533c2a957004d`).

Pinned Overte `f91d15a` SharedObject.cpp443 parents its Desktop/root item under
that same contentItem; line151 publishes its own offscreenWindow context. The
pinned SettingComboBox.qml (SHA256
`53577ed3a638d7f4db36b27ad4775eedf897073f6fd9b3923799414aabce13cf`)
uses a Controls2 Popup/ListView. Consequently popup visuals may be siblings of
Desktop rather than descendants of tabletRoot. Existing `hasDialog()` checks
native shown windows inside Desktop and cannot include this layer.

## Narrow capture change

The helper imports the already installed QtQuick.Controls2.15 and reads its
own attached Overlay. Only a visible overlay with a visible nonzero-size,
nontransparent child switches capture to the common private offscreen UI
ancestor. Hidden/empty overlays keep tablet-only capture; ordinary dialogs keep
their existing Desktop scope. More than256 children or an overlay outside that
ancestor produce a clear error before GPU work. No native3D framebuffer or other
native window is read. Existing2048x2048 bounds, cancelled GPU ownership,
revision checks, thirty/eight-second deadlines and frame ACKs are unchanged.

The existing dialogs wire surface is reused, with the actual tabletRect mapped
into the selected content item. Subsequent genuine pointer events use that exact
captured target and its dimensions. No settings effect, popup open command,
keyboard simulation or new visitor protocol is introduced.

## Passive diagnostic

`tests/integration/tablet-popup-audit.mjs` exports
`instrumentTabletPopupAudit(qml)` for an owned copied test gateway only. It adds
one fixed passive callback at the normal capture boundary. Private log records
contain only capture sequence/revision, fixed scope labels, bounded class tags
and rectangles/visibility/opacity. They exclude widget text/names, URLs, source,
credentials and pointer addresses. There is no remote query/evaluation endpoint.
It emits only changed geometry, up to64 records; enumeration is bounded256
children and twelve returned rows. Do not add this test observer to production.

## Validation and next actual gate

31/31 CPU/source-VM contracts pass: six overlay capture/input/cancel cases,
two passive diagnostics, eight existing QML input cases and fifteen existing
native helper/readiness cases. The first combined validation lacked an unchanged
native-browser-graphics.js fixture; copying that unchanged source resolved the
fixture-only failure. These tests execute production functions with controlled
Qt/GPU boundary objects and are not actual Qt pixels.

Parent-owned genuine acceptance must restart the gateway, click the real
profile arrow, preserve failed and successful screenshots, and retain all four
painted popup rows plus exact highlighted-index checks before Enter. If the
popup remains absent, use the passive observer to distinguish an unopened popup
from an open but excluded layer. Keep the original effect/framebuffer/restore
assertions and actual worker cleanup. Do not claim the proposal explains every
prior capture failure.

The helper's existing private native-input extension now uses the public C++
`QQuickItem::grabToImage(QSize)` overload solely for its own window's
`contentItem()`. It refuses foreign windows, descendant items, invalid tokens,
dimensions above 2048 and a second pending allocation. Captured owner/root/window
use `QPointer`; a synchronous signal retains the result until the original
trusted QML callback saves it, with revision/navigation/cancellation guards.
It exposes no file-path or framebuffer API. Cancellation retains one outstanding
driver allocation until ready or helper teardown; a stalled driver cannot
accumulate captures.

`python3 browser-client/tools/build-native-input.py --test` passes using the
SHA-pinned Qt 5.15.3 SDK and the native worker's actual runtime. The isolated
engine-free root paints known RGB pixels; genuine grabs verify those pixels,
token/dimension/foreign-target refusal, concurrent/reentrant refusal, actual
result release, reparent revocation and receiver destruction. Existing native
text/selection/validator/undo/private-clipboard tests also pass. Eighteen updated
QML/PNG boundary cases pass. This genuine Qt fixture establishes the public
overload and lifetime; the running Overte worker popup/effect journey is separate.

## Actual native worker acceptance on2026-10-01

Both stock Chromium154 and Firefox156 now pass seventeen setting effects,
thirteen genuine painted-popup checks,100/80/60/Custom70% selection, browser
framebuffer dimensions and persistence after leave/rejoin. Start/end frontend,
gateway and pinned Settings source hashes match. Earlier popup and sandbox
refusal failures remain preserved. [Detailed proof](GRAPHICS_OWN_ROOT_VERIFICATION.md).
This does not establish complete native graphics parity or online fluidness.
