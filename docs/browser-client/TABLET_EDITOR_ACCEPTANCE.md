# Native Tablet Create, Settings and More acceptance

This is a behavioral acceptance design, not a completed result. No test in this
proposal changes a public world. The actual discovery harness passed with the installed native worker and
bundled Chromium153; Create,Settings and More screenshots were inspected.
Two earlier test-oracle failures are preserved in [the evidence](evidence/tablet-editor-routing-20261001.json). The route fix has five passing
production-helper VM tests; actual Qt/native/browser acceptance remains open.

## Version and ownership

Use the actual 2026.04.1 Interface worker and its installed scripts, not the
similarly named files on current main. `installed-app-filehashes.json` binds the
inspected files. Preserve the seven existing isolated-domain scene entities.
Do not restart `lab/native-participant.js` as a new observer: its initialization
may delete/recreate all matching `Browser Lab ` entities. A dedicated new
observer must use getters only and keep microphone muted.

The managed lab currently permits ordinary guest rez, connect, avatar rez and
asset URL visibility. It denies administrative and asset-write permissions.
Create shape tests need ordinary rez permission; asset uploads must retain
visible denial instead of temporarily increasing the visitor's rights.

## Create routing correction

Installed `system/create/edit.js:83` selects tablet UI with
`HMD.active || !Settings.getValue("desktopTabletBecomesToolbar", true)`.
Changing `Tablet.toolbarMode` alone does not change that setting. With the
fresh-profile default true, CREATE opens detached native Create Tools/Entity
List windows through `Desktop.PresentationMode.NATIVE`. Those windows are
outside the captured offscreen Qt Tablet/desktop item tree.

`create-tablet-route.patch` sets the isolated worker preference false before
loading real default scripts, retains the existing toolbar/capture mode, and
restores the prior isolated value on helper close. It does not edit operator
profiles or replace any Create operation with a bridge entity mutation.

Run the discovery harness only after applying the patch and restarting the
owned gateway. From `browser-client`:

```sh
OVERTE_LAB_URL=http://127.0.0.1:8090 node tests/integration/tablet-editor-routing.mjs
```

The harness joins only `overte://127.0.0.2:45102`, captures the actual native and
browser PNGs for Create, Settings and More, and records source hashes at both
ends. Its success explicitly means UI discovery, not functional acceptance.
The home grid on the pinned release is 480 by 706: CREATE (240,460), SETTINGS
(100,600), MORE (240,600). Current Create also captured a480by706 surface; calibrate its
actual captured tablet rectangle before issuing mutations. Do not reuse home
aspect ratio for Properties/List coordinates.

## Create behavioral gate

1. Record browser world entity snapshots and ordered entity updates in a bounded
   local Map. Record an independent native observer's getter-only view. Keep IDs
   only in private local artifacts; publish aggregate results.
2. Open actual CREATE, confirm `qml/Edit.qml` is visible. The CREATE tab's SHAPE
   button emits `newEntityButtonClicked/newShapeButton`; installed edit.js calls
   real `Entities.addEntity({type:"Shape", shape:"Cube", ...}, "domain")` and
   selects that new entity. Use Qt pointer input, not injected EventBridge JSON.
3. Require exactly one newly observed domain Shape. Exclude local tool-handle
   entities. Record its actual ID and initial properties; if ambiguous, stop
   without issuing edits or deletes.
4. Use the actual Properties name field to assign a unique per-run prefix;
   confirm both browser and independent native peer receive that name. Edit a
   bounded dimension/color property through the same native Properties UI and
   confirm the actual entity properties and rendered browser geometry change.
5. Keep the unique own entity selected, open actual LIST and use its Delete
   control (`EventBridge {type:"delete"}` inside the installed HTML). Require
   removal in both observers and preservation of every baseline domain entity.
6. On failure, retain the exact owned ID locally and perform cleanup only for
   that proven new entity. Never delete by broad name prefix or whole-world
   enumeration. A cleanup report cannot substitute for successful GUI deletion.
7. Separately test a configured no-rez guest domain: visible native permission
   denial, no entity creation, no admission or account privilege change.

This covers primitive rez/edit/delete. Complete native transform-tool parity
remains a separate gate: installed edit.js depends on Controller mouse events
and Camera.computePickRay; the existing browser interaction bridge only sends
entity click signals. Local manipulator entities alone do not prove selection,
translation, rotation, scaling, clone/undo or transform dragging works.

## Settings behavioral gate

The pinned actual Settings app routes General, Graphics, Audio, Controls,
Security, QML Allowlist and Script Security. Graphics writes native Render
properties including verticalFieldOfView, viewportResolutionScale, bloom,
local lighting, shadows, haze and ambient occlusion. The browser owns its own
camera and renderer; current Tablet effects expose only mute and shield.
Therefore native switch/slider changes cannot yet establish a browser visual
setting effect.

After a bounded renderer-setting adapter exists, use native Qt inputs and
verify the browser projection/drawing-buffer/lighting effect, native effective
value, independent setting behavior, fresh-session restore and reset. Keep
native scripting/security permissions in the private worker boundary; never
copy an operator's entire Qt settings profile. Audio input/output settings need
an explicit browser media-device mapping and actual device selection proof.
Until then, report Settings menu navigation and native-only changes separately
from browser rendering behavior.

## More behavioral gate

Installed `system/more/app-more.js` loads the official `more.html`. The catalog
is `https://more.overte.org/applications/metadata.js`; its real buttons invoke
ScriptDiscoveryService.loadScript/stopScript and refresh running script data
from the native worker. Use a reviewed, benign actual catalog application,
verify an observable native/browser effect, stop it, verify removal, and prove
fresh-session preference restore. A fake locally hosted script/catalog does not
prove official More behavior.

The gateway's `--defaultScriptsOverride` causes native ScriptEngines::saveScripts
to save only its default-script entry instead of visitor-installed scripts.
A narrow validated visitor-installed-script record and approved restore path
are needed; current persona/Home/bookmark DTOs do not retain that list. Do not
copy account state or allow arbitrary host/private-file script URLs.

## Bounds and evidence

Use existing 90-second domain join and 30-second first Tablet frame bounds;
warm capture remains 8 seconds. Keep each UI action wait bounded and save
failure PNGs/errors. No 30-minute endurance test is required: the user canceled
it. Record native/browser versions, installed app and runtime source hashes,
exact commands and owned cleanup outcomes. Preserve failures, and distinguish
native-only state from visitor-rendered or independently observed effects.
