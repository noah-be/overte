# Windows acceptance matrix

Windows releases, GPU drivers, and desktop-session variants are execution
dimensions of `windows-main`; they are not permanent Git branches. Every lab
machine runs the same `windows-desktop` manifest and uses a private target
entry. Release-specific paths, hashes, and provisioning therefore stay in the
lab configuration instead of forking the behavior contract.

The initial acceptance lanes are:

| Release lane | Session | Required suites |
| --- | --- | --- |
| Current supported Windows desktop release | Dedicated local interactive account | smoke, asset-smoke, domain-smoke, sound-smoke, e2e-core, e2e-recovery |
| Next Windows desktop release before adoption | Dedicated local interactive account | smoke and e2e-core |

A row is enabled only when all of these conditions are true:

- Jenkins, Java, OculiX, and Interface run at the same integrity level.
- The agent can open the active input desktop and does not run in Session 0.
- Interface, Java, and the OculiX IDE JAR match their configured SHA-256 values.
- The desktop remains unlocked and locally attached for the complete suite.
- Display scaling, resolution, GPU driver, Overte build, and Windows release
  are recorded as non-secret Jenkins metadata.
- Private selectors, local account paths, and target configuration are absent
  from published logs and artifacts.

The same commit first passes the hardware-free adapter tests on
`windows-main`. Jenkins then runs the enabled rows. A row-specific failure stays
attached to that lab target; adapter changes remain shared and are reviewed
once against `windows-main`.

Adding another supported Windows release, GPU vendor, display scale, or RDP
validation lane requires provisioning and an acceptance run, not another
permanent source branch. Locked or disconnected RDP sessions are not valid for
the local-interactive lane.
