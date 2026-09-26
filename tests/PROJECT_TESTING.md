# Project testing

Run commands from the repository root. The shared runner provides repository
checks and an optional configured native layer. Portable host contracts and
physical-device acceptance have separate commands and evidence requirements.

## Host prerequisites

Use a Linux host for the documented common test path. The runner uses Bash and
POSIX process groups; native Windows application builds follow
[BUILD_WIN.md](../BUILD_WIN.md) instead. The GitHub-hosted reference environment
is declared in [project-tests.yml](../.github/workflows/project-tests.yml):
Ubuntu 24.04, Python 3.12, Node.js 22, and JDK 17.

Install Git, Bash, Python 3.11 or newer, Node.js, `jq`, and a C++17 compiler
available as `c++`; Android branch suites also need Java/Javac. Python 3.11 is
required by repository helpers using `hashlib.file_digest`; use the CI versions
above when reproducing CI behavior. The quick profile compiles a small portable
production C++ regression. It needs no configured Overte build, Android SDK,
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
development packages, and Qt Quick Test tools. The workflow contains the exact
Ubuntu package list. These host Qt contracts are separate from the complete
client's platform-specific Qt/Conan dependency graph.

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
portable production C++ regression, and the portable E2E control plane. It also
runs the product suites declared by
[`platform-profile.json`](platform-profile.json). The shared profile declares
no product suites; Android branches declare their own entry points. A missing
declared entry point is an error. See [source ownership](../docs/SOURCE_LAYOUT.md).

Use `--suite NAME` to focus a run and `--fail-fast` to stop after the first
failure. `--timeout` is a limit for each suite. The default continues after
failures so one run can report independent problems.

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
| `documentation` | `quick` | `python3 tests/run-project-tests.py --suite documentation` |
| `native-smoke` | `quick` | `python3 tests/run-project-tests.py --suite native-smoke` |
| `source-layout` | `quick` | `python3 tests/run-project-tests.py --suite source-layout` |
| `shared-script-behavior` | `quick` | `python3 tests/run-project-tests.py --suite shared-script-behavior` |
| `native-ctest` | `native` | `python3 tests/run-project-tests.py --suite native-ctest` |
<!-- generated:test-suites:end -->

## Complete portable host contracts

```bash
python3 tests/device/run_control_plane_tests.py --profile full \
  --require-qml --timeout-seconds 900 \
  --junit build/test-results/device-e2e-control-plane.xml
```

This gate runs the complete control-plane self-tests, standalone production
C++ regressions, and QML contracts on the host. `--require-qml` makes unavailable
required host checks fail instead of skip. It needs no connected target and
does not build the complete Overte client. The shared CI runs it in addition to
the project quick profile.

<a id="full-profile"></a>

## Native C++/Qt suites

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
