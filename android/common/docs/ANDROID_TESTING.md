# Android testing

The Android test suite is split into explicit tiers so contributors can get
fast feedback without accidentally starting a device test or an expensive
build. `android/common/tests/suite/catalog.json` is the source of truth. The runner never
discovers tests by filename glob.

The fast and contract tiers parse every tracked Android `*.sh` entry point with
`bash -n` and every tracked Python source through the standard-library AST
parser. Executable Python entry points must retain the repository's Python 3
shebang. These checks catch syntax regressions even in hardware-only scripts
that cannot execute on a pull-request host, without creating bytecode or cache
files. They are syntax contracts, not substitutes for behavior tests or
general-purpose linters.

## Test architecture

| Tier | Purpose | Expected use |
| --- | --- | --- |
| `fast` | JVM, native host, JavaScript and isolated QML behavior | Every local change and pull request |
| `contracts` | Source, architecture, privacy, packaging and security invariants | Every pull request |
| `host` | All focused host behavior suites | Local investigation and future CI expansion |
| `prepared-host` | Pico-relevant Qt/C++ suites from an existing CMake/Conan build | Explicit prepared developer host |
| `regression` | The complete established device-free phone gate | Protected branches, nightly and manual CI |
| `device` | Physical ARM64 phone smoke and lifecycle coverage | Explicit device lab invocation only |
| `instrumentation` | AndroidX tests on a connected emulator or device | Explicit prepared Android environment |
| `coverage` | JVM, production JavaScript and optional native coverage reports | Prepared Phone dependencies |
| `robolectric` | Phone and VR launcher behavior across each reviewed SDK matrix | Clean host with locked Gradle dependencies |
| `mutation` | Fast curated policy mutation gate | Pull requests and local changes |
| `mutation-extended` | Full deterministic mutation campaign | Scheduled or manual CI |
| `endurance` | Repeated JS, native and QML lifecycle/property checks | Scheduled or manual CI |
| `stability` | Shuffled and parallel host-suite isolation audit | Scheduled or manual CI |
| `all` | Every catalog entry, including device tests | Never use as an unattended host shortcut |

The categories are complementary:

- JVM tests cover pure Java/Kotlin logic and extracted Android state machines.
  Robolectric additionally executes the real launcher Activity, resources,
  permission requests, intents and saved-instance-state lifecycle without a
  device.
- Native host tests cover C++ logic without starting Android or Qt.
- JavaScript tests execute the production Phone bootstrap, action bar and app
  scripts with controlled fakes for tablet, QML-fragment and system APIs.
- Qt Quick tests exercise QML properties, signals and bindings in isolation.
- Contract tests protect invariants that cannot be expressed economically as
  runtime tests, including permissions, privacy and packaged resources.
- Device tests cover the Android lifecycle, system integration, graphics and
  hardware-dependent behavior that a host test cannot prove.

The hardware-free Pico harness self-tests run in `fast`, `host`, and
`contracts`; they exercise lock, unattended-runner, and microphone-script
control flow with fakes, never ADB hardware. The six full Pico-relevant Qt/C++
suites require an existing configured dependency build and are therefore kept
in their explicit tier:

```bash
android/common/tests/run-tests.sh prepared-host
```

That tier may rebuild the six named targets and has a 30-minute catalog
timeout; each resulting executable has its own 120-second timeout. To inspect
an already-built tree without triggering dependency or shader regeneration,
run `android/vr/pico/tests/pico-host-regression-test.sh --no-build --build-dir <build>`. Both
the hardware-free fixtures and this prepared runner honor quoted `TMPDIR`
paths, remove their bounded temporary state on success or failure, and are
represented honestly in the catalog JUnit report. The prepared tier is not a
CI pull-request gate and does not contact ADB or a headset.

The same three device-free tiers compile and execute the production
`AndroidAudioInputPolicy` directly. The Robolectric harness additionally
compiles its real `AndroidAudioInput` caller against Android API classes, which
guards the caller and policy API from drifting apart. It does not behavior-test
the enum-to-`MediaRecorder` mapping or start `AudioRecord`: mapping, allocation,
blocking reads, capture-thread/JNI delivery and device-supported formats remain
Android/Pico runtime boundaries.

