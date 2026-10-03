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

The trusted setup now retains the caller's exact UID/GID numeric identity instead
of mapping it to namespace ID zero. It still installs and reads back all twelve
deny routes and retires all five capability sets before the confined owner runs.
The gateway passes the actual native `--setenv` contract to immutable admission;
the host bwrap launcher receives only fixed PATH/LANG. CPU tests reproduce the
old host/native mismatch against the actual admission code, verify the corrected
contract, and keep native loader variables out of the host launcher. The original network tests are unchanged. Hosted Ubuntu run 37120210342
qualifies these three network controls at the exact candidate SHA below.

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

Verified results remain tied to their exact source and execution scope:

- Ubuntu [37120210342](https://github.com/noah-be/overte/actions/runs/37120210342),
  at `42612a99dbdbabce298adcbab080fbff80856965`: the protocol/network job succeeds
  with all 1,572 component tests passing, zero failures and zero skips. All three
  original real-network tests pass, including twelve denied routes, scoped UDP,
  capability retirement and parent-death cleanup. The signed setup runs all 133
  CPU contracts successfully and the browser build passes. The separate native
  startup job still fails; later GUI journeys are not run in manual diagnostics.
  The overall workflow fails and does not establish full browser qualification.
- Ubuntu [37120791566](https://github.com/noah-be/overte/actions/runs/37120791566),
  at `c7aaa59bc39bc7983bf4294d001263a3c8fc0559`: fixed metadata measures 129 native
  environment entries against the old 128-entry preparation bound. All observed
  type/key/value/NUL guards pass. Preparation is corrected with a finite
  256-entry limit and a direct check of the exact serialized 64 KiB launch record;
  original per-field, loader/HOME/native/hash guards and complete argv/env remain.
  Four CPU regressions fail before the fix and pass afterward, including exact
  byte-boundary and aggregate-overflow controls.
- Ubuntu [37121546297](https://github.com/noah-be/overte/actions/runs/37121546297),
  at `17e9eff6ec42e6f660559be0015560a739d0c5ff`: preparation now succeeds and the
  observer reaches exact owned native endpoint and stored settings readback.
  HTTP 200 success accompanies a native `commit-failed` marker and failed guest
  permissions. The non-truncated exact-target summary reports one `linkat`
  `EEXIST` and sixteen unmatched destinations; this recoverable first operation
  does not establish the commit cause. The original zero-capability contract
  remains the sole failure among 130 unit tests. Diagnostic continuation keeps
  that job failed.
- Isolated Fedora CPU checks: Places/queue fixtures 11 passing, actual managed
  startup credential controls 29 passing, bounded stderr projector 17 passing,
  provisioning 11 passing and guest permissions 6 passing. The four environment
  records, five probe controls, five unchanged workflow-oracle controls and
  three aggregate-curator controls pass; original fixed-curator controls pass
  separately (four). These tests start no native services or GUI sessions.
- The required repository quick suite at the environment repair passes all 34
  checks in 156.30 seconds. Workflow Actionlint, pinned-action audit and
  `git diff --check` pass. Earlier Fedora component runs retain their explicit
  network/Xvfb failures and do not substitute for Ubuntu results.

The initial Places and plaintext-credential regressions failed against the
published code. The current shipping PR head still needs owner integration,
a fresh CodeQL run and full native/browser acceptance. No security review
thread is resolved. The original capability failure, stored-settings failure
and later browser/device journeys remain open requirements; successful
protocol tests and diagnostic preparation do not waive them.
