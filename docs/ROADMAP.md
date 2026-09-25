# Experimental fork roadmap

> [!CAUTION]
> This roadmap describes an unofficial, AI-assisted hobby fork. It is not an
> Overte project commitment or a statement of official platform support.

- **Updated:** 2026-09-25
- **Current milestone:** `PICO-P1` — Pico 4 personal alpha
- **Next:** `IOS-P1` — iPad personal alpha
- **Later:** `PHONE-V1` — broader Android Phone device coverage
- **Completed:** `PHONE-P1` — Android Phone personal alpha; `R0` — repository baseline

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

### PICO-P1 — Pico 4 personal alpha

**Goal:** Meet the common personal-alpha definition on one explicitly named
physical Pico 4, including worn-headset rendering, controllers, interaction,
audio, lifecycle, and thermal behavior.

The detailed exit criteria and evidence boundary are authoritative on the
`android-vr-pico` product branch and the
[PICO-P1 milestone](https://github.com/noah-be/overte/milestone/1).

**Single next action:** Review the eleven open Pico acceptance criteria against
existing evidence and identify the physical-device candidate for the first
remaining acceptance check.

## NEXT

**IOS-P1 — iPad personal alpha.** After `PICO-P1`, reconcile the documented
bootstrap boundary with the integrated client, then meet the common definition
on one explicitly named physical iPad. iPhone coverage follows later. See the
[IOS-P1 milestone](https://github.com/noah-be/overte/milestone/3).

## LATER

**PHONE-V1 — Broader Android Phone device coverage.** Extend the completed
`PHONE-P1` personal alpha with at least one Adreno and one Mali device, plus
longer lifecycle, thermal, battery, and audio checks. This is a future preview
stage, not a reopening of the personal-alpha milestone.

Signing, store publication, and wider device support can proceed separately
once the corresponding personal alpha is repeatable.

## COMPLETED

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
| Pico 4 | NOW | Physical-device acceptance still open | [PICO-P1: personal alpha](https://github.com/noah-be/overte/milestone/1) |
| iPad | NEXT | Integrated client experimental; physical-device acceptance still open | [IOS-P1: personal alpha](https://github.com/noah-be/overte/milestone/3); iPhone coverage later |
| Android Phone | LATER (broader coverage) | [Personal alpha completed](https://github.com/noah-be/overte/milestone/2); known limitations retained | PHONE-V1: broader device coverage |

The linked milestones hold detailed acceptance criteria and evidence. Historical
records and technical ownership belong in the linked documentation rather than
this priority overview.

## Working rules

- Exactly one repository milestone may be in `NOW`.
- Use one primary product track and at most one maintenance track at a time.
- Keep at most three active topic branches; classify or archive the rest.
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
- `PICO-P<n>` and `PHONE-P<n>` for Android personal-alpha milestones;
- `IOS-P<n>` for iPhone and iPad personal-alpha milestones;
- `<TARGET>-V<n>` for broader preview milestones.

Pull requests should name the milestone they advance and the exit criterion
affected. Completing a task is not sufficient by itself; the resulting evidence
must satisfy the corresponding criterion.