Contract tests are not a replacement for behavior tests. When logic can be
called directly, prefer an executable unit or component test. Keep text-based
checks for stable architectural, packaging, security and privacy guarantees.

The machine-readable [Phone test inventory](../../phone/tests/phone-test-inventory.json)
guards this boundary. CI recursively discovers Phone-owned Java, native,
JavaScript and QML code, every `+android_phoneInterface` QML selector, the
`Phone*.h` UI policies and `SafeAssetPath`, plus the manifest and backup-policy
XML. Every discovered file must name
real test evidence or a specific Android/Qt runtime boundary. It also parses
`PHONE_DEFAULT_SCRIPTS` and requires every startup script to be classified.
Adding production code without test ownership therefore fails the fast and
contract tiers. Decorative drawables, strings and generated Qt resources are
intentionally excluded; packaging tests cover their shipped presence without
pretending that each visual asset needs a unit test.

The suite-runner self-tests exercise this gate with isolated adversarial
fixtures. They verify rejection of new unowned production files, stale or
unrelated evidence, unreviewed runtime-boundary claims and duplicated default
scripts. Evidence must both exist and reference the named production component;
the two accepted Android/Qt runtime boundaries are a review-required validator
allowlist rather than free-form exemptions.

The Phone source-level inventory is complemented by
`android/common/tests/project-module-inventory.json`, which covers all seven Gradle modules:
the legacy Interface, Pico Interface, Quest Interface, both Frame Players, and
the Qt and Oculus libraries. Its fast contract parses every manifest, verifies
the application/library plugin and native target wiring, snapshots explicit
backup policy, requires real host evidence, and records a concrete runtime
boundary. This is module ownership, not a claim that VR rendering or Qt native
behavior ran on the host. Pico keeps its existing device-free regression suite;
Quest/Oculus tracking and compositor behavior, both Frame Player render loops,
and the legacy Interface Qt/OpenGL path remain explicitly hardware/runtime-only.
For the five application modules the same record is also the reviewed security
snapshot: exact compile/minimum/target SDK values, permission allowlists and the
effective exported activity/service/receiver/provider surface. Exported values
are evaluated with Android's target-SDK rules, so legacy manifests retain their
historical intent-filter-implied exports while modern Pico components must be
explicit. This makes an added permission or externally reachable component a
reviewed inventory change; it does not describe the legacy targets or storage
permissions as modern security practice.
The Pico and Quest launcher records also treat forwarded application arguments
as sensitive: the contract rejects direct `System.out`, `System.err`, or Android
`Log` calls that include the argument field. Robolectric verifies transport to
the explicit internal Activity without requiring or printing its contents.

The native host suite links and executes the real
`QtInputConnectionCompat.cpp` JNI exports with null JNI handles, proving their
intended no-dereference `JNI_TRUE` behavior and ABI spellings. The URL/Back JNI
bridge retains source contracts for UTF-16 acquisition/release, pending
exception handling, queued URL ownership and deadlock-safe Back dispatch. Its
actual `JNIEnv` function table, Qt event-loop thread affinity and queued callback
timing require the Android/Qt runtime and are not represented by a fake host
environment.

