# Windows desktop adapter

This target-owned adapter implements the current shared Overte device E2E
contract for interactive Windows desktops. Windows releases and GPU/desktop
variants are lab rows rather than Git branches; see
[`ACCEPTANCE_MATRIX.md`](ACCEPTANCE_MATRIX.md).

The adapter provides one authoritative Interface lifecycle plus:

- exact PID, creation-time, executable-path, and recursive process-tree ownership;
- foreground, process, launch, stop, and window-scoped screenshot operations;
- bounded look, movement, jump, flight, grounding, and tablet input through OculiX;
- sequenced in-client probe snapshots and behavior-gated input retries;
- same-process scene reload, domain navigation, asset loading, and sound playback.

Synthetic input delivery alone is never success. The shared in-client probe
must independently observe the requested camera, avatar, scene, tablet, asset,
or sound behavior.

Copy [`targets.example.json`](targets.example.json) outside the checkout, keep
it private, fill in the Interface, Java, and OculiX paths and all three SHA-256
digests, then export `OVERTE_WINDOWS_TARGETS`. The adapter checks every digest
before discovery and again at use. Selectors, account paths, and target
configuration must never be published in CI artifacts.
Interface and OculiX inherit only a bounded set of ordinary Windows session
variables plus explicit target environment entries. Harness paths, selectors,
GitHub tokens, and Jenkins-prefixed values are removed before either child is
started.

The Jenkins agent must run as an interactive process in the dedicated lab
user's active input desktop. Windows Session 0 and an inaccessible input
desktop are rejected before discovery or automation. Keep Jenkins, Java,
OculiX, and Overte at the same integrity level; UAC secure desktop,
higher-integrity windows, locked sessions, and disconnected desktop sessions
intentionally remain outside the adapter's authority.

Use the OculiX IDE JAR because the API-only JAR has no `-r` script runner. Use
an open-source OpenJDK 17 or newer and pin both files. The driver selects only
the launched Interface PID, resolves its window, focuses it, and bounds every
mouse/key hold. Every hold uses `finally` to release its input. A failed or
timed-out OculiX invocation starts a separate bounded recovery action that
normalizes every key and button the driver may use.

Targets with both `probe.kind: injected-test-script` and
`clientControl.kind: fixture-command-http` advertise scene reload, domain
navigation, controlled asset loading, and sound playback. The adapter posts a
bounded JSON command to the controlled scene fixture origin and requires the
exact response before reporting that the request was accepted. The probe polls
that same-origin route. The adapter never uses clipboard shortcuts, external
URL handlers, or a second Interface process.

At launch the shared probe is copied into the target's hashed private state
directory. The configured state root and its logs must be restricted to the
dedicated account by the Windows ACL.
Cleanup captures the exact root and recursive child identities before closing
Interface, then uses normal and forced Windows process-tree termination only
for identities that still match their captured creation token and image path.

Validate the hardware-free contract from the repository root:

```powershell
py -3 -m unittest discover -s tests/device/adapters/windows/tests -p "test_*.py" -v
py -3 tests/device/verify_adapter.py `
  --adapter-manifest tests/device/adapters/windows/adapter.json `
  --check-cleanup
```

These tests are hardware-free. Enabling a matrix row additionally requires the
interactive Windows acceptance suites described in `ACCEPTANCE_MATRIX.md`.
