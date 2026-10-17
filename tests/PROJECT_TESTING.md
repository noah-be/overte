# Project testing

The dormant Android owner-transfer source composes one exact five-file npm
consumer generation with the required Android callee. It is preparation only:
Android activation remains disabled, and deployed legacy owners stay intact.
Ordinary, labelled and complete inventories retain 40, 45 and 46 distinct
executions, including diagnostic prerequisites and scaled variants.

The project owner independently recomputes trusted host selection. Partial CI
selections omit unchanged platform suites and produce nonreusable observations.
The complete declared profile can delegate only Pico to an actually selected
required Android owner; that pending handoff does not certify passing execution.
Legacy direct and push entry points retain their full profile. A complete
synchronization fallback can delegate only the same reviewed Pico suite after
independently re-reading and binding the actual source PR and required Android
plan through the trusted API. It still runs every shared suite and every other
profile entry, including branch extras. The receipt remains a nonreusable
pending-owner diagnostic; it cannot become complete qualification evidence.
The two foreign Browser/S3 lockfiles are absent from the host reader complement,
but changed lock paths still require the independently recomputed mandatory npm
owner. Android reporter sources remain real test inputs.

Before activation, review fresh reader identities against the final protected
source and actual child trees, qualify the complete prospective caller and Pico
handoff on hosted infrastructure, then propagate through governed parent syncs.
Unsupported combinations, unknown inputs and missing execution owners fail
closed. Local fixture regressions do not satisfy hosted qualification.

The prospective execution validator checks the complete owner generation and
the actual predecessor before allowing qualification jobs. The required outer
repository verifier separately enforces the activation blockers, reviewed
activation state and target branch. Successful prospective execution cannot
authorize a merge while activation is blocked. Pending Pico handoffs remain
nonreusable diagnostic observations.

The staged Phone release-metadata regression invokes the unchanged production
archive tool on a small temporary Git repository. It verifies exact committed
archive content, revision and digest independently of unrelated checkout files,
including the two foreign npm lockfiles. Older test generations that archive
the real checkout retain conservative Android selection until this test is
integrated on both sides of the comparison.

Android's separately reviewed lock-only route covers only the two existing
ordinary Browser/S3 lockfiles and the ordinary 40-execution inventory. It
requires matching complete reader complements on both trees, the hermetic Phone
test on both trees, an unchanged regular orchestration-policy entry and an
independently recomputed mandatory npm owner. A lock graph outside the focused
security profiles requires the package's full JavaScript checks; it does not
change native reader independence. Mixed inputs, older readers and optional extended diagnostics retain the complete
Android selection. This finite proof does not exempt either package directory
or the repository's CI tools as a whole.


For a task-oriented entry point, use the
[automated testing portal](../docs/portal/testing/index.md). This page remains
the authoritative guide for project-runner commands and prerequisites.

Run commands from the repository root. The shared runner provides repository
checks, a complete portable host profile, and an optional configured native
layer. Physical-device acceptance has separate commands and evidence requirements.

Automatic Browser client workflows run only when their own client files change:
`browser-client/` for the Browser client and `browser-direct-client/` for the
Direct browser client. Their package manifests and lockfiles remain relevant.
Markdown-only edits, workflow configuration, cleanup, shared native sources and
platform-only changes do not start Browser builds, rendering tests or journeys.
The atomic-settings diagnostic retains only its exact Browser laboratory inputs.
Workflow changes receive the ordinary workflow/security contract checks. Native
and platform changes retain their applicable independent checks. Explicit manual
diagnostics remain available. Required Browser-owner activation is not deployed
by this change.

## Host prerequisites

Pull requests changing only the regular `package.json` / `package-lock.json`
files in `tools/jsdoc` or `server-console` (optionally with Markdown) select
bounded tool checks instead of the full host suite and native client build.
The required repository gate still verifies successful dependency installation,
an audit of all dependency severities, and behavior of each affected tool:
JSDoc generation, or console tests and the packager entry point. Run them locally
with `python3 tools/repository-checks/tool_dependencies.py --projects tools/jsdoc,server-console`.
Installation scripts are disabled; this lane does not claim GUI or complete
distributable-packaging coverage. Mixed source/build changes, unknown paths,
and nonregular files retain the existing broader checks. Protected pushes use
the exact before/after commit inventory to select the same bounded tool lane.
They do not publish complete host-qualification evidence for partial tool checks.
Synchronization PRs continue to use the independently required topology gate;
a regular tool-only delta selects the affected tool checks directly, while
mixed source changes retain exact-parent host evidence reuse or the full fallback.

Use a Linux host for the documented common test path. The runner uses Bash and
POSIX process groups; native Windows application builds follow
[BUILD_WIN.md](../BUILD_WIN.md) instead. The GitHub-hosted reference environment
is declared in [project-tests.yml](../.github/workflows/project-tests.yml):
Ubuntu 24.04, Python 3.12, Node.js 22, and JDK 17.

Install Git, Bash, Python 3.11 or newer, Node.js 22 or newer, `jq`, CMake 3.24
or newer, CTest, Ninja, Make, and a C++17 compiler available as `c++`;
Android branch suites also need Java/Javac. Python 3.11 is
required by repository helpers using `hashlib.file_digest`; use the CI versions
above when reproducing CI behavior. The quick profile compiles small portable
production C++ regressions and checks CMake test registration using stub targets.
JavaScript syntax checks use two bounded subprocesses and preserve complete,
ordered diagnostics; neither JavaScript nor shell source is executed by syntax checks.
Local Unix sockets must be available for the input-protocol tests.
It needs no configured Overte build, Android SDK,
emulator, or physical target. A QML test runner is optional locally and its
absence is reported as skipped by the device control-plane report.

Install the pinned Python workflow-parser dependency once in a local environment:

```bash
python3 -m venv build/repository-checks-env
source build/repository-checks-env/bin/activate
python3 -m pip install -r tests/requirements-repository.txt
```

The dependency is used by offline Doctor contract tests; it grants no network or
GitHub access to the quick suite. CI installs the same requirements explicitly.

For the complete host control-plane gate, also provide `pkg-config`, GLM headers, Qt 6
development packages, Qt Quick Test tools, and `unshare` with permission to
create user and network namespaces. Artifact validation runs real CLIs without
network access; unavailable isolation fails those tests. The workflow contains
the exact Ubuntu package list. These host Qt contracts are separate from the
complete client's platform-specific Qt/Conan dependency graph.

The actual embedded-Web channel contracts also need matching Qt WebChannel
development headers: `libqt5webchannel5-dev` for the actual Pico Qt 5 backend
and `qt6-webchannel-dev` for Qt 6 in the Ubuntu reference environment. Ordinary
project CI, parent qualification and downstream validation install both and
check the matching Quick, WebChannel and Network pkg-config modules before
running contracts. An unavailable module is a prerequisite failure; keep the
actual selected backend test enabled.
The Scripts/Assets document views import `Qt.labs.folderlistmodel`; install
`qml-module-qt-labs-folderlistmodel` and
`qml6-module-qt-labs-folderlistmodel` for the Qt 5 and Qt 6 behavior runs.

The host profile also compiles the real shared embedded-HTML policy and the
actual account-authentication signal bindings for Pico, Phone, desktop and the
retained legacy Android path. These checks require Qt Core development files
and Qt's `moc`; they do not instantiate a native browser or authenticate a device.
The `goto-dialog-script` host suite compiles the complete production
`DialogsManagerScriptingInterface` with real Qt Core/QML and matching `moc`,
exposes that QObject to a `QJSEngine`, and runs the actual `scripts/system/goto.js`.
Only the native UI receiver and tablet/toolbar controls are substituted. It
checks queued dispatch, rapid toggles, external close followed by script stop,
ordinary stop, queued clicks followed immediately by stop, missing close
notifications, and signal/button cleanup in both toolbar and tablet modes.
It also compiles the actual native show/hide/toggle methods and visibility
observer for Phone and tablet branches, substituting rendering/focus boundaries,
to verify external-close state and preservation of another app's keyboard focus.
Set `OVERTE_GOTO_TEST_QT=Qt5` or `Qt6` to select the
fixture SDK; extracted SDKs use standard pkg-config and runtime-library paths.
These host results do not prove physical controller input or rendered navigation.
The `embedded-web-qml` host suite requires Qt Quick Test's `qmltestrunner`
(Qt 5.15 or Qt 6), Qt Quick, and Qt Test QML modules. It executes the actual
shared tablet/world callers with only the operating-system browser boundary
substituted, including the first EventBridge message before channel idle,
single message delivery, source replacement, and keyboard transitions.
Set `OVERTE_QML_TEST_RUNNER` to select a matching Qt Quick Test executable.

The `recorded-voice-native` host suite requires Qt Core development files and
matching `moc`. It executes the actual AudioClient capture/playback callback and
AudioScriptingInterface methods with real Qt signals, queued calls and timers;
the operating-system audio sink/source and resampler boundaries are substituted.
The `recorded-voice-qml` suite uses the same Qt Quick Test prerequisites as
`embedded-web-qml` and clicks the actual shared voice controls and buttons in
both controller/desktop and direct-touch configurations. These checks do not
prove microphone permissions, hardware routing, native sink behavior or sound
on a phone, iPhone/iPad or Pico headset.
Set `OVERTE_VOICE_TEST_QT_CORE=Qt5Core` or `Qt6Core` to select the native fixture's
SDK; an extracted Qt SDK also uses the standard `PKG_CONFIG_PATH`,
`PKG_CONFIG_SYSROOT_DIR` and `LD_LIBRARY_PATH` variables.

The `snapshot-native` host suite compiles the actual animated-capture and upload
callbacks with Qt Core, Gui, Concurrent and Network, plus matching `moc`. Only
application/render/preferences and HTTP transport boundaries are substituted.
It executes the unchanged production GIF encoder using the attributed pinned
public-domain fixture, real image decoding, storage-authority checks, delayed
render cancellation and replacement, and atomic terminal races. The
`snapshot-qml` suite requires Qt Quick Controls 2 and Layouts in addition to
Qt Quick Test. It clicks the production native review and tests generic and
QFileSelector-selected system export boundaries. The shared JavaScript suite
also executes the production SNAP script for all four capture modes, desktop
compatibility, errors and closing while capture or upload is pending.
Set `OVERTE_SNAPSHOT_TEST_QT=Qt5` or `Qt6` to select the native fixture SDK.
The same extracted-SDK variables documented for voice tests apply. GLM uses
the existing `OVERTE_TEST_GLM_INCLUDE` override when it is not installed globally.
These checks do not prove Photos/system chooser behavior, GPU capture or image
upload against a real metaverse. Native device acceptance remains separate.

The `document-tree-native` host suite compiles the real `FileDialogHelper` with
matching Qt Core, Quick, Quick Test, Widgets and Test development packages and
`moc`. It exercises directory hierarchy, symbolic-link rejection, independent
file/tree operators, request cancellation, destroyed owners and cross-thread
completion. The actual OffscreenUi bundle route executes with its surface
manager substituted. Set `OVERTE_NATIVE_QT_MAJOR=5` or `6` to select the SDK.
These checks do not prove a platform document provider or a complete client build.

The `obj-material-native` host suite compiles the production OBJ tokenizer,
geometry/material parser and resource request bodies with actual Qt Core/Gui
and GLM. It executes generated HFM textures through the production material
consumer, covering relative MTL hierarchy, multiple materials, explicit FST
texture-base overrides, external URLs, decoded PNG bytes and the existing
flattened-export fallback. Resource providers and HFM/render storage remain
explicit host boundaries; live asset-server and device rendering acceptance
remain separate. The same Qt-major and GLM include overrides apply.

