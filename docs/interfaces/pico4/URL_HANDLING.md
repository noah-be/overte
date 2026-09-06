# Pico 4 URL handling preparation contract

Status: pre-admission Pico-local contract slice. PI-003 is not admitted or complete.

Revision 09 adds the production Java `PicoRestartUrlPolicy` at the private
`RestartArguments.store` and `consume` boundaries. Both paths validate the exact
restart argument prefix and supported world scheme before Qt receives arguments.
The native policy additionally rejects decoded controls and local-file traversal,
and caps the encoded URL at 4096 bytes. Its JVM tests execute the actual class
used by the app. The older Python module below remains a preparation fixture;
it is not a native keyboard implementation. External Android deep links remain
unsupported; no receiver is added. General's shared focus/UI and auth bindings
remain pending.

## Existing behavior retained

The exported Pico activity is a `MAIN`/`LAUNCHER`/Pico-VR entry point. It has no
`BROWSABLE` category or URL data filter and does not forward caller-provided
arguments to the private Qt activity. Consequently, arbitrary external deep
links are unsupported and must not be represented as a Pico capability.

Trusted in-process restart handling fully percent-encodes its URL before adding
the private `--url` argument. Existing Android world startup accepts only
`hifi`, `http`, `https`, and `file` URLs. The prepared Pico-local policy mirrors
that list; `hifiapp` remains an app-start route rather than a world URL.

## Prepared device-free boundary

`android/vr/pico/src/contracts/pico_url_contract.py` provides a small local
decision boundary for a future Pico URL-entry adapter:

- input is NFC-normalized and capped at 4096 UTF-8 bytes;
- controls, bidi overrides, malformed escapes, credentials and unsupported
  schemes fail closed without returning the supplied target;
- network world URLs require a host;
- `file` accepts only an absolute local path without traversal or remote
  authority;
- Unicode paths, query text and internationalized hosts are deterministically
  encoded;
- cancel or focus loss clears the pending text and terminates the entry session;
- a rejected submit retains focus for correction, while an accepted submit
  closes it.

Decision objects intentionally hide accepted targets from their representation,
so ordinary assertion or diagnostic output does not expose a private location.

## Deferred dependencies

This slice does not expose a new Android intent receiver, wire a production UI,
choose account/domain-auth behavior, define a Shared device/evidence schema, or
claim physical keyboard behavior. Production binding remains deferred to the
real PI-003 admission and accepted `SH-003`, `SH-004`, `SH-005`, PI-002,
`PX-15`, and `PX-16` handoffs.
