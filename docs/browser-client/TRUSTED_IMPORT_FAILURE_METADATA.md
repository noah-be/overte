# Trusted interpreter staging failure metadata

Substantial AI assistance was used. This observational change preserves the
original interpreter path, root ownership, immutable ancestry, alias size,
hash, descriptor and launch admission gates. It does not admit a relocated or
writable interpreter and does not change a system file or security profile.

The exact `5dc4d5ca` hosted workflows refuse during interpreter inventory with
`python-import-alias-target-untrusted` and
`runtime-package-path-not-root-trusted`. The first category combines file type,
ownership, writable mode and the original 4 MiB size bound. That result alone
does not establish which condition failed or identify the target. The second
can refer to a canonical file or an ancestor; its actual target is also unknown.

Staging now reports only a fixed entry kind and bounded entry/ancestor ordinal,
file type, root-owned and writable booleans, numeric permission bits, bounded
size and a digest of those metadata. No target path, UID, account, arbitrary
exception, argument or environment is printed. Unknown failures remain a fixed
refusal with a bounded observed OS error number. Every original failure still
exits unsuccessfully; a diagnostic is neither a compatibility fix nor hosted
qualification.

Run the complete original trusted-network suite with the reviewed static-library
prerequisite described in [the canonical alias guide](TRUSTED_PYTHON_ALIAS_POLICY.md).
The new eight CPU controls distinguish all four alias refusal conditions,
exercise the actual no-read oversize descriptor gate, verify context reset and
prove that hostile or unexpected metadata cannot reflect private text. They
also execute the actual CLI refusal. The agent packet passes all 90 contracts;
Root verification and the next exact hosted run are recorded in
[STATUS.md](STATUS.md). Existing hosted negative evidence remains retained.

The separate relocation design is unimplemented. Do not change path, size,
ownership or runtime policy based on an assumed hosted target. First obtain
the fixed metadata from the exact published checkpoint.
