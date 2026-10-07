---
last-updated: "2026-10-07"
last-reviewed: "2026-10-07"
scope: "Common harness result interpretation and local laboratory diagnosis"
---

# Results and troubleshooting

Start with the exact Jenkins job and build number. Read the failed stage,
selected suite's JSON/JUnit, source identity, and cleanup result together.
The [result contract](../../../tests/device/schema/RESULT_CONTRACT.md) owns the
machine-readable fields and validation rules.

## Interpret the outcome

| Runner result | Meaning | Next step |
| --- | --- | --- |
| Exit `0` | The selected run passed. | Confirm complete selection, source/artifact identity and any individual skips before describing coverage. |
| Exit `77` | An optional capability was unavailable. | Read the missing capability; this is not evidence that the scenario passed. |
| Exit `75` | Device-lab infrastructure failed. | Diagnose the adapter, transport, fixture or prerequisites before attributing a product defect. |
| Other nonzero exit | An application assertion failed. | Inspect fresh probe observations and the specific expected behavior. |

Jenkins runs requiring complete coverage use `--require-complete`; an unavailable
required capability cannot produce a partial pass. Pipeline configuration,
artifact verification, publication and cleanup can also fail the Jenkins build.

## Diagnose common symptoms

| Symptom | First checks |
| --- | --- |
| Authentication or controller unavailable | `overte-jenkins who-am-i`; local controller availability; the prepared wrapper installation. |
| Build waiting in the queue | Agent availability and the target resource lock in the local UI. |
| Configuration rejected before a session | Current product-branch Jenkinsfile and all mandatory external inputs. |
| Appium or WebDriverAgent cannot create a session | Adapter/toolchain versions, trust and signing prerequisites, profile validity, and the platform transport. |
| Installed candidate cannot be verified | Exact artifact bytes, producer receipt, installation receipt, and installed-app identity. |
| Scene/input command succeeds but behavior fails | Fresh advancing probe samples, controlled scene markers, and observed movement/tablet state. |
| A run skips modules | Advertised adapter capabilities and whether the requested run requires complete coverage. |
| Publication or cleanup fails | Quarantine diagnostics and owned-resource cleanup; preserve the failure rather than retrying it away. |

For iOS, follow the [artifact and WDA handoff](../../../tests/device/ios/README.md)
and the product branch's guide. A WDA signing or launch error is not by itself
an Overte behavior failure.

## Preserve useful evidence

The pipeline publishes only its explicit allowlist of selector-free results.
Raw screenshots, private target configuration, receipts and build artifacts are
not generic publishable diagnostics. See
[isolation and publication](../../../tests/device/jenkins/README.md#isolation-and-publication).

A public test summary contains the job/build, source revision, suite, platform,
outcome and limitations. Private installation evidence remains private. A run
that passed against an old source does not qualify a newer one.

Document a result separately from completing a tracked issue. The maintainer
decides issue completion unless that action was explicitly delegated.
