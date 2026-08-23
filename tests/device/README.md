# Overte device test harness

This directory contains the platform-neutral orchestration layer for tests on
physical devices. It deliberately has no dependency on ADB, Xcode,
`devicectl`, or a particular Overte application package. Platform branches add
small target adapters and catalogued test modules without forking the runner.

## Concepts

- An **adapter** discovers targets and translates generic operations into the
  platform's device tooling.
- A **module** is one independently reported test executable.
- A **suite** is a catalog label selecting one or more modules.
- A **capability** is an adapter feature such as `app.launch`,
  `lifecycle.background`, `telemetry.memory`, or `telemetry.thermal`.

The runner reserves one target for the complete run, gives every module its own
artifact directory, applies timeouts to complete process groups, always asks
the adapter to clean up, and publishes JSON plus JUnit results. A module
directory contains `INVALID` until that module completes successfully.

## Adapter protocol

An adapter manifest uses this format:

```json
{
  "schemaVersion": 1,
  "id": "android-phone",
  "command": ["./adapter.py"]
}
```

Relative commands are resolved against the manifest directory. The executable
receives one of these commands and writes exactly one JSON value to stdout:

```text
adapter discover
adapter describe --target TARGET
adapter invoke --target TARGET --operation OPERATION --arguments JSON
adapter cleanup --target TARGET
```

`discover` returns a list of objects with `selector`, `displayName`, `platform`,
`physical`, and `capabilities`. Selectors are treated as private transport
identifiers: the runner never writes them into reports and removes them from
captured module output. `describe` returns non-sensitive device metadata.
`invoke` returns an arbitrary JSON object. `cleanup` must be idempotent.

## Module catalog

```json
{
  "schemaVersion": 1,
  "modules": [{
    "id": "process-soak",
    "description": "Detect application exits and restarts.",
    "command": ["modules/process-soak.py"],
    "suites": ["stability"],
    "requires": ["app.process"],
    "timeoutSeconds": 900
  }]
}
```

Modules receive `OVERTE_DEVICE_ADAPTER_MANIFEST`,
`OVERTE_DEVICE_TARGET_SELECTOR`, and `OVERTE_DEVICE_ARTIFACT_DIR`. They can use
`adapter_client.py` to invoke operations without knowing the platform command.
Exit code 0 passes, 77 skips, and every other exit code fails.

## Running

```bash
python3 tests/device/run.py \
  --adapter-manifest path/to/adapter.json \
  --catalog path/to/catalog.json \
  --suite stability \
  --output-dir /tmp/overte-device-run
```

Use `--list` to inspect selection without connecting to a target. Run the
device-free contract tests with:

```bash
python3 -m unittest discover -s tests/device/self_tests -v
```

Every target adapter should also pass the reusable protocol verifier. The
optional cleanup check calls cleanup twice and therefore verifies the required
idempotency directly:

```bash
python3 tests/device/verify_adapter.py \
  --adapter-manifest path/to/adapter.json --check-cleanup
```