The fast CI job provisions Temurin JDK 21 because the native suite compiles the
real JNI compatibility exports. On developer hosts, CMake searches `JAVA_HOME`,
the optional repository JDK and the `java.home` reported by `javac` on `PATH`
(including Java 8's nested `jre` layout). If no JDK headers exist, configuration
fails with an actionable `jni.h` message; the mandatory JNI test is never
silently omitted. An unusual installation can pass
`-DOVERTE_JNI_INCLUDE_DIR=<jdk>/include` explicitly.

Each catalog command has a bounded timeout. On POSIX hosts the runner gives the
entire suite process group a short `TERM` grace period and then sends `KILL`, so
a timed-out shell wrapper cannot leave compilers or helper children running.
Non-POSIX hosts retain direct-process termination. Partial output, including
byte output and XML-invalid control characters, is preserved safely in an
atomically replaced JUnit report. Self-tests start a real hanging parent and a
`TERM`-resistant child and verify that neither process leaks.
Catalog entries without an explicit override use eight minutes. CI job limits
are deliberately larger than their longest inner suite/step timeout, leaving
time for atomic JUnit finalization, summaries and artifact upload.

## Host portability

The device-free entry points resolve the repository from their own script
location; they do not depend on the caller's current directory. The runner
self-tests, safe-asset Java harness, native/JNI CMake tests, JavaScript tests,
mutation gate and Robolectric suite are exercised in CI-oriented audits from a
separate working directory with the checkout and `JAVA_HOME` both containing
spaces. Keep every derived path quoted when adding a shell entry point.

Ubuntu Linux is the authoritative host and CI environment. The portable
Python, Node, Java and CMake portions are intended to work on macOS when their
declared toolchains are installed, but the complete Android packaging and
native-contract lanes currently rely on the Linux Android SDK/NDK and ELF
tooling and are not claimed as a macOS gate. The Bash-based suite is not a
native Windows test runner; use the Linux CI environment (or an equivalent
Linux VM/container) rather than interpreting source-level Windows branches as
validated Windows support.

## Running tests locally

Run commands from `android/`:

```bash
android/common/tests/run-tests.sh fast
android/common/tests/run-tests.sh contracts
android/common/tests/run-tests.sh host
android/common/tests/run-tests.sh regression
android/common/tests/run-tests.sh coverage
android/common/tests/run-tests.sh robolectric
```

The mandatory static-quality entry in `fast` uses ShellCheck 0.11.0 and Ruff
0.15.22 from a verified repository-managed tool directory. On a clean Linux
x86_64 host, run `android/common/tests/quality/install-tools.sh` before the tier. The installer
checks the ShellCheck archive digest and uses pip hash-checking for Ruff; the
lint runner rejects missing or version-drifted executables.

List a tier without executing it:

```bash
android/common/tests/run-tests.sh fast --list
```

Reports are written to `build/test-results/suite/TEST-android-<tier>.xml` in
JUnit XML format. A different destination can be selected with
`--report-dir /absolute/or/relative/path`.

The physical-device tier is intentionally explicit:

```bash
ANDROID_SERIAL=<serial> android/common/tests/run-tests.sh device
```

Run AndroidX instrumentation separately on a connected target after preparing
the Phone native dependencies:

```bash
ANDROID_SERIAL=<serial> android/common/tests/run-tests.sh instrumentation
```

The Gradle JVM tests likewise require the prepared Phone Qt/Conan graph because
the Android module compiles its main Qt activity before its unit-test source set:

```bash
JAVA_HOME="$PWD/vr/pico/pico-host-tools/jdk-21" \
  PATH="$PWD/vr/pico/pico-host-tools/jdk-21/bin:$PATH" \
  ./common/gradlew -c phone/settings.gradle :phoneInterface:testDebugUnitTest
```

Use the bundled JDK 21 explicitly. The host's OpenJDK 25 is not compatible with
this Gradle/Android plugin combination and fails while creating
`DefaultTestTaskReports` with `Type T not present`, before project test code is
compiled.

That task includes Robolectric coverage for `PermissionsActivity`: already
granted and denied microphone permission, unrelated and duplicate callbacks,
cold and replacement deep links, invalid-intent clearing, saved-state
recreation and exactly-once native-Activity launch. Direct Android-boundary
tests additionally cover exported `ACTION_VIEW` intents, internal extras,
wrong actions, missing data and rejected schemes. Robolectric
4.16.1 is pinned and Android resources are enabled for unit tests. For a clean
host without Android SDK, Qt or Conan, use `android/common/tests/robolectric/run-tests.sh`.
Its small Java harness compiles the real Activity and supporting production
sources directly, and stubs only the generated `R` symbol and the Qt-native
Activity class at the boundary. Across Phone, legacy Interface, Pico, and
Quest, 32 Robolectric source behaviors produce 71 executions. The exact matrix
is Phone (API 26/35), legacy Interface (API 24/26), Pico (API 26/35), and
legacy Quest (API 24/28/35). Phone contributes 13 source behaviors and 26
executions. Nine framework-independent legacy `HifiUtils` checks bring the
harness report to 80 granular JUnit cases. This harness is mandatory in the CI
coverage job and publishes JUnit XML.

The default `coverage` tier uses a dependency-free JaCoCo harness for ten
framework-independent Phone, Pico audio, Qt utility, and legacy Interface production classes and writes its report below
`build/reports/coverage/jvm-standalone`. It enforces 100% line coverage for all
ten classes and 100% branch coverage for nine. `AssetCacheExtractor` has a
95% branch gate because its final uncovered mkdirs/isDirectory branch represents
a filesystem race; its measured result is 25/26 (96.15%). The full Gradle
Android unit-test report remains available through
`android/common/tests/coverage/run-jvm-coverage.sh`, but requires the prepared Phone Qt/Conan
graph and writes below `phone/apps/phoneInterface/build/reports/coverage`.

Other cross-language reports are written below `build/reports/coverage`.
JavaScript coverage has independent production-file gates: `places.js`
requires 98% lines / 94% branches / 97% functions, `portal.js` requires
98% / 84% / 100%, `mobileActionBar.js` requires 95% / 86% / 100%,
`phoneEmote.js` requires 92% / 87% / 100%, and `mobileTabletApps.js` plus
`quickGoto.js` each require 100% in all three metrics. Each gate runs only its
matching production behavior test, so another script cannot compensate for a
regression. The non-gating aggregate summary currently reports 96.00% lines /
90.51% branches / 100% functions for Phone core. Native
coverage is explicitly skipped when `gcovr` is unavailable locally. CI creates
an isolated virtual environment, pins `gcovr`, and treats both native coverage
thresholds as mandatory. Current measured results are 100% lines/functions and
98.9% branches for the interface policies, plus 100% lines/functions/branches
for the pending-handoff state. The single uncovered parser branch is a
defensive non-finite check which the classic C++ numeric parser rejects first.

The startup asset-cache extractor is framework-independent behind the real
`AssetManager::open` adapter. Host and JUnit tests cover marker validation,
cache hits, nested binary/text copies, stale-file replacement, traversal
rejection and partial failure without publishing a success marker.
It is part of the mandatory standalone JaCoCo scope at 100% line and 96.15%
branch coverage (25/26). The sole uncovered branch is the benign filesystem
race where another process creates a missing directory between `mkdirs()` and
the subsequent `isDirectory()` check; forcing that race would make CI flaky.
Fixed-seed adversarial cases additionally cover absolute, Unicode, control and
very long manifest paths, duplicates, symlink escapes, invalid destination
roots, marker collisions, zero-length stream reads, close failures and partial
source failure. Failure cases verify that no regular success marker is
published; the stream-specific cases also assert resource closure.

Connected instrumentation coverage is intentionally separate from the host
coverage tier:

```bash
ANDROID_SERIAL=<serial> android/common/tests/coverage/run-instrumentation-coverage.sh
```

Read `android/phone/tests/phone-device-test.sh --help` before using it. It validates that the
target is a suitable physical ARM64 touch device and manages private diagnostic
output. Do not add a physical-device suite to `fast`, `host`, `contracts`, or
`regression`.

### QML host tool

QML component tests require `qmltestrunner` from a compatible Qt host
installation. If it is unavailable, `android/common/tests/qml/run-qml-tests.sh` prints an
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
JVM/native `coverage` plus the reviewed per-application Robolectric SDK matrix
independently for Android- or script-related pull
requests. JavaScript coverage is enforced in `fast`; the coverage job enforces
the scoped 100% JVM line/branch gate and the native 95% line / 90% branch gates.
The complete device-free `regression` tier runs after all three gates on
protected-branch pushes, nightly, or when selected through manual dispatch.
Test and coverage jobs upload their reports, including on failure.
Every job that compiles Java/JNI or invokes JavaScript provisions pinned
Temurin 21 and Node 22 respectively; tests do not rely on the changing tool
versions preinstalled in a hosted runner image.

Schedule and manual-dispatch runs additionally shard two longer checks into
independent jobs after the fast, contract and coverage gates. `stability` runs
two fixed-seed shuffled rounds, two isolated parallel replicas and serialized
Robolectric contenders without installing Qt. `endurance` uses 100 JavaScript
lifecycle cycles and 1000 native policy cycles, then runs only the dedicated
four-case QML lifecycle endurance component. It does not rerun the complete QML
component suite from `fast`. Both jobs have step timeouts below their job
timeouts so the catalog runner can atomically finish JUnit first; their
summaries and granular native/QML reports upload under `if: always()`.

Every CI job also runs `android/common/tests/reporting/generate_summary.py` under `if:
always()`. It reads only explicitly requested JUnit, JaCoCo/Cobertura or JSON
coverage, and mutation JSON inputs, writes a Markdown artifact under
`build/reports/summary/`, appends the same table to `GITHUB_STEP_SUMMARY`, and
prints a compact console view. Missing, malformed or internally inconsistent
reports are shown as `MISSING` or `MALFORMED`; they are never treated as zero
tests or successful coverage. Summary steps use `continue-on-error: true`, so
an aggregation defect cannot hide or replace the original test result. The
generator itself is dependency-free and tolerant by default; pass `--strict`
when a local/reporting contract should fail on report issues. Its fixtures run
in the fast tier and cover pass, failure, skip, glob aggregation, missing and
malformed inputs.

Report ingestion is bounded to 8 MiB per regular, non-symlink file and 256
unique matches per glob. Arbitrary DTD/entity declarations are rejected; only
the exact JaCoCo and gcovr/Cobertura declarations are stripped before parsing.
Labels are length-limited plain text, counters are bounded integers, mutation
modes are allowlisted, and diagnostics never copy report contents, URLs,
absolute input paths or test output into Markdown. Summary files use a private
random temporary file plus atomic replacement and refuse a pre-existing output
symlink.

The fast host runners also publish tool-native granular JUnit: CTest writes one
case per native executable, Qt Test writes one case per QML test function, and
Node's built-in `junit` reporter writes one case per JavaScript test. Each tool
continues to emit its normal human-readable console reporter simultaneously.
Reports are first written to a unique temporary file and atomically renamed;
the wrapper always returns the original tool exit status. Failure fixtures use
mock tools to verify nonzero propagation, parseable XML and cleanup of every
temporary report. `OVERTE_TEST_REPORT_DIR` can isolate concurrent callers.

The `ci-reproducibility-contract` suite runs in both `fast` and `contracts`.
It prevents the clean-host assumptions from drifting: third-party Actions must
use full commit SHAs, the Gradle distribution checksum must match 8.13,
Robolectric must use its committed lockfile in strict mode, both Qt Quick
Controls generations must be installed, and every required tier command and
JUnit upload path must remain declared. Its fixture tests intentionally remove
or weaken each declaration to prove that the contract fails closed. Run it
directly with `android/common/tests/ci/run-ci-contract-tests.sh`; it requires only Python's
standard library and does not parse YAML with a third-party package.

The workflow deliberately does not download the Android SDK or native app
dependencies and does not build an APK. The fast lane installs only the pinned
Ubuntu Qt 5 runtime packages required by `qmltestrunner`. Artifact builds and
hardware tests require separate, trusted runners and credentials; keeping them
separate makes the device-free gate reproducible and safe for pull requests.
The investigated emulator options, measured artifact/dependency sizes and the
prerequisites for an honest future instrumentation lane are documented in
[`ANDROID_EMULATOR_CI_FEASIBILITY.md`](ANDROID_EMULATOR_CI_FEASIBILITY.md).

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

## Mutation testing

The pull-request-sized mutation gate is deterministic and dependency-free:

```bash
android/common/tests/run-tests.sh mutation
```

It validates a clean baseline before applying mutations, then covers the pure
Java boundary policies (including asset cache marker/extraction behavior), the native graphics parsers and pending handoff,
and curated lifecycle/routing decisions in five production JavaScript files.
The JavaScript mutations are injected only by exact canonical source-path
substitution in the existing Node VM harness; normal test runs are unchanged.
A mutant is counted as killed only when the production-facing harness
reports its normal assertion-failure signature. Compilation errors, timeouts,
signals, JVM startup errors, and other harness crashes are infrastructure
errors and fail the run instead of inflating the score. A JSON result is
written to `build/reports/mutation/critical-policies.json`; the extended tier
uses `critical-policies-extended.json`, so an explicit `all` run cannot
overwrite the quick result.

The broader periodic set runs with:

```bash
android/common/tests/run-tests.sh mutation-extended
```

Both modes use the fixed-seed generated inputs already present in the Java and
native harnesses; neither reaches the network or depends on wall-clock timing.

## Device-free lifecycle endurance

The fast tier repeats production JavaScript lifecycle scenarios for 20 fresh
instances per script:

```bash
android/common/tests/run-tests.sh endurance
```

Each cycle starts the real `mobileTabletApps`, `mobileActionBar`, Phone Emote,
Places, Portal, and Quick Goto scripts through the existing VM harnesses,
interacts with them, and executes their real shutdown paths. Assertions verify
that signals/listeners, timers, message subscriptions, Tablet buttons,
portals/entities, and action-bar fragments are released after every cycle.
This deliberately checks owned resources rather than a noisy process-heap
number. The default 20-cycle run is PR-sized; scheduled CI increases it to 100
via `OVERTE_JS_ENDURANCE_CYCLES` (maximum 500).

The same `endurance` tier runs 100 long native policy cycles by default;
scheduled CI scales it to 1000 with `OVERTE_NATIVE_ENDURANCE_CYCLES`. Each
cycle executes 1,024 generated graphics-parser batches and 4,096 model-checked
PendingHandoff operations. The QML lane creates, interacts with, and destroys
200 sets of real Phone Emote, Address Bar, and Tablet Touch Configuration
components and verifies that their host owns no residual objects after each
event-loop cleanup. A sentinel self-check proves that the ownership assertion
observes a deliberately retained child before verifying its removal. Missing Qt host tools remain an explicit local skip and a
hard failure when `OVERTE_REQUIRE_QML_TESTS=1` is set.

These host checks cannot observe Android-owned Qt surfaces, Java/JNI global
references, platform IME callbacks, native renderer resources, or lifecycle
work scheduled by the Android framework. Those remain emulator/device-lane
responsibilities; a passing host endurance tier makes no claim about them.

Phone login state additionally runs an 8-instance, 8,192-step fixed-seed
reference model. It covers initial state, accepted and duplicate submissions,
all terminal outcomes through their shared `finishRequest` boundary, repeated
terminal delivery, and isolation between dialog instances. Native coverage
requires this header independently to retain 100% line and branch coverage.

## Scheduled stability audit

`android/common/tests/run-tests.sh stability` is intentionally separate from pull-request
gates. With committed seeds it runs two differently permuted serial rounds and
two parallel replicas of the Java, asset-cache, JavaScript, native, mutation,
and endurance host suites. Parallel native jobs receive private CMake build
directories, mutation jobs private JSON reports, and all other harnesses use
private temporary state. Robolectric retains its Gradle project output tree and
is protected by a bounded repository `flock`; the stability audit runs it after
the concurrent group with two simultaneous contenders and requires both
serialized executions to pass. This catches order coupling and workspace collisions
without making routine PR feedback substantially slower.

The stability runner starts each case in its own process group. A timeout sends
TERM to the complete group and escalates to KILL after a bounded grace period,
so a child process cannot outlive a failed audit. Runner fixtures verify the
two committed permutations, private replica paths, real parallel overlap,
temporary-workspace cleanup, timeout handling, and that an intentional exit-23
case makes the tier fail. Set `OVERTE_STABILITY_FIXTURE_FAIL=1` only when
testing that red-path behavior.
