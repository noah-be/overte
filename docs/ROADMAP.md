# Experimental fork roadmap

> [!CAUTION]
> This roadmap describes an unofficial, AI-assisted hobby fork. It is not an
> Overte project commitment or a statement of official platform support.

- **Updated:** 2026-10-13
- **Current work:** `CLIENT-PARITY` — equivalent useful features across iOS, Android Phone and Pico
- **Next:** artifact-bound cross-client acceptance
- **Later:** `PHONE-V1` — broader Android Phone device coverage
- **Completed:** `PHONE-P1`, `PICO-P1`, `IOS-P1` — personal alphas; `R0` — repository baseline

## North star

On a real target device, a user can build or install the corresponding Overte
Interface, enter a representative world, navigate and interact, use the
platform's intended audio path, survive lifecycle transitions, and exit cleanly
after a 30-minute session.

Platform parity means the same useful outcome, not an identical desktop UI.
Store publication, broad hardware support, and optional feature parity do not
block a personal alpha.

## Personal alpha definition

A personal alpha is repeatably usable by the maintainer on one explicitly named
physical device and source revision. It requires:

- a reproducible build and installation path;
- reliable application startup and entry into a representative Overte world;
- platform-appropriate movement, camera control, and interaction;
- usable tablet, text input, and system keyboard where they apply;
- audio output, mute control, and an explicitly tested microphone allow or deny
  path;
- background, foreground, restart, and clean-exit behavior;
- a 30-minute session without a crash, critical overheating, or uncontrolled
  memory growth; and
- documented limitations and deferred features.

A personal alpha does not require broad device coverage, store publication,
complete desktop parity, or a promise of support to other users.

## NOW

### CLIENT-PARITY — Cross-client feature parity

**Goal:** Make the useful feature set available through normal startup and
platform-appropriate controls on `apple-ios`, `android-phone` and
`android-vr-pico`. Preserve stronger existing capabilities; matching placeholders
or disabling working features does not satisfy parity.

The [shared feature contract](interfaces/FEATURE_PARITY.md) defines outcomes,
ownership, implementation dependencies and the acceptance boundary. The source
audit found gaps in Create/Emote entry points, world/tablet HTML, graphics control,
recorded voice testing and automatic Pico login. Shared omissions and runtime
limits remain visible in the contract.

**Single next action:** Qualify and integrate the reviewed common and platform
source through the regular parent hierarchy before building the exact native
candidates.