The phone pad projection regression requires the real GLM headers (`libglm-dev`
on Ubuntu). The isolated synchronization validation workflow installs this package
and the listed Qt 5 development/QML packages for both complete fallback and
product differential checks.
A prepared local package can instead be selected with
`OVERTE_TEST_GLM_INCLUDE` pointing at its include directory. The host requirements
also pin Pillow for the native-frame black-interior negative control. The full
gate includes phone placement, pad projection, joint storage, QML property/thread
delivery, and actual Qt Quick accessibility/product-text regressions.
The phone startup and Settings click regressions additionally require Qt 5 Core, Gui, Qml, Quick and Test
development packages and the Qt Quick 2 QML module (`qtdeclarative5-dev` and
`qml-module-qtquick2`, `qml-module-qtquick-controls2`, `qml-module-qtquick-layouts`
and `qml-module-qtquick-window2` on Ubuntu). They reproduce the early attached-property cache
failure with real Qt 5, verify native ownership across the temporary parser
application, and verify short Settings clicks through the actual parented QML load.
They also check that the General Preferences cancel control and the shared Back
control have distinct identifiers. The Phone editor regression compiles the
production QtEditText Java source with host Android boundaries and proves that
landscape input preserves editor options while disabling fullscreen extraction.
Java delivery and native JNI-boundary checks preserve observed keyboard visibility
independently of the occluding inset, including visibility-only transitions.
The APK provenance gate inspects packaged DEX definitions and rejects missing or
duplicate Qt Java replacement classes. The Gradle Qt-jar task binds its exclusion
list as an explicit cache input. Physical Phone attestation still runs before each
adapter operation; its property reads use one fresh snapshot, and session reuse
does not repeat the same attestation or cache it across operations.
A verified, extracted Fedora Qt 5 host package may be selected with
`OVERTE_TEST_QT5_SYSROOT`; these dependencies do not replace the Android runtime.

Platform-only synchronization checks install the same QML and Qt 6 host packages
before running their product suites. Android Phone regressions require Qt 6 Core
and Widgets even when shared parent results are reused. Documentation-only
synchronization skips this prerequisite installation.

On disposable GitHub-hosted Ubuntu 24.04 runners, both host workflows enable
unprivileged user namespaces for the current VM through the runtime-only
`kernel.apparmor_restrict_unprivileged_userns=0` setting, then require the
`unshare` probe to succeed. This accommodates Ubuntu's
[AppArmor namespace restriction](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/).
The setup refuses other runner environments, writes no persistent system
configuration, and does not run tests with host root privileges. The isolated
test commands retain `--net`; failures are never replaced by an unsandboxed
fallback. Local hosts and device-lab runners need their own reviewed namespace
policy; these workflows do not configure them.

Prepare the additional pinned SPDX/CycloneDX validators in a dedicated environment:

```bash
python3 -m venv build/host-tests-env
build/host-tests-env/bin/python -m pip install -r tests/requirements-host.txt
unshare --user --map-root-user --net true
```

This environment is used only for host tests and does not populate a product
dependency cache. The quick profile needs only `requirements-repository.txt`.

## Quick profile

```bash
python3 tests/run-project-tests.py --profile quick --list
python3 tests/run-project-tests.py --profile quick --timeout 240 \
  --junit build/test-results/project-tests.xml
git diff --check
```

The list command shows the suites selected for the current checkout. A
successful execution prints `PASSED` rows and a summary containing `0 failed`,
and exits with code zero. The JUnit report records each suite's captured output;
inspect the device control-plane report for individual skipped host checks.

The quick profile checks repository policies, source/syntax integrity,
dependency and release contracts, JavaScript behavior, documentation, a
portable production C++ regressions, and the portable E2E control plane. It also
runs the product suites declared by
[`platform-profile.json`](platform-profile.json). The shared profile declares
no product suites; Android branches declare their own entry points. A missing
declared entry point is an error. See [source ownership](../docs/SOURCE_LAYOUT.md).

Additional host suites cover device-result schemas, mocked Jenkins orchestration,
the desktop input protocol, performance-result contracts and native metrics,
dependency-free server-console behavior, and native CMake test registration.
The Jenkins tests use local fixtures and never contact a laboratory or device.
VirtualBaton scenarios exercise both shipped copies with deterministic delivery
orders and real event-loop smoke tests. Python suite discovery fails if it finds
no tests, so moving or removing a test directory cannot silently leave a green gate.

Use `--suite NAME` to focus a run and `--fail-fast` to stop after the first
failure. `--timeout` is a limit for each suite. The default continues after
failures so one run can report independent problems.

## Combined host profile for CI

```bash
build/host-tests-env/bin/python tests/run-project-tests.py --profile host \
  --timeout 240 --host-timeout 900 --junit build/test-results/project-tests.xml
```

This profile covers the union of the quick and complete portable host checks.
It runs the full device control plane once, including the quick device tests and
the phone-spawn regression; it omits those two redundant quick invocations.
All other quick suites and every branch-owned product suite remain selected.
Unlike the native `full` profile, `host` needs no configured Overte build.

The full control-plane suite requires QML and writes its detailed report to
`build/test-results/device-e2e-control-plane.xml`. Its total time limit is
`--host-timeout`; other suites retain `--timeout`. On timeout the runner allows
up to five additional seconds to clean up isolated workers before forcing exit.
On Linux, both outer runners also adopt and reap escaped descendants if a nested
scheduler must be killed, with a separate one-second reaping deadline. Detached
children cannot survive the runner or keep its captured output pipe open. This
ownership requires a standalone, single-threaded process with no existing
children. On Linux, an occupied process is rejected before launching the command
or changing ownership; embedded concurrent callers are unsupported.
Failures in the full group fail the combined project result.

Shared CI, parent qualification and sync fallback use this combined profile.
Parent branches run their push tests only in parent qualification, which creates
the same exact-commit evidence after success. Shared CI retains leaf and
development-branch pushes, reusable PR calls and manual runs. The actual PR
merge candidate and the integrated parent commit remain distinct test inputs.

## Available project suites

The `producer-proof` quick suite tests the dormant
[`producer.py`](../tools/test-evidence/producer.py) protocol. Its descriptors bind
the exact live PR base, head, merge commit/tree, selected owners, trusted policy
and producer workflow source separately from the tested candidate. Bounded
single-member artifacts require independently authenticated run, job, app and
artifact facts. A self-consistent JSON digest does not authenticate a producer.

Authority selection considers all run statuses and attempts. Missing current
attempts, unresolved descriptors, ambiguous ordering and mixed job attempts
prevent reuse; a newer pending, failed or cancelled producer cannot inherit an
older green result. Aggregate verification requires the exact selected successful
jobs, unchanged final live identity, the original expiry and actual source/runtime
inputs. Shared owners use the existing trusted execution-receipt validator.
Other owner kinds and relayed or mixed-attempt proofs remain unsupported.

The `producer-api` quick and host suite tests the dormant
[read-only authenticated API adapter](../docs/PRODUCER_API_PROOF.md). It derives
run, latest-attempt job, app, artifact and original reusable-workflow facts from
independent GitHub GET responses. It verifies a complete trusted workflow tuple
at the API-observed original merge, all-status paginated authority inventories,
bounded raw archive digests and initial/final live refs. Fake API fixtures
cannot replace missing authentication with artifact claims or an older green.

These helpers change no active workflow, dispatch, retry or metadata-skip
behavior. Before activation, producers must publish early descriptors and
complete aggregate proof; all selected native, documentation, security, browser
and sync owners need complete inner validators. Actual publisher isolation,
producer concurrency/fallback ownership and trusted caller/template compatibility
require separate implementation and review.

The `attested-runtime` quick/host suite tests a separate, default-off
[original-runtime admission and zero-selection terminal](../docs/ATTESTED_RUNTIME_REUSE.md).
It preserves the exact original tested environment in source fingerprints and
does not install or claim to measure the unused consumer VM. Every shared suite
must be reusable and the declared product inventory must be empty. Policy,
controller, exact requirement, variant, source, authority or expiry changes
prevent a result. Existing legacy API provenance limits remain activation
blockers; this dormant helper changes no active workflow or current sync fallback.

The `android-ci` suite runs in both the quick and combined host profiles. It
checks the staged Android ownership controller with disposable Git trees,
mocked command results and isolated Python environments. These fixtures verify
the Fast/Contracts union, one owner for Robolectric and Pico, complete native
and Robolectric SDK case coverage, and failure propagation through tier views.
Planning and receipt verification read bounded regular Git blobs from the exact
commit, including newly discovered Phone test classes, so a `.github`-only sparse
checkout produces the same plan as a full checkout. Running selected commands
still requires their candidate files to be checked out. The fixtures reject
missing, symbolic-link, gitlink, oversized and dirty source inputs.
They require no Android SDK, Gradle run or product build. The controller and
[reviewed policy](../.github/android-checks.json) are staged for later workflow
wiring. Its current evidence closure covers the repository because controller
loading also validates the branch-owned platform profile.

The `codeql-selection` quick suite tests the active
[`tools/repository-checks/codeql.py`](../tools/repository-checks/codeql.py)
language selector. It compares complete immutable Git trees, including deleted,
renamed and mode-changed inputs, without importing candidate code. Pure Python
changes select Python; JavaScript/TypeScript, templates and extracted data select
JavaScript/TypeScript. Overlapping manifests, query-pack directories, shared
controls, unknown inputs, incomplete inventories and unresolved aliases retain
both languages. Scheduled scans always retain both languages.

The CodeQL workflow runs the helper from trusted default-branch code against
the exact immutable base and merge candidate. It creates only the selected
language jobs; a final `codeql-checks` aggregate rejects selection failures and
failed, cancelled, missing or unexpectedly skipped analyses. Unrelated workflow
YAML selects JavaScript data analysis; a local Python action selects Python.
Changes to the actual CodeQL workflow/configuration still select both languages.
The activation uses the existing trusted CLI and conservatively scans both
languages until the reviewed successor is integrated. Its tests run in the
required quick and combined host profiles; the shared registry binds the test,
helper, immutable-inventory module and actual CodeQL workflow/configuration.
Review the helper's configuration hashes after changing CodeQL configuration
or action versions. It selects languages, not individual files within a scan.
PR and default-branch push scans still run independently for affected languages;
cross-event result reuse is not implemented by this language-selection change.
The `browser-cpu-selection` quick suite exercises dormant trusted Browser CPU
history routing and both inner and outer required-result validation against
real Git histories. It also runs in the combined host profile. Its registry
uses a full-repository fallback because actual CLI tests read trusted routing,
package-generation, event-target and workflow policies together. The
[Browser selection guide](../docs/BROWSER_CPU_SELECTION.md) records the exact
paired sole-owner transfer and source-history migration still required before
activation. Browser activation remains off and active workflows are unchanged.

The `test-evidence` quick suite checks trusted execution receipts, complete
suite-input fingerprints, actual runtime identity and parent qualification.
The shared registry is [`.github/test-suites.json`](../.github/test-suites.json).
It declares canonical commands and complete source/fixture/helper closures;
unreviewed closures remain conservative. Changed Python import modules and
ancestor Node package metadata cannot hide behind an unchanged entry point.

