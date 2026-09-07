# Pico 4 URL handling and remaining acceptance

The production Java policy is
`android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico/PicoRestartUrlPolicy.java`.
`RestartArguments.store` validates the exact private argument prefix and world
URL before persistence. `RestartArguments.consume` validates the recovered
arguments again before `RestartActivity` supplies them to Qt.

The policy accepts the base `--display=OpenXR` argument or that prefix followed
by one `--url` value. Supported world schemes are `hifi`, `http`, `https` and
`file`. It normalizes Unicode to NFC, rejects invalid surrogate sequences,
controls, bidi overrides, backslashes, credentials and malformed URI syntax,
and caps the final encoded URL at 4096 UTF-8 bytes. Network URLs require an
authority; Unicode DNS names use Java IDN validation. Local file URLs require
an absolute path, reject traversal after URI decoding, and permit no authority
except `localhost`. `hifiapp` is not a world URL scheme.

The exported Pico activity remains a `MAIN`/`LAUNCHER`/Pico-VR entry point. It
has no `BROWSABLE` category or URL data filter and does not forward arbitrary
caller-provided arguments to the private Qt activity. External Android deep
links are unsupported and must not be advertised as a Pico capability.

## Local verification

`android/vr/pico/tests/device/test_native_url.py` compiles and runs the actual
Java policy with host JVM cases. It also checks the production restart call
sites as source. These checks establish neither Android storage durability
nor device keyboard behavior.

The earlier Python URL-entry model was a preparation fixture without a
production caller. It is not part of this integrated source tree. Its simulated
focus, cancel and submit state transitions are not evidence for a real Pico
input surface; the sealed platform history retains that earlier model.

## Remaining original acceptance

PI-003 and the complete URL/input scope remain unaccepted. Actual native URL
entry, keyboard focus and cancellation, shared UI/auth integration, protected
restart persistence, foreground transitions and exact artifact/device evidence
must be verified through their original SH-003, SH-004, SH-005, PI-002, PX-15
and PX-16 dependencies. The Java validation boundary does not establish these
other requirements or authorize a new exported receiver.
