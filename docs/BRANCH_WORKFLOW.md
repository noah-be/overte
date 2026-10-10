# Branch synchronization workflow

This fork separates shared work from platform- and product-specific work. A
change flows only from a less specific branch to a more specific descendant.
Do not merge a device branch back into its parent merely to distribute one
device's implementation.

## Local branch-name guards

Use the policy's `<kind>/<scope>/<lowercase-hyphenated-name>` form, such as
`fix/android-phone/default-microphone`. A task branch uses
`task/<scope>/<positive-issue-number>-<lowercase-hyphenated-name>`.
`fix/android-phone-default-microphone` is invalid: it omits the separator after
the scope. Permanent branch names and configured Dependabot security-update
names have their own explicit rules.

Before creating a branch, validate it without requiring a pull request:

```bash
python3 tools/branch-policy/check.py check-name --branch fix/android-phone/default-microphone
```

Install or update the guards from a reviewed checkout once per clone:

```bash
python3 tools/branch-policy/install.py install
python3 tools/branch-policy/install.py status
```

The installer places a copy of the reviewed checker and policy in the shared Git
directory, so linked worktrees, including older checkouts, use the same installed
rules. It preserves unrelated hooks and refuses conflicting hooks or custom
`core.hooksPath` settings. It does not silently replace another developer's hook
setup. Reinstall after a reviewed policy update; policy edits in a working branch
do not replace the installed copy.

The reference-transaction guard rejects invalid new local branch refs before
creation, including ordinary `git branch`, `git switch -c`, and `git worktree add
-b`. Existing branch updates and deletions, tags and remote-tracking fetches remain
possible. The pre-push guard validates each destination branch name, including
an alias such as `HEAD:refs/heads/another-name`, before publishing any refs.

These are local safeguards, not server-side authorization. Git's files backend
does not expose the new name to the reference-transaction hook for every local
rename or copy (`git branch -m` / `-c`); pre-push still rejects publishing those
invalid names. Git hooks can be bypassed or disabled, and they are not installed
automatically by a clone. The read-only Repository Health Doctor therefore also
audits all remote branch names, even without a pull request. An invalid name is
a finding, never permission to delete that branch. Preserve its commits when
correcting its name.

## Branch hierarchy

```text
main
├── android-main
│   ├── android-phone
│   └── android-vr
│       └── android-vr-pico
└── apple-main
    └── apple-ios
```

`main` owns platform-neutral code and Linux and Windows support, including
desktop adapters, packaging, tests, and lab integration. `android-main` and
`apple-main` own code shared by their operating-system families. Product
branches own adapters, packaging, runtime integration and policy specific to
that product. Linux distributions and Windows releases are CI and lab targets
maintained on `main`. There are seven permanent branches and six direct edges.

## Source ownership

The [source layout policy](SOURCE_LAYOUT.md) separates Android application
implementation from `main`. During its one-time migration, retain Android-owned
files and the branch test profile on the Android side of the merge. Subsequent
synchronization uses the same forward-merge topology.

## Propagation order

After a reviewed change reaches `main`, synchronize it in this order:

1. `main` → `android-main`
2. `android-main` → `android-phone`
3. `android-main` → `android-vr`
4. `android-vr` → `android-vr-pico`
5. `main` → `apple-main`
6. `apple-main` → `apple-ios`

The Android and Apple lines are independent after their respective `main`
merge, but each parent must be merged before its children. Desktop changes
are reviewed and tested on `main` without a separate desktop synchronization edge.
Use normal pull requests so branch protection and target-specific CI run at
every boundary. The synchronization bot reads these direct relationships from
`.github/branch-policy.json`. The current synchronization workflow reports
parent-to-child drift without writing to the repository; a maintainer opens or
refreshes each required synchronization pull request manually.

The retired Quest and macOS branches are historical records, not children
in this hierarchy. They must not receive synchronization PRs or new product
work.

