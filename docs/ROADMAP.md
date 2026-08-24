# Experimental fork roadmap

> [!CAUTION]
> This roadmap describes an unofficial, AI-assisted hobby fork. It is not an
> Overte project commitment or a statement of official platform support.

- **Updated:** 2026-08-24
- **Baseline before this roadmap:** `main@9f00d77028`
- **Current primary milestone:** `PICO-P1`
- **Current maintenance milestone:** `R0`

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
Pico 4, including worn-headset rendering, controllers, interaction, audio,
lifecycle, and thermal behavior.

The detailed exit criteria and evidence boundary are authoritative on the
`android-vr-pico` product branch.

**Single next action:** Install the APK from the current candidate revision on
one explicitly selected Pico 4 and run the documented core-journey baseline,
recording the first blocking failure.

## NEXT

1. **PHONE-P1 — Android Phone personal alpha.** After `PICO-P1`, meet the
   common definition on one explicitly named physical Android phone before
   expanding the hardware matrix.
2. **IOS-P1 — iPad personal alpha.** After `PHONE-P1`, reconcile the documented
   bootstrap boundary with the integrated client, then meet the common
   definition on one explicitly named physical iPad. iPhone coverage follows
   later.

## MAINTENANCE

### R0 — Reliable baseline and project compass

**Goal:** Make the fork understandable and safe to continue before expanding
the product surface.

**Exit criteria:**

- [x] this roadmap is the single repository-level source for portfolio order;
- [x] every product has a priority, honest maturity, evidence reference, and
  one next gate;
- [x] fork-specific contribution, security, ownership, and funding policies do
  not contradict the repository README;
- [x] the roadmap and fork-policy baseline is propagated through every
  permanent child branch without importing new upstream changes;
- [x] the quick project suite and branch-topology checks pass; and
- [ ] topic branches and worktrees are classified and safely reduced using the
  [`R0 cleanup checklist`](BRANCH_CLEANUP.md).

**Single next action:** Review the seven worktrees with local changes one at a
time, starting with the superseded Android/Pico roadmap worktree, and preserve
unique work before removing anything.

## LATER

- **PHONE-V1 — Android Phone preview coverage.** Add at least one Adreno and one
  Mali device plus longer lifecycle, thermal, battery, and audio evidence.
- Optional signing, notarization, store work, and wider device support begin
  only after the corresponding personal alpha is repeatable.

## PARKED

- **QUEST-Q0 — Meta Quest.** Preserve the product branch and existing preview
  evidence, but do not resume implementation until a named physical Quest is
  available. Virtual or simulated testing is not a substitute for this gate.
- **MAC-P1 — macOS personal alpha.** Preserve the current hosted Intel evidence,
  but do not resume product work until a named physical Mac is available.
  Further virtual/software-renderer testing is not a substitute for this gate.

## Portfolio

Priority describes current project attention. Maturity describes evidence; it
does not imply that a target is actively being developed.

| Interface or area | Priority | Current maturity | Development branch | Last reviewed evidence | Next gate |
| --- | --- | --- | --- | --- | --- |
| Repository baseline | MAINTENANCE | Structurally verified; cleanup incomplete | `main` | `main@5456a20883`; quick suite 7/7 on 2026-08-24 | Safely complete `R0` cleanup |
| Pico 4 | NOW | Host-verified and build-ready; device acceptance incomplete | `android-vr-pico` | Interface roadmap and status reviewed 2026-08-24 | `PICO-P1` |
| Android phones | NEXT 1 | Emulator-verified and build-ready; device coverage incomplete | `android-phone` | Interface roadmap and status reviewed 2026-08-24 | `PHONE-P1` after Pico |
| iPhone and iPad | NEXT 2 | Simulator-verified bootstrap; integrated client experimental | `apple-ios` | iPad roadmap and status reviewed 2026-08-24 | `IOS-P1` after Android Phone |
| macOS | PARKED | Hosted Intel runtime-verified; physical hardware unavailable | `apple-macos` | Interface status reviewed 2026-08-24 | Resume `MAC-P1` with a named physical Mac |
| Meta Quest | PARKED | Experimental; physical hardware unavailable | `android-vr-quest` | Branch and preview delta reviewed 2026-08-24 | Resume `QUEST-Q0` with a named physical Quest |
| Linux and Windows desktop | OUT OF SCOPE | Inherited historical baseline | `main` | Fork baseline | Fork regression checks only |

Detailed technical facts and evidence remain authoritative in the interface
documentation on each named product branch. This table records only portfolio
order and the next acceptance boundary.

## Working rules

- Exactly one repository milestone may be in `NOW`.
- Use one primary product track and at most one maintenance track at a time.
- Keep at most three active topic branches; classify or archive the rest.
- Do not merge, rebase, cherry-pick, or otherwise import new changes from the
  upstream Overte repository into this AI-assisted fork.
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
- `MAC-P<n>` for macOS personal-alpha milestones;
- `<TARGET>-V<n>` for broader preview milestones; and
- `QUEST-Q<n>` for Quest incubation milestones.

Pull requests should name the milestone they advance and the exit criterion
affected. Completing a task is not sufficient by itself; the resulting evidence
must satisfy the corresponding criterion.
