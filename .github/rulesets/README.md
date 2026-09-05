# Repository ruleset manifests

The six top-level ruleset manifests are complete GitHub REST update payloads,
apart from the server-owned ruleset ID. They are the persistent desired state
after the archived branch refs are retired. Do not apply a manifest by name
alone: map it to the reviewed live ruleset ID and retain a rollback export.

The former `Archived branches` ruleset is intentionally represented under
`retirements/archived-branches.json`, together with all thirteen exact source
tips, annotated archive-tag targets, and deletion batches. Its live instance
must remain active until every tag has been verified and all listed safety
preconditions pass. It is then deleted through the normal Rulesets API before
the explicit `4/4/4/1` branch-deletion batches. This is not an administrator or
ruleset bypass. The immutable `refs/tags/archive/**` namespace remains covered
by the Android/canonical/archive tag ruleset throughout.

Required status checks are strict and bound to GitHub Actions integration ID
`15368`. A check with the same display name from another integration does not
satisfy the rule. The Desktop workflow job, manifest, and contract all use the
context `Enforce main desktop sync path`. Permanent branch governance also
requires `sync-test-reuse`; it is an always-terminal trusted gate, so path
filters cannot leave a required status pending. It reports ordinary pull
requests without delegating their existing checks and authorizes a sync fast
path only after exact evidence validation.

Deletion and non-fast-forward protection remains enabled for permanent branches
and tags. The retirement manifest records the temporary lock on archived target
and `backup/**` branches until their verified deletion. The tag manifests cover the namespaces currently used
for canonical releases, Android Phone releases and dependencies, Pico 4
previews, candidates and dependencies, and archival tags.

The active transition configuration uses
`review-profiles/solo-maintainer.json`. It requires checks and resolved review
threads but zero approving reviews, so the sole maintainer is not locked out.
Every pull-request rule in the manifests must exactly match this profile.

Switch all pull-request rules to
`review-profiles/independent-reviewer.json` as one coordinated change once a
second maintainer or consistently available reviewer has accepted the role.
That profile requires one approval, dismisses stale approvals, and prevents the
last pusher from supplying the final approval. Do not activate it while one
person is the only reliable reviewer.

Repository merge settings are versioned in `repository-merge-settings.json`.
Only merge commits are enabled for the transition topology. Auto-merge and
automatic branch deletion remain disabled. No ruleset requires signed commits.

Live rulesets and repository merge settings must not be changed merely because
these files are merged. Apply them only after an explicit approval, then export
and compare the remote state with these manifests. Update coordination state
only after that verification succeeds.