This work is coordinated through three High-reasoning client sessions with
isolated worktrees and a shared integration owner. On 2026-10-13 the owner
explicitly requested the three client milestones and their open/closed issue
inventory: [IOS-P2](https://github.com/noah-be/overte/milestone/6),
[PHONE-P2](https://github.com/noah-be/overte/milestone/4) and
[PICO-P2](https://github.com/noah-be/overte/milestone/5).
Completed source/host tasks and open current-artifact acceptance criteria are
separate; the completed personal-alpha history is retained.

## NEXT

Build the exact integrated candidates and run the same reference-world journeys
on the three devices. Record source revision, artifact identity, configuration,
environment and actual outcomes, including negative/lifecycle cases. Host tests
alone cannot establish device equivalence.

## LATER

**PHONE-V1 — Broader Android Phone device coverage.** Extend the completed
`PHONE-P1` personal alpha with at least one Adreno and one Mali device, plus
longer lifecycle, thermal, battery, and audio checks. This is a future preview
stage, not a reopening of the personal-alpha milestone.

Signing, store publication, and wider device support can proceed separately
once the corresponding personal alpha is repeatable.

## COMPLETED

### IOS-P1 — iPad personal alpha (2026-10-10)

The owner completed the personal-alpha milestone. The
[closed IOS-P1 milestone](https://github.com/noah-be/overte/milestone/3) contains
eleven closed acceptance issues and no open issues. Its accepted scope remains
personal alpha; it does not certify the new full cross-client parity goal.

### PICO-P1 — Pico 4 personal alpha (2026-09-27)

The owner completed the personal-alpha milestone. The
[closed PICO-P1 milestone](https://github.com/noah-be/overte/milestone/1) contains
eleven closed acceptance issues and no open issues. Its accepted scope remains
personal alpha; new parity work preserves the existing VR behavior.

### PHONE-P1 — Android Phone personal alpha (2026-09-25)

All eleven acceptance issues are complete. The owner accepted the recorded
physical-device evidence, including the final audio and keyboard checks. See the
[closed PHONE-P1 milestone](https://github.com/noah-be/overte/milestone/2)
for source revisions, test records, and the scope of that acceptance.

Known limitations remain documented: microphone permission regrant requires an
app restart, and the intermittent Go To/Back crash is tracked in
[#933](https://github.com/noah-be/overte/issues/933). Broader device coverage and
F-Droid admission/publication are separate from personal-alpha completion.

### R0 — Reliable baseline and project compass (complete)

**Goal:** Make the fork understandable and safe to continue before expanding
the product surface.

**Exit criteria:**

- [x] this roadmap is the single repository-level source for portfolio order;
- [x] every product has a priority, honest maturity, evidence reference, and
  one next gate;
- [x] fork-specific contribution, security, ownership, and funding policies do
  not contradict the repository README;
- [x] the roadmap and fork-policy baseline is propagated through every
  permanent child branch without reverse-merging child work;
- [x] the quick project suite and branch-topology checks pass; and
- [x] all remote topic branches are classified, archived where needed, and
  retired using the [`R0 cleanup record`](BRANCH_CLEANUP.md); local workspace
  cleanup is deliberately post-review and is not a repository exit criterion.

## Routine maintenance

Maintain repository checks, security settings, and the parent-to-child branch
flow alongside the current product milestone. R0 remains completed; routine
maintenance is not a second active milestone. Technical ownership and branch
structure are documented in [branch governance](BRANCH_GOVERNANCE.md).

## Retired targets

Meta Quest and macOS are no longer development targets. Their history is
retained in the [cleanup record](BRANCH_CLEANUP.md); neither has a planned
resumption milestone.

## Product overview

| Product | Priority | Current status | Next milestone |
| --- | --- | --- | --- |
| Pico 4 | NOW (shared parity) | [Personal alpha completed](https://github.com/noah-be/overte/milestone/1) | [PICO-P2](https://github.com/noah-be/overte/milestone/5): shared features and artifact-bound acceptance |
| iPad | NOW (shared parity) | [Personal alpha completed](https://github.com/noah-be/overte/milestone/3) | [IOS-P2](https://github.com/noah-be/overte/milestone/6): shared features and artifact-bound acceptance; iPhone coverage later |
| Android Phone | NOW (shared parity) | [Personal alpha completed](https://github.com/noah-be/overte/milestone/2); known limitations retained | [PHONE-P2](https://github.com/noah-be/overte/milestone/4); PHONE-V1 broader coverage remains later |

The linked milestones hold detailed acceptance criteria and evidence. Historical
records and technical ownership belong in the linked documentation rather than
this priority overview.

## Working rules

- Keep one coordinated portfolio goal in `NOW`; its client milestones track the
  same CLIENT-PARITY goal rather than independent competing priorities.
- Use one active portfolio goal. CLIENT-PARITY has three client workstreams and
  the required shared/platform integration work; the owner explicitly authorized
  this parallel coordination.
- Keep branches focused on their ownership layer and retire only fully integrated
  work. The parallel parity goal requires isolated product and parent worktrees;
  do not delete unintegrated branches to meet an arbitrary count.
- Import upstream Overte changes only through the reviewed, one-way
  [`upstream intake policy`](UPSTREAM_INTAKE.md), from upstream `master` to
  fork `main`.
- Do not submit AI-assisted fork changes, issues, or pull requests to the
  upstream Overte project.
- Every change must advance a named exit criterion or repair a verified
  regression.
- Each active product roadmap has exactly one single next action.
- Update evidence only after a test at a named source revision and environment.
- Move chronological logs and superseded plans to `archive/`; do not use them as
  current instructions.
- Prefer milestone order and exit criteria over hobby-project deadlines.

## Milestone naming

Use stable identifiers in roadmaps and pull requests:

- `R<n>` for repository-wide maintenance;
- `PICO-P<n>` and `PHONE-P<n>` for Android product stages; P1 is personal alpha
  and P2 is the current cross-client parity stage;
- `IOS-P<n>` for iPhone and iPad product stages with the same P1/P2 distinction;
- `<TARGET>-V<n>` for broader preview milestones.

Pull requests should name the milestone they advance and the exit criterion
affected. Completing a task is not sufficient by itself; the resulting evidence
must satisfy the corresponding criterion.
