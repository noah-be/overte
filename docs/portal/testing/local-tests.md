---
last-reviewed: "2026-10-07"
scope: "Linux host; current checkout's shared and declared product suites"
---

# Local tests

Run commands from the root of the checkout that owns your change. Shared work
starts on `main`; Android Phone, Pico, and iOS product work uses its owning
branch. The [platform index](../../interfaces/README.md) links those guides.

## Prepare the host

Use the [host prerequisites](../../../tests/PROJECT_TESTING.md#host-prerequisites)
before your first run. The common path needs Linux, Python 3.11 or newer, and
the listed JavaScript, build, and C++ tools. Quick tests need no configured
Overte product build or connected device.

Install the pinned workflow-parser dependency in a repository-check environment:

```bash
python3 -m venv build/repository-checks-env
build/repository-checks-env/bin/python -m pip install -r tests/requirements-repository.txt
```

## Run quick checks

```bash
build/repository-checks-env/bin/python tests/run-project-tests.py --profile quick --list
build/repository-checks-env/bin/python tests/run-project-tests.py --profile quick \
  --timeout 240 --junit build/test-results/project-tests.xml
git diff --check
```

Success means a zero exit code and a summary with `0 failed`. Inspect individual
skips before describing the coverage. The `--timeout` limit applies to each
suite, not the whole invocation.

For focused work, select a suite with `--suite NAME`. Discover names using
`--list`; the [canonical suite inventory](../../../tests/PROJECT_TESTING.md#available-project-suites)
is generated from the runner.

## Run the complete host layer

The complete host profile additionally needs Qt/QML tools, validation packages,
and working user/network namespaces. Follow the
[combined host profile](../../../tests/PROJECT_TESTING.md#combined-host-profile-for-ci)
for its exact environment and command. Missing required prerequisites fail that
profile; do not remove isolation or checks to manufacture a pass.

## Run native tests

Configure the product using its build guide with `OVERTE_BUILD_TESTS=ON`, then
use the [native test instructions](../../../tests/PROJECT_TESTING.md#native-cqt-suites).
The `full` profile requires a configured native build. It builds `all-tests`
and runs CTest; the `host` profile does not build the complete client.

Local Jenkins orchestration self-tests use fixtures. They do not contact the
laboratory or operate a device.
