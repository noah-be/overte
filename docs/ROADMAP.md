# Experimental fork roadmap

> [!CAUTION]
> This roadmap describes an unofficial, AI-assisted hobby fork. It is not an
> Overte project commitment or a statement of official platform support.

- **Updated:** 2026-08-24
- **Baseline before this roadmap:** `main@9f00d77028`
- **Current repository milestone:** `R0`

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

### R0 — Reliable baseline and project compass

**Goal:** Make the fork understandable and safe to continue before expanding
the product surface.

**Exit criteria:**

- [ ] this roadmap is the single repository-level source for portfolio order;
- [ ] every product has a priority, honest maturity, evidence reference, and
  one next gate;
- [ ] fork-specific contribution, security, ownership, and funding policies do
  not contradict the repository README;
- [ ] the current `upstream/master` baseline is integrated through `main` and
  propagated through every permanent child branch;
- [ ] the quick project suite and branch-topology checks pass; and
- [ ] topic branches and worktrees are classified as active, mergeable,
  superseded, backup, or archival.

**Single next action:** Review and merge the project-compass documentation,
then update the fork policy in a separate `docs/main/fork-policy` change.

## NEXT

1. **PICO-P1 — Pico 4 personal alpha.** Meet the common personal-alpha
   definition on one explicitly named Pico 4, including worn-headset rendering,
   controllers, interaction, audio, lifecycle, and thermal behavior.
2. **PHONE-P1 — Android Phone personal alpha.** Meet the same common definition
   on one explicitly named physical Android phone before expanding the hardware
   matrix.
3. **IOS-P1 — iPad personal alpha.** Reconcile the documented bootstrap boundary
   with the integrated client, then meet the common definition on one explicitly
   named physical iPad. iPhone coverage follows later.

## LATER

- **MAC-P1 — macOS personal alpha.** Meet the common personal-alpha definition
  on one explicitly named physical Mac and record its architecture. Hosted
  software-renderer tuning is not a substitute for this gate.
- **PHONE-V1 — Android Phone preview coverage.** Add at least one Adreno and one
  Mali device plus longer lifecycle, thermal, battery, and audio evidence.
- Optional signing, notarization, store work, and wider device support begin
  only after the corresponding personal alpha is repeatable.

## PARKED

- **QUEST-Q0 — Meta Quest.** Preserve the product branch and existing preview
  evidence, but do not resume implementation until `PICO-P1` is complete and
  the old hardware-unverified preview has been deliberately reconciled.

## Portfolio

Priority describes current project attention. Maturity describes evidence; it
does not imply that a target is actively being developed.

| Interface or area | Priority | Current maturity | Development branch | Last reviewed evidence | Next gate |
| --- | --- | --- | --- | --- | --- |
| Repository baseline | NOW | Structurally verified | `main` | `main@9f00d77028`; quick suite 7/7 on 2026-08-24 | Complete `R0` |
| Pico 4 | NEXT 1 | Host-verified and build-ready; device acceptance incomplete | `android-vr-pico` | Interface status reviewed 2026-08-24 | `PICO-P1` |
| Android phones | NEXT 2 | Emulator-verified and build-ready; device coverage incomplete | `android-phone` | Interface status reviewed 2026-08-24 | `PHONE-P1` |
| iPhone and iPad | NEXT 3 | Simulator-verified bootstrap; integrated client experimental | `apple-ios` | Interface status and active branch reviewed 2026-08-24 | `IOS-P1` on iPad |
| macOS | LATER | Intel host/runtime verified; native arm64 experimental | `apple-macos` | Interface status reviewed 2026-08-24 | `MAC-P1` |
| Meta Quest | PARKED | Experimental and hardware-unverified | `android-vr-quest` | Branch and preview delta reviewed 2026-08-24 | Reassess after `PICO-P1` |
| Linux and Windows desktop | UPSTREAM-MAINTAINED | Inherited from Overte | `main` | Upstream baseline | Sync and regression checks only |

Detailed technical facts and evidence remain authoritative in the interface
documentation on each named product branch. This table records only portfolio
order and the next acceptance boundary.

## Working rules

- Exactly one repository milestone may be in `NOW`.
- Use one primary product track and at most one maintenance track at a time.
- Keep at most three active topic branches; classify or archive the rest.
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
- `MAC-P<n>` for macOS personal-alpha milestones;
- `<TARGET>-V<n>` for broader preview milestones; and
- `QUEST-Q<n>` for Quest incubation milestones.

Pull requests should name the milestone they advance and the exit criterion
affected. Completing a task is not sufficient by itself; the resulting evidence
must satisfy the corresponding criterion.
