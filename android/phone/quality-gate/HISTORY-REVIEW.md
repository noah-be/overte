# Historical secret review, 2026-09-20

Reviewed all 90 findings from the full reachable-history Gitleaks scan of source
revision `e895d142383e8a9c76704f11958cdc19310dcde3`. No credential was used to
authenticate to any service. Git history was not rewritten. Raw values and
detailed owner follow-up evidence remain outside the repository.

## Demonstrated false positives

| Basis | Findings | Verification |
|---|---:|---|
| Jenkins plugin versions | 46 | Matched lines are plugin ID:version declarations. |
| Source integrity digests | 8 | Recomputed each referenced file's SHA-256 at the exact historical commit. |
| Diagnostic/JUnit canaries | 8 | Inspected synthetic inputs and assertions that private values never reach output; includes encoded canaries. |
| OAuth client identifier | 1 | Traced the constant into the client ID map and `client_id` parameter; it is not a client secret. |

The OAuth distinction is specified in [RFC 6749 section 2.2](https://www.rfc-editor.org/rfc/rfc6749#section-2.2).
Exceptions are exact, expiring historical records, not a baseline accepting
every finding before this date. They remain visible as WARNING.

## Still blocking: 27 findings, not necessarily 27 distinct credentials

| Group | Findings | Historical dates | Required evidence |
|---|---:|---|---|
| Crash-report ingestion tokens | 8 | 2020–2025 | Identify intended public-ingestion scope versus private capability, owner and current status. |
| Legacy CI/upload credentials, including AWS ID | 4 | 2019 | Owner review of account/key pairing, scope, retirement or rotation. |
| NASA API keys | 2 | 2016–2019 | Key owner and retirement/restriction evidence. |
| Android build upload tokens | 2 | 2018 | Identify upload service account and revocation status. |
| Google Poly API keys | 6 | 2017 | Identify cloud project, restrictions and key status; age/service name alone is insufficient. |
| Embedded RSA private key | 1 | 2017 | Identify purpose, affected trust/signing use, retirement or replacement. |
| Hardcoded API/access tokens | 2 | 2014–2016 | Owner and token lifetime/revocation evidence; test location alone is not proof of synthetic data. |
| HipChat tokens | 2 | 2013 | Owner and retirement evidence. |

No activity, validity, exploitability or current ownership is inferred from a
detector hit. A commented-out value remains exposed in history. Service
retirement does not establish the status or reuse of a particular key.

Next obtain owner/provenance information, prioritizing the RSA key and CI/upload
credentials. For inherited project credentials whose owners are unknown, prepare
a private, value-free inquiry for the user to approve; do not contact upstream
or create public issues automatically. Keep unresolved findings blocking.

Revocation evidence needs its own explicit disposition review; it must not be
misclassified as a false positive or silently added to this allowlist. Any later
history cleanup is a separate decision and does not invalidate copied secrets.

## Regression protection

The existing Phone contract runner executes `test_gate.py`. Tests cover exact
identity matching, expiry, changed blob digest, changed rule/line/commit/path,
source/history isolation, malformed/broad/duplicate review entries and unavailable
Git objects. The full-history scanner revalidates each matched blob binding
against Git. Unit tests use temporary Git repositories and need no upstream
history download; the actual secret gate still rejects shallow history.
