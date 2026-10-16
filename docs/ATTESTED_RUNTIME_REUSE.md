# Reuse of the original tested environment

[`attested.py`](../tools/test-evidence/attested.py) prepares a cheap terminal for
complete shared-suite reuse. It does not install or measure an unused consumer's
Qt, Java, Node or Python test environment. Both parent and candidate source
fingerprints retain the **exact original recorded execution environment**. The
result explicitly has `consumer_environment: null` and `execution: null`; it
does not claim tests ran on the consumer VM.

The trusted [admission policy](../.github/attested-runtime.json) enables the
isolated protected profile for a controlled first native attempt. This is source
preparation, not evidence that an environment passed admission or tests. The
deployed legacy project, parent and CodeQL endpoints do not call the protected
producer or consumer. Their existing execution paths remain authoritative until
the exact reviewed installation. The legacy terminal separately retains
`ACTIVATION_READY = False`; no public CLI or enable flag can activate it.

## Protected supervisor capability

The separate protected producer and original-PR main consumer use
`producer_workflow.PRODUCTION_READY`, `sandbox.ACTIVATION_READY`,
`attested.ISOLATED_ADMISSION_READY` and, for consumption,
`postmerge.SOURCE_READY`. Together with `metadata_context.SOURCE_READY` and
`ci_profile.SOURCE_READY`, these six capabilities enable only the reviewed native
attempt and its authenticated consumers. Candidate JSON and CLI arguments cannot
supply source authority, runtime evidence or a successful publisher.
`sandbox.ACTIVATION_READY` applies only to the protected supervisor; the legacy
`sandbox.execute` and `sandbox.capture_after_execution` entrypoints always fail.
The legacy `attested.ACTIVATION_READY` terminal remains false and is independent
of protected original-environment admission.

The exact disabled [`shared-sandbox.json`](../.github/shared-sandbox.json) object
is the diagnostic/legacy configuration identity used by the fixed namespace
plan. Its `enabled: false`, empty `qualified_hosts` and contract qualification
`unavailable` do not describe the separate protected producer's permission.
They must remain unchanged when that producer is qualified. Supplying enabled
JSON or host assertions is rejected. A manual diagnostic always records
`authority: none`, `production_qualified: false` and `reusable: false`, including
when the protected source capabilities are true.

