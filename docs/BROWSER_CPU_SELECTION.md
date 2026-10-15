# Dormant Browser CPU-history CI selection

[`browser_cpu.py`](../tools/repository-checks/browser_cpu.py) and the
[canonical workflow template](../tools/repository-checks/workflows/browser-client.yml)
prepare a narrow CPU-history route. The active Browser workflow is unchanged.
It is currently advisory; this preparation does not make it a required gate or
complete the independently required repository-check handoff.

The reviewed active workflow builds the production browser twice, once in each
of its `browser` and `native-journey` jobs. It also installs Chrome/Qt and runs
actual browser/native journeys. Those existing job bodies and diagnostic input
conditions remain in the dormant template. They are selected for other, mixed,
unknown, nonregular, unreviewed-reader and manual changes.

## Exact source scope

Only twelve exact `100644` paths declared in the trusted helper may select the
CPU route: the seven startup/fork-rename history-repair files, four reserved
workflow-history migration files, and the existing software-fixture workflow
reader. There is no `tests/**`, fixture directory,
file-extension, caller path-list or candidate-supplied skip rule. New history
paths require a trusted parent-policy review.

The comparison reads both complete immutable Git trees with replacement refs
disabled and bounded Git subprocesses. It includes additions, deletions, both
rename paths, modes, symlinks and gitlinks. Both non-CPU reader inventories must
match the hardcoded reviewed boundary from `2750afb6416a4dc71366974f24c8e3e87e5228af`.
Any unknown/changed app, package, reader, workflow or other input keeps the full
route. An earlier reader change followed by a CPU-only edit remains full until
that graph is reviewed explicitly. A successful build does not refresh policy.
Symlinks/gitlinks anywhere in either tree disable CPU selection independently.

The only workflow bootstrap is the exact reviewed legacy workflow blob changing
to the exact canonical template from the independently trusted controller.
That transition must accompany approved CPU-history edits; workflow-only edits
remain full. Only those two reviewed workflow identities are normalized into
the same reader boundary. Unknown workflow bytes are never normalized or
accepted as orchestration. Candidate copies of the helper/template cannot grant
approval. Known independent controller/registry/test-guide files are excluded
from the reader anchor but never from the changed-path classification.

## What the CPU job actually runs

The CPU lane runs the actual `npm ci` and `npm test` commands in `browser-client`,
then both current Jenkins Python contract entry points:

```bash
python3 browser-client/ci/jenkins/test_runner.py
python3 browser-client/ci/jenkins/test_chrome_scope.py
```

These tests include real namespace/network/worker-isolation and private-X11
fixtures. The lane retains ffmpeg, Xvfb, xauth, bubblewrap, slirp4netns, iproute2,
Python and compiler/crypto prerequisites. It preserves the existing hosted
runner AppArmor preparation and exact signed trusted-network qualification,
including its own tests and small security-launcher C compilation. They are
legitimate fixture prerequisites. Missing tools or namespace permission fails
the selected job; there is no skip-as-pass fallback.

It does not run Vite/TypeScript distribution builds, install Chrome/Qt product
dependencies, download native application artifacts, start the full laboratory
or run actual browser/native journeys. It sets the supported browser-download
suppression flags during npm dependency installation. Browser package/lock
changes require the full route and its explicit `npm audit --audit-level=high`;
the audit is not used as a substitute for behavior or build checks.

The Jenkins Python guards become newly explicit in this CPU lane; they were
not already mandatory jobs in the reviewed advisory Browser workflow. This is
CPU and security-fixture evidence, never product/browser journey acceptance.

## Trusted routing and final validation

Separate route and final jobs each check out the trusted default-branch policy
and independently read the exact event candidate. They validate repository ID,
the checked-out SHA, exact ordered event base/head merge parents, complete
source inventory and the exact canonical workflow. The final rederives the
entire plan and compares every routing output before requiring selected jobs.

CPU selection requires actual CPU-job success and both heavy jobs skipped. Full
selection requires both existing heavy jobs successful and CPU skipped. Missing,
pending, failed, cancelled or unexpectedly executed jobs fail the final check.
An unselected heavy-job failure cannot be converted into a green CPU skip.
Manual startup diagnostics retain their existing execution conditions, but the
helper labels their output `diagnostic-only`, never a required PR handoff.

The verifier consumes authenticated same-run `needs` supplied by the approved
workflow. Arbitrary JSON passed to its Python API/CLI is not authentication or
reusable evidence. It does not elect a prior green run, renew proof or suppress
another mandatory gate.

## Activation remains separate

Generate the exact dormant template to a review file with:

```bash
python3 tools/repository-checks/browser_cpu.py workflow --output /tmp/browser-client-reviewed.yml
```

The generator refuses to overwrite the active workflow in its source checkout.
Before any activation, complete all of the following in separately reviewed work:

1. Land the trusted helper/template first. Re-review/re-anchor against the final
   trusted parent if other prerequisite changes changed its reader inventory.
2. Extend native host-only ownership from the existing seven CPU paths to all
   twelve exact regular paths, with negative coverage. This preparation does
   not change the native policy or an already running prerequisite PR.
3. Combine the exact canonical workflow installation, V34 fork-history repair
   and bounded V35 workflow-history admission. Existing capture fixtures and the
   shipping preparer pin the legacy workflow bytes. V34 alone does not admit a
   future template. V35 must retain historical assertion bodies and admit only
   exact old/new workflow bytes through its bounded archive/adapter/manifest.
   Unknown workflow bytes and self-hash cycles remain forbidden.
4. Wire an independently required outer repository gate to validate orchestration
   and authenticate the exact candidate/plan/final result, then verify the first
   source-triggered run executes CPU checks and no production-build/journey jobs.

No active workflow, current repair fixture, required branch rule, dispatch or
build is changed by this preparation. Run its required offline regression with
`python3 tests/run-project-tests.py --suite browser-cpu-selection`; it uses small
temporary Git repositories and never installs tools or executes product work.
