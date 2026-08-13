# Unified project and interface testing

`tests/run-tests.py` is the catalog-driven entry point for project, Android,
Pico and platform-specific host tests. The root catalog imports the existing
Android catalog and the Pico catalog, so profile selection, timeouts, isolated
temporary directories and atomic bounded JUnit output behave consistently.

## Quick profile

```bash
tests/run-tests.py --profile project-quick \
  --junit build/test-results/project-tests.xml
```

This profile needs Bash, Python 3, Node.js, Java/Javac, and `jq`, but no Android
SDK, Qt build, emulator, headset, display, or audio device. It runs:

- security and reproducibility contracts for the device-free and trusted-build
  Pico GitHub Actions workflows;
- repository-wide Python, Shell, JavaScript, JSON, XML, symlink, Gradle-wrapper,
  and CMake-test integrity checks;
- dependency-free Node.js behavior tests for shared JavaScript libraries;
- the interface/subsystem coverage model, reachability and native-test-debt
  validations;
- all Pico 4 host-side behavior, source-contract, fixture, and mock-ADB tests.

Use `--list`, `--suite NAME`, `--interface NAME`, `--category NAME`,
`--fail-fast`, and `--timeout SECONDS` to focus a run. Imported suite names are
namespaced, for example `android:phone-robolectric-launcher` and
`pico:openxr-input`. The default continues after suite failures so one run
exposes independent problems. `tests/run-project-tests.py`,
`android/common/tests/run-tests.sh`, and the Pico scripts remain compatibility
frontends.

Useful interface profiles include `android-fast`, `android-host`,
`android-contracts`, `android-regression`, `android-robolectric`,
`pico-device-free`, and `apple-host`. Hardware-writing suites are excluded
unless explicitly selected with `--allow-hardware`.

## Full profile

The full profile adds every CTest-registered C++/Qt test. It requires an
already configured native build because Overte's Qt and Conan dependencies are
large and platform-specific:

```bash
tests/run-tests.py --profile project-full \
  --native-build-dir build-tests \
  --timeout 1800
```

The native layer builds the `all-tests` target and runs CTest with
`--output-on-failure --no-tests=error`. `OVERTE_TEST_BUILD_CONFIG` selects the
configuration and defaults to `Debug`. The full profile also exposes the
macOS-only launcher XCTest suite and records it as skipped when Xcode is not
available.

## Coverage interpretation

[`project-coverage.json`](project-coverage.json) maps eight shipped interface
surfaces, all direct `libraries/*` directories and every registered native
group to evidence with an explicit strength (`behavior`, `contract`, or
`structural`). `covered`, `partial`, and `gap` are validated differently, so a
file inventory can no longer masquerade as behavior coverage. This is
architectural coverage, not a claim of 100% line coverage.

Host automation cannot validate GPU-driver behavior, physical audio devices,
distributed deployment, or headset tracking/thermal behavior. These limits and
known interface gaps are recorded beside the relevant surface rather than
silently counted as covered. Native line coverage should be collected from a
configured instrumented CMake build; the quick profile deliberately remains
portable and deterministic.

[`test-reachability.json`](test-reachability.json) is the small, reviewed list
of manual and compatibility entry points. Its validator discovers runnable
test sources and fails when a new test is neither catalog-reachable nor
explicitly manual. [`test-debt.json`](test-debt.json) similarly makes remaining
native `QSKIP` and disabled suites visible. Jitter, Workload and Recording now
contain registered assertions instead of placeholder passes or an unreported
manual executable.

Intentional legacy syntax exceptions are exact allowlists. The health suite
fails if a new exception appears or an old exception becomes stale, preventing
the lists from becoming generic suppression buckets.
