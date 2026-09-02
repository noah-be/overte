# Cross-platform E2E operations

This directory is the target-neutral control plane. Integrated desktop and
shared Appium adapters translate the closed capability vocabulary into their
transport operations; common modules never import those tools. The Appium
adapter is a shared transport only and does not include Android or iOS product
implementation history.

## Lifecycle and acceptance

`acceptance-policy.json` assigns every platform/suite cell one monotonic state:
`implemented`, `accepted`, or `required`. Implemented means the portable
contract exists. Accepted additionally requires registered real-target
evidence. Required makes absence, skip, or infrastructure failure block the
matrix. A quarantine annotation never changes a product failure. The current
repository policy records no physical evidence and leaves production cells at
`implemented`.

Validate the policy and inspect the adapter verifier without contacting a
target:

```bash
python3 tests/device/validate_policy.py \
  --policy tests/device/acceptance-policy.json \
  --catalog tests/device/catalog.json
python3 tests/device/verify_adapter.py --help
```

## Fixture and CI ownership

`execution-profiles.json` is the closed recipe inventory for every catalog
suite. It declares the fixture class, session lifecycle, runtime tier, tablet
policy, additional environment, and upgrade artifacts. `execution_plan.py`
joins recipes with the catalog and policy before adapter discovery. Unknown
suites, incomplete coverage, and missing external inputs fail first.

Compile a scene-backed mock plan without starting a target:

```bash
python3 tests/device/execution_plan.py \
  --policy tests/device/acceptance-policy.json \
  --catalog tests/device/catalog.json \
  --profiles tests/device/execution-profiles.json \
  --platform mock --suite e2e-core \
  --fixture-provider auto --require-ready
```

`fixture/orchestrate.py` owns the serverless HTTP fixture and, when executable
paths are supplied, the controlled domain stack. It publishes one private
environment JSON outside the checkout and terminates owned child process
groups. Its control token is never printed.

`pipeline.py` applies compile, fixture preparation, run/cleanup, collection,
evaluation, and audit. Only classified infrastructure errors may be retried;
product and security failures are never retried. Every attempt remains an
immutable result. Run the complete flow against the deterministic mock in an
ephemeral output directory:

```bash
run_root="$(mktemp -d)"
OVERTE_MOCK_E2E_STATE="$run_root/state.json" \
python3 tests/device/pipeline.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json \
  --policy tests/device/acceptance-policy.json \
  --profiles tests/device/execution-profiles.json \
  --platform mock --suite e2e-core --allow-virtual \
  --output-dir "$run_root/pipeline"
```

Domain recipes additionally require the two server executable paths. Upgrade
recipes require regular, non-symlink source and candidate artifacts plus both
versions. All are checked before target discovery.

## Stability campaigns

`stability_campaign.py` runs one explicit platform/suite cell 10–20 times.
Each repetition is a fresh pipeline run. A product or security failure stops
immediately; only a classified infrastructure error may consume the bounded
retry allowance. `campaign-summary.json` always records zero product retries.
The complete command contract is device-free inspectable:

```bash
python3 tests/device/stability_campaign.py --help
```

The Jenkins campaign is separately opt-in and uses this engine without a
Jenkins retry wrapper. No hardware or Jenkins job is started by the shared
contract checks.

## Evidence and evaluation

Each pipeline writes a timeline and summary. Completed runner attempts write
JUnit, summary, and a selector-free run manifest; the pipeline also writes a
separate artifact-privacy audit. `audit_artifacts.py` rejects
credential-shaped content, credential-bearing URLs, and explicitly supplied
private identifiers. `evaluate_matrix.py` derives release gates from the
checked-in policy. Virtual targets cannot satisfy a production gate.

`analyze_history.py` reports pass rate, infrastructure-error rate, duration
percentiles, and mixed pass/product-failure flakiness. Contract reader
compatibility and migrations live in `contract-versions.json`.

The hardware-free CI entry point is:

```bash
python3 tests/device/run_control_plane_tests.py --profile quick
```

The portable frontier includes scene, movement, interaction, tablet, audio,
lifecycle, rendering, text, multi-user, recovery, entity synchronization,
permission recovery, crash recovery under load, and update/upgrade contracts.
These remain common contract implementations until each real adapter advertises
the required operations and governed physical evidence is registered. No
R11–R15 or evidence-campaign result is claimed by this document.
