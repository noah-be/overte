# SH-003 CheckBox/RadioButton focus and activation v001

Actual Shared CheckBox and RadioButton now use StrongFocus only while visible
and enabled; hiding/disabling clears focus and selects NoFocus. Sound handlers
do not act for hidden/disabled controls. CheckBox constructs its own original
HifiConstants instead of relying on an undeclared outer `hifi` identifier.
Native Qt toggle/radio-selection logic and category/capability policy remain
unchanged. No platform hook, synthetic activation or new retained route.

Requires sh003-button-interaction/v001 source
81a136e122252015b531b9d42ccd3b9cb82305e8, manifest
bdfbbce4396d8595ae8f154843a9f4271e92de154f0d6df9b61be90079a23402,
because this release extends its actual Qt test harness. Import both changed
test files; the original Button delta remains unchanged.

`test_ui_button.py` loads all three complete production controls, original
styles and metrics through real Qt6 Quick Controls. Nine control/OS-fixture
cases pass. Real mouse cancel/hide/disable, Space, actual Tab traversal,
ancestor hide, checked state and sibling radio exclusivity are verified.
Only OS identity and Tablet receivers are substituted; raw label-canary capture
has no sanitizer. The two added controls have no platform-specific behavior.

Pending: Switch/other controls, custom ControllerSettings/graphics and keyboard
geometry, native controller/touch/accessibility review, Qt5/whole-platform builds
and original SH-003 acceptance. These host cases are not device acceptance.
