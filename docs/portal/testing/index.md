---
last-reviewed: "2026-10-07"
scope: "Shared fork test layers; product qualification belongs to its owning branch"
---

# Automated testing

Choose the layer that answers your question. Repository checks, product builds,
and tests on physical devices establish different facts.

| Layer | Where it runs | What a pass establishes |
| --- | --- | --- |
| Quick repository checks | Local Linux host or GitHub runner | Policies, source contracts, syntax, portable regressions, and selected branch-owned tests pass. |
| Complete host profile | Prepared Linux host or GitHub runner | The complete portable control plane and host contracts pass without a physical target. |
| Native build and CTest | Configured native build or selective GitHub native lane | Selected real product and C++/Qt test targets build and execute. |
| Physical-device E2E | Configured Jenkins laboratory and target adapter | The selected installed application performs the observed scenario on that target. |
| Device acceptance | Registered evidence and acceptance-policy evaluation | The named platform/suite meets its version-bound acceptance requirements. |

## Start with a local check

Follow [Local tests](local-tests.md) and the detailed
[project testing guide](../../../tests/PROJECT_TESTING.md). Use the runner's
`--list` output for the current checkout instead of relying on historical suite
counts.

## Continue to the relevant environment

- [GitHub Actions](github-actions.md) explains pull-request checks and native routing.
- [Jenkins laboratory](../jenkins/index.md) explains real-target operations.
- The [physical-device harness](../../../tests/device/README.md) defines the
  available scenarios, capabilities, result formats, and complete-run rules.

## Describe evidence precisely

Record the source revision, test command or Jenkins build number, selected
suite, environment, outcome, and any skipped checks. For device evidence also
record the candidate artifact and verified installed-app binding in the private
receipt. Public summaries use platform names, never transport selectors.

An enabled Jenkins job is configuration, not a passing test. A historical
`SUCCESS` is evidence about that historical run, not a newer product build.
The checked-in [acceptance registry](../../../tests/device/acceptance-evidence.json)
on the inspected `main` contains no physical acceptance records.
