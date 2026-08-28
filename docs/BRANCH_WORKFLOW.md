# Branch synchronization workflow

This fork separates shared work from platform- and product-specific work. A
change flows only from a less specific branch to a more specific descendant.
Do not merge a device branch back into its parent merely to distribute one
device's implementation.

## Branch hierarchy

```text
main
├── android-main
│   ├── android-phone
│   └── android-vr
│       ├── android-vr-quest
│       └── android-vr-pico
├── apple-main
│   ├── apple-ios
│   └── apple-macos
├── linux-main
└── windows-main
```

`main` owns platform-neutral code. `android-main`, `apple-main`, `linux-main`,
and `windows-main` own code shared by their operating-system families. Product
branches own adapters, packaging, runtime integration and policy that apply
only to that product. Linux distributions and Windows releases are CI and lab
targets within their operating-system branch, not permanent child branches.

The common device-test harness under `tests/device/` is parent-owned by
default. `tests/apple-branch-path-ownership.json` lists the narrow paths that a
specific Apple child may own inside that tree. The current iOS adapter,
RemoteXPC transport, signing and artifact handoff, product toolchain, and local
device-lab pipeline are `apple-ios`-owned; they do not propagate through
`apple-main` into `apple-macos`.

## Propagation order

After a reviewed change reaches `main`, synchronize it in this order:

1. `main` → `android-main`
2. `android-main` → `android-phone`
3. `android-main` → `android-vr`
4. `android-vr` → `android-vr-quest`
5. `android-vr` → `android-vr-pico`
6. `main` → `apple-main`
7. `apple-main` → `apple-ios`
8. `apple-main` → `apple-macos`
9. `main` → `linux-main`
10. `main` → `windows-main`

The Android, Apple, Linux, and Windows lines are independent after their
respective `main` merge, but each parent must be merged before its children.
Use normal pull requests so branch protection and target-specific CI run at
every boundary. The synchronization bot reads these direct relationships from
`.github/branch-policy.json`; every `main` update therefore opens or refreshes
the guarded sync pull requests for both desktop operating-system branches.

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

## Adapter ownership

Universal touch layout and capability defaults belong on `main`. Native and
selector-backed adapters remain in their product branch:

- Android Phone adapter: `android-phone`
- iPhone and iPad adapter: `apple-ios`
- Linux desktop adapter: `linux-main`
- Windows desktop adapter: `windows-main`
- macOS desktop adapter: `apple-macos`

VR branches do not inherit Phone touch adapters, and `apple-macos` does not
inherit the iOS adapter. A new adapter starts on its product branch and must not
be promoted to a parent unless the implementation genuinely applies to every
child of that parent.

The `Apple path ownership` pull-request check loads both its checker and policy
from `origin/apple-main`. A child pull request therefore cannot approve a
change by weakening its own copy of the rule. Changes to parent-owned harness
paths must go through `apple-main`; explicitly listed product-owned paths may
differ only on their matching target branch.

Desktop adapter implementations must not be owned by `main`, `android-main`,
or an Android product branch. Only the portable adapter protocol, behavior
modules, fixtures, and in-client probe remain on `main`. Fedora, Ubuntu,
openSUSE, display-server, desktop-environment, and Windows-version differences
are expressed as private target configuration and CI matrices inside the
owning operating-system branch.

## Verification

After synchronization, verify ancestry rather than relying only on matching
file contents:

```bash
git fetch origin --prune
git merge-base --is-ancestor origin/main origin/android-main
git merge-base --is-ancestor origin/android-main origin/android-phone
git merge-base --is-ancestor origin/android-main origin/android-vr
git merge-base --is-ancestor origin/android-vr origin/android-vr-quest
git merge-base --is-ancestor origin/android-vr origin/android-vr-pico
git merge-base --is-ancestor origin/main origin/apple-main
git merge-base --is-ancestor origin/apple-main origin/apple-ios
git merge-base --is-ancestor origin/apple-main origin/apple-macos
git merge-base --is-ancestor origin/main origin/linux-main
git merge-base --is-ancestor origin/main origin/windows-main
```

Each command must exit successfully. Also use `git branch -r --contains` for a
product-adapter commit and confirm that it appears only in its intended product
branch unless a later reviewed propagation deliberately changes that scope.