## Reconciliation merges

Long-lived child branches can contain earlier copies of a change or unrelated
product work. If GitHub reports no comparable commits or a direct merge would
replay obsolete history, create a temporary reconciliation branch from the
child, merge the current parent into it, resolve conflicts according to the
child's current platform contracts, and open the pull request back to that
child. Never force-push a protected integration branch.

When resolving a conflict:

- preserve the parent's shared API and tests;
- preserve newer child-specific runtime and security behavior;
- remove obsolete duplicated implementations only after their replacement is
  present; and
- run both the parent's relevant contracts and the child's complete required
  gate before merging.

The reconciliation branch name must exactly match
`reconcile/<child-scope>/<name>`. It starts at the current child and its head is
the normal merge commit whose first parent is that exact child SHA and whose
second parent is the exact current direct-parent SHA. Both tips are obtained
from the GitHub API by the trusted default-branch policy checker and must remain
unchanged throughout its attestation.

Privileged branch-policy and synchronization paths are not manually resolved
on a temporary reconciliation branch. Their complete head tree must exactly
match the current direct parent's tree for every privileged path: existence,
mode, object type, and object SHA are all compared. Missing, additional,
changed, or deleted privileged entries fail closed. The checker also requires
both current commits to be ancestors of the head and rejects API, comparison,
or incomplete-tree errors. It runs with read-only permissions and never
executes code from the pull request. Other governance changes remain owned by
`main`, and an ordinary `sync/*` topic receives no reconciliation privilege.

## Adapter ownership

Universal touch layout and capability defaults belong on `main`. Native and
selector-backed mobile adapters remain in their product branch; desktop
adapters are maintained on `main`:

- Android Phone adapter: `android-phone`
- iPhone and iPad adapter: `apple-ios`
- Linux desktop adapter: `main`
- Windows desktop adapter: `main`

VR branches do not inherit Phone touch adapters. A new adapter starts on its
product branch and must not be promoted to a parent unless the implementation
genuinely applies to every child of that parent.

Desktop adapter implementations, the portable adapter protocol, behavior
modules, fixtures, and in-client probe belong on `main`. Fedora, Ubuntu,
openSUSE, display-server, desktop-environment, and Windows-version differences
are expressed as private target configuration and CI matrices maintained from
`main`. Retiring separate desktop branches does not remove desktop product
support or tests.

## Verification

After synchronization, verify ancestry rather than relying only on matching
file contents:

```bash
git fetch origin --prune
git merge-base --is-ancestor origin/main origin/android-main
git merge-base --is-ancestor origin/android-main origin/android-phone
git merge-base --is-ancestor origin/android-main origin/android-vr
git merge-base --is-ancestor origin/android-vr origin/android-vr-pico
git merge-base --is-ancestor origin/main origin/apple-main
git merge-base --is-ancestor origin/apple-main origin/apple-ios
```

Each command must exit successfully. Also use `git branch -r --contains` for a
product-adapter commit and confirm that it appears only in its intended product
branch unless a later reviewed propagation deliberately changes that scope.

## Exact-parent test reuse

