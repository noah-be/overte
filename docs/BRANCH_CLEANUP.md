# R0 branch and remote cleanup

> [!IMPORTANT]
> This is the verified repository-level cleanup record for this unofficial
> fork. It does not authorize local workspace deletion or another upstream
> intake. Future intake uses the separate
> [upstream intake policy](UPSTREAM_INTAKE.md).

**Facts freeze:** 2026-09-03, after the Session 53X ref lifecycle and before
the documentation merge SHA and its mandatory final forward propagation were
created.

## Final remote structure

- exactly nine permanent branches:
  `main`, `android-main`, `android-phone`, `android-vr`, `android-vr-pico`,
  `apple-main`, `apple-ios`, `linux-main`, and `windows-main`;
- exactly 143 logical tags;
- no remote topic, hold, backup, Quest, or macOS branch remains;
- no open pull request or active/waiting Actions run at the facts freeze; and
- all eight direct parent-to-child edges were complete. The final
  documentation commit is propagated through the same 4 + 3 + 1 waves before
  Session 53X closes.

The nine branches are the complete live branch set. Platform work moves only
from parent to direct child; no child-to-parent or sibling merge is permitted.

## Retired branch recovery

The final 13 non-permanent branches were deleted only after exact tip and
consumer checks. Each tip remains reachable from a protected annotated tag:

| Retired branch | Recovery tag |
| --- | --- |
| `android-vr-quest` | `archive/android-vr-quest-2026-08-28` |
| `apple-macos` | `archive/apple-macos-2026-08-28` |
| `backup/pico4-native-coverage-2026-08-09` | `archive/backup-pico4-native-coverage-2026-08-09` |
| `backup/pico4-work-2026-08-01` | `archive/backup-pico4-work-2026-08-01` |
| `test/android/phone-hardware-acceptance` | `archive/android-phone-hardware-acceptance-2026-09-03` |
| `test/ios/ipad-hardware-acceptance` | `archive/ios-ipad-hardware-acceptance-2026-09-03` |
| `test/main/cross-platform-e2e-integration` | `archive/test-main-cross-platform-e2e-pr477-2026-09-03` |
| `test/pico/pico4-hardware-stability-upgrade` | `archive/pico4-hardware-stability-upgrade-2026-09-03` |
| `feature/universal-touch-ui` | `archive/feature-universal-touch-ui-2026-09-03` |
| `fix/ios/ipad-fast-dev-texture-reuse` | `archive/ios-ipad-fast-dev-texture-reuse-2026-09-03` |
| `test/universal-touch-ui-android-validation` | `archive/universal-touch-ui-android-validation-2026-09-03` |
| `test/universal-touch-ui-apple-validation` | `archive/universal-touch-ui-apple-validation-2026-09-03` |
| `tests/unify-interfaces` | `archive/tests-unify-interfaces-2026-09-03` |

The immutable archive-tag ruleset protects `archive/**` against deletion and
non-fast-forward updates without bypass. A second recovery path is the
externally stored and verified bundle whose SHA-256 is
`407bae393314005e145232242e66d54ed2858e5c25e31537b2ff2085c5ef2257`.
It contains all 13 deleted tips.

## Earlier cleanup history

- Session 40B preserved 38 archive branches through 35 archive tags and
  deleted 163 redundant remote branches. Its handoff state was 22 branches and
  132 logical tags.
- Session 41B removed 12,837 caches totalling 7,635,481,517 bytes and 679
  artifacts totalling 60,956,343,235 bytes. Twenty-four additional artifacts
  were already naturally absent. It did not modify the 12 releases or their
  18 release assets.

## Separately tracked follow-up evidence

- **R17 hardware acceptance:** R17 remains an optional, separately authorized
  hardware project. No hardware, device, emulator, or simulator acceptance was
  performed in Session 53X, and successful device-free checks do not satisfy
  R17.
- **Natural Actions artifact expiry:** The 100 recorded archived-branch
  Actions artifacts, totalling 720,210,441 bytes, are retained for natural
  expiry. No manual deletion or payload download is part of this cleanup. The
  latest recorded expiry is 2026-11-28T08:08:11Z; E34 remains open until a
  fresh post-expiry audit confirms that no active artifact remains for the
  archived branches. Actions artifacts are distinct from release assets.
- **Release and supply-chain pilot:** Session 53X added an inactive,
  fail-closed bundle-validation and attestation/draft workflow foundation, but
  did not run a release workflow or create or modify a release, release asset,
  draft, or release tag. A real pilot requires separate authorization for the
  exact product, tag, commit, workflow, and release object. The 12 legacy
  releases and 18 legacy assets remain unchanged and are not retroactively
  claimed to be complete, reproducible, attested, or immutable. Independent
  legacy payload digests and historical attestation binding remain separate
  E37/E40 work.

## Exit criteria

- [x] exactly nine permanent remote branches remain;
- [x] all retired branch tips have a protected tag and recovery-bundle path;
- [x] no remote topic, hold, or backup branch remains;
- [x] no unique remote commit was discarded;
- [x] the repository branch and tag counts are recorded here; and
- [x] local workspace cleanup is explicitly deferred until after coordinator
  review and is not a repository success criterion.

Local branches, worktrees, and untracked files may contain independent user
work. They were deliberately not cleaned in Session 53X and must be reviewed
separately before any local deletion.
