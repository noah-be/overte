# SH-003 deterministic profile slice v001

Functional selector contract, not UI acceptance. Header `CapabilityProfile.h`
provides Product, Support, resolveProduct, profileSelectors and controlSupport.
It uses only C++14 and is callable from native owners without Qt. The actual
Shared caller is `libraries/shared/src/shared/FileUtils.cpp`; the backlog's
historic `interface/src/FileUtils.cpp` path is the same file's old location
(still named in its header). No platform-owned path is changed.

Pinned stacks, highest-priority extras first:

- Phone: android_phoneInterface, android_interface; append gles only for GLES32.
- Pico: android_picoInterface, android_questInterface; append gles only for GLES32.
- iOS: ios, mobile, touch, android_phoneInterface, android_interface, webview;
  append gles only for GLES32. No webengine selector.

iOS aliases explicitly reuse presentation from the existing apple-ios stack;
they never determine native identity, permissions, orientation or WebEngine
support. iOS overrides precede the aliases. A mixed Android+iOS define stack is
Unknown and does not receive either mobile profile. Existing other Android
products retain their previous selector behavior but receive no new profile
capability grant. Desktop behavior remains unchanged.

Control IDs reuse Tablet Contract v1 in tests/device/tablet-ui-contract.json.
Unknown controls are Hidden. Supported is the required product behavior, not an
observation or a hardware PASS. Tolerated graphics must remain non-essential;
Phone/iOS controller/HMD controls are Hidden. Native owners consume this policy
for their controls; subsequent Shared QML work must enforce it on retained
surfaces and validate focus/geometry. A hidden control must not remain focusable
or writable through another visible entry. This slice does not assert that all
existing QML already satisfies that requirement.

The test profile-test.cpp compiles the actual resolver and checks all three
stacks, mixed/unknown stacks, forbidden WebEngine on mobile, known/unknown
controls and VR hiding. Full QFileSelector resource-resolution snapshots,
Shared QML control binding, geometry/focus negatives and visual/touch validation
remain pending. iPhone/iPad orientation/window policy is not invented here;
native owners preserve existing modes and record product decisions separately.
SH-002 artifact acceptance remains pending. No admission JSON is created.
