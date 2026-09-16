# Shared query selection and editable input

Desktop and Tablet QueryDialog distinguish initial text from an initial numeric
selection index. Both bind editable state and return editText for editable lists,
currentText for fixed lists, and TextField text for ordinary input. The Tablet
completion path focuses the visible selection/text control. The resize helper's
maximum-width property spelling is consistent.

The shared ComboBox has a real TextInput content item. Qt's native ComboBox binding
updates editText; no signal newer than the declared QtQuick import is required.
Read-only presentation remains elided. Editable Space/Right/Return events are
passed to native handling; empty-list navigation avoids modulo-zero state. Popup
and showList are exposed for existing query callers.

Synchronous OffscreenUi::getItem now creates the complete selection configuration
before QML completion, matching the asynchronous path. Calls from another thread
are marshalled to the UI owner before creation and modal waiting. Existing
cancellation, accepted-empty and failed-creation behavior remains explicit.

Focused tests run the complete shared ComboBox with real Qt keyboard/popup events;
style/metrics/label/scrollbar dependencies are fixtures. Exact dialog binding,
result and completion expressions run in selection/text harnesses; window sizing,
HMD/keyboard and icon helpers are seams. Actual C++ getItem, modal listeners and
wait methods run with Qt signals and a worker-thread caller; creation is a seam.
Index-ignore and Space-swallow mutations fail. These tests do not establish full
native window/IME/accessibility, layout or all SH003
retained-control coverage. Original platform and39-node acceptance stays open.

The retained popup now takes focus and handles Up/Down/Return/Enter/Space and
Escape explicitly. Opening resets the highlighted index to the selected index;
external selection changes synchronize it. Navigation from no selection reaches
the last/first entry. Invalid explicit indices do not commit. Native delegate
activation, explicit selection and editable Return notify acceptance; closing
alone does not. Hidden/disabled controls close the popup without acceptance and
showList cannot reopen it. Mouse selection and keyboard selection are both
covered by actual Qt events, including exact signal counts. Escape, hide and
disable do not accept. The test scene is explicitly visible, as in a real caller;
a hidden TestCase cannot stand in for a visible interactive control.

These focused checks cover the tested local Qt6 paths. Arbitrary model roles,
IME composition, all focus transfers and native Qt5/platform behavior remain
unqualified. The exact former source and restored cancel-acceptance / previous
index mutations fail the expanded behavioral assertions.
