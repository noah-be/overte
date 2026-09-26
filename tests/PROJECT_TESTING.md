# Project testing

Run commands from the repository root. The shared runner provides repository
checks, a complete portable host profile, and an optional configured native
layer. Physical-device acceptance has separate commands and evidence requirements.

## Host prerequisites

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

For the complete host control-plane gate, also provide `pkg-config`, Qt 6
development packages, Qt Quick Test tools, and `unshare` with permission to
create user and network namespaces. Artifact validation runs real CLIs without
network access; unavailable isolation fails those tests. The workflow contains
the exact Ubuntu package list. These host Qt contracts are separate from the
complete client's platform-specific Qt/Conan dependency graph.

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
Failures in the full group fail the combined project result.

Shared CI, parent qualification and sync fallback use this combined profile.
Parent branches run their push tests only in parent qualification, which creates
the same exact-commit evidence after success. Shared CI retains leaf and
development-branch pushes, reusable PR calls and manual runs. The actual PR
merge candidate and the integrated parent commit remain distinct test inputs.

## Available project suites

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
| `project-runner` | `quick` | `python3 tests/run-project-tests.py --suite project-runner` |
| `python-test-runner` | `quick` | `python3 tests/run-project-tests.py --suite python-test-runner` |
| `repository-checks` | `quick` | `python3 tests/run-project-tests.py --suite repository-checks` |
| `ios-build-qualification` | `quick` | `python3 tests/run-project-tests.py --suite ios-build-qualification` |
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
| `native-smoke` | `quick` | `python3 tests/run-project-tests.py --suite native-smoke` |
| `native-ci-policy` | `quick` | `python3 tests/run-project-tests.py --suite native-ci-policy` |
| `native-registration` | `quick` | `python3 tests/run-project-tests.py --suite native-registration` |
| `device-result-schema` | `quick` | `python3 tests/run-project-tests.py --suite device-result-schema` |
| `device-jenkins` | `quick` | `python3 tests/run-project-tests.py --suite device-jenkins` |
| `desktop-input-protocol` | `quick` | `python3 tests/run-project-tests.py --suite desktop-input-protocol` |
| `performance-contracts` | `quick` | `python3 tests/run-project-tests.py --suite performance-contracts` |
| `server-console-behavior` | `quick` | `python3 tests/run-project-tests.py --suite server-console-behavior` |
| `source-layout` | `quick` | `python3 tests/run-project-tests.py --suite source-layout` |
| `shared-script-behavior` | `quick` | `python3 tests/run-project-tests.py --suite shared-script-behavior` |
| `native-ctest` | `native` | `python3 tests/run-project-tests.py --suite native-ctest` |
<!-- generated:test-suites:end -->

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
module together. Every discovered case is retained; global Python mocks and
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

## Native C++/Qt suites

The selective PR lane is described in the [native CI guide](../tools/native-tests/README.md).
It routes from the exact merge candidate, builds affected production/test targets,
and runs bounded headless Qt tests. Documentation and known host-only changes do
not start a native build. The existing `repository-checks` aggregate requires the
selected native result; host sync qualification cannot substitute for it. Its
broad dependency environment must be prepared and qualified before activation.
This local wiring does not establish that the gate is deployed on GitHub.


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
