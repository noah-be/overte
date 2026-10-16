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

Actual hosted boundary and complete shared-suite compatibility must precede
installing the protected workflow endpoints. This source preparation supplies
neither a qualified image nor a qualification timestamp. The enabled policy and
source flags must be included in the original execution's runtime/controller identity.
The manual diagnostic records environment digests and suite/cleanup results;
it does not call the future enabled isolated admission policy. Its success alone
therefore cannot qualify that policy. The first authenticated native producer
must admit its actual original environment before starting any suite and must
complete protected execution/publication before reuse can be claimed. No earlier
native receipt is needed to attempt this first execution. A successful legacy
fallback does not establish this qualification; installation acceptance requires
the genuine protected receipt and native whole-receipt publisher commitment.

The manual `ci37` diagnostic independently binds its actual immutable protected
source, complete registry and actual policy bytes in the parent and read-only
probe. Its distinct `ci37-actual-source-diagnostic-v1` selection measures that
source while production policy pins the prospective installed workflow tree.
It does not modify that policy or supply production admission authority. Even
when both generation digests coincide, production validation rejects the
diagnostic selection. The ordinary producer and original-E consumer always
require the shipping production generation.

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
