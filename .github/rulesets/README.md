# Repository ruleset manifests

The seven top-level ruleset manifests are complete GitHub REST update payloads,
apart from the server-owned ruleset ID. They correspond one-for-one to the seven
repository rulesets exported on 2026-09-01. Do not apply a manifest by name
alone: map it to the reviewed live ruleset ID and retain a rollback export.

Required status checks are strict and bound to GitHub Actions integration ID
`15368`. A check with the same display name from another integration does not
satisfy the rule. The Desktop workflow job, manifest, and contract all use the
context `Enforce main desktop sync path`.

Deletion and non-fast-forward protection remains enabled for governed branches
and tags. Archived target branches and `backup/**` branches are additionally
locked against updates. The tag manifests cover the namespaces currently used
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
