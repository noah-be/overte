# Experimental fork roadmap

> [!CAUTION]
> This roadmap describes an unofficial, AI-assisted hobby fork. It is not an
> Overte project commitment or a statement of official platform support.

- **Updated:** 2026-09-25
- **Repository baseline:** Seven permanent branches and six synchronization
  edges; Linux and Windows support and tests maintained on `main`. Session 53X
  records remain historical evidence.
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

## COMPLETED

### PHONE-P1 — Android Phone personal alpha (2026-09-25)

The owner accepted the personal-alpha outcome and closed the
[PHONE-P1 milestone](https://github.com/noah-be/overte/milestone/2), with all
eleven acceptance issues completed. The milestone records the device evidence,
source revisions, and retained limitations; the final tested app was 0.1.2
(version code 3), built from `cd08e500d73d661c6050a8f3ad4c45921c03770c`.

The final audio and keyboard criteria,
[#802](https://github.com/noah-be/overte/issues/802) and
[#807](https://github.com/noah-be/overte/issues/807), were closed through explicit
owner approval of the recorded evidence. This completion does not claim a new
single-candidate rerun of all eleven criteria. Microphone permission regrant
requires an app restart; the intermittent Go To/Back crash remains tracked
separately in [#933](https://github.com/noah-be/overte/issues/933).

Broader `PHONE-V1` device coverage and F-Droid admission/publication remain
separate from this completed personal-alpha milestone.

## MAINTENANCE

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

**Maintenance handoff:** Keep the seven-branch topology, required checks,
workflow pins, recovery bundles, and security settings consistent. Review local
worktrees separately before any local deletion.

## LATER

- **PHONE-V1 — Android Phone preview coverage.** Add at least one Adreno and one
  Mali device plus longer lifecycle, thermal, battery, and audio evidence.
- Optional signing, notarization, store work, and wider device support begin
  only after the corresponding personal alpha is repeatable.

## ARCHIVED

- **Meta Quest.** Quest is not a development target for this fork. The retired
  `android-vr-quest` branch and its hardware-unverified preview evidence are
  retained for history only. There is no resume milestone or synchronization
  path from `android-vr`.
- **macOS.** macOS is not a development target for this fork. The retired
  `apple-macos` branch, hosted Intel evidence, and unfinished diagnostic work
  are retained for history only. There is no resume milestone or
  synchronization path from `apple-main`.

## Portfolio

Priority describes current project attention. Maturity describes evidence; it
does not imply that a target is actively being developed.

| Interface or area | Priority | Current maturity | Development branch | Last reviewed evidence | Next gate |
| --- | --- | --- | --- | --- | --- |
| Repository baseline | MAINTENANCE | Structurally verified; remote cleanup complete | `main` | Historical Session 53X: 9 branches, 143 tags and device-free checks; current hierarchy has 7 permanent branches | Preserve the verified baseline |
| Android phones | LATER (preview expansion) | Personal alpha accepted on one physical phone; known limitations retained | `android-phone` | [PHONE-P1 completion, 2026-09-25](https://github.com/noah-be/overte/milestone/2), including owner-approved audio and keyboard evidence | `PHONE-V1` broader device coverage; [#933](https://github.com/noah-be/overte/issues/933) tracked separately |
| Pico 4 | NOW | Host-verified and build-ready; device acceptance incomplete | `android-vr-pico` | Session 53X device-free contracts and selective fixes | `PICO-P1` |
| iPhone and iPad | NEXT | Host-verified bootstrap; integrated client experimental | `apple-ios` | Session 53X device-free contracts and selective fixes | `IOS-P1` after Pico |
| macOS | ARCHIVED | Historical hosted Intel evidence; never accepted on owned physical hardware | None (retired) | Historical archival evidence verified 2026-09-03; [cleanup record](BRANCH_CLEANUP.md) | None; not a project target |
| Meta Quest | ARCHIVED | Historical experimental code; never accepted on physical hardware | None (retired) | Historical archival evidence verified 2026-09-03; [cleanup record](BRANCH_CLEANUP.md) | None; not a project target |
| Linux desktop | OUT OF SCOPE product; E2E MAINTENANCE | Inherited client support and tests maintained on main | `main` | Historical Session 53X checks; branch ownership simplified 2026-09-16 | Repeatable Linux `e2e-core` target evidence |
| Windows desktop | OUT OF SCOPE product; E2E MAINTENANCE | Inherited client support and tests maintained on main | `main` | Historical Session 53X checks; branch ownership simplified 2026-09-16 | Hardware-free adapter contracts, then an interactive target |

Detailed technical facts and evidence remain authoritative in the interface
documentation on each named product branch. This table records only portfolio
order and the next acceptance boundary.

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
