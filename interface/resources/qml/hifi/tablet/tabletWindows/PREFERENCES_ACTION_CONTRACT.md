# SH-003 Tablet Preferences Save/Cancel dispatch v002

v002 adds one readonly Button dispatch capability, `usesAndroidClickAction`.
The base and both derived handlers read this same value; do not duplicate an OS
test in the dialog. Main/Pico and Phone retain Android-only callback selection;
Apple retains Android-or-iOS. This does not globally enable the iOS callback on
other source variants or remove Apple's existing callback for other consumers.

Three explicitly selected test variants (`OVERTE_UI_VARIANT=main|phone|apple`)
assert the intended dispatch truth table independently of the implementation.
Main is the default. Tests require all four updated Python/C++ test files and
existing Button/toggle fixtures. Phone/Apple import their separately pinned
General-produced compatible source release, not the main patch over differing
production files. Preserve Phone's `nav.back` selector and Android
`settings.back` message; preserve Apple's existing callback Cancel-to-home
including keyboard lowering on Android/iOS. Other noncallback routes are intact.
The base callback is the intended route on Apple's affected mobile builds;
the accidental second derived restore/navigation is removed, not redefined.

v001 below described only the main/Pico source variant. It is not suitable as
an unchanged Phone migration or a passing Apple implementation. Both owners
reported those exact integration differences; v002 resolves dispatch selection.
No native Qt5, persistence, full dialog or whole-UI acceptance is implied.

## Historical v001 main/Pico behavior

The actual TabletPreferencesDialog buttons now select one existing handler path
per normal activation. Android uses the Shared Button's androidClickAction;
derived onClicked acts only on other platforms. This removes a second restore/
navigation on Android without assuming that derived handlers replace the base.
Raw Save/Cancel category console messages are removed.

Routes are deliberately preserved, not silently unified across platforms:
Android Cancel restores once, lowers its keyboard and goes to Tablet home.
Non-Android Cancel restores once and follows existing previous-app/script/HMD
stack/home rules. Save retains its existing all-platform routing and edit-focus
commit behavior. A canceled pointer press performs neither action. This is
normal-event exact-once dispatch, not transaction/idempotency protection against
arbitrary repeated programmatic calls or persistence callback reentry.

Requires sh003-button-interaction/v001 source
81a136e122252015b531b9d42ccd3b9cb82305e8, manifest
bdfbbce4396d8595ae8f154843a9f4271e92de154f0d6df9b61be90079a23402.
No new native hook or platform-owned source change. The toggle release is
compatible but not a prerequisite for these two derived Button users.

`test_tablet_preferences_actions.py` executes both COMPLETE original derived
Button blocks and all four COMPLETE original action functions over the actual
Shared Button, styles and metrics in real Qt6 Quick Controls. OS identity is
the only production-code substitution; layout/sections/persistence, Tablet/HMD
and navigation receivers are explicit fixtures. Thirty-six OS/HMD/back-route/
action combinations pass, including real pointer cancellation and click.
Raw QML console capture is positively probed before checking canary absence.

Baseline718190b0df RED specifically reproduced Android Cancel restoring twice
under real Qt6 base/derived handler composition. No duplicate native Qt5 claim
is made. Fixed matrix PASS; host core dumps disabled. Native Qt5/Android/HMD
route observation, whole dialog construction/actual preference persistence,
custom settings layout/keyboard and original SH-003/device acceptance remain
pending. This release resolves Pico's concrete derived-handler source request,
not all retained settings or UI parity.
