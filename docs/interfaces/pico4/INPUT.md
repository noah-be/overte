# Pico native text entry — revision 09

PI-003/PI-007 implementation, not worn-headset keyboard acceptance.
Qt PicoWebViewItem now accepts standard committed/preedit IME text and key
events, grants active focus on pointer press and sends UTF-16 through its
existing private JNI bridge. Android edits only the single current active,
focused WebView while the Activity has window focus. Navigation, destruction,
another editor and window focus loss relinquish that ownership and finish native
composition. No text is interpolated into JavaScript, normalized, copied to a
clipboard or logged. Valid combining characters, RTL text, surrogate pairs and
emoji sequences are preserved exactly; malformed UTF-16, prohibited control
characters and edits above 4096 UTF-16 units fail closed.

Backspace/delete remove a selected range or a whole Unicode code point, not half
a surrogate pair. Enter, Tab and basic cursor keys use Android editor key
semantics. Escape finishes composition and releases Qt focus; this is not a
transactional rollback of already committed text. Nonlocal IME replacement
offsets are rejected until DOM/Qt cursor synchronization is available. Clipboard,
undo/redo, surrounding-text queries, precise DOM caret geometry and every IME
variant are not claimed complete. The generic item rectangle is the current
IME anchor; text itself is marked sensitive/nonpredictive at the Qt boundary.

Focused tests execute production Android editor operations with a test-only
InputConnection and compile actual Java callers against API 26/36. Qt callback
wiring is source-checked; full Qt/JNI build and real offscreen WebView/IME
execution remain pending. Shared Tablet keyboard spawning, semantic focus
order, labels, world-space legibility and the physical controller path retain
their original acceptance gates. Experimental hands do not replace controllers.

