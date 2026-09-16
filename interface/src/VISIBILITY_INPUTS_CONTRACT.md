# SH-005 single effective Qt/native visibility publication

IMPLEMENTATION ONLY. Requires lifecycle/v002 and HTTP cancellation/v001+v002.
This is input arbitration for the existing ONE applicationGate, not a parallel
connection state engine, native-focus authentication or full SH-005 acceptance.

The C++14 ApplicationLifecycle.h exports two full-client, out-of-line functions:
`void overte::lifecycle::observeQtVisibility(bool foreground);`
`void overte::lifecycle::observeNativeVisibility(bool foreground);`
Only Shared Qt startup/activeChanged supplies Qt observations. Native owners use
the second function instead of directly calling applicationGate().visible().
Both functions queue to the existing QCoreApplication thread when necessary;
without an application they do nothing. Existing native latest-event transport
and early-delivery retry remain required; a void call is not an applied receipt.

Qt must report active. Native is an additional veto once the first native
observation is received, retained for that process; without a native observer,
existing Qt-only behavior remains. Native true cannot override Qt false, and Qt
true cannot override native false. Before any Qt observation the input is false.
There is no detach/reset-to-unknown API. Native owners must discard stale events
from their own source before publishing; this bool API cannot authenticate or
order unrelated producer streams. Separate native focus/permission/audio inputs
are not silently equated with Activity foreground.

The actual Application_Events publication computes the effective input, applies
it to the single Gate, then supplies the Gate's returned foreground state to the
actual AddressManager HTTP policy. Thus duplicate observations don't invalidate
requests and a stopped Gate cannot reopen HTTP after a new true observation.
Early native input does not create AddressManager. Startup republishes retained
inputs immediately after that dependency is installed. QObject queue latency is
explicit: cancellation occurs when the input is applied, not synchronously in
an arbitrary native thread or within a guaranteed OS stop deadline.

Phone migration: replace its owned PhoneUrlHandler.cpp native submit line
`applicationGate().visible(foreground)` with
`overte::lifecycle::observeNativeVisibility(foreground)`; retain local pending-URL
cancel and existing AndroidHelper/LifecycleHandoff transport. No General edit of
that file, new JNI signature or additional native singleton is required.

Pico's previously released HTTP startup override line is replaced precisely by
`overte::lifecycle::observeQtVisibility(QGuiApplication::applicationState() == Qt::ApplicationActive);`
Add `#include "ApplicationLifecycle.h"` if absent. The original later member
activeChanged seed and signal connection remain. No other override changes are
released. Pico/iOS may bind an existing applicable native foreground producer to
observeNativeVisibility, but must not create an early-DSO copy of applicationGate.
Do not claim a native observer was installed when only Qt is consumed.

Focused tests execute the COMPLETE original publication and both exported
functions with real Qt queued cross-thread delivery, original Gate/tickets,
and only the dependency-registry/AddressManager forwarding boundary substituted.
They cover early native pause, both input orders, duplicates, stale HTTP tickets,
queued pause/resume, absent-native Qt-only behavior and stopped-Gate rejection.
Original Qt event-body and original HTTP/startup tests remain included; full
Qt5/Qt6 application/native compilation and device ordering are pending.

This slice synchronizes navigation Gate and HTTP policy only. Render
_isForeground, audio, DomainHandler/ICE/UDP/STUN, full bounded reconnect/recovery
trace and informed entity consent/finite revoke remain separate open work.
