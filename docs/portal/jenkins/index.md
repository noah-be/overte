---
last-reviewed: "2026-10-07"
scope: "Existing local Overte Jenkins laboratory; operator overview"
---

# Jenkins laboratory

The local Jenkins laboratory coordinates tests that need a configured target.
It supplies the agent, an exclusive device lock, private credentials, bounded
execution, cleanup, and result publication. The common harness and platform
adapters perform the actual scenarios.

Use this path:

1. Check [dated laboratory status](status.md) and choose the platform job.
2. Follow [Run a laboratory test](run-tests.md) to select the installed candidate
   and the intended suite.
3. Read [Results and troubleshooting](results.md) for the outcome and evidence.

## Access the existing installation

The local controller is available at `http://127.0.0.1:8080`. On the prepared
laboratory host, `overte-jenkins` wraps the official Jenkins CLI and supplies the
existing authentication through a protected file.

```bash
overte-jenkins who-am-i
overte-jenkins list-jobs
overte-jenkins help build
overte-jenkins help console
```

The wrapper is a locally installed operator tool. A fresh clone does not install
it or configure a laboratory. The available CLI commands depend on the installed
Jenkins/plugins; use `help` rather than assuming a `get-build` command exists.

## Components and ownership

| Component | Owner and role |
| --- | --- |
| Jenkins job | Chooses a source branch or exact revision and the external deployment parameters. |
| Shared Jenkins pipeline | Validates inputs, takes the target lock, runs selected suites, and stages permitted evidence. |
| Device runner | Reserves a target, applies timeouts, produces JSON/JUnit, and cleans up. |
| Platform adapter | Translates advertised capabilities into Appium, ADB, desktop, or platform-owned operations. |
| Controlled fixture and in-client probe | Provide deterministic content and observed effects inside Overte. |
| Acceptance policy and registry | Distinguish implemented scenarios from registered physical acceptance. |

The [shared pipeline guide](../../../tests/device/jenkins/README.md) owns
implementation details. The [device harness](../../../tests/device/README.md)
owns scenarios and capability semantics.

## Platform paths

- **Android Phone:** product source and its Jenkinsfile belong to `android-phone`.
- **Pico:** product source and its Jenkinsfile belong to `android-vr-pico`.
- **iPad/iPhone:** product source and its Jenkinsfile belong to `apple-ios`;
  signed Overte and WebDriverAgent artifacts and installation evidence are
  separate prerequisites. See the [shared iOS handoff](../../../tests/device/ios/README.md).
- **Desktop:** the common desktop adapters and product source belong to `main`;
  a checked-in adapter does not mean its local job is enabled.

Agents, resource names, credential identifiers, device selectors, signing data,
and populated target files stay in the private laboratory configuration.
