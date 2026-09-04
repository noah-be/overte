# Android Phone working system

Use the pinned [Overte task workflow reference](https://github.com/noah-be/overte/issues/599)
as the starting point. GitHub Issues are the only authoritative task source;
branches and pull requests provide delivery and evidence, not task status.

## Visible workflow

Move one workflow label at a time through `Inbox → Ready → Active → Closed`.
`Blocked` is an exception state and must name both the blocker and the condition
that will unblock it. Closed means Done and needs no Done label.

Keep no more than three repository-wide Ready Issues and three repository-wide
Active Issues. Every Ready or Active Issue states exactly one next physical
action.

## Start, stop, and resume

Start by reading the Issue, checking its Ready fields and the WIP counts, and
moving it to Active. Freeze the current target-branch head, then create
`task/<scope>/<issue>-<lowercase-slug>`; Android Phone work uses the
`task/android-phone/...` scope.

Before stopping or being interrupted, comment on the Issue with the current
state, completed checks, exact next step, blocker, branch/PR/worktree, and local
changes to preserve.

To resume, open the Active Issue, read its latest status comment, verify the
branch/PR and remote state, and perform exactly the recorded next action without
expanding scope.

## Quick status check

```bash
gh issue list -R noah-be/overte --state open --label 'workflow: ready'
gh issue list -R noah-be/overte --state open --label 'workflow: active'
gh issue list -R noah-be/overte --state open --label 'workflow: blocked'
git status --short --branch
git worktree list
```

This guide describes task handling only. It does not replace Android Phone
product documentation or interface-parity documentation.
