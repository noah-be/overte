# Shared domain login terminal receiver

The complete LoginDialog constructor now forwards DomainAccountManager's
loginComplete/loginFailed on every platform, including Android VR/Pico. Only
these two connections move outside the existing Android account/focus guard.
AccountManager's native Android route, Phone (and retained Apple iOS) pending
state cleanup, focus connections, dismissal and showWithSelection HMD/Tablet
routing are unchanged. No duplicate domain connections are added.

Actual Pico Application_Setup connects DomainAccountManager::authRequired to
DialogsManager::showDomainLoginDialog; the latter selects domain login and
calls LoginDialog::showWithSelection. LoggingInBody.qml's existing Connections
targets loginDialog. This change closes that route's missing terminal receiver;
it does not replace Pico Setup, a native provider or a platform-owned caller.

Import the narrow constructor delta, preserving your platform guards. Tests
require existing PhoneLoginState.h and the actual unchanged LoggingInBody.qml.
Set OVERTE_LOGIN_VARIANT=main (Main/Phone/Pico) or apple (retained Apple source).
The fixture compiles the COMPLETE original constructor with real QObject/moc
and the original PhoneLoginState for Pico, Phone, desktop and iOS define stacks.
Real QQmlEngine/Connections execute the COMPLETE original success/failure
handlers and loadingSuccess body for domain login. Visual objects, timer-start
and loader are explicit test boundaries; no whole UI or timer-render proof.
Checks cover exact single forwarding, success callback/start, failure spinner/
glyph clearing and original loader payload, pending-state cleanup ownership,
unchanged account/focus guards, dismissal and QObject receiver destruction.

For a finite real credential timeout, separately consume domain-auth-generation
v001/v002 AND its mandatory additive snapshot prerequisite correction:
discovery-visibility/v001 source6026087a7942c224ac0086ece436cb61f5302ac1,
manifest83c72c242b095114af7db65739faa3b793fe668d0850483f50a62cad63575b8b,
RequestCancellation.h SHA256
4e348bbe82e4e5c3be0705e0bb73f80bf880fd0b4e3023ea71465142df8acdce.
That manager's existing loginFailed signal carries its 15-second event-loop
deadline outcome. This fixture emits the actual signal on a test manager;
the separate complete manager test verifies its actual 15-second timer.

The existing failure handler still describes all failures as bad credentials;
typed timeout/recovery UX and preservation of domain selection after reload
need separate source review. Foreground/auth request identity across multiple
dialog instances, account login, provider/Qt5/Android/Apple runtime acceptance,
HMD rendering and full node acceptance remain pending. This is not an APK
result and does not alter the frozen SH-001 source.
