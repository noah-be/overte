# Full Client native keyboard geometry (IO-006)

SH-003 sh003-ios-native-ui/v001 transfers this implementation while preserving
the existing General-owned header, property ABI, QML semantics and orientations.
The actual Full Client singleton now uses KeyboardGeometry.h in UIKit points.
Only a full-width occlusion touching the window bottom reserves imeInsetBottom.
Floating/undocked overlap sets keyboardVisible independently. Unknown/invalid
frames clear old geometry; zero exposed inset does not mean a measured keyboard.

The passive non-accessible layout observer refreshes safe area and window bounds;
window identity, screen position and orientation changes invalidate old IME state.
Show/change end-frame notifications repopulate it. Hide, missing active windows
and suspension clear it. QPointer callbacks and observer teardown guard lifetime.
The existing E2E accessibility controls and ordinary passive overlay remain separate.

Coordinate conversion uses the window's screen coordinate space, as described by
[Apple's keyboard frame documentation](https://developer.apple.com/documentation/uikit/uiresponder/keyboardframeenduserinfokey).
No density multiplier or additional safe-area subtraction is applied to IME height.

Focused checks: ios/tests/keyboard-geometry-test.py executes the production C++
geometry helper and source-checks UIKit lifecycle wiring. Existing touch UI and
E2E identifier source checks pass; the former now checks the pinned SH-003
profileSelectors implementation rather than the superseded literal FileUtils code.
This is not native execution. Xcode/ARC/UIKit/Qt compilation, dock/float/hide and
rotation/Stage Manager/split-window transitions, first responder behavior,
hardware keyboard, focus and VoiceOver acceptance on iPad/iPhone remain pending.
