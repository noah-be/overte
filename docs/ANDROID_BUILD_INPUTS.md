# Dormant Android APK source-input planning

The trusted helper [`android-build-inputs.py`](../tools/repository-checks/android-build-inputs.py)
compares complete immutable Git trees for the Phone and Pico device Debug
variants. No workflow consumes its output. It does not build, dispatch, skip a
required check, authorize a cache hit or qualify an APK.

The reviewed product workflows, `android-phone-build.yml` and `pico4-build.yml`,
are manual `workflow_dispatch` workflows. They use isolated self-hosted runners
and reject refs outside their approved product branch/tag patterns. They are
not PR APK producers. Keep their explicit prohibition on running untrusted PR
code on those hosts. This preparation changes none of those triggers, jobs,
runner labels or safety rules.

## Compare exact source revisions

Run the reviewed helper from a trusted checkout, supplying full commit SHAs and
a repository containing both Git objects:

```bash
python3 tools/repository-checks/android-build-inputs.py \
  --repository /path/to/product-checkout \
  --base FULL_BASE_COMMIT_SHA --candidate FULL_CANDIDATE_COMMIT_SHA \
  --variant phone
```

Use `--variant pico` for the Pico source contract. Ref names, caller path lists,
candidate policy files and mutable worktree contents cannot replace the exact
Git input inventory. Missing objects, incomplete inventories and unsupported
variants fail with exit code 2, requiring verification. Candidate scripts are
never executed or imported. The shared reader disables Git replacement objects
and includes file modes, deleted entries, renames as both old/new paths,
symlinks and gitlinks.

The result includes exact base/candidate commit and root tree IDs, source
fingerprints, every changed path, the reviewed contract and
`requires_source_build`. A false value means only that the changed tracked
files are outside the reviewed app build/package readers. All listed
`verification_required` dimensions remain unresolved. Empty change inventories
remain conservative; an empty or absent report is never a successful build.

## Reviewed reader boundaries

| Variant | Reviewed revision | Reviewed source contract |
| --- | --- | --- |
| Phone | `277bad9119c9ee16f4bbb3038cedeb6625741d34` | ARM64 device Debug, SDK 36/target 36, NDK 27.3.13750724, verified Phone 16 KiB dependencies |
| Pico | `410847ff312553de81f9f8ff7e32029b22495603` | ARM64 device Debug, SDK 36/target 35, NDK 27.3.13750724, explicit bound source graph/runtime and Debug E2E OpenXR layer |

Phone and Pico fingerprints and dependency contracts are distinct. Phone's
verified 16 KiB sentinel/contents are not interchangeable with Pico's dependency
source-graph binding. Release/signing, Phone emulator, F-Droid, custom Gradle
properties and environment overrides are outside these reviewed contracts.

Both complete trees must match their variant's hardcoded reviewed reader
boundary before any exclusion applies. The boundary binds every other tracked
entry, including unknown files. A native, Java, Gradle, CMake, Conan, provenance,
resource or APK-verifier change disables all exclusions until the graph is
explicitly reviewed again. A later host-only edit after that reader change
still requires a source build; a previous successful build does not refresh the
boundary. `review_boundary()` computes a review proposal and grants no approval.

Exclusions are limited to the exact host-control paths/modes and standalone npm
manifests/locks declared in the helper, ordinary Markdown below `docs/`, and
three named root/testing guides. The shared executable test runner is exempt
only at its reviewed `100755` mode. There is no blanket `tests/`, `tools/`, npm
lock or Markdown exemption. In particular:

- Native headers and sources, Java sources, app manifests/resources, Gradle
  settings/wrapper/properties, CMake/bootstrap/shader readers, Conan recipes,
  profiles/locks/patches, dependency release policy and Pico provenance helpers
  remain application inputs.
- Markdown and package metadata below packaged `scripts/`, Interface resources,
  and device fixtures remain application inputs. Both products' actual Gradle
  asset-copy rules and Interface's complete RCC graph are anchored.
- Standalone browser/server-console/archive/test npm projects are outside the
  reviewed Android app graph. Android returns before desktop tools and
  server-console configuration, with tools disabled; JSDoc npm inputs are also
  independent for these exact graphs. Changing a build reader to consume one
  of these inputs invalidates the boundary before an exemption can apply.
- Product build workflows, package verifiers and in-tree dependency producer
  manifests remain anchored. Symlinks/gitlinks anywhere in either tree disable
  all exclusions, including unchanged aliases to a changed independent file.

Independent host, security and product checks remain necessary. Excluding their
files from APK source inputs does not claim their success or transfer ownership.

## Evidence still required before activation

The selector observes tracked repository inputs only. It does not identify the
actual Android SDK/NDK, JDK, Gradle/CMake/compiler/Qt tools, effective environment
and Gradle flags, Conan package bytes, generated files, local overrides or
workspace cleanliness. Pico's external source-graph inventory and Phone's
runtime/alignment verification still require their actual existing validators.

Dependency preparation, native compilation and APK packaging share dynamic
generated inputs and external configuration. Their complete independent
closures have not been proven here. The result reports that separation as
unknown requiring verification, rather than emitting dependency/native/package
cache keys. Existing Gradle and native incremental behavior is unchanged.

Git/source equality also excludes commit-derived build metadata, package
version overrides, timestamps and signing keys. It must never label an old APK
with a new candidate SHA or replace actual package/content/signature checks.
Any future activation needs an independently trusted caller validating the live
repository/base/head/merge and exact supported configuration, authenticated
owners for all selected checks, actual external environment/dependency evidence,
and APK provenance/content evidence. No current function or CLI flag bypasses
those requirements.

Run the required offline regression suite with:

```bash
python3 tests/run-project-tests.py --suite android-build-inputs
```

It uses temporary Git repositories and source fixtures, with no SDK downloads,
network access, product builds or devices. Actual reviewed snapshots and their
reader anchors were inspected locally; CI tests do not require remote history.
