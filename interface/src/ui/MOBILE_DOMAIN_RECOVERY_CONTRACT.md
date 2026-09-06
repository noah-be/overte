# Mandatory selected Phone/iOS receiver follow-up

Domain-login-outcome/v001 changed generic LoggingInBody only. Its new typed
signal must also be consumed by the actual selected
LoginDialog/+android_phoneInterface/LinkAccountBody.qml on Phone and the retained
iOS mobile/touch alias. Those clients do not run the generic progress body.
Pair v001 with this mandatory follow-up before treating their presentation as
usable. Sealed v001 metadata/tests are not rewritten or claimed as selected-body
proof. Its generic/Pico behavior is unchanged.

The new selected handler clears waiting/requestSubmitted for its domain outcome,
including a reopened pending view that did not submit again. It displays typed
timeout or honest generic failure text, selects/focuses the existing password
control, and delegates cancellation to the existing guarded dismiss() routine.
Closed or non-domain views ignore the signal. Unknown reason data cannot become
user-visible text. Existing account/social completion/failure, submit/dismiss,
IME/navigation, UI controls and platform imports are unchanged.

The new focused test executes this COMPLETE original selected handler on real
Qt/QML Connections for submitted/reopened, timeout/failure/cancel, closed and
account cases. Field/focus/dismiss are explicit boundaries, not native UI or a
full component load. The preceding original constructor/manager/ticket tests
prove source-side outcome correlation separately. Full selected native loader,
IME/focus/dismiss, Qt5 and cross-view acceptance remain pending.

Prerequisites: matching Main/Apple domain-login-outcome/v001 and its full chain;
test helper test_login_dialog_domain_receiver.py from that release. Main and
Apple variants preserve their different imports (Apple omits QtQuick.Controls
1.4); import the narrow patch or the matching variant only. No node/artifact
acceptance, automatic retry or frozen build change.
