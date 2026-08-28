# Windows desktop adapter

This target-owned adapter implements the shared Overte device E2E contract for
interactive Windows desktops. Native process ownership uses Windows creation
times and process-tree cleanup; visual input and window-scoped screenshots use
the pinned OculiX IDE runtime in [`overte.sikuli/`](overte.sikuli/).

Copy [`targets.example.json`](targets.example.json) outside the checkout, keep
it private, fill in the local executable and OculiX paths plus the JAR SHA-256,
and export `OVERTE_WINDOWS_TARGETS`. Selectors and account paths must never be
published in CI artifacts.

The Jenkins agent must run as an interactive process in the dedicated lab
user's desktop session. Windows Session 0 is rejected before discovery or
automation. Keep Jenkins, Java, OculiX, and Overte at the same integrity level;
UAC secure desktop and higher-integrity windows intentionally remain outside
the adapter's authority.

Use the OculiX IDE JAR because the API-only JAR has no `-r` script runner. Pin
its digest in the target file and use an open-source OpenJDK 17 or newer. The
driver selects the launched Interface process by exact PID, resolves only its
window, focuses that window, and bounds every mouse/key hold. A synthetic input
event alone is never a pass: the common in-client probe verifies focus, scene,
avatar, view, tablet, asset, and sound behavior.

Targets with both `probe.kind: injected-test-script` and
`clientControl.kind: probe-command-file` also advertise domain navigation,
controlled asset loading, and sound playback. The adapter copies the shared
probe beside a mode-0600 `e2e-client-command.json`; it never uses clipboard
shortcuts, external URL handlers, or a second Interface process.

Validate the hardware-free contract from the repository root:

```powershell
py -3 -m unittest discover -s tests/device/adapters/windows/tests -p "test_*.py" -v
py -3 tests/device/verify_adapter.py `
  --adapter-manifest tests/device/adapters/windows/adapter.json `
  --check-cleanup
```