The existing `test-evidence` quick suite also loads `sandbox-test.py` and
`sandbox-host-test.py`. Their fixed Linux boundary controls use real temporary
Git trees and offline process/kernel fixtures, without privileged host probes.
The owning suite retains its complete repository input fallback. The manual-only
`.github/workflows/shared-sandbox-host-diagnostic.yml` matches its canonical
template at `tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml`.
Dispatch it only from reviewed, protected `main`. It accepts no candidate inputs
and has no PR trigger; no ordinary PR producer or reusable evidence is enabled.

The prospective Ubuntu 24 diagnostic verifies its loaded controls against the
immutable manual workflow source. A bounded raw-object materializer creates a
private, pristine detached Git snapshot without executing checkout filters,
hooks or candidate configuration. Complete source and metadata inventories
reject dirty bytes, extra import paths, aliases, writable modes and gitlinks.
The private index matches the immutable tree; a fixed in-sandbox Git status
must be clean. A tracked `build` path is rejected because its writable mount
would hide source inputs. Complete histories above 4,096 objects or 64 MB are
unsupported by this bounded diagnostic materializer.
The separate `materialize_candidate_snapshot()` source helper supports larger
ordinary candidates without changing that fixed diagnostic. It streams each
unique Git object once, verifies public object IDs with protected Git, and
retains the pristine index and complete source/metadata negative inventory.
Materialized source and stored-object hashes must match the verified stream;
corrupted copies cannot become their own trusted inventory baseline.
Limits are 64 MiB per blob, 1 GiB materialized source, 2 GiB unique object bodies,
32,768 objects, 65,536 expanded/inventory entries and 300 seconds. The Git reader
has a 512 MiB address-space limit; tree/commit metadata and Python stream chunks
have separate fixed bounds. Unsupported sizes, aliases, modes or unavailable
process limits fail rather than produce a partial successful snapshot.

The caller names at most eight immutable commits. Only those commits and their
complete ordinary trees enter the private Git store; the helper never walks
unbounded ancestry or fetches objects. Each included commit with an omitted
parent is explicitly marked in `.git/shallow`, while its raw ordered parents
remain unchanged. The retained snapshot digest binds that exact Git context as
well as the files. Future execution receipts and suite fingerprints must bind
this context before Git-sensitive suites can reuse results: equal file trees
alone are insufficient. This helper authorizes no execution or reusable proof;
actual shared-suite compatibility, complete runtime capture and protected
publication still require qualification.
Only exact trusted probe/runtime source enters a separate read-only projection;
candidate policy code cannot replace it. The boundary profile workload is a fixed real-Git
fixture, never an application build or arbitrary PR command.

A root-owned sibling guardian holds the actual cgroup kill/events descriptors
before releasing any low-UID work. Pipe EOF after a deliberately SIGKILLed root
worker must kill kernel-observed surviving trusted cleanup canaries and confirm
the entire owned scope empty. Normal completion and failure use the same scope.
The restricted UID starts from one byte-identical copy of the verified controller
in a root-owned public `/tmp` directory, rather than reopening the private runner
checkout. Exclusive creation, read-only mode, ownership and byte checks protect
that copy; all boundary, shared and controller-death launches keep the same
attach-before-release gate. Runner-home permissions are never widened.
Separate protected probes run before work and after every workload is gone;
source, run attempt, snapshot, projection and the effective diagnostic runtime
must agree. This small stdlib profile is explicitly not the complete portable
host environment identity. Production launch/post-capture remain denied.
Its exact environment includes `PWD=/work`, which Bubblewrap also sets for the
fixed working directory. Mismatches remain failures; bounded diagnostics name
the failing fields and variable keys/counts without printing environment values.
Live Ubuntu qualification, complete shared-host suite/toolchain compatibility,
publisher credential isolation and authenticated reuse publication remain
required before any successful result can authorize reuse.

The same dispatch-only workflow offers finite `boundary`, `shared-host` or `ci37`
profile, defaulting to the unchanged fixed boundary fixture. `shared-host`
prepares the existing Python 3.12 host virtualenv, Node 22, JDK 17, Qt 5/6 and
GLM prerequisites and seals their actual versioned installations. It accepts
no revision, suite list, command or environment input. Only its own immutable
protected-main source executes, using the streamed snapshot and its explicit
shallow commit/ordered-parent context. Matching the canonical depth-2 checkout,
only the target and its at most seven immediate ordered parents enter the private
Git store; missing grandparents remain explicit shallow boundaries. Legacy
execution and post-capture remain disabled. The separate protected source capabilities
permit a controlled native attempt only after the reviewed workflow installation;
the deployed legacy owners do not invoke them. Android activation remains disabled.

The shared-host adapter calls the existing trusted process controller with the
complete common registry commands, preserving QML assertions and the 900-second
`device-control-plane-full` deadline. It runs no standalone Browser product,
journey, SDK, device or application build. Each independent command receives a
fresh writable scratch directory, private namespaces, an independent low host
UID and a root-owned scope/guardian. Prepared inputs and source stay read-only;
source/projection inventories are verified around the whole batch rather than
rehashing the complete repository for each suite. The Git exception is exactly
`safe.directory=/work`, with a distinct captured runtime flag; wildcard or
ambient Git settings remain rejected. Candidate output is bounded and encoded;
private root-owned reports and command files are outside the namespace.

Separate protected probes must capture the complete actual isolated full
environment before work and after every prior scope
has kernel-confirmed cleanup. Unknown/mismatching E, failed/missing/cancelled
commands or changed prepared/source inputs fail the diagnostic. Local tests
use real Git fixtures and fake suite launches only; they establish neither
privileged Ubuntu compatibility nor a complete runtime measurement. Even a
future hosted diagnostic pass has `authority=none` and `reusable=false`.
Authenticated producer/publisher provenance remains a separate prerequisite.
The isolated full environment has schema 3 and profile
`ubuntu24-isolated-host-qt5-qt6-v1`. Inside the protected probe, after readonly
mount validation, `runtime.capture_isolated_host_environment()` retains the
complete root-measured venv, Python, Node and Temurin17 installation identities
and its exact external certificate-store identity when selected. The captured
executable roots must match those identities. The parent checks the probe's
binding and rehashes prepared inputs after cleanup. These mandatory identities
remain in original E, suite fingerprints and the native whole-receipt hash;
bare legacy full E cannot enter isolated admission. No consumer VM is measured.

The shared diagnostic reuses the script's loaded controller module, so its
trusted `Unavailable` exception retains its explicit denial reason. A foreign
loaded module is rejected rather than replaced. Other failures retain the
nonzero unavailable result and expose only bounded public exception types,
errno names, trusted source callsites and operation stages. A bounded cause
chain preserves an earlier failure when cleanup also raises. Generic exception
text, command arguments, environment values and arbitrary filenames are not
reported. These diagnostics grant no execution, publication or reuse authority.

