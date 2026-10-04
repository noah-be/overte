# PR #1023 stabilization

This candidate starts at published commit
`261fc77c1c322410f6096e65dcff0388c372286d`. It is prepared in a separate
checkout; the existing browser owner retains integration and publication of
`feature/main/browser-client`. Material AI assistance: OpenAI Codex.

The launcher and atomic provisioning probe now keep the random administration
token in memory. They persist only its native SHA-256 verifier. Regression tests
exercise actual startup/preparation code without launching services and refuse
the previous plaintext `runtime/admin.json` file. The probe's reviewed six-file
source manifest (including the Chrome launcher) is checked against the candidate; integration with other
`manage.py` changes requires a new review and exact manifest update.

The Places adapter escapes HTML delimiters and JavaScript line separators in
generated string literals. Its regression executes the actual adapted handler
with hostile input and verifies the exact destination and absence of injected
code. The queue-test HTTP fixture declares plain text and disables MIME sniffing
while preserving its reflected URL, queue and concurrency assertions.

The existing owner's bounded stderr diagnostics are applied to the three real
network tests. A recovery test verifies that their original assertions, control
predicates, cleanup and deadlines remain byte-exact. Only fixed operation names,
exception categories, errno numbers and bounded inline-probe line numbers are
reported publicly. Raw stderr remains private and is never an uploaded artifact.
These observations cannot establish syscall or AppArmor causality.
Exact fixed refusal categories from the immutable owner admission module are
also projected; unknown or conflicting exception prose remains unclassified.

The existing Browser client workflow has an explicit, default-off manual
`startup_diagnostics` input. Diagnostic runs retain all protocol/network tests,
isolation/audio preflight and actual native startup requirements. They omit
later GUI/browser journeys and label the run accordingly; curated journey
evidence reports those journeys as `not-run`. Pull-request and ordinary full
workflow assertion coverage is unchanged; the integrated owner recipes use Google Chrome only. A diagnostic success is not full qualification.

The existing Owned atomic settings diagnostic has a separate default-off manual
`continue_diagnostics_after_contract_failure` input. Its original contract tests
remain unconditional and their failure still fails the job. Only an explicit
diagnostic selection permits the existing fresh-domain preparation and observer
to continue after that failure, retaining the original domain argv, ownership,
private capture and fixed summary validation. This obtains further evidence;
it cannot qualify or replace the failed zero-capability contract.

Focused verification on the isolated Fedora checkout:

```text
node --test browser-client/gateway/places-override.test.mjs browser-client/gateway/asset-download.test.mjs
  11 passed, 0 skipped
node --test browser-client/gateway/network-test-stderr.test.mjs
  15 passed, 0 skipped
python3 -B browser-client/lab/test_manage_state.py
  29 passed
python3 -B -m unittest discover -s browser-client/lab/atomic-provisioning -p test_probe_credentials.py
  2 passed
python3 -B browser-client/lab/test_provisioning_diagnostics.py
  11 passed
python3 -B browser-client/lab/test_guest_permissions.py
  6 passed
git diff --check
  passed
```

