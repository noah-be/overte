# Browser Graphics Settings adapter

The adapter is integrated into the gateway, Tablet protocol, main and
BrowserWorld. Actual native Qt pointer journeys passed in Chromium153 and stock
Firefox156: all12 changes reached actual browser state/framebuffer dimensions,
settings survived leave/rejoin, and the reopened native page restored defaults.
Separate real BrowserWorld GPU fixtures passed in both bundled engines, proving
local-light pixels, projection changes and collision-constrained camera behavior.
[The native control evidence](evidence/tablet-graphics-runtime-20261001.json)
retains earlier capture, reconnect-driver and Firefox capture-driver failures.
Four-control acceptance does not establish complete native graphics parity.

## Supported controls and truthful UI

Only four controls are enabled: Field of View (integer20–130), Resolution scale
(10–200%, steps of10), Local Lights, and Allow camera clipping. The last checkbox
is the inverse of the `cameraClipping` constraint setting. Native Settings widgets
are retained from the actual pinned 2026.04.1 package. Owner-local effective UI states carry
a monotonic sequence so a queued older state cannot overwrite newer controls. The private Graphics page
explicitly states that additional graphics options are unavailable in this adapter.
Presets, bloom, custom shaders, deferred rendering, shadows, ambient occlusion,
haze, anti-aliasing, LOD, refresh-rate profiles and monitor selection remain open. Those
features remain required parity work; this initial adapter does not remove them from
the goal or claim the full Settings application is complete.

The native worker's reduced resolution and disabled duplicate world draw jobs
remain untouched. A browser request cannot silently import the worker's10%
resolution into the visitor's renderer. The browser World's established device
pixel ratio is the100% base. Requested50% means half that ratio in each dimension;
200% means twice it. Other world sampling, texture quality and sources remain
unchanged.

## Files and startup boundary

`loadBrowserGraphicsPackage(defaultScriptsURL)` must run at gateway startup on
an operator-approved installed file URL. It reads bounded regular files without
following a terminal symlink, checks exact known SHA256 values for settings.js,
Settings.qml, GraphicsSettings.qml and the imported SettingSlider/SettingBoolean/SettingComboBox
components, and caches those bytes. Unsupported package versions fail clearly.
Only2026.04.1 has reviewed source hashes in this prototype.

Call `package.prepare(session.directory)` before launching a visitor worker. It
returns `{scriptURL,channel,readOnlyOverrides,schemaVersion:1}`. Add the six
read-only file overrides to the existing worker sandbox list, preserving their
original installed paths for relative imports. Copying/mounting these files
never edits the installed package or operator profile. Native controller source
is cached at module import. Different visitors receive different private random
local-message channels; gateway restart is required after source changes.

The subsequent resolution-only preset selector uses the original pinned native
combobox. Default100%, Balanced80% and Faster60% require explicit visitor selection;
the four existing wire fields and initial100% default stay unchanged. Custom
reflects other valid percentage values and cannot select a hidden setting. The
eleven native/generated-QML contracts and the actual six-file read-only kernel
mount test pass. Genuine Qt preset clicks and framebuffer effects are pending;
the earlier four-control native results do not prove this added selector.

## Native helper hooks

The existing native Tablet helper should include `config.graphics.scriptURL`
and create the controller before loading installed default scripts:

```js
Script.include(config.graphics.scriptURL);
graphics = createBrowserGraphics({
    channel: config.graphics.channel,
    now: Date.now,
    send: send // the existing revision-gated engine outbox, never direct Qt WS
});
```

Forward each authority change to `graphics.setAuthority(revision,approved)`;
call `graphics.poll()` in the existing engine interval; forward validated
`graphicsResult` actions to `graphics.receive(message)`; call `graphics.close()`
on helper teardown. No new timer or direct WebSocket write is created inside a
Qt callback. Pending input is disabled until the browser's effective ACK arrives.
The exact eight-second ACK deadline is retained; expired/replayed/revoked ACKs
cannot alter controls.

## Wire and admission

Native to browser, after current native permissions and Tablet revision gate:

```json
{"type":"tablet","kind":"graphics","revision":3,"schemaVersion":1,"requestId":7,"operation":"change","field":"resolutionPercent","value":50}
```

The initial `operation:"request"` omits field/value and asks for the actual
browser target state. `validateBrowserGraphicsRequest` produces the bounded DTO;
node should extract it from the existing authenticated envelope and attach only
the actual current revision. Browser replies through the same owned session:

```json
{"type":"tablet","action":"graphicsResult","revision":3,"schemaVersion":1,"requestId":7,"accepted":true,"settings":{"version":1,"fieldOfView":70,"resolutionPercent":50,"localLights":true,"cameraClipping":true}}
```

`validateBrowserGraphicsResult` checks the exact supported settings shape and
bounded optional message. Node forwards no result without current approved
session/native/Tablet authority. The app receives only the owner-local effective
state, and its actual native QML controls reflect that state. Unknown fields,
nonfinite/out-of-range numbers, wrong revisions and stale request IDs fail.

## Browser hooks

Create one `WorldGraphicsTarget`/`BrowserGraphicsController` per BrowserWorld,
with authority callback bound to the exact live visitor World/session/epoch and
permission revision. The callback must not merely compare a globally mutable
revision number. Close/revoke synchronously during session leave, connection
loss, replaced World or permission denial. A new visitor owns a new controller;
there is no global/account/domain shared settings controller.

The target applies the actual Three camera projection, renderer pixel ratio,
local-light slot enable state and third-person camera collision constraint.
Parent World integration must implement honest getter/setter bindings for the
last two settings. Keep light slots stable and zero their contributions when
local lights are disabled, preserving existing shader permutation safeguards.
Keep global zone/environment lighting unaffected. Viewport allocation must
retain the World's hardware/canvas allocation bounds and report failure rather
than claiming an unsupported scale was applied.

The controller reads the target after applying the request. A thrown or silently
ignored setting returns `accepted:false` with the actual effective values;
partial failure never reports the desired DTO as if it succeeded. If authority
changes during apply/read/store callbacks, no ACK or preference write survives.
A preference-storage failure leaves an honest rendering ACK and bounded warning.
Browser-owned narrow graphics preference persistence can use the validated DTO;
never copy native account/Qt settings wholesale.

## Required actual acceptance

Use the isolated managed domain, actual native Settings button and Graphics
page, genuine pointer input to the native slider/switch, and record both native
PNG plus browser metrics/pixels. Test FOV20/130 projection, resolution50/100/200
actual drawing-buffer dimensions, local entity light contribution, and the
camera clipping inverse. Verify displayed effective values after refusal,
authority loss and reconnect. Run stock Chromium and Firefox with frozen source
hashes; preserve initial failures. CPU callback spies are not GPU evidence.
