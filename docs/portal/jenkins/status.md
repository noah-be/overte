---
last-reviewed: "2026-10-07"
scope: "Local laboratory snapshot on 2026-10-07; not a live dashboard or device acceptance"
---

# Laboratory status — October 7, 2026

This is a dated, read-only inventory of the existing local Jenkins laboratory.
Job enablement, configured source, schedules and historical outcomes were read
through the official CLI. No build or device action was triggered for this
documentation. Recheck Jenkins before planning a new run.

## Regular jobs

| Job | Enabled | Configured source branch | Last recorded build (UTC date) |
| --- | --- | --- | --- |
| `android-device-e2e` | Yes | `android-phone` | #33, SUCCESS, 2026-08-28 |
| `ios-device-e2e` | Yes | `apple-ios` | #28, SUCCESS, 2026-08-29 |
| `overte-device-phone-smoke` | Yes | `android-phone` | #4, FAILURE, 2026-08-30 |
| `overte-device-ipad-smoke` | Yes | `apple-ios` | No recorded build |
| `overte-device-pico-smoke` | No | `android-vr-pico` | #4, SUCCESS, 2026-08-30 |
| `pico-device-e2e` | No | `android-vr-pico` | #113, SUCCESS, 2026-08-30 |
| `overte-e2e-linux` | No | `main` | No recorded build |
| `overte-e2e-macos` | No | `apple-main` | No recorded build |
| `overte-e2e-windows` | No | `main` | No recorded build |

These jobs obtain `tests/device/jenkins/Jenkinsfile` from their configured
branch. The inspected configurations have no timer trigger. Enabled jobs still
require valid deployment parameters, artifacts and a ready target.

## Separate qualification and diagnostics

| Job | Enabled | Last recorded build (UTC date) | Evidence scope |
| --- | --- | --- | --- |
| `overte-browser-native-ci` | Yes | #8, FAILURE, 2026-10-02 | Dedicated browser/native qualification; separate from mobile device acceptance. |
| `overte-m4-ipad-wifi-diagnostic` | Yes | #8, SUCCESS, 2026-09-27 | Historical iPad transport diagnostic. |
| `overte-m4-ipad-launch-diagnostic` | Yes | #6, SUCCESS, 2026-09-27 | Historical iPad launch diagnostic. |

The browser job's [own guide](../../../browser-client/ci/jenkins/README.md)
records its exact-source qualification and remaining failures. Diagnostic
successes do not establish complete portable E2E or acceptance of today's
installed candidate. Other candidate and historical diagnostic jobs exist;
this table is an operator entry point, not an exhaustive job list.

## Repository and acceptance state

The shared documentation baseline inspected for this chapter is fork `main` at
`a0102a0133078b36ce3a384a974348b57c22501a`. Product-branch configurations and
private laboratory settings have separate identities.

- The shared [acceptance registry](../../../tests/device/acceptance-evidence.json)
  is empty at that baseline. Implemented suites have not thereby become
  registered physical acceptance.
- Regular inspected jobs do not expose a voice-roundtrip parameter. The local
  voice work discussed on October 7 has not been activated in those jobs.
- Historical successful builds above date from August and September; they do
  not qualify the October 7 fork source.
- Host inspection did not check current device connectivity, installed signing
  profile validity, adapter readiness, or artifact/installed-candidate binding.

## Refresh this snapshot

Use `overte-jenkins who-am-i` and `list-jobs`, then inspect the current job forms
and build history locally. CLI `get-job` exposes the full XML and must remain
private; extract only the enablement flag, public source branch, timer presence,
build number, UTC date and outcome for documentation. The installed CLI has no
`get-build` command; the UI or a read-only CLI `groovy` projection can provide
build metadata without a raw HTTP fallback.

Update this dated page with new observations and their limits. Never silently
turn old diagnostic results into current platform acceptance.