A synchronization changing only regular `package.json` / `package-lock.json`
files under `tools/jsdoc` or `server-console`, optionally with Markdown, runs
the [bounded tool checks](../tests/PROJECT_TESTING.md#host-prerequisites).
The trusted gate verifies the existing topology and both Git trees' file modes
before selecting this profile. It includes rename sources and rejects mixed
source/build deltas from the bounded lane. Pushes run the same affected-tool
checks without publishing complete host-qualification evidence. Such syncs do
not repeat the native client build, complete host suite, or product suites.

The four permanent branches that have children (`main`, `android-main`,
`android-vr`, and `apple-main`) qualify each exact pushed commit once, except
for Markdown-only pushes and the bounded tool-only pushes above. The
qualification runs the shared project and complete device-control-plane suites,
then uploads a short-lived machine-readable artifact. The artifact binds the
repository numeric ID and name, parent commit and tree, qualification workflow
blob, shared test definitions, workflows, lockfiles, toolchain inputs, test
configuration, successful results, run identity, GitHub Actions App ID, and
validity interval. Its canonical JSON digest makes accidental or malicious
content changes detectable.

The trusted `sync-test-reuse` check is loaded only from the default branch. For
one of the six direct edges it re-reads the current base and parent refs,
validates the exact merge parents and merge tree, rejects paths outside the
parent delta, and accepts exactly one matching non-expired qualification from a
successful `push` run of the expected workflow. It re-reads both permanent refs
after verification so a target or parent race fails closed.

Dispatched validation is correlated by both the gate's `GITHUB_RUN_ID` and
`GITHUB_RUN_ATTEMPT` (`gate-<run-id>-attempt-<attempt>`). The `dispatch-and-wait`
command requires `--gate-run-id` and takes the attempt from `--gate-run-attempt`
when supplied, otherwise from `GITHUB_RUN_ATTEMPT` for compatibility with older
workflow definitions. Missing, invalid, or nonpositive attempts are rejected
before any API request; there is no constant default. A rerun must not reuse
an earlier attempt's result. The gate waits for the current attempt to
become visible and complete successfully. Multiple matching runs, an
unsuccessful current run, or a timeout fail the gate in both reuse and full
fallback mode.

The trusted default-branch `reconciliation_repair_paths` configuration can
authorize exact nonprivileged product paths per target. A reconciliation
touching one of these paths (including either side of a rename) must pass the
existing branch-policy API attestation: exact current base/direct-parent merge,
same repository, parent-identical privileged tree, and unchanged refs. The
executed merge candidate must also retain the exact parent's privileged tree.
Only listed extra paths are allowed outside the parent delta; the exact legacy
retirement contract remains separate. Such reconciliations always select the
complete fallback, even for Markdown or valid parent qualification. This is
conservative: a listed path inherited unchanged from the parent also forces
fallback. No new direct-sync, topology, or ruleset exception is introduced.


The iOS ownership transition has seven exact native-only repair inputs: the
iOS audio adapter pair, the native binding tests, the retained Appium adapter
and its relocated test, and the existing product-owned RemoteXPC privacy
fixture. This does not authorize shared probe, fixture, runner or protocol
changes on the iOS leaf. Those changes must arrive through `main` and
`apple-main`. New native adapters and self-tests live under
`tests/device/ios/adapters/` and `tests/device/ios/self_tests/`; generic shared
imports keep the parent implementation. Each attested native repair requires
the complete fallback and the independent exact-candidate iOS build gate.
The trusted iOS host gate installs the existing pinned host requirements in
a separate test environment before executing native regressions, including
independent permission-switch image checks. Product dependency caches and
physical-device qualification remain separate.

When all bindings match, a separate read-only validation workflow runs only the
edge-specific hardware-free differential profile. The redundant Android and
project-wide suites delegate to this required check, while topology, policy,
workflow-security, documentation, and relevant Android VR or iOS checks remain
independent. A Markdown-only sync selects only documentation and contract
validation after the same topology and identity checks, without requiring
parent qualification evidence or selecting the full fallback. Rename sources
must also be Markdown; executable files under `docs/` are not exempt.
Markdown-only pushes skip parent qualification and the project-wide suite.
CodeQL also skips Markdown-only pushes and pull requests; scheduled scans remain.

Missing, stale, duplicated, incomplete, foreign, or otherwise mismatched
evidence selects the complete shared fallback in the isolated read-only
validation workflow. It never turns an evidence error into an unchecked pass.
Ordinary task, feature, promotion, Dependabot, and fork pull requests are not
eligible for delegation and keep their existing full path-appropriate checks.
The machine-readable contract is
[`../.github/sync-test-reuse.json`](../.github/sync-test-reuse.json).
