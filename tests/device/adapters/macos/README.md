# macOS desktop adapter

This adapter belongs only to `apple-macos`. It implements the shared Overte
device E2E contract for an interactive macOS desktop through the pinned OculiX
IDE runtime in [`overte.sikuli/`](overte.sikuli/). Process identity uses the
stable macOS start timestamp, and cleanup owns the launch process group.

Copy [`targets.example.json`](targets.example.json) outside the checkout, keep
it private, fill in the application executable and OculiX paths plus the JAR
SHA-256, and export `OVERTE_MACOS_TARGETS`. Configure the executable inside the
bundle, for example `/Applications/Overte.app/Contents/MacOS/Overte`, rather
than the `.app` directory itself.

Run Jenkins as a LaunchAgent of the logged-in, dedicated lab user. Grant
Accessibility and Screen Recording only to the stable Jenkins/Java paths used
by that LaunchAgent, and define its `PATH` explicitly. A daemon, SSH-only
session, or ad-hoc replacement Java path does not inherit those grants and is
an infrastructure error.

Use the OculiX IDE JAR because the API-only JAR has no `-r` runner. Pin its
digest and use an open-source OpenJDK 17 or newer. The driver resolves the
launched Interface by exact PID, focuses only that application's window, and
bounds every pointer and keyboard hold. Input delivery alone never passes a
test; the common in-client probe supplies the behavior evidence.

Targets with both `probe.kind: injected-test-script` and
`clientControl.kind: probe-command-file` also advertise domain navigation,
controlled asset loading, and sound playback. The adapter copies the shared
probe beside a mode-0600 `e2e-client-command.json`; it does not use clipboard
shortcuts, an external URL handler, or a second Interface process.

Run the hardware-free checks from the repository root:

```sh
python3 -m unittest discover \
  -s tests/device/adapters/macos/tests -p 'test_*.py' -v
python3 tests/device/verify_adapter.py \
  --adapter-manifest tests/device/adapters/macos/adapter.json \
  --check-cleanup
```
