# Hosted alias provenance and retained Atomic failures

The browser workflow enables `OVERTE_TRUSTED_ALIAS_DIAGNOSTICS=1` in its
existing trusted-network qualification step. After the original alias admission
refuses, the helper reports bounded metadata and rethrows the exact original
exception. Admission order, permissions and resource bounds are unchanged.
The diagnostic defaults off. Each alias resets its canonical identity before
inspection, so a failed chain cannot reuse an earlier alias's target.

The output contains fixed lexical and canonical name classes, the single
installed owning package and version restricted to four known Python packages,
and bounded ELF direct-dependency flags. Package metadata is not a signature
verification. The helper reads library metadata; it does not read library
contents. Interpreter ELF inspection uses at most 262,144 bytes with explicit
header, dynamic-table, string and FD identity checks. Loader search-path values,
raw package output and mapped-library identities are excluded. Unsupported or
changed inputs refuse observation and cannot admit the original alias.

The separate retained-prefix reader opens one existing capture relative to
checked directory descriptors. It requires owned `0700` directories and an
owned regular `0600` file of at most 8,192 bytes, refuses symlinks and special
files, checks unchanged FD identity, and closes all descriptors. Its output is
limited to fixed status, category and byte count. Use the recorded capture from
the original invocation:

```sh
python3 browser-client/lab/atomic-provisioning/read_private_preflight.py \
  --cache "$ATOMIC_DIAGNOSTIC_CACHE" --capture "$task_original_capture_name"
```

Checkpoint `6f7a35d` already reports `capability-action-refused`, outer exit127,
no milestones and untruncated prefixes. The exact failing suboperation remains
unknown. The reader does not rerun the command or infer a message from its
53-byte length. All original command, timeout, capability and filesystem checks
remain unchanged.

Local validation passes all110 trusted-network Python/C contracts in3.367s and
all93 Atomic contracts in2.934s. The new cases include exact exception identity,
default-off behavior, stale alias prevention and retained-prefix refusal
controls. Hosted validation remains pending.

A separate inactive prototype authenticates signed Ubuntu interpreter and
library package members. Those package bytes do not prove equality with the
installed hosted interpreter or library, and absence of a direct ELF dependency
does not prove absence of indirect loading. The original general4MiB alias
bound, aggregate bounds and rights remain in force.
