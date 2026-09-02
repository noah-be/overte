# R0 branch and worktree cleanup

> [!IMPORTANT]
> This is a temporary R0 maintenance checklist for this fork. It does not by
> itself authorize an upstream intake, and it must not be used to delete a
> branch, worktree, commit, or untracked file without the checks below. Planned
> upstream updates use the separate [upstream intake policy](UPSTREAM_INTAKE.md).

**Snapshot:** 2026-08-24

- 66 local branches;
- 49 `origin` refs after pruning deleted remote refs;
- 20 linked worktrees;
- 18 local branches whose tracked `origin` branch is gone; and
- 9 `origin` topic branches not contained by ancestry in a permanent branch.

## Safety rules

Before removing a ref or worktree:

1. confirm that it is not one of the nine active permanent branches or the
   frozen `android-vr-quest` and `apple-macos` archives;
2. confirm that no open pull request uses it;
3. inspect the worktree with `git status --short`;
4. compare its unique commits with the intended permanent target;
5. preserve required unique work in a reviewed branch, explicit archival tag,
   or external bundle; and
6. remove the worktree before deleting its checked-out local branch.

Do not use an upstream ref as a cleanup target or source when classifying or
deleting cleanup refs. This restriction does not prohibit a separately
reviewed upstream intake.

## Active permanent branches — keep

- `main`
- `android-main`
- `android-phone`
- `android-vr`
- `android-vr-pico`
- `apple-main`
- `apple-ios`
- `linux-main`
- `windows-main`

## Archived branch — keep frozen

- `android-vr-quest`, preserved at archival tag
  `archive/android-vr-quest-2026-08-28`; do not synchronize, update, or delete
  it.
- `apple-macos`, preserved at archival tag
  `archive/apple-macos-2026-08-28`; do not synchronize, update, or delete it.

## Existing work to close or pause

- [ ] `fix/ios/ipad-fast-dev-texture-reuse`: finish or deliberately stop the
  existing iPad checkpoint, then pause iOS expansion until `PICO-P1` and
  `PHONE-P1` are complete.
- [x] `test/macos/qemu-low-power-diagnostic`: pull request #176 closed without
  merging and its unique commit preserved at archival tag
  `archive/macos-qemu-low-power-pr176-2026-08-28`.

These are existing work boundaries, not permission to start another product
track. `PICO-P1` remains the first product milestone after R0.

## Review before deciding

- [ ] `test/universal-touch-ui-apple-validation`
- [ ] `test/universal-touch-ui-android-validation`
- [ ] `feature/universal-touch-ui`
- [ ] local `tests/unify-interfaces`, which is 33 commits behind `main` and has
  one unique commit at this snapshot

For each branch, record whether its result already exists under a different
commit, still advances a current milestone, or should become archival evidence.

## Quest topic evidence

- [ ] `quest-port`: preserve any unique hardware-unverified evidence in the
  frozen Quest archive or an explicit archival tag, then retire its worktree.

## Superseded documentation

- [ ] `docs/android-phone-pico4-roadmap`: superseded by
  [`ROADMAP.md`](ROADMAP.md). Preserve only unique historical evidence that is
  still useful, then archive or remove the branch and its worktree.

## Explicit backups

- [ ] `backup/pico4-native-coverage-2026-08-09`
- [ ] `backup/pico4-work-2026-08-01`

Create an archival tag or external bundle after verifying unique commits before
deleting either backup ref.

## Merged remote topic refs — cleanup candidates

The following groups were contained by ancestry in a permanent branch at the
snapshot. They may be removed from `origin` only after the safety checks:

- completed documentation branches for Android Phone, Pico 4, iOS, macOS, and
  the interface documentation audit;
- completed shared Tablet QML and Qt 6 fixes targeting `main`;
- completed iOS tablet, touch, locomotion, and lifecycle fixes; and
- completed macOS build, rendering, runtime, first-frame, and diagnostic fixes.

Regenerate the exact candidate list before deletion; do not rely on this
summary after branch state changes.

## Local branches with a deleted remote — cleanup candidates

At the snapshot this group contains completed `ci/macos/*`, `fix/macos/*`, the
merged `docs/main/*` branches, `ci/main/auto-merge-branch-sync`, and
`test/macos/classify-first-frame-progress`.

Some are still attached to a worktree. Apply the safety rules and remove only
one verified branch/worktree pair at a time.

## Worktree classification

- **Keep:** the primary `main` worktree and worktrees for a genuinely active
  checkpoint.
- **Temporary keep:** permanent-branch worktrees until internal propagation and
  topology checks are complete.
- **Review:** device-stability, emulator-testing, interface-test, iOS common,
  Qt 6 Tablet, and universal-touch validation worktrees.
- **Archive review:** Quest and macOS worktrees; preserve unique evidence, then
  retire them rather than resuming development.
- **Cleanup candidate:** superseded roadmap and completed topic worktrees after
  their unique work and local status have been verified.

## Exit criteria

- [ ] all nine active permanent branches and the frozen Quest and macOS
  archives remain intact;
- [ ] no more than three topic branches are active;
- [ ] every remaining topic branch is active, parked, or an explicit backup;
- [ ] every remaining worktree has a current purpose;
- [ ] no unique commit or untracked work is lost; and
- [ ] final branch, remote-ref, and worktree counts are recorded here.
