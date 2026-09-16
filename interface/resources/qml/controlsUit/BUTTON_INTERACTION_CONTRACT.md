# SH-003 shared Button activation/focus v001

The actual controlsUit/Button.qml retains ordinary Qt Quick Controls click and
Space-key activation, plus the existing Android `androidClickAction` callback.
A canceled press is no longer converted into `clicked` on Android: pointer
departure, hide/disable and lost grab must not activate an action. Controller
pointer drift may therefore cancel a selection; any future usability repair
must operate on native pointer stability, not synthesize consent from cancel.

Visible/enabled controls use StrongFocus (including Tab); hidden/disabled ones
use NoFocus and clear focus. Shared click side effects require visible/enabled
state, and the Android callback must actually be a function. The two raw
label-bearing console messages are removed. Existing derived onClicked handlers
are not treated as overrideable or as a security boundary; trusted code can
still explicitly emit a signal. No category, controller/HMD capability or
native entry route is removed by this delta.

`test_ui_button.py` loads the COMPLETE production Button and original styles/
TouchUiMetrics through real Qt6 Quick Controls with offscreen software rendering.
Real QTest mouse/keyboard input and QSignalSpy cover click, out-of-bounds cancel,
Space, hide/disable during press, ancestor hiding, focus restoration, invalid
callback type and raw-log label canary absence. Only `Qt.platform.os` is
substituted with android/linux/ios fixture identity; Tablet sound/action/enum
receivers are test-only. This is not native Android/iOS/controller execution.

Baseline6026087a79 RED: Android canceled→clicked assertion failed; Linux/iOS
hidden-focus policy failed. Core dumps disabled. Fixed three OS cases PASS;
fixture QObject ownership is explicitly C++ to avoid engine-deleting its stack
receiver. Tests must preserve this distinction from production ownership.

Consumers: all existing Shared controlsUit Button users on Phone/Pico/iOS and
desktop, including Tablet/custom settings. No new native hook or additional
contract prerequisite for the isolated delta. The existing original styles and
TouchUiMetrics component dependencies remain required.

Pending: other controls, custom ControllerSettings/graphics labels/order and
keyboard behavior, native controller/touch/assistive technology review, Qt5 and
whole-platform builds, original SH-003/device acceptance. Not full UI parity.
