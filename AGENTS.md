# Issue work in this fork

For creating or changing issues in `noah-be/overte`, follow
[the issue workflow](docs/ISSUE_WORKFLOW.md) and use the validated
`overte-issue` tool. The current policy is `.github/issue-policy.json` on the
fork's `main` branch, including when working from an older product worktree.

Install the reviewed helper and Codex skill with
`python3 tools/issue-intake/install.py` if they are unavailable. Read
`tools/issue-intake/skill/SKILL.md` for the conversation-to-issue procedure.
Do not bypass a rejected draft through raw GitHub writes. A normal user request
to create or update an issue is sufficient authorization for that operation;
do not add a separate approval ceremony.

Write GitHub content in English. The only authorized Overte GitHub write target
is `noah-be/overte`. Explicitly bind every mutation to that fork, check ownership
before writing, and read back the saved resource and labels. Upstream Overte
repositories are read-only. Do not publish private device/account data.

New work enters Inbox; it does not expand the current active task. Preserve
existing labels outside the managed type/platform/workflow dimensions and retain
useful evidence when restructuring. Do not migrate unrelated legacy issues as a
side effect of another task.

For changes to the intake implementation run `python3 tests/issue-intake-test.py`
and the repository checks required by `CONTRIBUTING.md`. Test with fake API
responses or dry runs; do not create disposable live test issues.
