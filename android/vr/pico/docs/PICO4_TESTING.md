# Pico 4 hardware-independent test suite

For the repository-wide runner that includes this suite, see
[`tests/PROJECT_TESTING.md`](../../tests/PROJECT_TESTING.md).

The Pico 4 suite protects Android packaging, OpenXR, WebView, audio, controller
interaction, tablet/Create UI, serverless worlds, performance tooling, and the
headset automation scripts without requiring an Android SDK, emulator, or
headset.

## Quick start

Run the complete suite from the repository root:

```bash
android/vr/pico/tests/pico-device-free-test.sh
```

The standard run requires Python 3, Bash, Node.js, a JDK (`java` and `javac`),
and `jq`. See everything the runner knows about or run a focused subset:

```bash
android/vr/pico/tests/pico-device-free-test.sh --list
android/vr/pico/tests/pico-device-free-test.sh --category openxr --category audio
android/vr/pico/tests/pico-device-free-test.sh --test webview-bridge
```

CI can keep running after failures and publish a JUnit report:

```bash
android/vr/pico/tests/pico-device-free-test.sh \
  --timeout 120 --junit build/test-results/pico4-device-free.xml
```

Use `--fail-fast` for local diagnosis. `--skip-missing` is intended only for
constrained developer machines; CI deliberately treats missing tools as a
failure so that lost coverage is visible.

## Coverage model

[`pico4-coverage.json`](../tests/pico4-coverage.json) is a risk-based capability
matrix. Every Pico capability has at least two checks, every catalogued test is
mapped, and critical OpenXR, input, microphone, and world-loading capabilities
are checked independently. `pico4-coverage-test.py` enforces those invariants.

This is not native line coverage: much of the production code needs Android,
Qt, JNI, or an OpenXR runtime and cannot be loaded into a generic host process.
The suite therefore combines:

- executable pure Java and JavaScript behavior tests;
- Python source-contract and XML/Gradle packaging tests;
- mock-ADB integration tests for all headset automation scripts;
- fixture schema and power-analysis behavior tests.

The matrix reports 100% *risk-capability mapping*, not 100% executable line
coverage. Real rendering, tracking accuracy, microphone hardware, thermal
behavior, APK installation, and vendor runtime compatibility remain explicit
hardware acceptance concerns.

## Optional native host regression

If a configured desktop CMake test build already exists, run the Pico-relevant
native suites as an additional layer:

```bash
android/vr/pico/tests/pico-host-regression-test.sh --build-dir build-tests
```

This is intentionally separate because configuring the full Qt/Conan build is
far heavier than the deterministic device-free suite.

## Adding coverage

Add a stable test name and category to `TESTS` in `pico4-test-suite.py`, then map
it to one or more capabilities in `pico4-coverage.json`. Prefer behavior tests
for extracted platform-independent logic. Use source contracts only for JNI,
Android, Qt, or OpenXR paths that cannot execute on the host, and assert safety
invariants rather than formatting details.
