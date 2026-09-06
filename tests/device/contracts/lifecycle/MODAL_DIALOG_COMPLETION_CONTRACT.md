# Shared modal dialog completion

Message, input, file and asset dialog listeners now publish at most one terminal
response. Completion sets the terminal flag, disconnects the dialog and removes
asynchronous ownership before emitting a copied result. Direct receivers can
reenter selection, destroy the dialog or delete the listener without a subsequent
member access. Destruction cancels the request; failed dialog creation delivers a
queued cancellation after callers can attach a response handler.

All five asynchronous factory paths register and parent their listeners to the owner.
Owner destruction deletes pending listeners; it does not imply an affirmative response.
Destroying a pending listener removes its registry entry. Only registered listeners
are scheduled for deferred deletion; synchronous stack listeners are not. Waiters
use a guarded pointer if an event handler destroys their listener. Message results
retain StandardButton values; input/file/asset selection conversions remain intact.

The focused host fixture compiles the actual base declaration, all four complete
listener classes, base methods and owner registration/removal methods against real
Qt6 QQuickItem/QObject/signals/QPointer/QTimer/moc. Only the OffscreenUi dependency
owner and dialog-creation factories are seams. Tests cover all four selection
results, reentrant duplicate selection/cancellation, destruction before/after
selection, null creation, listener deletion in response, pending listener deletion,
missing owner, synchronous stack lifetime and deletion while waiting. Compiled
negative mutations remove duplicate suppression or failed-creation delivery.

This is a shared UI lifecycle prerequisite. It does not establish trustworthy
human intent, origin/source/epoch binding, client entity-script consent grants,
full QML/native widget integration, Qt5/native platform compilation or original
39-node acceptance. The entity-script default-deny fence remains in place. A
response receiver must still validate its own live request before acting; ordinary
modal responses are not an authorization token.
