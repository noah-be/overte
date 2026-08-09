# Android testing

The Android test suite is split into explicit tiers so contributors can get
fast feedback without accidentally starting a device test or an expensive
build. `tests/suite/catalog.json` is the source of truth. The runner never
discovers tests by filename glob.

## Test architecture

| Tier | Purpose | Expected use |
| --- | --- | --- |
| `fast` | JVM, native host, JavaScript and isolated QML behavior | Every local change and pull request |
| `contracts` | Source, architecture, privacy, packaging and security invariants | Every pull request |
| `host` | All focused host behavior suites | Local investigation and future CI expansion |
| `regression` | The complete established device-free phone gate | Protected branches, nightly and manual CI |
| `device` | Physical ARM64 phone smoke and lifecycle coverage | Explicit device lab invocation only |
| `instrumentation` | AndroidX tests on a connected emulator or device | Explicit prepared Android environment |
| `coverage` | JVM, production JavaScript and optional native coverage reports | Prepared Phone dependencies |
| `all` | Every catalog entry, including device tests | Never use as an unattended host shortcut |

The categories are complementary:

- JVM tests cover pure Java/Kotlin logic and extracted Android state machines.
  Robolectric additionally executes the real launcher Activity, resources,
  permission requests, intents and saved-instance-state lifecycle without a
  device.
- Native host tests cover C++ logic without starting Android or Qt.
- JavaScript tests use controlled fakes for tablet and system-script APIs.
- Qt Quick tests exercise QML properties, signals and bindings in isolation.
- Contract tests protect invariants that cannot be expressed economically as
  runtime tests, including permissions, privacy and packaged resources.
- Device tests cover the Android lifecycle, system integration, graphics and
  hardware-dependent behavior that a host test cannot prove.

Contract tests are not a replacement for behavior tests. When logic can be
called directly, prefer an executable unit or component test. Keep text-based
checks for stable architectural, packaging, security and privacy guarantees.

## Running tests locally

Run commands from `android/`:

```bash
tests/run-tests.sh fast
tests/run-tests.sh contracts
tests/run-tests.sh host
tests/run-tests.sh regression
tests/run-tests.sh coverage
tests/run-tests.sh robolectric
```

List a tier without executing it:

```bash
tests/run-tests.sh fast --list
```

Reports are written to `build/test-results/suite/TEST-android-<tier>.xml` in
JUnit XML format. A different destination can be selected with
`--report-dir /absolute/or/relative/path`.

The physical-device tier is intentionally explicit:

```bash
ANDROID_SERIAL=<serial> tests/run-tests.sh device
```

Run AndroidX instrumentation separately on a connected target after preparing
the Phone native dependencies:

```bash
ANDROID_SERIAL=<serial> tests/run-tests.sh instrumentation
```

The Gradle JVM tests likewise require the prepared Phone Qt/Conan graph because
the Android module compiles its main Qt activity before its unit-test source set:

```bash
JAVA_HOME="$PWD/pico-host-tools/jdk-21" \
  ./gradlew -c settings-phone.gradle :phoneInterface:testDebugUnitTest
```

That task includes Robolectric coverage for `PermissionsActivity`: already
granted and denied microphone permission, unrelated and duplicate callbacks,
cold and replacement deep links, invalid-intent clearing, saved-state
recreation and exactly-once native-Activity launch. Robolectric
4.16.1 is pinned and Android resources are enabled for unit tests. For a clean
host without Android SDK, Qt or Conan, use `tests/robolectric/run-tests.sh`.
Its small Java harness compiles the real Activity and supporting production
sources directly, and stubs only the generated `R` symbol and the Qt-native
Activity class at the boundary. Each of the nine behaviors runs on API 26 and
35. This harness is mandatory in the CI coverage job and publishes JUnit XML.

The default `coverage` tier uses a dependency-free JaCoCo harness for the five
framework-independent production classes and writes its report below
`build/reports/coverage/jvm-standalone`. It enforces 100% line and branch
coverage for that deliberately narrow scope on clean CI hosts. The full Gradle
Android unit-test report remains available through
`tests/coverage/run-jvm-coverage.sh`, but requires the prepared Phone Qt/Conan
graph and writes below `apps/phoneInterface/build/reports/coverage`.

