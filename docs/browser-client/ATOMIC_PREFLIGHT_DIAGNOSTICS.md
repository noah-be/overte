# Owned atomic observer preflight diagnostics

This packet adds observations to the existing `test_zero_cap_own_child_and_same_namespace_user_ipc_launch_preflight` test. The authorized hosted run 36980752327 at source `5dc4` completed signed dependency staging, then this test returned outer exit code 127. Its published failure does not establish whether command execution, dynamic loading, namespace setup or another step failed. This packet fixes diagnostic loss; it does not fix or identify that historical failure.

The original outer unshare/setpriv arguments, inner unshare arguments, all five capability-zero assertions, inner exit-zero/fsync-success assertion, eight-second outer timeout and five-second observer limit are unchanged. No skip, retry, privilege, profile, environment, dependency version or syscall predicate is added. Native startup and the nineteen-stage domain lifetime are untouched.

The generated entry prints fixed milestones around observer import, the existing capability assertion and the existing tracer call. Capability classification uses the existing `/proc/self/status` read and exports only `zero`, `nonzero`, `absent` or `unparseable` for each of the five fixed sets. It does not expose masks and does not replace the original assertion.

On the original nonzero outer result, the assertion message projects the already captured stdout/stderr into fixed enums. The projection examines at most the first 8 KiB of each captured stream and reports truncation. The original subprocess PIPE capture itself remains unchanged; this is a projection bound, not a new total capture-memory guarantee. Known English command/loader messages are classified conservatively; locale changes, unrecognized wording and a bare exit 127 remain unclassified. No raw stderr, paths, arguments, executable/library names, environment labels or process identifiers are returned.

After the existing observer returns, the generated entry reads only its own fixed `native-output.private.log` using the existing regular-file/no-follow/nonblocking/private-mode guard and existing 256 KiB retained-log cap. The exported inner observation uses an 8 KiB prefix and separately preserves existing observer capture-truncation flags. Read refusal is recorded without substituting for the original exit/fsync assertion. Fixed inner-start and inner-fsync markers are observations only: a marker cannot satisfy the fsync syscall predicate. Capability/milestone records are diagnostics, not authority or security admission tokens. Every summary retains `cause: not-established`; no LSM or profile attribution is inferred from EPERM.

## CPU verification and integration

Apply the four-file patch only if the manifest's before hash matches `lab/atomic-provisioning/test_observer.py`. `observer.py` is an unchanged, hash-bound test dependency, not part of the patch. Run from a reviewed source root:

```sh
python3 -B -m unittest discover -s browser-client/lab/atomic-provisioning -p test_preflight_diagnostics.py
```

The thirteen CPU tests use authored fake subprocess/observer results and the actual generated entry and inner source. They do not execute unshare, setpriv, strace, native servers or GUI processes. Controls retain the original command lists, environment, limits and predicates, verify that all five nonzero-capability cases still fail before tracing, and prove import/tracer/inner-exit/fsync failures remain failures. Privacy, malformed/deep JSON, oversized-prefix and unknown-error controls cover the enum projection.

The existing atomic workflow discovers `test_*.py`; the new CPU suite is included without changing a workflow step or adding a gate. The helper is used by source-root tests only and is not a new staged native/probe dependency. For the next authorized actual hosted run, use the unchanged full workflow and signed tracer. Preserve a nonzero result as failure. Read only the fixed diagnostic assertion fields; do not publish private captured logs. This packet has no actual hosted qualification or native performance claim.
