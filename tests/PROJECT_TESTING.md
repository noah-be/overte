# Hardware-independent project testing

The project test runner provides three layers from one entry point.

## Quick profile

```bash
tests/run-project-tests.py --junit build/test-results/project-tests.xml
```

This profile needs Bash, Python 3, Node.js, Java/Javac, and `jq`, but no Android
SDK, Qt build, emulator, headset, display, or audio device. It runs:

- repository-wide Python, Shell, JavaScript, JSON, XML, symlink, Gradle-wrapper,
  and CMake-test integrity checks;
- dependency-free Node.js behavior tests for shared JavaScript libraries;
- the project coverage model validation;
- all Pico 4 host-side behavior, source-contract, fixture, and mock-ADB tests.

Use `--list`, `--suite NAME`, `--fail-fast`, and `--timeout SECONDS` to focus a
run. The default continues after suite failures so one run exposes independent
problems.

## Full profile

The full profile adds the deterministic, headless C++/Qt core tests. It requires an
already configured native build because Overte's Qt and Conan dependencies are
large and platform-specific:

```bash
tests/run-project-tests.py --profile full \
  --native-build-dir build-tests \
  --timeout 1800
```

The native layer builds the `all-tests` target and runs 42 CTest tests in
parallel with failure output and a per-test timeout. Benchmarks are not
correctness tests and are excluded by default. Six environment-dependent tests
(physical audio devices, packaged codecs, GPU drivers, legacy model fixtures,
and a settings shutdown issue) are also separated from the headless gate. Use
`OVERTE_TEST_INCLUDE_BENCHMARKS=1` and/or
`OVERTE_TEST_INCLUDE_INTEGRATION=1` for diagnostic runs. Configuration, jobs,
and timeout are controlled by `OVERTE_TEST_BUILD_CONFIG`,
`OVERTE_TEST_JOBS`, and `OVERTE_TEST_TIMEOUT`.

## Native coverage profile

Configure a Debug build with GCC coverage instrumentation, then run the tests
and generate dependency-free JSON and HTML reports:

```bash
cmake -S . -B build-coverage \
  -DBUILD_TESTS=ON \
  -DCMAKE_C_FLAGS_DEBUG='--coverage -O0 -g' \
  -DCMAKE_CXX_FLAGS_DEBUG='--coverage -O0 -g' \
  -DCMAKE_EXE_LINKER_FLAGS_DEBUG=--coverage \
  -DCMAKE_SHARED_LINKER_FLAGS_DEBUG=--coverage
tests/run-project-tests.py --profile coverage \
  --native-build-dir build-coverage --timeout 1800
```

The report defaults to `build/coverage/native/coverage.json` and `index.html`.
The wrapper rejects non-instrumented builds instead of producing a misleading
empty report. The verified deterministic run in this worktree reached 14.66%
lines, 19.49% functions, and 7.74% branches across all linked production
sources. Percentages are low because test executables link many libraries whose
features are outside each test's scope; file-level results are the useful guide
for choosing the next tests.

## Coverage interpretation

[`project-coverage.json`](project-coverage.json) maps all 12 major project areas
to dependency-light automation and, where available, native C++ suites. Its
test rejects newly registered but unmapped native groups. This is architectural
coverage, not a claim of 100% line coverage.

Host automation cannot validate GPU-driver behavior, physical audio devices,
distributed deployment, or Pico tracking/thermal behavior. These four limits
are explicitly represented as hardware/system acceptance layers rather than
silently counted as covered. The quick profile deliberately remains portable
and deterministic.

Intentional legacy syntax exceptions are exact allowlists. The health suite
fails if a new exception appears or an old exception becomes stale, preventing
the lists from becoming generic suppression buckets.
