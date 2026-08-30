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

`fixture/orchestrate.py` owns the serverless HTTP fixture and, when executables
are supplied, the controlled domain stack. It publishes one mode-0600 environment
JSON in a mode-0700 directory outside the checkout and terminates the complete
child process groups on signals. The control token is only present in that file,
never in stdout.

`pipeline.py` applies the same phases everywhere: prepare, validate fixture
environment, reserve/run/cleanup through `run.py`, collect, evaluate and audit.
Only module `error` outcomes are retried; product assertion failures and security
findings are never retried. Every attempt remains an immutable artifact.

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
