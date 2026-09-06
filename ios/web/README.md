# Contained native web adapter (IO-009)

Consumes General `sh007-native-web/v001`, manifest
`1e4e87fe6e5d29315b02ec934e38e8b28547c2c45ecd4bcfe2eb0ee45d174d7d`.
`NativeWebAdapter` uses the original process-wide `NativeWebPolicy`; it does not
implement a second URL parser or session. The actual Overte target directly links
the adapter and queued Qt startup registration in `ContainedWebView.mm`.

Current partial mode: explicitly confirmed, HTTPS same-origin **plain text only**.
HTML, XHTML, SVG and PDF responses are denied before response commit. This is a
fail-closed limitation, not approval of a new product mode or full web parity.
General must resolve the HTML/no-credential-autofill contract and Shared wording.
CSS hiding is defense in depth, not an input/autofill security boundary.

The optional view requires an iOS 18.4+ SDK and runtime for the public file-panel
denial delegate; older systems return unavailable without changing the app floor.
Multiple active key windows also return unavailable: the published request has
no originating scene identity, so an arbitrary confirmation target is unsafe.
Only main-frame navigation is admitted; subframes cannot expand this text mode.
The origin confirmation precedes native view creation and loading. Navigation,
redirect, response, history and reload check the current original Shared ticket.
There is no JavaScript, script injection, bridge, shared account-cookie injection,
supplied TLS credential, HTTP authentication, download or external browser fallback.
The data store is nonpersistent. One constant content-rule compilation is shared;
it contains no site grant or private URL and never queues request closures.

Replacement, close, scene/key-window loss and suspension invalidate the ticket
before teardown. A 30-second preparation/navigation deadline fails visibly. A
failed native teardown denies future presentations in this process; it is not
reported as successful OS cleanup. Errors use only the existing redacted event.

Focused host checks:

- `python3 ios/tests/native-web-adapter-test.py` executes the actual C++ adapter
  and original Shared singleton using real Qt; only UIKit operations are faked.
- `python3 ios/tests/native-web-wiring-test.py` checks source wiring and constant
  rule structure. It is not Objective-C++ compilation or WebKit behavior proof.
- `python3 libraries/qml/contracts/test_native_web.py` exercises General's policy
  and actual selected QML caller.

Pending: Apple SDK compilation/API availability; real confirmation/VoiceOver and
full-screen/window transitions on iPad and iPhone; no-prefetch before confirmation;
TLS/redirect/MIME-sniffing/autofill/cookie/cache/third-party traffic adversarial
checks; OS teardown and deadlines; full client composition. No simulator/device,
network capture, signing, supported HTML mode or node acceptance is claimed.
