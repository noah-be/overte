# Cross-platform E2E operations

This directory is the target-neutral control plane. Platform adapters translate
the closed capability vocabulary into Appium, XCTest/WebDriverAgent, OculiX, ADB,
OpenXR or another target-native open-source mechanism. Test modules never import
those tools.

## Lifecycle and acceptance

`acceptance-policy.json` assigns every platform/suite cell one monotonic state:
`implemented`, `accepted`, or `required`. Implemented means the portable contract
exists. Accepted additionally requires recorded real-hardware evidence. Required
means absence, skip, or infrastructure failure makes the release matrix red.
Promotion evidence is mandatory for explicit accepted/required overrides. A
quarantine is only an annotation in history reports and never changes a failure.

Validate the policy and adapter conformance with:

```sh
python3 tests/device/validate_policy.py \
  --policy tests/device/acceptance-policy.json \
  --catalog tests/device/catalog.json
python3 tests/device/verify_adapter.py --adapter-manifest ADAPTER.json \
  --policy tests/device/acceptance-policy.json --catalog tests/device/catalog.json \
  --minimum-state accepted --check-cleanup --require-target
```

## Fixture and CI ownership

`execution-profiles.json` is the closed recipe inventory for every catalog suite.
It declares the fixture class (`none`, `scene`, or `domain`), whether a fresh
session is required, the runtime tier, tablet-policy input, additional environment
and upgrade artifacts. `execution_plan.py` joins these recipes with the catalog
and acceptance policy before adapter discovery. Unknown suites, incomplete recipe
coverage and missing external inputs fail without contacting a target.

For example, compile a scene-backed plan without starting it:

```sh
python3 tests/device/execution_plan.py \
  --policy tests/device/acceptance-policy.json \
  --catalog tests/device/catalog.json \
  --profiles tests/device/execution-profiles.json \
  --platform linux --suite e2e-core \
  --fixture-provider auto --require-ready
```

`fixture/orchestrate.py` owns the serverless HTTP fixture and, when executables
are supplied, the controlled domain stack. It publishes one mode-0600 environment
JSON in a mode-0700 directory outside the checkout and terminates the complete
child process groups on signals. The control token is only present in that file,
never in stdout.

`pipeline.py` applies the same phases everywhere: compile, prepare, own or validate
the fixture environment, reserve/run/cleanup through `run.py`, collect, evaluate
and audit. With the default `--fixture-provider auto`, it starts one unified
orchestrator for all selected suites and retains its private environment only in a
temporary mode-0700 directory. `--fixture-provider external` plus
`--fixture-environment` is available when the lab owns the fixture lifecycle.
Only module `error` outcomes are retried; product assertion failures and security
findings are never retried. Every attempt remains an immutable artifact.
Suites can be named explicitly or selected directly from the acceptance policy
with `--minimum-state accepted|required`; an empty lifecycle selection fails.

```sh
python3 tests/device/pipeline.py \
  --adapter-manifest ADAPTER.json \
  --catalog tests/device/catalog.json \
  --policy tests/device/acceptance-policy.json \
  --profiles tests/device/execution-profiles.json \
  --platform linux --suite e2e-core \
  --output-dir /private/results/linux-core
```

Domain recipes additionally require `--domain-server` and `--assignment-client`.
Upgrade recipes require both version arguments and regular non-symlink source and
candidate artifacts. All are checked before target discovery.

Run a physical stability campaign with one explicit suite and one platform cell:

```sh
python3 tests/device/stability_campaign.py \
  --repetitions 10 --retry-infrastructure 1 \
  --output-dir /private/results/linux-portable-stability -- \
  --adapter-manifest ADAPTER.json --catalog tests/device/catalog.json \
  --policy tests/device/acceptance-policy.json \
  --profiles tests/device/execution-profiles.json \
  --platform linux --suite portable-smoke
```

The allowed range is 10–20 repetitions. Each repetition is a fresh common
pipeline run. A product or security failure stops the campaign immediately and
is never retried; only a classified infrastructure error may consume the bounded
retry allowance. `campaign-summary.json` always records zero product retries.

`update-upgrade` is ordered as source installation, source launch/version check,
safe setting change, in-place candidate installation, candidate version and
setting-retention checks, followed by the common scene/look/move/tablet smoke and
unconditional cleanup. Android-family adapters additionally inspect the APK
package and candidate version with the pinned `OVERTE_ANDROID_AAPT` executable
before changing the installed package. Source and candidate must have increasing
version codes and distinct version names and must be signed by the same key.

## Evidence and evaluation

Each run contains a selector-free `timeline.jsonl`, JUnit, summary, run manifest,
module evidence and a SHA-256 `artifact-manifest.json`. `audit_artifacts.py`
rejects credential-shaped content, credential-bearing URLs and explicitly
supplied private identifiers. `evaluate_matrix.py --policy ... --catalog ...`
derives release gates from policy. Virtual targets cannot satisfy a gate unless a
platform is explicitly exempted; that exception is intended for `mock` self-tests.

`analyze_history.py` reports pass rate, infrastructure-error rate, duration p50/
p95 and mixed pass/product-failure flakiness per platform/suite. Contract reader
compatibility and migration rules live in `contract-versions.json` and are checked
by `validate_contract_versions.py`.

`run_control_plane_tests.py` is the hardware-free CI entry point. Its quick
profile is part of `tests/run-project-tests.py`; the project GitHub workflow also
runs the full Python regression and requires the QML contract runtime. Both layers
write JUnit reports without device selectors or fixture control tokens.

## Portable suite frontier

In addition to scene, movement, interaction, tablet, audio, lifecycle, rendering,
text, multi-user and recovery coverage, the common layer defines:

- `entity-sync-smoke`: independent controlled actor mutation, exact revision and
  actor attribution;
- `permission-recovery`: native microphone deny/grant plus process continuity and
  restoration;
- `crash-recovery-under-load`: forced crash with loaded scene/tablet, new process,
  scene and tablet recovery;
- `update-upgrade`: supplied source/candidate build versions plus persisted safe
  setting continuity.

These suites remain `implemented` on production targets until each target adapter
and real-device gate supplies acceptance evidence. This prevents common mock
coverage from being mistaken for hardware acceptance.
