# Historical secret review — 2026-09-20

## Current assessment of the original 90 findings

The original Gitleaks report examined reachable history at
`e895d142383e8a9c76704f11958cdc19310dcde3`. Its 90 findings now comprise:

- 63 previously reviewed false positives: 46 Jenkins plugin versions,
  eight integrity digests, eight diagnostic/test canaries, one OAuth client ID.
- 11 additionally verified public identifiers: eight Sentry public ingestion
  keys and three OAuth client IDs. Exact historical exceptions have been restored
  and revalidated after the branch reset.
- 16 remaining historical credential-related findings. Their bound literal
  fragments are absent from the current tracked working tree and Git index.
  This does not establish revocation, harmlessness or synthetic origin.

This is targeted review of existing findings, not a fresh full scan. No service
was authenticated to or probed, no credential value was printed, no owner was
contacted and no history was rewritten. The fork owner has explicitly stated
that only Git history was inherited, without adopting or reusing those accounts
or keys.

## Eleven public identifiers

Three assignments named OAUTH_CLIENT_ID/ANDROID_OAUTH_CLIENT_ID were traced
through historical Gradle configuration into LoginFragment's client_id URL
parameter. Client secrets are separate configuration values. OAuth client IDs
are not secrets: [RFC 6749 section 2.2](https://www.rfc-editor.org/rfc/rfc6749#section-2.2).

Eight Sentry minidump URL findings contain the public sentry_key field, not
sentry_secret or a symbol-upload token. The pinned implementation constructs
this URL from public_key:
[Sentry project-key implementation](https://github.com/getsentry/sentry/blob/d5672c510a77e0d472eeb8b9eab1ea32ba7f6507/src/sentry/models/projectkey.py#L280).
Public ingestion identifiers can still permit event spam; this classification
is not a statement about server limits, ownership or key revocation.

The allowlist binds commit, path, blob hash, scanner rule, line range and expiry.
No wildcard or current-source/artifact exception was added. Two offline tests in
`test_history_public_identifiers.py` pass against the actual historical Git
objects and reject changed finding identities. The existing static runner now
includes these tests. Historical warnings remain visible.

## Remaining sixteen findings

| Historical group | Findings | Existing source evidence | Fork-relevant disposition |
| --- | ---: | --- | --- |
| RSA private key | 1 | Historical entity-certificate signing development code; later code removes the private key and local signing. | Historical exposure; whether any remaining trust system accepted it is unestablished. No current literal match. |
| AWS access key ID | 1 | CI identifier; the corresponding secret is referenced through the CI secret store. | The ID alone is not an authentication secret. No current literal match; no claim about the paired credential's status. |
| Backtrace upload token | 2 | Native symbol upload authentication, not public crash-ingestion identification. | Historical capability; no current literal match. |
| Google Poly API key | 6 | Asset-listing/loading assignments repeat one historical value. | Historical API credential; no current literal match. |
| NASA API key | 2 | Tutorial copies contain a value distinct from DEMO_KEY. | Historical API credential; no current literal match. |
| Metaverse access token | 1 | QML test sends access_token. | A test location alone does not establish a fake token. No current literal match. |
| Discourse API key | 1 | Snapshot sharing passes api_key to the forum. | Historical API credential; no current literal match. |
| HipChat token | 2 | Historical Jenkins integration configuration. | Historical integration credential; no current literal match. |

Absence was checked using previously hash-bound fragments from the exact
historical blobs and fixed-string Git searches of both tracked working tree and
index. Values were passed through stdin, with matched output suppressed. The
[redacted review record](history-current-presence-review.json) identifies scope
and findings. This does not cover untracked files, encoded/transformed values,
future source changes, downloaded build inputs or the eventual APK.

## What this means for the next action

There is no demonstrated current literal secret to remove among these sixteen,
and no established user-owned credential to rotate. Historical exposure remains
an upstream security matter with unknown validity; do not relabel it as a false
positive or claim revocation. Owner follow-up may help, particularly for the RSA
trust question or upload capability, but is not automatically a requirement that
the fork owner obtain revocation certificates for all historical entries.

No automatic F-Droid rejection has been established from these historical hits.
Do not infer a release blocker solely from their presence in inherited history.
The executable local gate now implements the user's decision: these sixteen
become WARNING only after exact historical binding, expiry and current
tracked-source absence checks. Their dispositions are in `history-risks.json`,
separate from false positives. Reintroduction or changed/unavailable evidence
retains FAIL. Current-source and artifact scans are unchanged. See the README
for the implementation boundary and regression command.

### Historical integration tests in CI

`test_history_public_identifiers.py` validates the actual old Git objects in a
full checkout. A shallow checkout without those objects explicitly skips this
integration class; it cannot establish historical-source binding. Synthetic
exception regression tests and current-source/artifact checks still run. The
release history scanner itself is unchanged and does not accept missing objects
as evidence for an exception. The full-checkout historical tests passed locally
on 2026-09-22; use a full checkout to repeat that coverage.
