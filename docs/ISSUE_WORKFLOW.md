# Structured issue workflow

GitHub Issues in `noah-be/overte` are the authoritative task source. A user may
describe a bug, idea, task or acceptance criterion naturally in a Codex session.
Codex searches existing issues, structures the report and uses `overte-issue`
to validate, create and verify it. Users do not need to memorize fields or labels.

## Source of the rules

[The policy](../.github/issue-policy.json) defines the field names, required
content, labels, workflow states and limits. The helper reads the current policy
from `main` on every normal invocation. Its reviewed executable code is installed
locally, not downloaded and executed automatically on each issue request.
Changes to the policy and helper go through repository review and contract tests.

The [Codex skill](../tools/issue-intake/skill/SKILL.md) explains how to extract facts
from a conversation without inventing missing information. The global Codex
instruction routes Overte issue requests to it even outside a repository checkout.
The repository `AGENTS.md` provides the same entry point inside a checkout.

## Four kinds

| Kind | Primary label | Minimum intake content |
| --- | --- | --- |
| Bug | `bug` | Observation, expected behavior, reproduction and environment |
| Idea | `idea` | Proposal and benefit |
| Task | `type: task` | Summary, scope, outcome and checkable done criteria |
| Acceptance | `acceptance` | Criterion, pass conditions, verification method, historical assessment, candidate baseline, remaining verification, platform and native milestone |

Unknown reproduction/environment details are allowed explicitly in bug Inbox
entries. A solution is not required to report a defect. Ideas are refined before
they enter Ready/Active. `enhancement` remains a supplementary label; it does not
replace `idea`. A bug assigned to a milestone remains a bug, not an acceptance
criterion merely because it is milestone work.

Choose only the documented platform scope: `ios`, `android phone`, and `pico`.
Shared prerequisites can have multiple platform labels. Repository-only work may
use an empty platform list. Milestone membership uses the native field; no
milestone labels are introduced. Existing supplementary labels are preserved.

## Workflow and views

`Inbox → Ready → Active → Closed`; `Blocked` is an exception state.

- Every open structured issue has exactly one workflow label.
- Ready and Active each have a repository-wide limit of three, counting older
  issues too. They require scope, outcome, done criteria, one next action,
  dependencies (an empty list means none), and required checks.
- Blocked requires a concrete blocker and the condition that allows work to resume.
- Successful closure requires outcome, done criteria, required checks and evidence.
  Codex must verify the real results and any required integration before closing.
  The validator checks structure; it cannot prove that a device test occurred.
- A consciously rejected proposal or duplicate closes as `not_planned`, with its
  rationale/link retained in the description. Closed issues have no workflow label.
