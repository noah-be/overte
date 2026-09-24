# Developer guide and documentation index

This is the entry point for work on the experimental fork. The
[repository roadmap](ROADMAP.md) owns product priority; this guide explains how
to find the code and verify a focused change.

## Choose the right checkout

Use [source ownership](SOURCE_LAYOUT.md) to select the branch that owns your
change. Shared client, libraries, UI, repository tools, and Linux/Windows work
start on `main`. Product work starts on its named branch in the
[platform guide index](interfaces/README.md). That index links directly to each
branch's current status and build guide; the Android application sources are
not present on `main`.

Use the [branch governance guide](BRANCH_GOVERNANCE.md) for topic names and the
[contribution guide](../CONTRIBUTING.md) before preparing a pull request. Keep
fork contributions in `noah-be/overte`; the upstream project has a different
contribution policy.

## Run the first local check

Use the Linux host environment in [project testing](../tests/PROJECT_TESTING.md).
It records the supported Python baseline, other prerequisites, and optional
host tools. From the repository root:

```bash
python3 tests/run-project-tests.py --profile quick --list
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

The first command lists the suites for this checkout. A successful run prints
`PASSED` for each selected suite, reports `0 failed`, and exits with code
zero. Inspect any skipped checks in the device control-plane report before
describing the evidence. `git diff --check` produces no output when it succeeds.
These checks establish repository and host behavior; they do not compile the
complete client or establish device acceptance.

For a native build, follow [Linux](../BUILD_LINUX.md),
[Windows](../BUILD_WIN.md), or your [platform's guide](interfaces/README.md).
Keep the build variant and output paths from that guide together. The
[architecture map](ARCHITECTURE.md) connects code areas to tests.

## Find the authoritative guide

| Task | Start here |
| --- | --- |
| Understand components and source entry points | [Architecture](ARCHITECTURE.md) |
| Select and run the relevant verification layer | [Project testing](../tests/PROJECT_TESTING.md) |
| Work on a platform port | [Platform guides](interfaces/README.md) |
| Choose the next product outcome | [Roadmap](ROADMAP.md) |
| Record or refine a task | [Issue workflow](ISSUE_WORKFLOW.md) |
| Synchronize shared changes | [Branch workflow](BRANCH_WORKFLOW.md) |
| Inspect the next repository maintenance action | [Maintenance guide](REPOSITORY_MAINTENANCE.md) |
| Inspect repository automation | [Tool index](../tools/README.md) |
| Understand nightly audit results | [Repository Health Doctor](REPOSITORY_HEALTH.md) |
| Review imported upstream changes | [Upstream intake](UPSTREAM_INTAKE.md) |
| Report a vulnerability | [Security policy](../SECURITY.md) |
| Check licensing and attribution | [License inventory](LICENSING.md) |

Keep commands and detailed facts in the linked guide. Update that guide when
the implementation changes. Generated sections are maintained by their named
tool; dated evidence and superseded plans belong in clearly marked history.