The account check accepts only sudo's complete single stdout denial line with
empty stderr. sudo 1.9.15's successful zero-command listing can exit 0: its
[privilege display](https://github.com/sudo-project/sudo/blob/SUDO_1_9_15p5/plugins/sudoers/display.c#L499)
returns success, and the [frontend](https://github.com/sudo-project/sudo/blob/SUDO_1_9_15p5/src/sudo.c#L1251)
maps that to exit 0. Grant listings, extra text and policy/authentication errors
remain unsupported; failure diagnostics expose only public counts, hashes and
classification markers.

The prospective
[`protected-project-tests.yml`](../tools/repository-checks/workflows/producers/protected-project-tests.yml)
and [`producer_workflow.py`](../tools/test-evidence/producer_workflow.py) prepare
the reusable-PR handoff. The existing route publishes an early descriptor, one
protected shared job executes the independently selected trusted commands, and
a separate native publishing job commits to the complete canonical receipt
hash. Other package owners and the existing Qt-free impact path remain intact.
Only an already selected full-host profile is eligible; this source does not
install Qt to obtain proof for a quick-only selection.

The dormant `protected-shared-producer-v1` generation pairs that callee with
[`producers/repository-checks.yml`](../tools/repository-checks/workflows/producers/repository-checks.yml).
The calling `project` job grants only contents, Actions, pull-request and checks
read access; the descriptor, shared executor and final publisher request that
same ceiling. Other jobs retain their existing permissions. Exact package and
Android generations bind the complete pair, preserving every older generation.
Caller and callee must be installed together after hosted qualification; neither
an individual approved file nor a matching job name authorizes publication.

The exact ordinary two-file installation from `android-owned-npm5-sync-ci-v1`
to this complete five-workflow tuple selects all 60 trusted suites once on
`main`, with reason `reviewed-protected-producer-transition`. The current
trusted tree must equal the PR base, and the complete candidate delta must
contain only the approved caller and callee; source, controller, registry and
platform profile remain unchanged. Existing candidate and trusted reader review
remains a prerequisite. This finite widening makes the eventual
installation PR eligible for the existing protected owner after its separate
activation prerequisites pass. It supplies no execution or publication proof.
Subsequent CI-only changes retain the existing 37-suite selection.

New isolated publication requires execution schema 3 and an independently
reconstructed source context: the original commit, its ordered immediate
parents, their tree identities and the actual shallow boundary. Legacy schema
1/2 validation remains available to its existing callers. The current 60 suites
read checkout content or self-created Git fixtures, rather than asserting
ambient history; their content fingerprints remain reusable across an unchanged
input closure. A future suite that consumes ambient commit/history semantics
must use the existing `candidate` scope. Source provenance is still checked for
every original receipt.

Runtime admission precedes candidate execution. Unavailable admission can leave
the existing mandatory nonreusable path selected; a started suite failure,
cancellation, timeout or changed post-execution environment cannot retry through
that path. Reports and command files stay outside candidate mounts, and only
the finished receipt becomes upload-readable after all scopes are empty.
The reviewed protected source capabilities and isolated policy permit a controlled
first native attempt. They supply no successful admission, execution or publisher.
Actual boundary/full-profile qualification, exact protected generation and
runtime-epoch deployment, native publisher qualification, Qt-free reusable
environment support and post-merge/child consumers remain incomplete. Offline
fixtures establish none of those hosted qualifications.

The prospective main-only parent consumer is
[`producers/parent-qualification.yml`](../tools/repository-checks/workflows/producers/parent-qualification.yml),
with its trusted implementation in
[`postmerge.py`](../tools/test-evidence/postmerge.py). Its source capability is
enabled, while the deployed legacy parent does not invoke it. It looks up the
exact current protected push before candidate checkout
or tool setup. Missing, stale, pending, failed, ambiguous, foreign or unsupported
proof leaves the existing actual test path selected once. The helper executes
no tests, retries no failed execution and captures no unused consumer runtime.

Admission retains the original PR merge commit and schema-3 receipt. The
read-only adapter independently authenticates original attempt 1, its complete
workflow generation, the successful final native publisher's whole-receipt
hash, original full environment, expiry and current protected integration.
Both complete source inventories and the original depth-2 Git context are
checked. Every trusted shared suite must have matching content closure;
candidate-scoped suites and changed declarations require actual execution.
The diagnostic consumer report lists reused and executed suites separately and
cannot become a new qualification artifact or renew original expiry.

`producer_workflow.controller_sources()` declares the finite reviewed producer
graph. Extra loaded repository modules fail producer admission. The consumer
reconstructs that identity from the original protected base only when all its
ordinary source/policy/template entries equal current reviewed immutable bytes;
it never executes historical Python or trusts a receipt's claimed policy root.
This is a new controller epoch. Earlier producer generations cannot supply its
proof. The isolated `/work` safe-directory runtime variant has a separate enabled
source capability; legacy runtime admission remains unavailable and unchanged.

The additive complete five-workflow generations permit installing this parent
while either the legacy or protected project owner is present. All 18 protected
previous generations remain valid, alongside the new CI37 producer tuple. The later protected-owner installation
still changes exactly its caller and callee and retains the approved parent.
The active manual diagnostic matches its canonical source. The actual protected
producer/consumer endpoints are not installed. Hosted boundary,
full-profile and final-publisher qualification, the protected runtime epoch and
the exact reviewed workflow installation are required before either producer or consumer can
authorize reuse. Child consumers remain separate work. A successful lookup
with no affected package inputs skips candidate
checkout and Node/Qt setup; affected independent package owners still execute.

The separate source-only CI37 profile is prepared in
[`ci_profile.py`](../tools/test-evidence/ci_profile.py),
[`runtime_ci.py`](../tools/test-evidence/runtime_ci.py) and the separate
[CI37 policy](../.github/ci37-runtime.json). Its environment has schema 2 and
profile `ubuntu24-ci37-v1`; legacy full Qt environment schema 1 remains separate
from the isolated full environment schema 3. Execution receipt schema 3 remains
unchanged. The exact ordered 37 CI owners, command
definitions and a conservative immutable executable/import/discovery/lookup
generation are mandatory. Three fixed Markdown leaves (`README.md`,
`tests/PROJECT_TESTING.md`, `docs/BRANCH_WORKFLOW.md`) may change bytes; their
membership and ordinary modes remain bound. The one additional data class is
the exact `.github/branch-cleanup.json` leaf under independent closed-schema
admission. Every workflow byte remains bound
because reviewed tests execute some YAML snippets. Changed
readers, unknown paths, extra commands, control-plane full owners and platform
suites require the existing full/nonreusable execution route.

The prospective capture records actual OS/image/namespace identity, the entire
installed Debian/Python package inventories, complete protected venv/Python/Node
file trees, Python startup and process flags, and actual Bash/Git/Node/CMake/
CTest/Ninja/Make/GCC/binutils identities. All system headers, GCC internals,
CMake modules, CRT and standard libraries remain conservative content inputs;
PIE startup objects, GNU linker-script referents and resolved ELF runtime
libraries are explicit. Unsupported tools, sysroots, lookup overrides, aliases,
linker scripts or incomplete inventories fail capture. There are no fabricated
Qt/GLM/Java capability fields or optional unknown identities.

Original-E admission and `plan_original_reuse()` perform no consumer tool or
environment probes. The pure plan requires exactly the same 37 original/current
owners and successful matching fingerprints using the unchanged original E.
It preserves original expiry, supplies no authentication or renewed receipt,
and cannot substitute full/quick environment projections. The existing native
adapter must independently authenticate the original schema-3 receipt and its
whole-receipt publisher hash before a caller may use that plan.

The dormant producer independently derives the exact owner from complete source
inventories before choosing this profile. Its protected projection includes the
fixed policy/readers; actual selected-profile capture and admission must pass
before any candidate suite starts. Unsupported CI37 capture selects the existing
actual fallback once; failures after candidate execution starts remain failures.
The native publisher still binds the whole original schema-3 receipt. The main
consumer independently derives both original and current 37-owner plans and uses
only authenticated original E. It creates no consumer environment or proof.

Source and policy flags permit a controlled native attempt. The production
generation binds the exact prospective installed workflow tree; changed implementation bytes
conservatively require actual fallback. The dormant protected producer selects
its profile before Java setup. Protected CI37 uses three prepared roots; the
full profile retains its existing four roots and Java/Qt prerequisites. A
successful pre-execution CI37 fallback restores Java before the existing legacy
path; a failure after execution starts cannot reach that fallback. CI37 adds no
prepared Java mount or Java environment/PATH entry; the system
`/usr` tree remains read-only. The CI37 schema asserts no Java capability.
The canonical manual diagnostic has a separate fixed `ci37` choice, using the
same protected source and cleanup checks with exactly 37 commands and actual E
before/after. Parent and probe independently bind the complete actual immutable
protected source, registry and real policy bytes. Its distinct diagnostic
selection derives that source's generation without changing the shipping future
generation. Production admission rejects that diagnostic selection even if the
two generation digests coincide.
Its result always has `authority: none`, `production_qualified: false` and
`reusable: false`. The active manual workflow includes the reviewed canonical
choice. No hosted CI37 capture, qualification, runtime
cost or speedup is established.

After final source composition, refresh host reader metadata/`REVIEWED_PROGRAMS`
first, then the prospective installed graph and CI37 definition/generation digests,
write the CI37 policy,
and refresh Android lock-reader anchors last. The exact CI37 JSON is outside
the product-reader digest. CI37 generation retains the exact Android
orchestration policy's path/mode/type but omits its SHA to break the second
cycle. Admission separately requires candidate == trusted == actual protected
root whole-blob identity; the returned selection binding and sealed controller
projection retain that SHA. No neighboring policy or reader is exempt.

The fixed cleanup-data class permits only bounded `holds` changes. Its seven
fields retain the exact fork identity, permanent branch topology, `keep-branch`
label and 30-day retention contract. Both complete immutable tree entries must
be ordinary existing blobs. Admission reads both object IDs through the
trusted bounded reader, checks the complete Git blob SHA1, rejects duplicate,
nonfinite or unknown JSON fields, and validates the closed schema. Producer
and protected probes use the existing config-free immutable Git reader;
postmerge uses a bounded fixed-fork Git blob API with no candidate checkout.
These data bytes stay in actual suite fingerprints rather than environment E.

A cleanup-hold JSON delta uses the existing full host route and independently
selects exactly 37 CI commands when all other generation inputs remain fixed.
The three variable Markdown leaves still use the documentation route and skip
host execution; the producer declines an unused descriptor. Other JSON/helper
changes retain existing actual execution. Source preparation and fake API/Git
tests establish this admission boundary, without hosted qualification or
activation. The canonical protected preparation implements independent profile
selection and the three-root CI37 setup; actual manual CI37 qualification is
still required before production enablement.
The focused offline checks are `python3 tools/test-evidence/ci-profile-test.py`
and `python3 tools/test-evidence/runtime-ci-test.py`, plus the focused
`ci-integration-test.py` and fake consumer cases; they use fake identity facts
and strict negative cases without compiling native fixtures or probing host tools.

The `android-build-inputs` quick suite checks dormant Phone and Pico APK source
planning with real immutable Git histories, including standalone npm locks,
native/Java/Gradle/Conan inputs, packaged resources, mode changes and stale reader
boundaries. It also runs in the combined host profile. The precise registry
closure binds its test, planner and shared immutable Git reader; global controls
bind Python import resolution. The [Android build-input guide](../docs/ANDROID_BUILD_INPUTS.md)
explains why this source plan neither changes the existing manual build triggers
nor proves external dependencies, build execution or reusable APKs.

The `ios-input-selection` quick suite exercises the dormant iOS repository-input
selector with temporary Git histories. It covers additions, deletions, renames,
file modes, symlinks, gitlinks, packaged resources and changed build readers.
The suite runs in both the quick and combined host profiles. Its registry closure
includes the test and selector implementation; shared controls also bind Python
import-resolution inputs. Missing inputs or unmatched proof require execution.

The selector is not active iOS routing or application-build evidence. Exclusions
apply only when both complete trees match the trusted reviewed reader boundary.
A stale boundary requires the application build, including a host-only change
after an earlier reader edit. Repository-input equality keeps exact commit/tree
provenance separate and never qualifies an older IPA for a new source revision.

The separately deployed `host-v1` iOS qualification generation uses this
selector while retaining its own required, same-run iOS host contracts. Its
finite independent inventory includes the reviewed CI ownership and receipt
helpers, workflow templates, policy files and exact generic control-plane
runner. These files are outside the protected iOS application configure,
resource, E2E and packaging reader graph; their shared `project-runner`,
`device-control-plane-full` and CI contract checks remain required when selected.
The exact executable-host inventory includes `tests/project-suite-self-test.py`
and the separately required Doctor CLI `tools/repository-health/check.py`,
preserving their known `100755` modes. Both application and own-host reader
boundaries are recomputed from protected `apple-ios` commit
`2fc894a0605103843b36653f250f854714a963ee`, never from an unprotected candidate.
Neither npm lockfile belongs to the unconditional CI-only inventory. Their
separate conditional omission requires an independently enforced exact package
owner and both reviewed application and own-host reader boundaries. Unknown neighboring
files, mode changes and historical application reader drift still require the
application build. This classification does not publish IPA or reuse evidence.

The schema 2 iOS host policy also recognizes the exact reviewed
`host-v1-compiler-data-v1` workflow tuple for the guarded compiler-data restore.
The existing `legacy` and `host-v1` tuples retain their identities. Same-run
host requirements and application input selection apply independently;
registering a workflow tuple supplies no build or test result.

The exact reviewed compiler-cache transition can omit the application build
while retaining the mandatory iOS host checks. Subsequent independent CI and
documentation changes can use the exact installed cache profile. Temporary
comparison entries are normalized to the original reviewed reader boundaries;
actual source identities and test inputs stay intact. Unknown cache bytes, modes,
readers or mixed product changes retain the ordinary application gate.

For those two ordinary lockfiles, a complete required JavaScript package owner
also permits omission when dependency changes exceed the focused security-fix
profiles. The full package checks must still succeed in the required repository
aggregate. Missing package ownership, mixed product/configuration changes,
nonordinary modes and historical native/iOS reader changes retain their gates.
The existing full S3 package job provides that required ownership. A full Browser
profile alone does not: the historical separate Browser run is not represented
by the package job's required receipt. That full-owner integration remains open;
the selector must not invent a required package result to omit other work.

The iOS qualification verifier has a staged `inputSelection` setting in its
trusted policy. An absent or false setting preserves the deployed workflow's
legacy route and final report, including its broad ordinary-Markdown exemption.
The enabled selector keeps packaged Markdown conservative, separates app-build
and iOS-host decisions, and binds the complete candidate selection to a digest.
The final verifier requires its own event and candidate checkout and recomputes
every route field; it does not accept a caller's reason or skipped-job claim.

No policy activation or workflow change is included. Enabled lightweight final
reports fail until an independently authenticated shared host owner is wired.
Before activation, stage that owner verification and the approved canonical
workflow outputs (`host_required` and `selection`) and final event/candidate
arguments through the parent policy. The existing template remains unchanged.
Do not replace this missing evidence with another unconditional iOS-host run.

Parent qualification uses the default-branch `tools/test-evidence/run.py`
controller against a separate clean candidate checkout. It records actual
executed suites and fingerprints rather than accepting the candidate runner's
claim about the selected inventory. The controller preserves timeout and
process cleanup, scopes disabled Git fixture maintenance to candidate
subprocesses, and removes GitHub tokens and Actions command-file variables from
those subprocesses. Receipt and virtualenv outputs must remain outside the
candidate's tracked/unignored source tree.

Reusable proof requires the actual supported host environment, including
toolchain, Qt backends, package versions and relevant flags. An unsupported
identity still runs the required full verification but produces no reusable
pass. An isolated sync validator independently checks full candidate inputs,
actual environment, original provenance and expiry; it executes unmatched
shared suites and declared product suites. See the
[reuse protocol](../docs/BRANCH_WORKFLOW.md#exact-parent-test-reuse).

The following inventory is generated from the runner's common and native
suites. Regenerate it with `python3 tools/repository-policy/check.py --write`
after changing their registration; do not maintain a second list manually.
Product suites stay in [`platform-profile.json`](platform-profile.json); list
them for this checkout with
`python3 tests/run-project-tests.py --platform-only --list`. Keeping product
entries out of this shared table allows it to propagate unchanged to children.

<!-- generated:test-suites:start -->
| Suite | Layer | Run individually |
| --- | --- | --- |
| `dependency-releases` | `quick` | `python3 tests/run-project-tests.py --suite dependency-releases` |
| `test-evidence` | `quick` | `python3 tests/run-project-tests.py --suite test-evidence` |
| `producer-proof` | `quick` | `python3 tests/run-project-tests.py --suite producer-proof` |
| `host-producer-preparation` | `quick` | `python3 tests/run-project-tests.py --suite host-producer-preparation` |
| `producer-api` | `quick` | `python3 tests/run-project-tests.py --suite producer-api` |
| `attested-runtime` | `quick` | `python3 tests/run-project-tests.py --suite attested-runtime` |
| `project-runner` | `quick` | `python3 tests/run-project-tests.py --suite project-runner` |
| `python-test-runner` | `quick` | `python3 tests/run-project-tests.py --suite python-test-runner` |
| `host-selection` | `quick` | `python3 tests/run-project-tests.py --suite host-selection` |
| `repository-checks` | `quick` | `python3 tests/run-project-tests.py --suite repository-checks` |
| `android-ci` | `quick` | `python3 tests/run-project-tests.py --suite android-ci` |
| `android-orchestration` | `quick` | `python3 tests/run-project-tests.py --suite android-orchestration` |
| `android-owner-transfer` | `quick` | `python3 tests/run-project-tests.py --suite android-owner-transfer` |
| `android-build-inputs` | `quick` | `python3 tests/run-project-tests.py --suite android-build-inputs` |
| `codeql-selection` | `quick` | `python3 tests/run-project-tests.py --suite codeql-selection` |
| `browser-cpu-selection` | `quick` | `python3 tests/run-project-tests.py --suite browser-cpu-selection` |
| `ios-build-qualification` | `quick` | `python3 tests/run-project-tests.py --suite ios-build-qualification` |
| `ios-input-selection` | `quick` | `python3 tests/run-project-tests.py --suite ios-input-selection` |
| `repository-policy` | `quick` | `python3 tests/run-project-tests.py --suite repository-policy` |
| `policy-consistency` | `quick` | `python3 tests/run-project-tests.py --suite policy-consistency` |
| `documentation-contracts` | `quick` | `python3 tests/run-project-tests.py --suite documentation-contracts` |
| `repository-doctor` | `quick` | `python3 tests/run-project-tests.py --suite repository-doctor` |
| `repository-maintenance` | `quick` | `python3 tests/run-project-tests.py --suite repository-maintenance` |
| `branch-policy` | `quick` | `python3 tests/run-project-tests.py --suite branch-policy` |
| `branch-name-guard` | `quick` | `python3 tests/run-project-tests.py --suite branch-name-guard` |
| `branch-cleanup` | `quick` | `python3 tests/run-project-tests.py --suite branch-cleanup` |
| `sync-test-reuse` | `quick` | `python3 tests/run-project-tests.py --suite sync-test-reuse` |
| `workflow-action-pins` | `quick` | `python3 tests/run-project-tests.py --suite workflow-action-pins` |
| `release-bundle` | `quick` | `python3 tests/run-project-tests.py --suite release-bundle` |
| `workflow-contracts` | `quick` | `python3 tests/run-project-tests.py --suite workflow-contracts` |
| `repository-health` | `quick` | `python3 tests/run-project-tests.py --suite repository-health` |
| `issue-intake` | `quick` | `python3 tests/run-project-tests.py --suite issue-intake` |
| `project-coverage` | `quick` | `python3 tests/run-project-tests.py --suite project-coverage` |
| `codeql-remediation` | `quick` | `python3 tests/run-project-tests.py --suite codeql-remediation` |
| `javascript-behavior` | `quick` | `python3 tests/run-project-tests.py --suite javascript-behavior` |
| `device-e2e-contracts` | `quick` | `python3 tests/run-project-tests.py --suite device-e2e-contracts` |
| `device-control-plane-full` | `host` | `python3 tests/run-project-tests.py --suite device-control-plane-full` |
| `documentation` | `quick` | `python3 tests/run-project-tests.py --suite documentation` |
| `safe-landing-lifecycle` | `host` | `python3 tests/run-project-tests.py --suite safe-landing-lifecycle` |
| `embedded-web-policy` | `host` | `python3 tests/run-project-tests.py --suite embedded-web-policy` |
| `embedded-web-qml` | `host` | `python3 tests/run-project-tests.py --suite embedded-web-qml` |
| `web-entity-visibility` | `host` | `python3 tests/run-project-tests.py --suite web-entity-visibility` |
| `places-native-qml` | `host` | `python3 tests/run-project-tests.py --suite places-native-qml` |
| `account-auth-dispatch` | `host` | `python3 tests/run-project-tests.py --suite account-auth-dispatch` |
| `lod-preferences` | `host` | `python3 tests/run-project-tests.py --suite lod-preferences` |
| `goto-dialog-script` | `host` | `python3 tests/run-project-tests.py --suite goto-dialog-script` |
| `recorded-voice-native` | `host` | `python3 tests/run-project-tests.py --suite recorded-voice-native` |
| `recorded-voice-qml` | `host` | `python3 tests/run-project-tests.py --suite recorded-voice-qml` |
| `snapshot-native` | `host` | `python3 tests/run-project-tests.py --suite snapshot-native` |
| `snapshot-qml` | `host` | `python3 tests/run-project-tests.py --suite snapshot-qml` |
| `document-tree-native` | `host` | `python3 tests/run-project-tests.py --suite document-tree-native` |
| `obj-material-native` | `host` | `python3 tests/run-project-tests.py --suite obj-material-native` |
| `native-smoke` | `quick` | `python3 tests/run-project-tests.py --suite native-smoke` |
| `native-ci-policy` | `quick` | `python3 tests/run-project-tests.py --suite native-ci-policy` |
| `native-registration` | `quick` | `python3 tests/run-project-tests.py --suite native-registration` |
| `device-result-schema` | `quick` | `python3 tests/run-project-tests.py --suite device-result-schema` |
| `device-jenkins` | `quick` | `python3 tests/run-project-tests.py --suite device-jenkins` |
| `desktop-input-protocol` | `quick` | `python3 tests/run-project-tests.py --suite desktop-input-protocol` |
| `performance-contracts` | `quick` | `python3 tests/run-project-tests.py --suite performance-contracts` |
| `server-console-behavior` | `quick` | `python3 tests/run-project-tests.py --suite server-console-behavior` |
| `source-layout` | `quick` | `python3 tests/run-project-tests.py --suite source-layout` |
| `shared-script-behavior` | `host` | `python3 tests/run-project-tests.py --suite shared-script-behavior` |
| `native-ctest` | `native` | `python3 tests/run-project-tests.py --suite native-ctest` |
<!-- generated:test-suites:end -->

Pull requests run the `issue-intake` contracts through the required central
repository/project gate. Its registered command remains
`python tests/issue-intake-test.py`, including the CI37 owner set. Both the
source generation 13 and reviewed generation 22 recipes retain that owner and
their required host-result aggregation. The dedicated Issue intake workflow
handles issue, milestone, scheduled and manual reconciliation; it has no
separate pull-request contracts job.

## Complete portable host contracts

```bash
build/host-tests-env/bin/python tests/device/run_control_plane_tests.py --profile full \
  --require-qml --timeout-seconds 900 \
  --junit build/test-results/device-e2e-control-plane.xml
```

This gate runs the complete control-plane self-tests, artifact identity/SBOM
validation, selected standalone production C++ regressions, and QML contracts
on the host. `--require-qml` makes unavailable
required host checks fail instead of skip. It needs no connected target and
does not build the complete Overte client. The shared CI runs it as part of
the combined host profile above; run this separate command when focusing on the
control plane itself.

The full self-tests use two isolated Python worker processes, keeping each test
module together. Re-exported test classes loaded under a synthetic module name
are reloaded through their importing module, while their original test IDs remain
the basis for selection and execution accounting. Every discovered case is retained; global Python mocks and
environment changes are never shared between workers. Temporary target locks
belong to their individual fixtures. Use `--self-test-jobs 1` on this command
for serial debugging. Worker failures, import failures, missing cases and
timeouts fail the gate; reports include deterministic module output and counts.
Parallel workers require Linux process cleanup support. Other hosts default to
serial execution. The parallel run also writes
`build/test-results/device-self-tests.json` with selected/loaded case identities
and execution counts, which CI retains with the JUnit reports.

Other drivers under `tests/device/contracts` require separately prepared hosts
(for example Qt Quick, V8, or platform SDKs) and are not all selected by this
gate. Follow their owning platform instructions and each driver's prerequisites.
Likewise, server-console dependency compatibility tests and Electron smoke tests
need the dependencies declared in `server-console/package.json`; only the three
dependency-free behavior files run in the common quick profile. This gate does
not claim that those separate environments were tested.

<a id="full-profile"></a>

## SafeLanding host lifecycle regression

The common host suite compiles the SafeLanding header and implementation with
real Qt signals, bounded thread scheduling, and entity/render fixtures. It runs
both the Pico physics-only handoff and the shared visual-readiness path. Physics
readiness is substituted and the mutex has scheduling hooks; this is host
synchronization evidence, not a product build or device acceptance.

~~~bash
python3 tests/run-project-tests.py --suite safe-landing-lifecycle --timeout 240
SAFE_LANDING_QT_CORE=Qt5Core python3 tests/safe-landing/test_safe_landing_lifecycle.py
~~~

The host profile uses Qt 6 Core development files, pkg-config, moc, and c++.
The explicit Qt 5 command requires matching Qt 5 Core development files and moc.
Missing prerequisites fail the suite. See
[the suite guide](safe-landing/README.md) for isolated baseline reproduction,
negative controls, and later native/Pico qualification. The Pico runtime-parity
copy should delegate to this common suite when the change reaches its child
branch, so there is one authoritative driver.

## Native C++/Qt suites

For document-root, symlink, index, and SSI regressions, the
[embedded-webserver guide](embedded-webserver/README.md) also provides a focused
Qt5 build of the actual product library and its registered native test.

The selective PR lane is described in the [native CI guide](../tools/native-tests/README.md).
It routes from the exact merge candidate, builds affected production/test targets,
and runs bounded headless Qt tests. Documentation and known host-only changes do
not start a native build. The existing `repository-checks` aggregate requires the
selected native result; host sync qualification cannot substitute for it. Its
broad dependency environment must be prepared and qualified before activation.
This local wiring does not establish that the gate is deployed on GitHub.

Exact `package.json` and `package-lock.json` changes in `browser-client`,
`browser-direct-client`, and `script-archive/marketplace/S3Server` belong to
their JavaScript packages and do not select an Overte native build. Browser
workflows, package behavior checks and security checks retain their ownership.
This is an exact manifest exemption: accompanying native/build inputs, unknown
neighboring files and non-regular changes retain conservative native validation.

The versioned S3Server required-package policy selects `main`; the six child
branches retain legacy compatibility until their explicit activation. Its trusted
controller is `tools/repository-checks/package_checks.py`; the approved exact
workflow generations remain in `tools/repository-checks/workflows/packages/`.
Local activation wiring does not establish deployment on GitHub. The existing
tool CLI still accepts only
`server-console` and `tools/jsdoc`; adding S3 to a caller string cannot bypass
the full host checks.

The controller independently computes two decisions from the exact
candidate: `host_mode` and an OR-selected `package_set`. Regular S3
`package.json`/`package-lock.json` changes can use a bounded Node.js 22 lane:
one `npm ci --ignore-scripts --no-fund --no-audit`, one complete
`npm audit --audit-level=low`, and `npm test`. There is no S3 build script.
Mixed browser, native, unknown or non-regular changes retain their normal host
and native checks and still select S3 whenever its inputs changed. Unknown push
history conservatively selects full host checks and S3. Removed or non-regular
required npm manifests cannot produce successful package evidence.

The new project aggregate always checks every selected result and binds its
receipt to the candidate commit, full tree and trusted plan. The required outer
aggregate recomputes that plan and verifies the receipt. Legacy tool checks have
one owner; S3 has a separate owner even during delegated syncs. A bounded sync
does not run S3 again or claim a successful S3 JUnit case: it records the external
required package owner. Parent qualification owns parent pushes, and the shared
project workflow owns leaf pushes, preserving the current branch partition.

Deployment requires two stages. The trusted helpers and approved templates
must land on the default branch before installing the exact project, parent and sync
templates plus the appropriate outer caller. The package caller with direct
browser checks is separate from the existing approved browser generation, which
remains valid. Finally activate `package_checks_required_branches` in trusted
repository policy for each reviewed target. Until activation legacy callers stay
valid; a new caller must prove the strict receipt contract whenever it is used.
PR activation uses the exact base repository and branch, never the head branch.
Push activation uses the qualified branch in the event ref. A manual run with an
unqualified ref additionally requires matching trusted runner branch metadata;
tags, missing refs and malformed identities fail closed. Activating `main` does
not activate old child push or manual callers.
S3-only sync shortening additionally requires activation and exact approved
workflow blobs in both the protected target and merge candidate, so partially
propagated child branches retain full validation. Browser package profiling is
separate work; this foundation does not remove browser build variants.

The trusted package helpers additionally define an internal `include_browser`
capability, disabled in every current CLI and workflow call. It recognizes only
the exact Browser `package.json` and `package-lock.json` paths. With a trusted
opt-in, their pure union with S3/JSDoc/server-console manifests selects the
applicable package owners; mixed, unknown and nonregular inputs retain full host
fallback and independent S3 coverage. Candidate JSON cannot enable this flag.

The prepared Browser profile in `tool_dependencies.py` performs one install
with scripts and the install audit disabled, one full `low` audit, the existing
`npm run build`, and `npm test`. It verifies the reviewed build/prebuild/test
script definitions and rejects new build/test lifecycle hooks before installing.
The build still runs avatar preparation, which can read or fetch avatar inputs.
Fake-command tests establish ordering and failure propagation only: no Browser
build, unit suite, avatar preparation or E2E journey is qualified by this change.
Development-only lock metadata does not authorize a journey omission.

Deployment must bind the capability to independently recomputed required plans,
exact complete caller generations and successful package receipts. Transfer
standalone Browser manifest triggers atomically with that required owner so it
does not add a third install/build to the existing two Browser jobs. Preserve
meaningful browser/native journey ownership until its replacement is separately
reviewed; this helper does not activate a Browser gate or change any trigger.

The separate `npm_consumers.py` capability is selected automatically by the
complete approved `npm-consumers-v1` caller generation. The controller
independently compares complete immutable base and candidate trees and adds
focused consumers to the required package plan. It recognizes only the reviewed
`source-map-js` 1.2.1 to 1.2.2 update and `proxy-addr` 2.0.7 to 2.0.8 update.
Both historical and candidate package readers, ancestor configuration discovery,
all other lockfile entries and exact updated version/integrity metadata must
match reviewed inputs. Other updates retain their existing package owners;
unrelated CI/native changes neither expand nor replace package ownership.
Formatting-only reviewed lock changes select no execution. Unknown metadata
never becomes a passing test result.

The focused executor independently recomputes its selection, requires a clean
exact candidate and Node 22 (at least 22.12) with npm 10, disables ambient Node
and npm configuration and rejects materialized untracked npm configuration.
Every package npm command pins its exact package prefix and disables workspace
discovery, so an outer workspace or project `.npmrc` cannot replace the checked
package context.
Each selected package receives one script-free `npm ci`, one complete
`npm audit --audit-level=low` and its trusted functional probe. The S3 package
also retains its existing `npm test` without pre/post lifecycle hooks. The
source-map probe exercises mapping bounds, nested offsets, enumeration work,
serialization, sorting without string code generation and actual PostCSS map
consumption. The proxy probe exercises IPv4-mapped/IPv6 trust, forwarded chains
and actual local Express request address behavior. Neither profile selects
Vite, a Browser renderer/journey, or a native application build. These omissions
apply to the finite reviewed dependency/consumer closure, not arbitrary npm
updates. The required package receipt binds these exact profiles; the paired
Browser metadata route omits both legacy jobs for the same reviewed selection.

The approved `npm-consumers-v1` generation binds all five workflows together:
the existing project, parent-qualification and sync workflows, plus the paired
repository caller and Browser workflow in
`tools/repository-checks/workflows/npm-consumers/`. A complete approved pair
automatically enables consumer selection consistently in the package CLI and
both outer verifiers; candidate JSON and caller flags cannot enable it. Legacy
four-file callers retain their behavior. Once the protected base contains the
new generation, a candidate cannot revert to the legacy owner or opt out.

The paired Browser workflow preserves every existing Browser/native journey
step and manual input. Its metadata route omits both existing jobs only for an
exact focused package owner or reviewed formatting-only lock change. Unsupported
dependencies, changed Browser consumers, failed routing or missing outputs keep
the existing full jobs. Cancellation stops obsolete work. The paired repository
caller uses the independently selected package host mode, allowing formatting
changes to omit all test jobs without fabricating an execution receipt. These
active workflows match those exact admitted templates. Deployment on each child
requires complete genuine parent propagation; a local matching file is not
evidence that the child has been updated on GitHub.

Run the source selection and execution-boundary regressions with:

```bash
python3 tests/repository-checks-test.py NpmConsumerSelectionTests -v
```

The actual locked Node 22 qualification passed both new dependency probes and
both complete npm audits, preserved the S3 application test, and rejected the
old dependency regressions separately. Local execution does not certify a
hosted workflow, an activated merge gate, or a Browser/native journey.

The ordinary shared-host receipt producer is also staged and inactive. Its
alternate full workflow is
`tools/repository-checks/workflows/producers/project-tests.yml`; the existing
package templates and active workflows remain unchanged. The full host job
checks out trusted policy separately, installs its recursively pinned host/SBOM
requirements into an external virtual environment, and runs the trusted
`tools/test-evidence/run.py` against the exact clean candidate. It executes the
complete trusted shared inventory plus validated branch-owned platform suites,
retains the existing Qt5/Qt6, Node, Java and namespace prerequisites, and writes
an actual execution receipt and JUnit report outside the candidate checkout.
Failed suite runs keep their failure status and upload any resulting receipt
for diagnosis. Missing receipts cannot certify success.

`.github/package-workflow-generations.json` is trusted default-branch policy.
It approves complete four-workflow Git blob/mode tuples for both existing
package callers and their receipt-producing successors. Individual approved
files cannot be mixed into an unapproved tuple. The same comparison applies to
ordinary `.github`-only checkouts and independently authenticated API trees.
Candidate generation manifests have no authority. The package plan binds the
generation manifest, templates, actual trusted helper inputs and recursive
requirements. Missing trusted inputs from an existing sparse layout are read
as bounded ordinary blobs from its exact Git HEAD; ordinary deletions, aliases
and unknown or corrupt policy fail closed.

The `host-producer-preparation` quick suite covers this compatibility contract.
Receipt artifacts are diagnostic execution records, not authenticated producer
authority. A receipt's `reusable` field describes input/runtime eligibility; it
does not authorize an omission. There is no early descriptor, publisher
aggregate, API dispatch, artifact consumer or ordinary-PR reuse activation in
this slice. Those require independent exact event/candidate/source/run-attempt
authentication and complete owner verification before any checks can be waived.


Prepare a native build with `OVERTE_BUILD_TESTS=ON` using the relevant
[build guide](../BUILD.md). Then run the project full profile against it:

```bash
python3 tests/run-project-tests.py --profile full \
  --native-build-dir build-tests --timeout 1800
```

Replace `build-tests` with the directory you configured. This profile adds
[`project-native-test.sh`](project-native-test.sh), which builds `all-tests` and
runs CTest with `--output-on-failure --no-tests=error`.
`OVERTE_TEST_BUILD_CONFIG` selects the configuration and defaults to `Debug`.
The project full profile and the full portable host command above are distinct
layers; neither establishes physical-device acceptance.

<a id="coverage-interpretation"></a>

## Target runtime and coverage

For emulator, simulator, and device checks, use the owning
[platform guide](../docs/interfaces/README.md) and the
[device harness](device/README.md). Record the actual source revision,
environment, output, and any missing capability. A host fixture pass is not a
device pass; a successful input command is not proof of the resulting behavior.

[`project-coverage.json`](project-coverage.json) maps code areas to repository
checks, native groups, and hardware/system acceptance layers. Its test rejects
newly registered but unmapped native groups. This is an area inventory, not a
line-coverage measurement or proof that every behavior is tested. See the
[architecture map](../docs/ARCHITECTURE.md) for source entry points.

GPU drivers, physical audio, deployed distributed behavior, and headset
tracking/thermal behavior require the corresponding runtime evidence. Collect
native line coverage from an instrumented configured CMake build when needed.
Intentional legacy syntax exceptions remain exact allowlists; the health suite
rejects new or stale exceptions.


## Dormant required Android orchestration

The `android-orchestration` quick/host group verifies the next required Android
owner with disposable Git trees and mocked test processes. Its canonical caller
and reusable workflow are under `tools/repository-checks/workflows/android/`
and `tools/repository-checks/workflows/android-required.yml`. Active workflows,
platform profiles, existing advisory checks and scheduled/manual diagnostics
are unchanged. This preparation saves no live CI time yet.

The trusted `android_gate.py` controller derives the target, exact ordered merge
parents and full immutable source delta from the runner event and Git objects.
Outer routing, the reusable workflow and the final verifier independently derive
the candidate, plan and complete owner inventory. Caller outputs cannot select
views or waive cases. Every selected PR, including parent synchronization and
reconciliation, owns the union of fast/contracts/coverage/VR/Pico plus critical
mutation exactly once: 40 distinct executions. The Java 21 Robolectric owner is
separate from the shared Java 17 environment. Distinct JaCoCo, native gcov and
JavaScript coverage executions remain meaningful independent variants.

Reviewed current branch inventories are 80 Robolectric / 21 native / 30 Pico
cases for Android main and VR; Phone has 116 / 23 / 30, and Pico has 80 / 21 / 39.
Phone's nine focus methods at API 26 and 35 are mandatory minimum source
coverage. Missing classes, methods, SDK variants or reported assertions fail.
Additional simple Phone test classes are discovered from the complete Git tree,
including `.github`-only sparse checkouts. These are source and offline fixture
observations; no new product, Gradle, native or Robolectric execution is claimed.

A selected execution installs Qt 5, Node 22, Java 21 and trusted external host
tools. `android-host-prepare.sh` pins gcovr 8.4, Ruff 0.15.22 and ShellCheck 0.11.0;
the Ruff wheel and ShellCheck archive have fixed hashes. Actual tool identities
and the preparation/controller sources are bound to the runtime/plan. Candidate
commands inherit the existing fixed Git maintenance and credential/Actions
command-file stripping policy. The virtualenv, reports and actual execution
receipt stay outside the immutable candidate. Failed or incomplete owners block
the inner and outer final checks; uploaded receipts are diagnostic records,
not authenticated reusable artifact authority. An empty union performs no Android
tool setup and accepts no fabricated successful execution receipt.

Only verified empty tree deltas or changes within the exact reviewed independent
Browser and repository administration roots can omit Android executions. Both
complete trees must match the branch's reviewed reader-complement anchor. Unknown,
mixed, nonregular, root package, packaged Markdown and changed-reader inputs take
the full union. Historical reader drift also forces the full union. The anchors
are conservative source reviews, not an automatic dependency graph; a future
handoff must review and refresh them after its final source changes.

The four existing complete package workflow tuples remain approved. Four
additional exact tuples pair either shared project generation with either Android
caller. The Android callee must also match its trusted canonical blob; individually
approved files cannot be freely mixed. The generation manifest and actual helper
sources are bound in the plan. The older package templates remain byte-identical.

Activation is deliberately unavailable: trusted `required_branches` is empty,
two explicit blockers remain, and `ACTIVATION_READY` is false in the controller.
Clearing JSON fields alone cannot authorize deployment. A later reviewed change
must transfer advisory/profile ownership atomically, preserve the other 12 common
or 18 Phone profile suites, and transfer the `android-long-diagnostics` and manual
mutation/stability/endurance/regression prerequisites. Simply disabling the old
ordinary jobs would skip label-selected jobs through their existing `needs`.
Their exact transfer is outside this preparation. Manual ordinary verification
preserves the existing first-five-view behavior; critical mutation remains
mandatory on every selected PR. No branch-name waiver or evidence reuse is added.

## Staged selection for CI-only changes

The retained-source Android parent recipe first authenticates a small dispatch
plan on `android-main` and `android-vr`. It starts a separate platform job only
when that independently derived plan selects Android commands; common tests and
selected platform tests then run in parallel. Package and documentation routes
retain their own required owners. Main and Apple parents skip this dispatch job
because their reviewed platform profile is empty. The final parent check
recomputes the candidate and complete plan; dispatch outputs are never test
evidence, and a required platform failure still blocks qualification.

The staged host workflow in `tools/repository-checks/workflows/host/project-tests.yml`
uses the default branch's trusted `host_selection.py` controller. It recomputes
the exact package/candidate plan before selection and again before execution.
For explicitly reviewed CI and cleanup paths it runs the 36 CI contract groups while
omitting the 16 production host groups, seven unchanged product quick groups,
and their Qt development installation.
This is dependency-based impact selection; an omitted group is not reported as
a successful test or reused evidence.

Four exact shared inputs retain explicit mandatory owners: `.github/workflows/issue-intake.yml`
keeps `workflow-contracts`, the chat QML fixture keeps `shared-script-behavior`, and
both Snapshot Python fixtures keep `snapshot-qml` and `snapshot-native` under their
complete declared fixture/import root. The controller checks complete ordinary
base and candidate entries, including historical differences absent from a path
hint, and unions these owners with the existing CI and Device selections. A finer
dependency selector cannot remove a mandatory owner. Missing or nonregular entries,
unknown inputs and unreviewed reader changes keep the full fallback; an absent
required registry owner is an error. These admissions do not remove Device reader
inputs, broaden CI independence, or waive the required host work.

The `apple-ios` Device reader graph has additional unproved code edges, so an
actual change to any of the three mapped chat/Snapshot fixtures also retains
`device-control-plane-full` for that target, including hidden base/candidate
differences. The finer selector cannot remove this owner. An issue-workflow-only
change does not add Device, and the proved main, Apple parent and four Android
reader scopes keep their precise mapped owners. Unknown targets retain the full
fallback. The cumulative source rollout already changes the two independently
Device-owned eligibility fixtures; this conservative rule adds no work there.

The exclusion requires the exact reviewed host reader, discovery, manifest,
fixture and production-source generation in the candidate and trusted checkout.
Six separately reviewed child inventories preserve their own production sources,
platform profiles and both npm lockfiles. They are CI-only topic contents, not
completed parent synchronizations. The target comes from the independently
validated server event, never from the head branch or candidate policy. Unknown
historical differences, changed readers, mixed product changes, symlinks,
submodules and incomplete inventories retain every shared and declared platform
suite. The exact 32 additional CI paths are listed in `CI_ROLLOUT_PATHS`; no
directory-wide exemption for `tools/test-evidence` or `tests` is added.

The app selector separately classifies exactly the issue-intake workflow, its
installed-wrapper test and installer, the chat QML fixture, both Snapshot Python
fixtures and the two Android eligibility fixtures as independent of the reviewed
iOS configure/build/package/E2E graph. Both immutable trees must match the reviewed
app-reader complement and expected ordinary modes. This skips app work only:
`ios/tests/run-tests.sh` directly executes the chat and Snapshot fixtures, so the
required iOS host remains selected. Unknown neighbors, executable or aliased
fixtures, mixed product changes and historical reader drift retain app work or
fail source validation. No IPA, test PASS or reusable evidence is inferred.

For mixed CI and npm-lock changes, the trusted package plan can separately own
the two reviewed security updates or formatting-only changes. The shared host
controller validates that plan's candidate/tree/base binding and complete
consumer generation. Exactly these two foreign lock paths are excluded from the
reviewed product reader identity; changed locks still require their own mandatory
owner and ordinary entries on both snapshots. An unchanged lock after integration
does not cause a later CI-only PR to fall back to full host execution. Every
other file, mode, import/discovery member and product definition remains bound,
including the independently consumed `tests/device/ios/package-lock.json`.
The independently required package lane still installs, audits
and tests the changed dependencies; the host selection reports their external
ownership without inventing a successful or reusable test. Missing package
ownership, unsupported dependencies, absent/nonregular base entries and product
reader differences retain the complete host suite. This optimization applies
to the shared host controller; the separate sync fallback still requires its
own reviewed selection and authenticated result handoff.

The initial child CI rollout changes the control-plane launcher's process cleanup.
It therefore runs the 36 CI groups **and** `device-control-plane-full`, including
its real `--require-qml` checks, prepared host dependencies and 900-second timeout.
The other 15 host groups and unchanged platform declarations are omitted only
for the reviewed complete branch graph. Subsequent unrelated CI changes run 36
groups without Qt setup. A new reader, command, profile, optional header or import
search-path entry invalidates the exclusion. Registry host definitions and controls,
actual launchers and runtime helpers remain in the immutable reader identity.
The consumed OpenXR `android/vr/common/openxr/README.md` and Phone parity
`android/phone/device-tests/parity/fixtures/README.md` remain bound too; Markdown
alone does not make these fixtures independent.

`full_host` remains the workflow's compatibility signal for Qt prerequisites.
The 37-group route reports `full_host=true`, `complete_receipt=false`; needing Qt
does not mean all 59 shared groups ran. A complete receipt requires the exact
full trusted suite inventory, all declared platform suites and no new candidate
commands. Selection reports list omitted shared and platform groups explicitly.
Local selector tests and fake command runs do not qualify the actual 37-group
execution; that remains a required hosted deployment check. Deploying the CodeQL
results caller on a child with the original workflow also needs its separately
reviewed base-only transition; host admission does not grant it.

Deployment requires the staged complete workflow tuple to be reviewed and landed
on main before replacing the active callee. The unchanged required aggregate
still blocks merging if host execution fails or is unexpectedly skipped.

On `main`, `.github/workflows/parent-qualification.yml` now deploys the canonical
`tools/repository-checks/workflows/host/parent-qualification.yml` generation and
applies the same impact selection after merges. Other parent branches receive
this workflow through their reviewed CI propagation. The complete workflow tuple
is admitted by trusted policy before deployment. Selection runs before Qt installation. Reviewed CI-only pushes run the CI groups; product,
unknown, changed-reader and nonregular inputs retain the full host route.
New candidate command variants run in the impact executor and cannot produce a
legacy full-inventory receipt unless all commands have a supported receipt.

An ordinary native PR or protected push with an exactly unchanged complete Git
tree can select `host_mode: unchanged`. The trusted router verifies raw commit
hashes, ordered PR merge parents or forward push ancestry, the full immutable
inventory, and native repository/event/ref identities. PR label inventory must
be present; an explicit Android diagnostic request retains real execution.
An empty supplied path list is insufficient. The required aggregate independently
recomputes this proof and requires skipped jobs with exactly empty outputs.
This route starts no host/package test and produces no execution receipt.

The dormant `protected-producer-original-default-v1` recipes extend that proof
to authenticated synchronization and protected-parent scheduling. They recheck
the complete current candidate and protected workflow source before omitting
setup, then verify native validation steps and repeat source/topology bookends
at the final gate. An unchanged parent also omits Android platform execution.
Its report has `execution: null` and carries no reused suites, test passes,
JUnit results or reusable evidence. These canonical recipes require the complete
reviewed installation and hosted qualification; source-only preparation does
not enable result reuse. The active source13 parent retains its historical Node
setup until that installation.

Protected candidate identity reads use `git --no-optional-locks` to preserve the
private immutable index while retaining the complete snapshot verification.

Protected execution presents ordinary Git files as physically read-only files.
Tests must keep logical Git modes, exact source bytes and alias checks intact;
when a test intentionally edits a temporary copy, make only that copied leaf
writable. Never change the original snapshot permissions. Synthetic native-event
fixtures that clear their environment must supply Git's safe-directory setting
for their exact trusted checkout, without a wildcard or inherited configuration.
The device control-plane runner prints failed group names at the end of a failed
run so bounded host diagnostics retain the failing group without exposing its
arbitrary output.
For failed parallel Python self-tests, the final line also reports up to four
failed module basenames and their total count from the current bounded report.
This diagnostic stays within 450 ASCII bytes so the protected host's 512-character
tail retains it. Missing, stale, aliased or invalid reports are reported as
unavailable; serial runs do not read a parallel report. This output never changes
test status, timeouts, coverage or evidence authority.

Under the current reviewed catalog and ownership policies, rare controller-source
upgrades after installing generation 22 use governed maintenance: normally install
complete generation 13 (`npm-consumers-sync-ci-v1`) on main and all six children,
restore Android's six original owner/contract files, and preserve every required
owner and platform profile. Upgrade controller source through the normal 13 checks,
then obtain fresh native 22 qualification before reinstalling 22. This sequence
does not authorize automatic downgrades, waive B/D source checks or mint E. Routine
product PRs with unchanged controllers need no staging.

Original evidence lookup on the four parent branches can traverse at most eight
normal, exactly equal-tree integrations whose native PR and parent jobs prove
that no tests executed. The lookup retains the original execution's base,
candidate, default source, environment and expiry; the original merge time
still bounds publication. Every hop and the current protected parent are
independently authenticated. A failed, retried or execution-bearing newer run
cannot expose an older passing result. Leaf branches retain their existing
direct lookup; this is not transparent historical reuse on all seven branches.

The canonical Documentation push owner on `main`, `android-phone`,
`android-vr-pico` and `apple-ios` also supports the unchanged-tree route. Its
early output only schedules a sparse candidate checkout. The trusted
`postmerge.py --verify-empty --candidate <checkout>` entrypoint independently
checks the complete raw candidate, current source and native Documentation job
again before suppressing the three standalone documentation commands. It does
not wait for a parallel parent/project job, capture an environment or publish
test passes. The result remains `reusable: false`, `execution: null` and has no
evidence authority. Missing initial proof keeps the existing documentation
fallback; changed proof during final verification fails the owner. These source
contracts still require actual native qualification before reuse is enabled.

A partial parent run uploads its real JUnit results and a diagnostic
`host-selection.json` with the exact candidate, package plan, selected and
omitted names, and `reusable: false`. That report makes no passing claim for
omitted tests. It does not publish `qualification.json` or the legacy reusable
qualification artifact. Complete executions retain the existing schema-2
creator and full-inventory receipt checks. Until authenticated partial-evidence
reuse is implemented, synchronization consumers treat an absent/partial parent
qualification as unavailable and execute their required shared and platform
tests. PR/push evidence reuse remains a separate unfinished optimization.

The complete `npm-consumers-sync-ci-v1` successor admits the staged
`tools/repository-checks/workflows/sync-ci-selection.yml` caller. It adds an
independent affected-CI execution lane; it does not reuse a partial parent
report. The trusted validator checks live topology and exact merge parents,
recomputes the required npm plan and both immutable reader inventories, and
selects prerequisites before Java/Qt setup. The four finite executable CI
scripts retain their exact ordinary `100755` modes on both trees, including
`tools/repository-health/check.py`, which the required Doctor host owner exercises.
New executable neighbors, missing files and changed modes remain conservative.
Android retains two finite complete reader families: the corrected source13
tree and the reviewed future installation with its six-file legacy-owner
handoff. Each uses its own exact fingerprint. A partial handoff, changed product
reader or unreviewed historical difference still requires full verification.
This separate
inventory proof does not change the router's conservative documentation rules.

That caller passes the trusted selection digest back to execution. Selection is
recomputed before and after actual execution, and a separate nonreusable receipt
requires exact successful coverage of every selected command. Omitted groups
carry their negative dependency proof, not a fabricated pass. Independently
mandatory npm owners stay external and are not executed twice. Attested product
repairs, unknown readers, unsupported package ownership, changed test commands,
mode changes or incomplete inventories retain complete shared/platform fallback.
Legacy callers without the selection binding retain their previous behavior.
The changed complete device-control-plane launcher still requires its real Qt
and portable C++ contracts; selected host setup is not an application build.

The shared application-script group is a host group: its native chat wrapper
requires Qt Quick Test and its other native wrappers exercise Qt/QML and C++
contracts. Its commands and assertions are unchanged. The dependency-light quick
profile does not run this mixed production group. The full native profile retains
its existing script coverage. Relevant product changes and
conservative full-host selection still require every one of its tests.

The seven product quick groups omitted for CI-only input changes cover shared
JavaScript security regressions, VirtualBaton, server-console behavior, device
result schemas, Jenkins tooling, desktop input, and performance contracts. Their
actual dependencies have no reads/imports/execution of the admitted CI roots.
The immutable guard includes their complete definitions as well as the complete
non-CI source inventory. A changed reader/definition or unknown historical input
requires full verification; the product assertions remain unchanged.

The trusted executor also reads the candidate registry as bounded data. New or
changed command/context combinations execute in addition to required trusted
checks; candidate definitions cannot drop or replace an existing command. A new
command conservatively requires full setup and verification before it can pass. Exact
duplicate commands in the same context execute once. Unsupported new execution
contexts fail closed for explicit owner review. This prevents newly registered
tests from remaining unexecuted until after their first merge.


## Selected CodeQL security results

On `main`, `.github/workflows/codeql.yml` deploys the canonical
`tools/repository-checks/workflows/codeql-results.yml` generation. It preserves the
whole-language scans and final selected-job truth table, then independently
checks GitHub's processed security results. GitHub's native summary may be
neutral when an unchanged language was deliberately omitted. A successful
analyzer exit alone therefore cannot serve as the selected finding gate.

The trusted verifier must bind current candidate, repository, original workflow
run/attempt, successful selected analysis jobs and processed analysis categories.
Missing, stale, ambiguous or failed processing cannot pass. Open findings in a
selected category block the result; dismissed findings retain their dismissal.
The verifier does not reuse SARIF, upload empty results for omitted languages or
publish private source/alert payloads. Weekly full scans remain unchanged.

The source verifier and exact workflow generation must be protected before
installing the active workflow. The staged ruleset payload is
`tools/repository-checks/workflows/codeql-main.json`. It covers all seven permanent
branches. Update the existing selected-results ruleset only after the gate has
been deployed and passed a real current PR on every included branch; preserve
the existing ruleset identity and its strict GitHub Actions binding. The payload
adds `codeql-security-results` to the other required contexts, without another
analysis run. The historical payload filename and ruleset name remain stable.
The staged workflow runs a selection/result check for documentation-only PRs
so the required context is present; no language analyzer runs for that case.
Both aggregate checkout steps and the API verifier execute in a clean job that
never runs candidate code. The exact new CI files remain outside the reviewed
iOS application reader graph, while their own required CI checks still run.

The exact original CodeQL workflow on a protected child is admitted only as the
base of a reviewed deployment, never as a legacy candidate. Verifier-only and
regression-test Python changes select Python; shared extractor controls, the
selector implementation and unknown inputs retain their cross-language checks.

The independent trusted `sync-test-reuse` pull-request-target gate also pins
the new exact CodeQL workflow when `codeql_results_required_branches` is
activated for the target. A candidate cannot substitute an older workflow or
imitate the result job name to avoid its verifier. The trusted source policy
enables this check for all seven permanent targets. Protect that source policy
before extending the existing required-context ruleset to the children; a green
job name alone cannot authenticate the verifier recipe. The separate ruleset
also requires live qualification of the actual selected-result gate on every
included branch. Enabling the source guard grants no successful analysis or
native qualification.

The dormant `tools/repository-checks/workflows/metadata-edits/codeql.yml`
successor also receives PR base-retarget `edited` events. Before reading the
candidate, its trusted event classifier recognizes only complete title/body
changes. Those events use isolated concurrency and a distinct skipped security
check name; they do not replace a failed or missing required result. Missing or
failed classification, unknown fields and base edits keep canonical required
qualification. Retargets independently select languages from the new base and
current merge and require their current-run analysis and processed findings.
The exact old and successor result-workflow blobs are admitted together during
source deployment; once a protected base uses the successor, both the result
verifier and independent sync gate reject reverting it. The metadata classifier
is a finite shared analysis control. Neither this staged template nor its source
admission activates it; active workflows and existing security assertions remain
unchanged until separately reviewed deployment and hosted qualification.

The separate dormant `metadata-edits/codeql-metadata.yml` and protected
repository caller prepare authenticated retention for complete title/body edits
on same-fork `main` PRs. Their small reusable metadata job supplies GitHub's
native original merge-source reference. Its isolated standard-library helper
reads only the immutable protected base and marks a one-way non-producer
invocation; neither its output nor a previous green aggregate grants authority.
After that marker, unavailable proof fails the small selector instead of
starting another producer. The metadata source capability is enabled, but no
active workflow deploys this lane. It cannot accept legacy green jobs as
protected execution evidence.

Repository retention initially covers only independently selected CI work with
no native, Android, npm, tool-package or browser owner. It requires the exact
complete six-workflow generation, the original same-merge protected schema-3
receipt, original environment, native whole-receipt publisher commitment and
unchanged controller, expiry and live candidate bookends. Documentation and
selected workflow-security jobs retain their actual same-merge native source,
successful steps and check records. CodeQL separately rechecks the original
same-merge selected analyses, pinned extractor version and fresh open findings,
including a native source record when no language was selected. Complete run
inventories keep ordinary missing, pending or failed producers blocking; only
authenticated metadata non-producers are excluded. No consumer environment,
renewed proof, fabricated omitted-suite result or scanner execution is created.
General product/package contexts and child branches still need separate
authority. Local fixtures establish no hosted deployment qualification.

The finite installation selector also admits the exact current
`android-owned-npm5-sync-ci-v1` to `protected-producer-metadata-ci-v1`
transition together with the exact pinned CodeQL successor. Only the caller,
project, parent, new metadata workflow and CodeQL active endpoints may differ;
the complete protected base must equal the trusted tree. The old CodeQL blob
is `6d55d0fe4e9edc86204c66e1fa3967681793a2cd` and its metadata successor is
`3a273057a38255ca368d3028594fb94227ba7c3b`. This selects every trusted host
suite once so the first native producer receipt and first ordinary CodeQL
analyses can bind the same merge. Capabilities and enabled policies still need
their reviewed stable protected source beforehand. Selection grants no runtime
admission, qualification or permission to omit a required result. The earlier
three producer pairs and separate parent-installed metadata pair remain valid.

The active workflow exactly matches `metadata-edits/codeql-pinned.yml` and pins
the official CodeQL 2.27.2 Linux bundle through the pinned init action's `tools` URL. Init still
uses its existing versioned hosted toolcache; a matching installation needs no
new download or extraction. A required step checks init's actual
`codeql-version` before Analyze. The independent result verifier also requires
that successful step and current processed analyses reporting version 2.27.2.
All earlier result generations remain admitted for source rollout, while both
independent gates reject returning from a deployed result generation to an older
one. The deployment transition requires both complete language scans.

Only an edit to an existing ordinary `100644` `.github/android-orchestration.json`
or `.github/test-suites.json` may select Python without JavaScript when both
immutable trees use that exact pinned workflow and unchanged reviewed CodeQL
configuration. The reviewed extractor has no generic JSON extraction and its
single-file TypeScript parser cannot read imported JSON; its ancestor readers
recognize package/tsconfig files rather than these two policy leaves. Python and
the policy governance tests remain required. Additions, removals, aliases, mode
changes, older or unknown workflow/configuration, other JSON, YAML, package
locks and mixed JavaScript inputs keep their existing conservative owners.

The same pinned generation admits four further existing ordinary
`100644` metadata leaves: `.github/branch-cleanup.json`, `.github/issue-policy.json`,
`.github/repository-health.json` and `.github/dependency-releases.json`. Only when
both immutable trees use the exact pinned workflow and unchanged configuration
do these leaves contribute no CodeQL language. Neither pinned extractor reads
these generic JSON files, and no candidate generator runs during the fixed
no-build analysis. Their governance and functional tests remain required.
Mixed Python, JavaScript, package or analysis-control changes retain their
existing language owners. Unknown siblings, additions, deletions, renames,
aliases, mode changes and query-pack inputs cannot inherit this exception.
YAML remains a JavaScript analysis input. The deployment transition cannot use
either JSON optimization; both immutable trees must already contain the exact
pinned workflow, and current selected analyses and findings remain required.

The exact pinned generation also excludes edits to existing ordinary `100644`
native leaves with these case-sensitive suffixes: `.c`, `.cpp`, `.h`, `.hpp`,
`.m`, `.mm`, `.qml`, `.vert`, `.frag` and `.glsl`. Both complete immutable
inventories and both old/new Git blobs are required. The trusted reader bounds
each blob to 4 MiB, the aggregate to 16 MiB and the inventory to 64 distinct
blobs, verifies object hashes, and conservatively rejects non-UTF-8/binary or
shebang content. No candidate source is imported or executed. Missing or
unsupported proof keeps both scans selected.

The reviewed JavaScript extractor may inspect native file headers, but none of
these unsupported suffixes produces extracted source; Python default recursive
discovery follows `.py`/`.pyw` and extensionless scripts. TypeScript's reviewed
single-file parser cannot read these native bodies indirectly. Existing file
membership preserves package and startup directory discovery. Additions,
deletions, renames, executable/mode changes, unknown suffixes, extractor overrides,
analysis controls, aliases and submodules cannot use this exception. Mixed
language changes retain their required scans, while the independent required
result gate recomputes the selection and still requires a successful current
selector even when no language is selected. Product/native tests remain owned
by their existing gates; scheduled CodeQL scans remain full.
