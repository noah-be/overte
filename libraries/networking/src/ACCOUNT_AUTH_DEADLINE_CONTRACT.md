# Account credential request deadline — SH-005

All five actual password/auth-code/Steam/Oculus/refresh POST methods attach the
same15-second precise single-shot Qt timer to the reply. This is total elapsed
request time after POST returns, not an activity-reset timeout. The reply is the
callback context: its destruction cancels observation and no strong ownership
keeps it alive. Already-finished replies are ignored. No automatic retry follows.

Before abort the timer marks the reply timed out. Both complete token callbacks
reject that flag even if abort emits finished synchronously with NoError/2xx/
otherwise-valid tokens. The existing login failure or refresh-only waiting reset
is retained, with no overwrite/persistence on timeout. QPointer guards cleanup
if an abort callback destroys the reply immediately; survivors get deleteLater.
Normal Qt abort/finished delivery is the transport contract, not a synthetic
finished signal injected by this helper.

Focused tests compile all five complete original request methods plus the real
helper, use actual Qt POST/reply/QTimer and wait the actual15 seconds. They test
five simultaneous hung requests, earlier successful requests, deletion before
timeout, immediate deletion during abort and deferred survivor cleanup. Real
completion tests reject timeout+NoError+valid body for both actual callbacks.
Network/TLS/provider and account-data/storage/profile remain explicit boundaries.

Requires matching Account request v001 plus completion v003 and their diagnostic/
storage/helper prerequisites. Retained Apple Qt error guards stay intact. The
event loop may deliver late if its thread is blocked or the OS suspends the app;
this is not a hard OS stop deadline. Target/request generation, foreground/retry
policy, initial URL validation, streaming/total memory, separate error callback
exactly-once semantics and full native/artifact/privacy acceptance remain pending.
