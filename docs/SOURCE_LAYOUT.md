# Shared and Android source ownership

`main` contains the portable client, libraries, shared resources, desktop support,
tests, and repository control plane. Android applications and their toolchains,
Android-only resource selectors, native backends, packaging, and device-specific
checks belong to `android-main` and its product descendants. The physical paths
on the Android branches remain unchanged.

## Working branches

| Work | Starting branch |
| --- | --- |
| Portable client, shared libraries, generic UI and tests | `main` |
| Shared Android runtime and dependency infrastructure | `android-main` |
| Android Phone application and acceptance | `android-phone` |
| Shared Android VR behavior | `android-vr` |
| Pico-specific application and acceptance | `android-vr-pico` |
| Shared Apple integration and iOS application | `apple-main` and `apple-ios` |

This is one repository with forward merges, not separate repositories and not
selective cherry-picking. Source ownership does not require removing platform
enums, preprocessor conditions, capability defaults, compatibility interfaces, or
portable tests that exercise multiple platform profiles from shared code.

Some shared files retain historical product names. `PhoneLoginState.h` is also
used by shared account lifecycle bindings and desktop/iOS contract tests.
`PhoneDialogRouter.h` is a small compatibility interface implemented by the
shared dialog manager. `PicoPlaces.qml` is the shared non-WebEngine fallback,
selected by the absence of 3D HTML support. Shared tablet placement, property
validation, and controller scripts also retain existing public names. Renaming
these interfaces is not part of the Android application source migration.

The `+android_interface` and `+android_phoneInterface` selectors are also shared
mobile interfaces, despite their historical names. The iOS capability profile
explicitly selects both; its accessibility, Qt 6 bridge, login, and touch tests
consume these QML and script files. They and `touchscreenvirtualpad-phone.json`
remain on `main`, together with their mobile recovery and behavior tests. They
are inventoried as shared dependencies in the source policy. The Android-only
Pico/Quest selectors and native Android implementations leave `main`. Changing
the shared selector names would require a separate coordinated iOS/Phone API
migration; deleting them would break iOS.

## Test boundaries

`tests/platform-profile.json` declares the source profile and the branch-owned
test entry points. `main` uses the `shared` profile with no product suites. The
Android integration uses the `android` profile with mandatory product suites.
The common runner validates that the profile and every declared entry point
exist; a missing platform suite is an error, not a successful skipped check.

The ownership inventory in `.github/platform-source-policy.json` and
`tests/source-layout-test.py` reject Android application sources on the shared
profile and missing Android build entry points on the Android profile. Portable
Portal, Places, QuickGoto, and script-API tests moved from the Android tree to
`tests/javascript`. Android integration tests retain their real production
inputs on the Android branch. Shared source/syntax checks do not establish
Android runtime acceptance or replace device tests.

Reusing a shared parent's qualification never waives the child's declared product
suites: non-documentation reuse runs `--platform-only` on the candidate. The full
fallback runs both shared and product suites. This keeps the first
`main` to `android-main` boundary covered after Android tests leave `main`.

## GitHub Actions

Manual Android workflow files on `main` contain registration-only jobs. They
retain input definitions but cannot build, sign, release, access a device, or run
on a self-hosted runner. Selecting `main` fails with an instruction to choose the
owning product branch or approved release tag. The Android branch retains the
complete workflow under the same name, including all original trust, signing,
device-lock, and approval gates.

This registration is required because GitHub only enables `workflow_dispatch`
for workflows present on the default branch. Select the product revision in the
Actions branch selector or supply it with `gh workflow run --ref`. See
[GitHub's manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Shared parent qualification, branch governance, issue routing, artifact evidence
primitives, and synchronization policy remain on `main`. They describe all
products without owning the Android application implementation. Gradle dependency
updates explicitly target `android-main`.

## One-time migration and later synchronization

1. Integrate shared changes into an Android preservation candidate while keeping
   the current Android runtime, source moves, and fixes. Record both starting
   revisions and resolve conflicts explicitly.
2. Remove Android-owned files from the shared candidate after separating portable
   tests, platform suites, and manual workflow registrations.
3. Merge the shared candidate into the Android candidate, retaining Android-owned
   files and workflow implementations from the preservation tree. Keep the Android
   test profile and run shared plus product checks. Verify the retained blobs and
   modes against the preservation tree.
4. Review and integrate both sides as one coordinated migration. Propagate in the
   normal parent-first order. Other descendants receive the removal; Android
   descendants retain their own product changes and Android-owned paths.

Never blindly apply the shared deletion to the Android family. Unchanged files
can otherwise be deleted automatically by Git; changed files can produce
modify/delete conflicts. Do not resolve these conflicts by replacing the complete
Android tree with `main` or an old snapshot. Do not rewrite existing history or
delete platform branches for this migration.

After the migration merge records both histories, unchanged Android-owned files
remain child-owned during subsequent parent merges. New shared fixes still flow
through normal merge commits. Upstream intake must respect this source boundary:
if an upstream change brings back Android applications, separate the Android
portion before integrating it on `main`.

The historical Android ownership report described integration lanes that could
all contain every application. This source-boundary policy supersedes that part
of the report; historical evidence remains available on its original revisions.

## Device control plane imports

The shared ADB primitive lives in `tests/device/adb_transport.py`, next to the
portable device control plane that uses it. Shared adapters must not import
Android application modules. Product-specific candidate adapters remain usable
only from their owning branches. Central dependency policy validates consumers
according to the explicit source profile; shared branches retain registration
stubs, while Android branches must keep the real resolver-backed consumers.