API references: [Android InputConnection](https://developer.android.com/reference/android/view/inputmethod/InputConnection)
and [Qt 5 QQuickItem](https://doc.qt.io/qt-5/qquickitem.html).

Check: `python3 android/vr/pico/tests/device/test_text_input.py`.

## Queued input ownership

PI-005/PI-007: all five Android WebView input entries (pointer, editor focus,
text, key and scroll) capture a Pico-local weak Activity/generation ticket
before enqueueing. The Android main-thread callback rechecks the ticket, active
instance, current Activity, window focus and actual WebView context. Initial
state, pause, focus loss and current-owner destruction deny new input and
invalidate older queued input; rapid resume cannot revive it. Resume grants
only with window focus; focus gain grants only while resumed. Activity
replacement changes ownership, and obsolete Activity callbacks cannot veto the
new owner. Generation exhaustion remains permanently closed.

Cleanup runs outside the gate monitor, with existing isolated Android cleanup
steps; a failed cleanup does not re-enable the gate or skip later Activity
teardown steps. Navigation, rendering and resource operations retain their
separate paths. This is not a Shared network or consent gate and does not
introduce an allow route.

Queued input also captures the concrete WebView instance present at admission,
using a weak reference. The registry supports cross-thread admission reads with
ConcurrentHashMap; creation/removal and all View effects remain on Android main.
Dispatch rejects an absent or replaced instance even when the native handle,
Activity and foreground generation are unchanged. An absent admission target
cannot become valid merely because a view is created before dispatch. Fresh
input for the successor remains accepted. Pending commands do not strongly retain
the old View/Activity. Navigation/render/resource command semantics are unchanged.

This guards admission-to-dispatch replacement, not an obsolete native command
first arriving after a handle has already been reused, native creation/frame
callbacks, or the entire native-pointer lifetime protocol.

`test_web_input_queue.py` executes the original five production entries and
gate with a test-only Android scheduler/view boundary (RED before wiring, PASS
after). `test_activity_teardown.py` executes original resume/pause/focus/destroy
bodies and the original foreground publisher/gate with Android effect
boundaries, including cleanup faults. Full SDK Java compilation and affected
input/cleanup/JNI tests pass; physical event ordering, IME and controller
acceptance remain pending.

Same-Activity instance replacement was independently reproduced RED against the
original five input entries before adding the instance check, then PASS after.
The test uses the actual concurrent registry declaration and a worker-thread
producer, with an explicit Android queue/view boundary. It also verifies fresh
successor input and absent-at-admission denial. This is host evidence, not actual
Chromium/JNI/Qt scheduling or a physical-controller test.

## Shared Button cancellation and focus

sh003-button-interaction/v001 source 81a136e122252015b531b9d42ccd3b9cb82305e8,
manifest bdfbbce4396d8595ae8f154843a9f4271e92de154f0d6df9b61be90079a23402,
is consumed unchanged. All five release files match, as do the complete original
stylesUit tree and TouchUiMetrics/TouchUiProfile against the pinned source.
Pico's existing Tablet service and TabletGeneralPreferences dialog use original
controlsUit Button for Save/Cancel; no Pico QML fork or native hook is added.

Canceled presses no longer synthesize Android clicks. Real click and Space
activation remain; hidden/disabled buttons lose focus and use NoFocus, returning
to StrongFocus when usable. Shared click/hover effects require visible/enabled
state and androidClickAction must be a function. Base label-bearing logs are
removed. Trusted explicit signals/derived handlers are not a security boundary.

Complete original Button/styles/metrics pass real Qt6 Quick Controls mouse/key
tests (1 method, three android/linux/ios OS fixtures, 4.452s). Only OS identity
and Tablet action/sound/enum receivers are substitutes; fixture receiver uses
explicit C++ ownership. This is not Android/Qt5/headset execution. No baseline
crash was rerun; core dumps disabled. Pico source checks pin the real dialog's
component use, not actual derived action dispatch or whole Tablet execution.

The subsequent Tablet preference action contract below resolves the concrete
Save/Cancel normal-event dispatch and category-log request while retaining each
platform's existing routes. Custom controller/graphics labels/order/keyboard
behavior and other controls still need their respective implementation/evidence.
Native pointer drift may now cancel a press correctly; controller usability
requires pointer stability work and physical review, not cancel-to-click revival.
Assistive technology, Qt5/platform builds and original SH003/PI007 gates remain.

sh003-toggle-interaction/v001 source 718190b0df0c05df50183c56e01229561b469208,
manifest 6fe43574a870b0c5c61cc6d7f743edddf2f873df9968bdeeff08cf416fd265f9,
extends the preceding Button prerequisite unchanged. Original CheckBox and
RadioButton now clear hidden/disabled focus and use StrongFocus only while
usable; shared sound effects check visibility/enabled state. CheckBox constructs
its own original HifiConstants instead of relying on an outer undeclared ID.
Native Qt checked-state/radio-selection logic and category policy are unchanged.

All five imported files match. The original real Qt harness now runs all three
complete controls across nine control/OS fixtures (1 method, PASS5.085s), adding
actual Tab traversal, checkbox state and sibling radio exclusivity. OS identity
and Tablet receivers remain test boundaries; no native hook or platform policy
is added. Pico source checks identify original ControllerSettings checkbox and
CheckBoxPreference/PrimaryHandPreference component use, not full derived effects.
Existing registry/Preference-base tests were not rerun: those do not execute
these changed controls and would not strengthen this evidence.

Switch/other controls, full derived preference effects and persistence, custom
settings/keyboard semantics, native controller/touch/accessibility review and
Qt5/whole-platform/original SH003 acceptance remain pending.

## Native WebView identity lifetime

PI005/PI007 native items now use a mutex-allocated positive 64-bit identity,
not their memory address. IDs are never reused during the loaded module's
lifetime; zero permanently denies creation after counter exhaustion. All 16
outbound JNI command handle assignments and frame image URLs use the same ID.
Java's opaque long-handle interface and current-instance input gate are unchanged.
Removing the registry entry precedes native destruction, so late creation/frame
callbacks and old image URLs cannot resolve a successor at the same address.
Already-queued creation callbacks retain the original Qt context/QPointer.

Destruction now requests Java cleanup for an acknowledged OR still-pending
creation. This preserves same-thread create/destroy queue ordering; the cleanup
request is best effort, not a completion receipt or a hard OS cleanup deadline.

The native lifetime regression independently reproduced stale callbacks reaching
a replacement and missing pending-creation cleanup before the fix (two RED
cases). The test executes original constructor/destructor, registry, image
provider/frame copy/URL and both native callbacks with real Qt locks, QPointer,
queued event delivery and image storage. Same-address placement reconstruction,
late and already-queued callbacks, fresh successor frames/images, pending cleanup
and permanent exhaustion pass after the fix. QuickItem input setup, Java buffer
access/outbound effects and creation-result receiver are explicit substitutes.
Source checks bind all command identities and the exhausted-creation guard.

This closes per-item native address reuse; it does not prove per-retry creation
ordering inside one live item, physical JNI/Chromium/Qt5 behavior, delivery of a
failed cleanup request, module unload/reload with live Java state, or the whole
Android lifecycle. Full native/platform build and headset acceptance remain.

## Tablet Save/Cancel action dispatch

sh003-tablet-preferences-actions/v001 source 1fe5a1feff84787b1237bcaf840284a82386e5c2,
manifest 4819833cf98612da851f6e22e23023ba2462e2dfb5c65ab9edf3c6319e9b6316,
is consumed unchanged on the existing Button prerequisite. All four release
files match. No Pico native hook or cloned preference route is introduced.

Android normal activation uses only the base Button's androidClickAction;
derived onClicked performs Save/Restore only on non-Android platforms. Both raw
category logs are removed. Android Cancel restores once, lowers the keyboard
and returns home. Other platforms retain their previous-app/script/HMD-stack/
home behavior. Save retains existing routing and edit-focus commit. Routes are
preserved, not silently unified. Pointer cancellation performs no action.

The release executes both complete original derived Button blocks and all four
complete action functions over original Shared Button/styles/metrics with real
Qt6 pointer input. Its 36 OS/HMD/back-route/action cases check exactly one normal
save/restore/navigation, cancellation and a positively probed raw QML log sink.
OS identity, layout/sections/persistence and Tablet/HMD/navigation receivers are
test boundaries; full dialog construction is not executed. General reproduced
Android Cancel restoring twice on the prior Qt6 baseline; this is not proof of
that behavior on native Qt5. No historical baseline was rerun in Pico.

This resolves the concrete source request, not persistence transactions,
idempotency under arbitrary repeated programmatic calls, callback reentry or
native Qt5/Android/HMD route observation. Whole dialog/real preference storage,
custom settings geometry/keyboard and all original SH003/PI007 gates remain.

## Shared Switch label actions and audio caller

sh003-switch-interaction/v001 source a2992b7807c8ffcbfb39a8f99e37c70fd052d71b,
manifest 7624d1896b30258079b7860aba25514424b2b4c43d187ab9946abe3ed034980c,
is consumed unchanged. All four release files match; original Audio.qml also
matches the pinned General commit. The focused extraction-helper prerequisite
is the already-consumed Tablet preference actions v001; no new native hook.

ON/OFF label clicks now pass through one visible/enabled user-choice function:
focus the actual control, set checked and emit its existing clicked signal once.
This reaches original onClicked consumers, including Audio.qml's muteMic.
Native click/Space and checked-change behavior remain; programmatic checked
assignment does not become a user click. Hidden/disabled inner controls clear
focus, usable ones have StrongFocus. Accessible.name uses the existing ON/OFF
label, and original constants provide nonzero default height without overriding
explicit caller sizing or touch scale.

Complete original Switch and original muteMic component pass real Qt6 Quick
pointer/Space/Tab tests (desktop/HMD modes, 1 method, 3.324s). Tests verify the
selected Audio property, label cancel, hidden direct-helper denial, focus,
attached accessible name and implicit height. AudioScriptingInterface storage
is a QQmlPropertyMap boundary, with fixture layout/bar selection; actual audio
engine/hardware and native assistive-technology delivery are not executed.

Pico source wiring retains its real AudioScriptingInterface dependency, original
Shared QML context publication, settings.audio route and muteMic desktop/HMD
property writes. Other Switch consumers' persistence/bindings, full custom
settings/keyboard semantics, native Qt5/platform build and original SH003/SH006
and PI005/PI007 acceptance remain pending.

## Tablet action dispatch capability v002 (Main/Pico)

sh003-tablet-preferences-actions/v002 source 8148b8258fd0ca522b3402ba5c8d3649d6a29df4,
manifest 7438aed838bd1d294d2b0bced4721fdc3de5d9d38a3da4a4f7d76f537bec4c64,
is consumed unchanged with all seven mutually required source/test/doc files.
Main/Pico v001, Button v001 and toggle v001 are the existing prerequisites.

Button exposes readonly usesAndroidClickAction for its existing dispatch choice;
both derived preference handlers use its inverse rather than duplicating an OS
test. Main/Pico remains Android-only. Neither Apple's Android-or-iOS selector
nor Phone's nav.back/settings.back routes are imported. Existing Pico normal
Save/Cancel behavior, including Android Cancel-to-home, remains unchanged.

Both original focused tests run explicitly with OVERTE_UI_VARIANT=main:
36 derived action/route cases PASS4.152s and nine control/OS cases PASS4.683s.
Expected platform callback truth tables are asserted independently of the QML
implementation. Pico source caller pin passes and enforces the original selector.
Other variants require their own immutable exports and are not Pico evidence.

Complete original blocks/actions/controls and test boundaries are as described
above; this source migration does not execute real persistence, whole dialog,
native Qt5/assistive input/HMD navigation or original integration/SH003 gates.

## WebView creation recovery on a changed URL

The existing +android_picoInterface/Web3DSurface.qml binds root.url to the
registered PicoWebView url property and native setUrl. After creation failures
exhausted the original retry budget, that setter previously stored a changed
URL but returned without creating a view. No new geometry event meant no
recovery. Original-method host regression reproduced this at the exhausted
failure state; a separate scheduled-retry case also failed immediate recovery.

A changed URL on an uncreated item now resets the existing retry count and calls
the existing createWebView. Original component/geometry/handle and pending guards
still apply. An unchanged URL does not reset the budget. A currently pending
creation is not duplicated; its result applies the current URL or retries with
it. An old scheduled retry cannot recreate a successfully created item. No new
Java/JNI API, URL scheme, timer loop or Shared source change is introduced.

Five cases execute complete original setUrl/createWebView/scheduleCreationRetry/
acceptCreationResult methods with real Qt timers. JNI allocation/Java command
effects and QuickItem completion/geometry/signals are explicit test boundaries;
the original Java URL policy and full Java caller are checked separately.
This does not prove per-attempt callback ordering, actual Android provider/
Activity recovery, Qt5 whole native compilation or physical navigation/IME.
Those remain deferred; native per-item identity and input generation fences
are unchanged. No persistent failure is relabeled as a successful WebView.