Protected execution additionally needs a reviewed enabled original-runtime
policy in a fresh isolated epoch. Its exact namespace flags include
`LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, empty `LC_CTYPE`/`TZ` and
`git_process_overrides=maintenance-disabled-safe-work`. The latter identifies
only the fixed `/work` safe-directory exception. The old ordinary profile
rejects that override. The descriptor checks these trusted policy prerequisites
before setup; no policy check replaces native API/source authentication, actual
protected before/after runtime measurements, kernel-confirmed empty scopes or
final publication. Policy denial before suites selects existing actual
execution. Started-suite, cleanup and post-measurement failures remain failures.

The first exact reviewed installation can perform the first qualification. It
needs no previous native receipt or duplicate manual full/CI37 run. The producer
must admit its actual original environment before any suite, complete protected
execution, compare the original before/after environment, confirm empty kernel
scopes and publish the native whole-receipt commitment. A successful legacy
fallback is valid existing execution but does not qualify protected reuse or
satisfy installation acceptance. Source preparation supplies no qualified image
or qualification timestamp.

The Qt-free CI37 production policy uses the separate
`ci37-protected-controller-v1` namespace and explicit controller epoch. It binds
the exact 37 definitions, complete registry and actual protected default-source
controller/import closure. A root-owned immutable manifest independently binds
the complete protected source tree and commit; the probe authenticates the
projected controller bytes before deriving that generation. Candidate tree
entries never supply the trusted default source. Candidate fingerprints retain
their complete input closures, while an ordinary changed CI test does not need
a new fixed whole-candidate generation certificate. Policy, platform, membership
or unknown lookup differences still decline before execution.

The manual `ci37` diagnostic independently binds its actual immutable protected
source, complete registry and policy bytes in the parent and read-only probe.
Its distinct `ci37-actual-source-diagnostic-v1` selection supplies no production
admission or reuse authority, including when generation digests coincide. It
cannot replace the first native publisher proof. The legacy whole-tree CI37
policy shape remains separately validated; it is not silently interpreted as
the controller-source policy.

The seven-target workflow generation requires the reviewed helper/controller
source on each protected target before native installation there. A candidate
cannot enroll its own missing trusted-base helpers. Source-only propagation
preserves child product/profile differences and all required checks. Android
platform suites remain separate required owners; unsupported profiles select
actual execution rather than relabeling shared results.

The unenrolled Android common/platform recipe keeps the original selection of
60 common suites and its complete 13 or 19 platform declaration. Only that complete
future catalog generation can separate the common native owner from a fresh
platform job. The common schema3 receipt records `include_platform: false` and
empty `platform_results`; it retains the actual full isolated environment and
cannot certify any Android command. Original-proof consumers also authenticate
the original completed platform job, then require the separate current platform
job through the final project or parent gate. The parent retains the required
`Qualify exact parent` check downstream of both jobs.

The platform job preserves the existing Java 17, Node 22, Python 3.12, Conan and
phone Qt6 fixtures. It uses the system CMake/CTest/Ninja without changing which
prepared Node/Python installation wins PATH lookup. A phone fixture requires
the actual available NDK compiler before execution; a missing compiler cannot
turn into an exit-zero skip. Only the existing authenticated Pico ownership
plan can defer `pico4-device-free` to the required Android owner. Other apparent
test overlaps grant no omission. These future templates remain outside the
installed catalog; source tests do not establish native or runtime qualification.

On a main PR, independently selected full-environment affected subsets retain
that original full environment and exact selected suite results. The complete
registry, definitions, graph, immutable delta and controller source must still
validate independently. CI37 and full profiles are not projected onto each
other. Reuse retains the original recorded environment; consumers do not
measure an unused VM environment.

In that exact generation, the current native publisher can own the three
documentation suites and the workflow-contract suite only after their actual
successful schema3 results and original native API proof are verified. The
standalone documentation job then skips. Actionlint, Zizmor and Gitleaks still
start in parallel; their success is independently required. The contract step
is deferred, and an actual same-candidate fallback contract job runs after the
project when the native owner is absent. A claim flag alone proves nothing;
failed or cancelled projects do not start extra fallback work. Earlier workflow
generations retain their existing standalone checks.

## Admission is separate from producer authentication

`validate_environment(environment, qualified_at, expires_at, now)` checks recorded
data against the trusted current contract. Its return value authenticates
neither a producer nor a passed test. `plan_zero_shared(...)` likewise only
compares complete source inputs. Callers must never treat JSON, a hash or the
shape of either result as API provenance.

The dormant `verify_zero_shared_sync(args, api=...)` uses the existing live sync
gate before and after work. It preserves that gate's actual guarantees and
limitations. The legacy gate currently lacks independent artifact API archive
digest/size validation and a complete independently approved producer source
chain. Artifact API metadata identifies a run, not an uploading job. The separate
[producer API protocol](PRODUCER_API_PROOF.md), complete publisher/owner proof and
credential/report isolation across all concurrent candidate jobs remain
activation prerequisites. This preparation does not resolve or bypass them.

## Bounded supported runtime generation

Admission requires the exact schema/profile and reviewed Ubuntu 24.04 x86_64
GitHub-hosted contract, CPython 3.12 in an isolated controller virtualenv with
both Python aliases bound, Node 22/npm 10, JDK 17, Qt 5.15/6.4, all recorded tool
and GLM digests, and complete original package inventories. Unknown/missing
fields, unreviewed flags, Python site/lookup overrides and changed fixture
variants are rejected. Original versions, binary hashes, package inventories,
backends, image/kernel and namespace identities remain unchanged fingerprint
inputs; supported versions are not declared equivalent to each other.

Both protected profiles provision the distribution's CMake/CTest and Ninja in
`/usr/bin` (`cmake` and `ninja-build`). The isolated PATH includes only the
prepared Python/Node/JDK tools and system executables; an outer runner's
`command -v` can instead find `/usr/local/bin` tools. Preparation checks the
actual `/usr/bin` executables, installs missing packages and rejects an
incomplete installation before the runtime probe. It does not expose additional
tool directories or establish hosted compatibility by itself.

The current recursive exact requirement pins must match the original installed
Python package inventory. Every actual producer/controller/requirement file hash
must also match the current trusted files. The runtime capture now includes the
admission module and policy bytes themselves. An epoch, policy, requirement or
controller change therefore invalidates earlier proof. There is no implicit
compatibility allowlist. An enabled policy permits an authenticated attempt;
qualification still requires the actual environment to pass admission and the
complete protected execution and native publication to finish successfully.

The original qualification must follow the reviewed epoch's `not_before`, stay
within its maximum 72-hour lifetime and remain unexpired through terminal
completion. The receipt preserves original run/attempt, qualification and expiry;
it never renews them. Consumer admission records its own current policy digest
separately from the original environment and source provenance.

## Zero-selection terminal boundary

The terminal independently verifies the exact live synchronization and local
immutable merge. Every current shared suite must have successful matching full
parent/candidate inputs under the admitted original environment. A single
required, context-sensitive, missing or failing suite makes this terminal
unavailable. It has no automatic retry, fallback, dispatch or check publication.

The candidate's immutable ordinary `tests/platform-profile.json` must declare
**no product suites**. This terminal cannot certify an unexecuted iOS or Android
host suite. Those platforms need a separate complete authenticated owner before
a future handoff can use this boundary. Existing bounded documentation/tool
profiles retain their own owners.

The existing branch differential runs exactly once with candidate credentials
removed. Its own real syntax-check prerequisites remain necessary when selected;
the terminal neither installs them nor skips a missing tool. It writes only the
one actually executed differential JUnit case. Reused suites are listed in the
receipt and are not fabricated as locally executed passing cases.

After the differential, the terminal rechecks the immutable checkout, live
classification, full original evidence/API gate facts, complete source plan,
current policy hashes, live parent/base/head/merge and original expiry. Changed,
pending, missing, incompatible or failed proof cannot produce this result.

## Verification

```bash
python3 tests/run-project-tests.py --suite attested-runtime
python3 tools/test-evidence/runtime-test.py
python3 tools/test-evidence/registry-test.py
python3 tests/host-producer-preparation-test.py
```

The required `attested-runtime` quick/host suite uses fake API facts and real
temporary immutable Git checkouts. It covers disabled policy, source/history and
package/controller drift, malformed or incompatible environments, exact flags,
epoch/expiry changes, missing/failed/context suites, nonempty platform ownership,
final authority/ref changes and policy mutation during the real differential.
It executes no product build, installation, dispatch or network request. Its
initial repository closure is conservative because fixtures read the complete
trusted controller, registry, sync policy and recursive requirement graph.

The Android40 current-source owner is separate from common-host reuse. Its
`SOURCE_CAPABILITY` is default off and applies only to the four fixed Android
targets under the complete `protected-producer-original-default-v1` generation.
It describes reviewed current execution code, not a previous hosted PASS. The
legacy Android activation flag and required-branch policy retain their existing
meaning. Protected D supplies every controller; an authenticated old14 B may be
the predecessor of the first exact22 installation, subject to the existing
immutable handoff checks. Candidate controller code is never imported.

For selected work, the final outer job independently authenticates its current
attempt-1 Android route, execute and verify jobs and their fixed successful
steps through native GitHub job/check facts. It rederives the complete ordinary
40-command union, including real runtime and subcase verification in the execute
step, and repeats source, plan, ref and native-job observations. Its outer run
remains in progress; this entrypoint creates no reusable E, receipt or historical
qualification. Failed, missing or skipped owners remain merge failures. An
independently proved unselected plan requires exact skipped/no-output behavior.
No actual Android workload or hosted qualification is asserted by this source
implementation; activation and complete workflow enrollment remain separate.
