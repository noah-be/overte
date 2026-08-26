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
└── apple-main
    ├── apple-ios
    └── apple-macos
```

`main` owns platform-neutral code. `android-main` and `apple-main` own code
shared by their operating-system families. Product branches own adapters,
packaging, runtime integration and policy that apply only to that product.

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

The Android and Apple halves are independent after their respective parent
merges, but each parent must be merged before its children. Use normal pull
requests so branch protection and target-specific CI run at every boundary.

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

VR branches do not inherit Phone touch adapters, and `apple-macos` does not
inherit the iOS adapter. A new adapter starts on its product branch and must not
be promoted to a parent unless the implementation genuinely applies to every
child of that parent.

The `Apple path ownership` pull-request check loads both its checker and policy
from `origin/apple-main`. A child pull request therefore cannot approve a
change by weakening its own copy of the rule. Changes to parent-owned harness
paths must go through `apple-main`; explicitly listed product-owned paths may
differ only on their matching target branch.

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
```

Each command must exit successfully. Also use `git branch -r --contains` for a
product-adapter commit and confirm that it appears only in its intended product
branch unless a later reviewed propagation deliberately changes that scope.
