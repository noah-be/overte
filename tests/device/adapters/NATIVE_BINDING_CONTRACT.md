# SH-004 canonical native adapter binding v002

v002 migration: preliminary parsing inspects only product/mode, so native
candidate flags may precede the action appended by the real Shared runner.
v001 handled native flags after the action only; use v002 for manifest commands.
The native signatures, bound manifest and identity/installation rules are unchanged.

Implementation prerequisite for the existing sh004-results/v003 producer, not
installation or SH-004 acceptance. No result/receipt schema is added.

The real `adapters/android/adapter.py` entrypoint accepts `--native-binding`.
`adapters/android/pico-bound.json` is its opt-in manifest, preserving adapter ID
android-pico-adb and all existing target selection, invocation and cleanup.
Use this manifest for future bound Pico runs. The old pico.json remains an
explicit unbound diagnostic path; v003 rejects its absent identity. No automatic
device run or substitution of accepted inputs is authorized by this release.

The entrypoint loads exactly `tests/device/adapters/pico4/binding.py` for Pico
or `android-phone/binding.py` for Phone. There is no environment/import-path
override, fallback module, or foreign bytecode load. An absent/symlinked module
fails BEFORE constructing the Android adapter, with a closed public diagnostic.
The actual source bytes are compiled directly; include them in source provenance.

The native owner implements these exact module functions in its owned path:

```python
def configure_parser(parser):
    # Add only the native candidate verifier's EXISTING input flags here.
    # Do not change kind/action/target/operation/arguments/native_binding.
    ...

def create_adapter(args, base_class):
    # Validate the complete independently pinned candidate input set first.
    # Return an instance of a subclass of the PROVIDED base_class.
    ...
```

The factory receives the actual canonical class, not a separately imported
duplicate `__main__` class. Its instance must preserve kind and exact profile.
The real canonical dispatch then calls its discover/describe/invoke/cleanup,
including original selected_target and cleanup_target behavior. Native code may
override describe/invoke for installation checks and call super. It must not
replace Shared schemas or duplicate the entire Android adapter/CLI. Existing
Phone wrappers may remain; this is an optional migration, not a new requirement.

Candidate association uses the native owner's existing SH-009 verifier and its
record/artifact/independently expected input/source/signer/version arguments.
This release does NOT upgrade its pending artifact receipt into installed proof.
Before returning v003 executionIdentity, native code must validate that pinned
candidate again and inspect the SAME selected target's installed package bytes:
for monolithic Android APKs, require one actual PackageManager package path,
the expected application ID, actual installed APK SHA256 equal to the verified
candidate SHA256, stable package mapping before/after and unchanged local
candidate bytes. Reject splits unless a separate exact split-set contract exists.
Use constrained native argv/path handling, never raw strings in a shell command.
No runner expectations or expected-hash echo are an OS observation.

The exact claim remains sh004-results/v003 executionIdentity:
integer schemaVersion1, sourceRevision SHA40, artifactSha256 SHA256 and
installedCandidateVerified=true. Reject missing/foreign/changed install state.
Recheck before/after any operation/session creation that can install a package;
reject a foreign install and one-candidate app.upgrade. Cleanup must remain
possible even when candidate verification fails, never be suppressed by a bad
receipt. Keep selectors, filesystem paths, URLs and raw exceptions private.

Bound result bytes and observed installed bytes still do not attest the build
producer, signature trust, SBOM semantics, physical profile or artifact admission.
Those remain the existing SH-002/009 and native gates. No real installation,
discovery or run is part of this source release. Missing native module/receipt
must fail closed, not use the test fixture's synthetic identity in production.

Checks: seven focused tests execute the original canonical parser/module loader/
dispatch and source entrypoint with test-only native OS boundaries, missing and
symlinked module, wrong class, Shared-option mutation, unchanged diagnostics and
closed-error negatives. Existing Phone/Pico discovery and cleanup tests are
run separately. Native integration and real installed-byte evidence are pending.
