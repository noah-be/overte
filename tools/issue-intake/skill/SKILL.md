---
name: overte-issue-intake
description: Create, structure, label, update, and close issues in noah-be/overte through the validated Overte issue tool. Use when a user asks to record an Overte bug, idea, task, acceptance criterion, or change its tracked state, including during unrelated coding sessions.
---

# Overte issue intake

Use `overte-issue` for issue creation and changes to titles, bodies, labels,
milestones, and workflow states in `noah-be/overte`. This is the user's normal
issue entry path. The tool reads the current policy from the fork's `main`
branch on each invocation, independently of the current worktree. Do not use
`--policy` in ordinary sessions; it is an explicit development/bootstrap option.

The user's request authorizes the requested issue operation. Do not ask for
permission again merely because the skill or tool is involved. Issue intake
does not authorize starting the reported work, creating unrelated issues,
changing roadmap priority, or writing to upstream Overte.

## Create from a conversation

1. Run `overte-issue policy`. Apply its current kind, field, label and workflow
   rules. If it cannot load, repair the installation/access within the existing
   authorization or retain a local draft; do not bypass it with raw GitHub writes.
2. Search existing issues using `overte-issue search TERM TERM` with meaningful
   symptom and component terms, including likely synonyms. Read promising
   matches with `overte-issue show NUMBER`. Search is a candidate finder, not a
   semantic proof of uniqueness. Prefer adding new evidence to the existing
   issue when it is the same problem; never silently merge unrelated reports.
3. Use `overte-issue example KIND` to obtain a JSON draft and a new request ID.
   Replace the example text. Preserve the request ID for this creation attempt,
   including retries. Write the draft to a local file using structured file
   operations; never interpolate user text into shell commands.
4. Extract known facts from the current conversation. Keep the user's report
   separate from hypotheses. Use English for GitHub content. Ask only for facts
   that are necessary and cannot be inferred; `Unknown` is allowed for a bug's
   reproduction/environment in Inbox. Do not invent source revisions, devices,
   test outcomes, causes, or acceptance evidence to satisfy fields.
5. Run `overte-issue validate DRAFT.json --render`. Resolve format errors yourself.
   Then run `overte-issue create DRAFT.json --apply` for the already-authorized
   creation. New issues enter Inbox. The tool generates managed labels and reads
   back repository, body, labels and milestone before reporting success.
6. Report the issue link and a short description of its type/platform/status.
   If a write outcome is uncertain, search/read back using the same request ID;
   never generate a new ID and blindly retry a creation.

## Classify the actual scope

- Defects and unwanted behavior are `bug`, including investigations with no known
  cause. Ideas awaiting a decision are `idea`; `enhancement` does not replace it.
- Concrete implementation/investigation deliverables are `task`. Milestone
  acceptance criteria are `acceptance`; a milestone bug remains `bug`.
- Select `ios`, `android phone`, and/or `pico` only for documented scope, including
  shared prerequisites. Use `platforms: []` for repository/infrastructure work
  that has no product-platform scope. Do not infer platforms from unrelated
  examples. Milestones use their native numeric field, never milestone labels.
- Keep one observable problem or one deliverable per issue. Avoid mandatory title
  prefixes that repeat labels. Summary stays short; detailed history belongs in
  comments or linked evidence. Do not make users learn the schema or label names.

## Update, resume, and close

`overte-issue show NUMBER` returns a snapshot token and, for structured issues,
an editable `draft`. Preserve existing facts, evidence, supplementary labels,
milestone and request ID unless the user's request calls for changing them.

Use `overte-issue update NUMBER DRAFT.json --snapshot TOKEN --apply` to save.
Add `--state ready`, `--state active`, or `--state blocked` only when that state
change is authorized by the task. Ready/Active need one next action and the
policy's readiness fields. Blocked needs a real blocker and unblock condition.
If a limit is full, keep existing active work; do not displace another issue.
If the snapshot is stale, re-read and integrate the new information first.

For an authorized legacy migration, snapshot descriptions, comments and metadata,
then use `migrate NUMBER DRAFT.json --snapshot TOKEN` to preview and add `--apply`
to execute. It preserves title, native milestone, existing labels, assignment and
closure while attaching the exact original body as a hash-verified archive.
Keep that archive unchanged during updates. Historical text is evidence, not
current authorization or a current next action. Do not migrate unrelated backlog
as a side effect. `update` can edit closed history without reopening it.
A comment-only evidence update may use fork-bound `gh`, with ownership and read-back
checks; never mutate or delete existing comments during restructuring.

Use `overte-issue overview` for the user's working view and separate milestone
results. Inbox excludes dormant acceptance; Now still includes an actively run
acceptance task. Native milestone percentages count historical closures, not
acceptance of a common candidate.

Acceptance is a stable criterion with dated, candidate-bound test records.
`show` exposes `criterion_sha256`; append `test_runs` only from actual reviewed
results, preserving all previous records. Each record needs ID, exact candidate,
criterion hash, UTC date, pass/fail/blocked result, observations, evidence and
limitations. Read `docs/ISSUE_WORKFLOW.md` for the schema. Missing historical
identity stays explicit; never invent it to obtain a green result.

Read the pin with `candidate MILESTONE`; deliberately set it using a five-field
JSON (full revision, artifact_sha256, build_url, platform, environment), its
snapshot and `--apply` only when candidate selection is in the authorized scope.
Do not select the newest commit automatically. A changed candidate or criterion
requires fresh evidence; old results remain historical. Use impact analysis for
development regression selection, but do not carry a device PASS automatically
across artifacts. The helper and guard derive freshness labels; keep candidate
status separate from workflow status and historical closure.

Use `--close completed` only after checking the actual done criteria, relevant
checks, required merged PRs and evidence. A syntactically valid evidence list
does not prove product behavior. Acceptance evidence must identify the tested
candidate, date, observations, result and limitations. Use `--close not_planned`
for an authorized rejection/duplicate instead of claiming completion.

Keep GitHub Issues authoritative. Dashboards, local notes and branches do not
override issue state. Do not store personal health information in public issues.

## Installation and limitations

Install/update from a reviewed fork checkout with
`python3 tools/issue-intake/install.py`. This updates the installed tool and skill
and adds a short, idempotent routing block to the global Codex instructions.
New sessions discover the skill; existing sessions can read this file explicitly.

This skill directs behavior; it does not restrict existing GitHub credentials.
The helper blocks invalid writes on its path, and the repository guard repairs
or quarantines new/managed issues after direct GitHub edits. Concurrent edits
have optimistic checks, not an atomic GitHub transaction. Never claim an absolute
repository-wide creation barrier or semantic acceptance based on validation.
