# PR #1023 stabilization

This candidate starts at published commit
`261fc77c1c322410f6096e65dcff0388c372286d`. It is prepared in a separate
checkout; the existing browser owner retains integration and publication of
`feature/main/browser-client`. Material AI assistance: OpenAI Codex.

The launcher and atomic provisioning probe now keep the random administration
token in memory. They persist only its native SHA-256 verifier. Regression tests
exercise actual startup/preparation code without launching services and refuse
the previous plaintext `runtime/admin.json` file. The probe's reviewed five-file
source manifest is checked against the candidate; integration with other
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
workflow behavior is unchanged. A diagnostic success is not full qualification.

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
