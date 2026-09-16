# Login QML diagnostic boundary — PX-16

The existing generic LoginDialog directory-load and two directory-edit console
sites emit fixed events only. Four create/link failure console sites no longer
evaluate or append an arbitrary `error` payload. Settings, account logout/auth
refresh, fields, provider routing and visible error presentation are unchanged.
No URL, account identity, reversible encoding or provider message is diagnostic
input at these seven sites. Fixed existing success/failure events remain intact.

`tests/device/contracts/redaction/test_login_qml_diagnostics.py` inventories all
24 original console expressions under LoginDialog, requires literal-only calls,
and executes those exact expressions through the real Qt JS console extension
with four seeded target/credential/error values and a positive raw-sink control.
This is expression-level sink proof, not whole-component/handler/native execution.
The optional baseline switch must produce RED on the prior source.

Main and Apple variants must preserve their existing imports and previous auth
receiver changes. No platform-owned source is included. Original source/node
dependencies, UI error/screenshot exports, native logs/crashes, provider behavior
and full accepted artifact privacy remain pending; this is not PX-16 PASS.