The new Places and launcher regressions failed against the published code before
the fixes. Full component and repository quick checks are queued behind the
shared build lock. Hosted run
[37117941828](https://github.com/noah-be/overte/actions/runs/37117941828), bound to
`0f077230f797c28c1c7b1a15c88b6ff05e529149`, built successfully and ran 1,566
component tests: 1,563 passed and the original three network tests failed.
The first reports Bubblewrap UID-map failure with errno 1; the other two report
an unclassified trusted Python bootstrap failure at line 17. Native provisioning
again reports HTTP 200 success with `commit-failed` and no saved configuration
change. These are startup observations, not kernel causality. Full Ubuntu
qualification and a fresh CodeQL run remain pending. Three native network
fixtures fail startup, native domain provisioning reports `commit-failed`, and
the separate atomic preflight fails its unchanged zero-capability contract.
Local Fedora results do not qualify Ubuntu's AppArmor environment. No security
review thread is resolved and the PR remains a draft until the owner integrates
and qualifies the resulting head.

## Local owner reconciliation

The existing implementation owner retains the verified Chrome-only launcher and
ordinary `browser` check name. The atomic probe now admits exactly six reviewed
lab source files, including the unconditionally imported Chrome helper, before
import, port checks or native execution. Old five-file metadata and mutated helper
bytes are refused; the complete original probe remains a CPU-only recovery
fixture. The isolated reconciliation passes89 focused source/HTTP fixture checks
and actionlint. These do not establish hosted or live native acceptance.

A separate owner-marker consistency regression rejects mixed unknown/malformed
markers and censored capture for `admissionRefusal`. Other diagnostic fields and
the original15 assertion bodies are unchanged. The incoming projector passes15
and fails the two new desired cases; the correction passes all17. Independent
rechecking passes26 focused desired/control/workflow cases, with zero skips.

The local R1/R2 checkpoint remains
`e000f7c5474d5cfcab3890989b9a3faeb39e52cb`. These stabilization changes are not
yet committed or published on the feature branch. Full unit/build/repository
gates still require the shared heavy-build lock. The retained earlier production
receipt does not qualify changed source, and the Ubuntu failures remain open.


## Network and probe source reconciliation (2026-10-03)

The owner integrated the narrow identity/environment changes from committed
`42612a99dbdbabce298adcbab080fbff80856965`. Trusted native admission receives
exact pre-delimiter `--setenv` pairs; the host bwrap receives only fixed PATH and
LANG. The single UID/GID map retains the caller's numeric identity. All original
twelve route and five-zero-capability retirement bodies, native boundary,
legacy route and current17-case projector remain unchanged. The six-source
Chrome schema/pins, helper and original golden probe fixture remain unchanged.
Fixed Atomic failure tags and exact workflow/probe whole-source recovery are
reconciled as narrow hunks, with malformed/unknown/duplicated recovery refused.

Fresh owner-copy commands and results:

```text
node --test gateway/network-worker-environment.test.mjs gateway/network-test-stderr.test.mjs
  20 passed
python3 -B -m unittest discover -s tools/trusted-network/tests -p test_route_contract.py
  10 passed
python3 -B -m unittest discover -s tools/trusted-network/tests -p test_launcher_environment.py
  1 passed
python3 -B -m unittest discover -s tools/trusted-network/tests -p test_owner_admission.py
  18 passed
python3 -B -m unittest discover -s lab/atomic-provisioning -p test_kernel_audit_integration.py
  5 passed
python3 -B -m unittest discover -s lab/atomic-provisioning -p test_probe_credentials.py
  4 passed
python3 -B -m unittest discover -s lab/atomic-provisioning -p test_source_coherence.py
  8 passed
```

All66 focused cases pass with zero skips. The original pre-correction failures
are retained. These pure admission/serialization tests do not run a native
namespace or device. Source changes require a fresh authenticated bundle through
its existing build/install safeguards; existing local prefixes and services have
not been replaced or restarted.

At the isolated exact SHA above, the protocol/network job in
[run37120210342](https://github.com/noah-be/overte/actions/runs/37120210342)
passed all three original actual network controls. The entire Browser run still
fails in native startup and its GUI journeys are not run. The Atomic run
[37120212527](https://github.com/noah-be/overte/actions/runs/37120212527)
retains the original zero-capability failure and now exposes the fixed observer
refusal `launch-environment-invalid`. No whole-run success, kernel cause,
public-world or browser/native acceptance follows from the network job.

Separately, committed narrow R1/R2 successor
`905e1a5239a1a2dcba03a799ef167a896911373e` passes all1,574 original component
cases, production build and34 quick-profile suites under the shared lock.
This includes an actual PreparedFbxCache teardown fixture; production R1/R2
bytes equal independently reviewed e000. Its gates do not cover the broader
unpublished stabilization/image/FST source. Complete integrated gates and a new
source-bound production receipt remain required before feature publication.

## Finite environment and fixed aggregate owner integration (2026-10-03)

The owner integrates exact17e9 observer/probe source and the045901 HOME-valid
entry-bound regressions. Fixed-six Chrome dependencies and the original complete
probe golden remain unchanged; four exact-once observation reversals precede
the existing two diagnostic reversals in CPU recovery. Fresh owner commands:

```text
python3 -B -m unittest -v test_environment_bound test_probe_credentials test_source_coherence
  19 passed
python3 -B -m unittest -v [six named pure ObserverTests controls]
  6 passed
node --test network-test-stderr.test.mjs
  17 passed
```

The42 cases have no skips and execute no native/tracer/namespace workload. The
valid256/257 count test fails when only the count predicate is removed. The
curator retains only its already validated finite aggregate DTO. Its fresh
`python3 -B -m unittest -v test_curate_observer test_stage_curate.FixedCuration`
passes all7 CPU cases; signed-stage/native cases are not executed by that command.
Two copy-preparation negatives (existing author log collision and the required
unused cache import environment) remain private evidence.

Isolated17e9/d2 hosted observations reach owned POST200 but retain commit-failed
and failed guest readback. The fixed aggregate reports linkat EEXIST1/ENOENT16,
no rename and one sync success. The exact-target DTO remains unchanged and
`settingsCommitCause` remains `not-established`. Local or hosted primitive
experiments are not native, kernel or AppArmor cause qualification. Original
zero-cap8s assertions remain unchanged. Full current feature qualification and
publication are still pending.
