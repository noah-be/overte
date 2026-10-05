# Completed Android source-boundary integration — 2026-10-05

This normal merge incorporates the original completed source-boundary
reconciliation tip `51c673499e` into the qualified `android-main` history.
The product, build, workflow and test trees retain the exact reviewed base
`d8bc29b7bff2041db2dd14f9089aa5a410380a03`; this receipt is the only tree addition.
Material review and conflict-resolution assistance: OpenAI Codex.

The source-boundary contract file already matches the original reconciliation
exactly. Independent later incorporation updated the Android/Phone recipes,
locks, bootstrap and tablet tests. Conflicts preserve those current qualified
sources. Three automatically reintroduced historical prebuilt checksum files
are omitted because current dependency locks and provenance already own their
replacement; no obsolete acquisition path is restored. The current test profile
also retains its additional bootstrap, provenance and host-tool checks.

Verify the complete original tip as an ancestor, equality of all existing paths
with the reviewed base, the repository quick profile and the normal protected
checks. The original full commit remains recoverable through the merge history.
No source boundary, required check or platform ownership rule is weakened.

This integration excludes ongoing F-Droid review and device acceptance. It
closes no issue, operates no device and does not remove a keep request. Remote
retirement remains subject to the independent branch-cleanup checks and backup
procedure.

Local candidate verification: `python3 tests/run-project-tests.py --profile quick --timeout 240` passed 42/42 groups in 158.63 seconds. Full workspace documentation, whitespace and owning-branch policy checks passed. Live required PR checks remain mandatory before protected integration.
