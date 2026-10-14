<!-- Copyright 2026 Overte e.V. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# iOS parity observation sheet — unfilled

Copy this outside the source tree into the coordinator-owned private run context.
No candidate is selected and no device action or passing observation is recorded
by this template. Follow [the procedure](PARITY_ACCEPTANCE.md). Preserve earlier
evidence under its original source/artifact identity; do not overwrite it.

| Required binding | Actual value / private receipt reference |
| --- | --- |
| Observation ID, operator and issue(s) | NOT ASSIGNED |
| Actual adapter path and result scope (observation-only / verified bound) | NOT SELECTED |
| Producing source SHA40, tree and ordered parents | NOT SELECTED |
| PR head/merge SHA40, if applicable | NOT SELECTED |
| Workflow / producing run / attempt / configuration | NOT SELECTED |
| Qt / Xcode / iphoneos SDK / deployment floor | NOT SELECTED |
| IPA SHA256 and size / package-verification receipt/hash | NOT SELECTED |
| Re-signing derivation and final signed-package SHA256, if applicable | NOT SELECTED |
| Installation receipt/hash and actual association limit | NOT BOUND |
| Verified installed-code executionIdentity, for a bound claim | NOT BOUND |
| Observed app version / anonymous device reference / iPadOS version and build | NOT OBSERVED |
| Actual runner SHA40 / catalog and fixture manifests SHA256 | NOT SELECTED |
| UTC start/end / session and process continuity reference | NOT OBSERVED |
| Controlled world/peer/roles and private test namespace | NOT ASSIGNED |

An absent or weaker installed-byte association must remain explicit. A source
checkpoint, JSON schema pass, launch command or historical IPA cannot fill these
fields by inference. Never record credentials, device serials or private selectors
in this sheet's public derivative.
The active Wi-Fi lab path can record real observations while retaining
`cryptographicInstalledByteBinding=false`. Such results must state that limit;
they cannot fill the optional bound identity field or pass its stronger gate.

| Criterion | Result | Visible outcome / failure or cancellation / private evidence path and SHA256 / UTC |
| --- | --- | --- |
| #1164 World/navigation | NOT PERFORMED | — |
| #1165 Account/domain authentication | NOT PERFORMED | — |
| #1166 Avatar/People | NOT PERFORMED | — |
| #1167 Create | NOT PERFORMED | — |
| #1168 All ten Emotes | NOT PERFORMED | — |
| #1169 World HTML/media and #1179 movie pixels | NOT PERFORMED | — |
| #1170 Tablet HTML/media | NOT PERFORMED | — |
| #1171 Graphics controls and actual effects | NOT PERFORMED | — |
| #1172 Mutual voice and recorded preview | NOT PERFORMED | — |
| #1173 Real peer Chat | NOT PERFORMED | — |
| #1174 Capture/preview/native save/share/upload | NOT PERFORMED | — |
| #1175 URL/file/folder scripts and actual execution | NOT PERFORMED | — |
| #1176 Assets/companions/model pixels/server mutation | NOT PERFORMED | — |
| #1177 Input/lifecycle/cleanup | NOT PERFORMED | — |

Use separate subrows when only part of a criterion is observed. Permitted result
descriptions are **not performed**, **blocked/not bound**, **observed failure**,
**partial observation** or **observed criterion outcome** with its exact scope.
Missing required parts keep the overall criterion incomplete; the worksheet
does not automatically mark an issue complete or supply machine acceptance.

For every executed step, retain:

1. Actual UTC and monotonic sequence, action through the normal entry, expected
   outcome, and independently observed visible result.
2. Contemporaneous private source/IPA/install/session receipt join and process
   continuity; record an intended restart as a new process boundary.
3. Original screenshot/video/file/server-observation path, size and SHA256;
   distinguish display content from recorder omissions. Screenshot contexts
   must not overwrite previous `screenshot.png` files.
4. Current request/ticket and real terminal outcome where observable, error or
   cancel behavior, cleanup and any persistent server/capture result. A
   requested cancellation is not proof of rollback after commitment.
5. Remaining limitation, counterpart comparison, and next precise verification.

Recheck the binding if the candidate, installed code, signing, process, runner or
fixture changes. End the observation at that boundary and create a new sheet;
do not combine versions into one passing result.
