# Immutable public descriptor fixture correction

This test-only patch replaces the five contracts' assumed immutable UTC file with the fixed packaged `/usr/lib/systemd/system/basic.target` file. Production trust validation, aliases, profiles, namespaces, capabilities and all resource bounds remain unchanged. The test still verifies canonical root-owned nonwritable ancestry, exact opened FD metadata, independent bytes/digest, metadata mutation and close, literal profile reads, sealed inventory, exact production C digest/read bounds and static build verification.

The exact hosted image is `ubuntu-24.04` version `20260927.320.1`. Its official runner-images release points to commit `1275e33f5019b02660b81ecc5622fe196211fa89`; that commit's `configure-system.sh` line 11 runs `chmod -R 777 /usr/share`. Actual hosted UTC metadata is regular, root-owned, 114 bytes and mode 0777. Original rejection was correct. See the separate frozen safe cause packet for source citations and failure mapping. No system file permissions are changed by this proposal.

The nested Systemd target preserves the original necessary-parent profile rule assertion. It is not a specially admitted runtime dependency: the unchanged original trust function must admit the real public file before the tests continue. Missing, writable, untrusted, nonregular or unexpectedly large input remains a failure. Official image inventory includes Systemd, but hosted execution of this patch is still pending. The target's bytes are independently hashed and compared; no expected contents are invented.

The five original test function ASTs are unchanged after normalizing only the fixed fixture variable and its exact target/parent profile literals. `assertion-preservation.json` records that check. Three added negatives preserve the measured UTC0777 refusal, matching-byte writable Python FD refusal with no reads and closed FD, and matching-byte writable C FD refusal with zero actual pread calls. The C test glue intercepts actual pread only for observation; the extracted production verifier is unchanged. It does not mistake the separate admission/read-budget counter for a read syscall.

Qualification: all eight focused contracts passed in 1.517 seconds; the complete alias test module passed 23/23 in 1.390 seconds, using the reviewed static library directory. This is local CPU/static-C qualification, not hosted CI acceptance. Initial authoring failures are retained separately: missing reviewed static-library setup, an unsupported metadata projection type and a test counter that initially observed admissions rather than syscalls. Only authored test/setup code was corrected.

The native/shared-library oversize refusal and Atomic outer exit127 are separate unresolved conditions. This patch neither relaxes the 4 MiB alias bound nor changes interpreter selection, grants or deadlines. The complete original workflow suite must still pass after those independently established causes are addressed.

## Review and apply

From the Root repository, verify the file before SHA from manifest.json, then `git apply --check` and `git apply` the `fixture.patch`. Only `browser-client/tools/trusted-network/tests/test_import_alias_policy.py` changes. Do not copy the packet's readonly source symlinks or replace workflow/source files.

## Repeat local CPU qualification

From `browser-client/tools/trusted-network/tests`:

```sh
PYTHONDONTWRITEBYTECODE=1 OVERTE_SETUP_STATIC_LIBRARIES=/tmp/overte-trusted-network-dependencies/static python3 -m unittest -v test_import_alias_policy
```

The library path above is the reviewed local CPU setup, not a portable hosted requirement. Hosted qualification uses its original signed prerequisites and unchanged complete required commands. No GUI, services, namespace activation or Root edits were performed by the packet author.