- `system: reference` is reserved for operating references such as
  [#599](https://github.com/noah-be/overte/issues/599), not work to start.

Use a small working view: Active is **Now**, Ready is **Next**, and Blocked is
**Waiting**. Inbox/ideas and milestone acceptance remain separate views. A
`validation: needs-info` entry is saved but does not belong in Ready/Active.
`validation: passed` means a structural check, never product acceptance.
No dashboard may independently override GitHub issue state.

Keep the current summary short. Preserve long investigation histories in comments
or linked evidence. Keep candidate identity, observations and limitations in
acceptance evidence. A milestone progress bar can include both bugs and criteria;
filter by `acceptance` when presenting acceptance-only progress. Native closure
counts describe historical disposition, never the current candidate pass rate.

## Install and use from any directory

From a reviewed checkout:

```bash
python3 tools/issue-intake/install.py
overte-issue policy
overte-issue search startup overlay
overte-issue example bug > /tmp/overte-bug-draft.json
```

Fill in the draft from the user's request, then:

```bash
overte-issue validate /tmp/overte-bug-draft.json --render
overte-issue create /tmp/overte-bug-draft.json --apply
overte-issue show 875
```

The `--apply` switch distinguishes a write from a preview. It is not an additional
permission request: use it when the user has already requested that operation.
Do not use `--policy` in ordinary sessions; that explicit override is for local
tests and the initial bootstrap before the policy exists on `main`.

`show` returns a snapshot token. Editing requires that token, so a stale draft
does not normally overwrite an intervening change. Use `update NUMBER FILE
--snapshot TOKEN --apply`, optionally with `--state ready|active|blocked` or
`--close completed|not_planned`. Preserve the existing request ID during edits
and retries. The helper reads back title, body, labels and milestone after writes.
It does not automatically repeat a failed creation request. Reusing the same
request ID finds an already-saved issue; mismatched content requires inspection.

## GitHub reconciliation and rollout

The [Issue intake workflow](../.github/workflows/issue-intake.yml) checks new and
managed issues after issue events and every six hours. It executes only trusted
`main` code, on a hosted runner, with repository issue write permission. Pull
requests execute only offline contract tests with read permissions.

The guard normalizes unambiguous type/platform labels, supplies a missing Inbox
state, removes workflow labels from closed issues and quarantines malformed
entries in Inbox with `validation: needs-info`. A completed closure without the
required structure/evidence is reopened for correction. A single bot comment is
updated with actionable errors; valid issues do not get a new success comment.
Human comments and body text are not rewritten by the guard.

WIP admission is checked by the helper before writing. The guard returns an
over-limit event's issue to Inbox. During a scheduled repair without an event
identity, the lowest existing issue numbers retain the available slots; it does
not invent priority. Local writes share a lock, and repository guard runs are
serialized. Independent GitHub writers can still race: this is optimistic
validation with eventual repair, not a globally atomic state transition.

Older issues without a structured marker or validation label are reported as
legacy and left unchanged. The policy records the start time for enforcement of
new issues, so deleting a new issue's marker does not remove it from oversight.
Migration of existing work is a separate, deliberate operation preserving facts
and evidence. No existing issue is deleted or bulk-rewritten during installation.

GitHub can delay/drop events or scheduled runs; the periodic pass catches missed
changes when it runs. Operational failures fail the workflow and do not count as
validation. Writes made with `GITHUB_TOKEN` do not rely on a second workflow event:
the guard performs its label and comment changes within the same run.

## Boundaries

Instructions and skills guide Codex but do not revoke other GitHub credentials.
The helper rejects invalid drafts before creation on its own path. GitHub direct
creation/API calls remain possible, and the guard operates after those events.
There is no claim that a public repository has a custom pre-creation barrier.
Semantic duplication, factual accuracy, scope and evidence quality still require
Codex/human judgment. Structural validation is deterministic and never grants
authorization to work on an issue or to claim successful acceptance.

The installed skill becomes discoverable in new Codex sessions. An existing
session may read its `SKILL.md` explicitly. Installation preserves existing global
instructions and creates a backup before changing them. Updating the helper means
rerunning the installer from a reviewed newer checkout; policy schema changes must
remain compatible or require an explicit tool update.

## Existing issue migration

Use `overte-issue migrate NUMBER DRAFT.json --snapshot TOKEN` for a preview,
then add `--apply` for an authorized migration. Obtain the token with `show`.
Migration preserves the issue number, title, native milestone, open/closed state,
closure reason, assignees and existing labels. Missing workflow/type labels are
added without reprioritizing existing work. Comments are untouched.

The entire original description is retained byte-for-byte as UTF-8 text in a
collapsed **Original description** section with a verified SHA256 and source
issue metadata. The archive is immutable through subsequent helper updates.
It is historical evidence, not an instruction to restart old work or revive old
authorizations. Keep a full issue/comment/metadata snapshot before a batch and
compare original descriptions, comments and disposition after every migration.
Historical completion is retained as recorded; restructuring is not a new test.

`overte-issue overview` returns Now, Next, Waiting and an Inbox excluding dormant
acceptance criteria, plus a separate milestone report. It computes current
candidate results from records rather than trusting labels or closed-issue counts.

## Candidate-bound acceptance

An acceptance issue is a stable requirement and verification procedure. Its test
records refer to exact candidates. Keep three different facts separate:

1. The criterion and pass conditions.
2. Historical observations and issue disposition.
3. Evidence for the explicitly pinned milestone candidate.

A candidate identifies the full source commit, SHA256 of the exact tested artifact,
build provenance, platform and non-sensitive device/OS/configuration baseline.
A branch name, a successful build, or "latest" does not identify tested bytes.
Use each platform's native milestone for its acceptance criteria. One platform's
artifact cannot certify a criterion that also requires other platforms.
Read the current pin with `overte-issue candidate MILESTONE`. To deliberately
select a candidate, prepare those five fields in JSON and use `candidate
MILESTONE FILE --snapshot TOKEN --apply`. This preserves the milestone description
and refreshes labels on all its criteria, including historically closed ones.
A commit or build does not silently select a candidate. Do not guess a pin from
the newest commit or the mixed candidates in old evidence.

Append a `test_runs` record to an acceptance draft obtained with `show`:

- Unique `id`, the five-field `candidate`, UTC `tested_at` and `result`
  (`passed`, `failed`, or `blocked`).
- `criterion_sha256`, provided by `show`, binds milestone, platform, scope,
  criterion, pass conditions and verification method.
- Factual `observations`, retained `evidence` references and explicit `limitations`.

The helper preserves previous records unchanged. Correct an erroneous result by
appending a new, dated result explaining the correction. Never fabricate a test
record from a historic PASS that lacks its full candidate/criterion binding.
A structural check cannot establish that a test occurred or that its evidence is
sufficient; Codex must inspect the actual evidence before recording PASS.

Only the latest result matching both the pin and criterion hash counts. A changed
artifact, commit, environment or criterion requires new verification. A later
failure overrides a previous pass. Candidate labels are derived automatically:
`acceptance: verified`, `acceptance: needs-test`, or `acceptance: no-candidate`.
Failed and blocked observations remain distinct in the overview. Historical
closure stays intact when the candidate changes; it is not a current green result.
The helper rejects a new completed closure without matching passing evidence.
The guard repairs derived labels on issue/milestone events and scheduled audits.

During development, use change-impact analysis to choose relevant regression tests;
there is no requirement to rerun all device tests after every repository commit.
The milestone report conservatively requires exact-candidate evidence. It does not
automatically carry passes between different artifacts, even if a change looks
unrelated. Pin a release candidate deliberately, run the required acceptance on
those bytes, and treat an unverified replacement as pending. Reviewed reuse for
identical build inputs in CI is separate from device acceptance; its existing
attestation rules must not be weakened.

This follows the separation of requirements, builds and test results described in
[Microsoft's traceability guidance](https://learn.microsoft.com/en-us/azure/devops/pipelines/test/requirements-traceability?view=azure-devops)
and the impact-based regression selection in the
[NASA software engineering handbook](https://swehb.nasa.gov/spaces/SWEHBVD/pages/102695526/SWE-191%2B-%2BSoftware%2BRegression%2BTesting).