Other cross-language reports are written below `build/reports/coverage`.
JavaScript coverage has independent production-file gates: `places.js`
requires 98% lines / 94% branches / 97% functions, `portal.js` requires
98% / 84% / 100%, and the Phone core scope requires 90% / 85% / 95%. Native
coverage is explicitly skipped when `gcovr` is unavailable locally. CI creates
an isolated virtual environment, pins `gcovr`, and treats both native coverage
thresholds as mandatory. Current measured results are 100% lines/functions and
98.9% branches for the interface policies, plus 100% lines/functions/branches
for the pending-handoff state. The single uncovered parser branch is a
defensive non-finite check which the classic C++ numeric parser rejects first.

Connected instrumentation coverage is intentionally separate from the host
coverage tier:

```bash
ANDROID_SERIAL=<serial> tests/coverage/run-instrumentation-coverage.sh
```

Read `tests/phone-device-test.sh --help` before using it. It validates that the
target is a suitable physical ARM64 touch device and manages private diagnostic
output. Do not add a physical-device suite to `fast`, `host`, `contracts`, or
`regression`.

### QML host tool

QML component tests require `qmltestrunner` from a compatible Qt host
installation. If it is unavailable, `tests/qml/run-qml-tests.sh` prints an
explicit skip and exits with the conventional code 77; the catalog runner
records that as a successful skip and continues the fast tier. Set
`PATH` to the project's Qt host-tool directory to enable these tests locally.
The fast CI job installs the Qt 5 Quick Test runtime and sets
`OVERTE_REQUIRE_QML_TESTS=1`, turning a missing tool or QML failure into a hard
failure. Local hosts without Qt retain the explicit skip behavior.

## Adding or changing a test

1. Put the test near its technology-specific support code and make it directly
   executable from the Android repository root.
2. Give it one feature-level responsibility and deterministic inputs. It must
   not depend on execution order, a developer home directory or public network
   state.
3. Reuse shared fakes and fixtures. Create temporary state in a private
   temporary directory and clean it on every exit path.
4. Add one entry to `tests/suite/catalog.json` with a unique ID, category,
   description, command and the narrowest appropriate tiers.
5. Run the narrow tier, then `contracts` or `regression` when the changed area
   participates in those gates.
6. Verify that failure output contains enough context but no device serials,
   private paths, tokens, raw deep links or user data.

Use names that describe behavior, such as
`deepLink_whenSchemeIsMixedCase_normalizesScheme`. Prefer small fakes over
large mocking frameworks, stable QML `objectName` values over coordinates, and
local server fixtures over live endpoints. A retry is not a fix for a flaky
test: control time, randomness, process state and asynchronous completion.

When production code cannot be tested without starting the complete app,
extract framework-independent parsing, decision logic or state transitions
behind a small adapter. Preserve the public behavior and add tests before and
after the refactor.

## CI policy

`.github/workflows/android-tests.yml` runs `fast`, `contracts`, and clean-host
JVM/native `coverage` plus the API-26/API-35 Robolectric launcher harness
independently for Android- or script-related pull
requests. JavaScript coverage is enforced in `fast`; the coverage job enforces
the scoped 100% JVM line/branch gate and the native 95% line / 90% branch gates.
The complete device-free `regression` tier runs after all three gates on
protected-branch pushes, nightly, or when selected through manual dispatch.
Test and coverage jobs upload their reports, including on failure.

The workflow deliberately does not download the Android SDK, Qt, native
dependencies or build an APK. Artifact builds and hardware tests require
separate, trusted runners and credentials; keeping them separate makes the
device-free gate reproducible and safe for pull requests.

## Device and nightly matrix

The target matrix for dedicated device-lab workflows is:

| Lane | Coverage | Cadence |
| --- | --- | --- |
| Emulator API 26 | Minimum supported Android behavior and recreation | Nightly |
| Emulator current stable API | Permissions, intents and standard Android UI | Protected branch/nightly |
| Emulator API 36 | Target-SDK compatibility and newest platform behavior | Nightly |
| Physical ARM64 phone | Qt/OpenGL, touch, audio, lifecycle and deep links | Protected branch smoke/nightly |
| Physical 16 KiB-page device | ELF loading and runtime page-size compatibility | Release/nightly |
| Pico target | VR-specific lifecycle, input, audio and graphics | Separate Pico device workflow |

Nightly scenarios should include cold and warm deep links, permission grant and
denial, background/foreground cycles, Back recovery, rotation or recreation,
login/logout, tablet navigation, audio, world connection failure/recovery, and
memory/performance baselines. Device jobs must be serialized per device, use a
bounded timeout, always clean up the installed test state, and publish only
privacy-scrubbed summaries.

Coverage should be reported separately for JVM, native and JavaScript code.
Raise thresholds gradually around critical parsers and state machines; a single
aggregate percentage is not a useful release gate for this hybrid application.
