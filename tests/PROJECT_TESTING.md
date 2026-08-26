# Hardware-independent project testing

The project test runner provides two layers from one entry point.

## Quick profile

```bash
tests/run-project-tests.py --junit build/test-results/project-tests.xml
```

This profile needs Bash, Python 3, Node.js, Java/Javac, and `jq`, but no Android
SDK, Qt build, emulator, headset, display, or audio device. It runs:

- security and reproducibility contracts for the device-free and trusted-build
  Pico GitHub Actions workflows;
- repository-wide Python, Shell, JavaScript, JSON, XML, symlink, Gradle-wrapper,
  and CMake-test integrity checks;
- dependency-free Node.js behavior tests for shared JavaScript libraries;
- the complete device-free E2E stack, adapter contracts, controlled fixture,
  mock Appium server, mock ADB transports, and mock OculiX execution;
- the project coverage model validation;
- all Pico 4 host-side behavior, source-contract, fixture, and mock-ADB tests.

Use `--list`, `--suite NAME`, `--fail-fast`, and `--timeout SECONDS` to focus a
run. The default continues after suite failures so one run exposes independent
problems.

## Full profile

The full profile adds every CTest-registered C++/Qt test. It requires an
already configured native build because Overte's Qt and Conan dependencies are
large and platform-specific:

```bash
tests/run-project-tests.py --profile full \
  --native-build-dir build-tests \
  --timeout 1800
```

The native layer builds the `all-tests` target and runs CTest with
`--output-on-failure --no-tests=error`. `OVERTE_TEST_BUILD_CONFIG` selects the
configuration and defaults to `Debug`.

## Coverage interpretation

[`project-coverage.json`](project-coverage.json) maps all 12 major project areas
to dependency-light automation and, where available, native C++ suites. Its
test rejects newly registered but unmapped native groups. This is architectural
coverage, not a claim of 100% line coverage.

Host automation cannot validate GPU-driver behavior, physical audio devices,
distributed deployment, or Pico tracking/thermal behavior. These four limits
are explicitly represented as hardware/system acceptance layers rather than
silently counted as covered. Native line coverage should be collected from a
configured instrumented CMake build; the quick profile deliberately remains
portable and deterministic.

Intentional legacy syntax exceptions are exact allowlists. The health suite
fails if a new exception appears or an old exception becomes stale, preventing
the lists from becoming generic suppression buckets.
