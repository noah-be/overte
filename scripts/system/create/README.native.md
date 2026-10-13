# Native Create on touch and headset tablets

The normal `edit.js` app loads `qml/Edit.qml`. On Android and iOS, this entry
uses `NativeCreate.qml`; desktop tablets retain `EditDesktop.qml`. Start the
editor as its own script engine and use the system tablet with `toolbarMode`
set to `false` for touch clients. A startup script's JavaScript variables do
not propagate into the editor's separate engine.

The native surface provides these user outcomes:

- NEW creates the existing sixteen entity types in the domain or on the user's
  avatar. Model, image, web, sound, script and material resources accept a URL.
  More options opens the existing detailed creation dialogs, including model
  collisions and textured/filled PolyVox volumes. These retain their existing
  domain-host creation behavior and require domain rez permission.
- LIST uses the existing nearby-entity scan, name/type filtering, refresh and
  single or multiple selection. Other users' avatar entities remain excluded.
- PROPERTIES changes name, position, rotation, dimensions, color, visibility,
  physics and collision flags. Lock/unlock requires lock permission. The
  searchable typed fields expose scalar and nested properties for URLs, text,
  animation, audio, materials, lighting, physics and other entity types. Editing
  a nested field retains its siblings and uses the existing property converters.
  The advanced JSON editor handles arrays and other structured properties; identity,
  host, ownership and computed properties are excluded.
- TOOLS delegates duplicate, copy/paste, delete, parenting, focus, movement,
  grid, space, rotations, export and domain assets to the existing editor. Voxel
  mode exposes single/sphere/cube, add/remove, click/continuous, ray/controller
  brush, diameter and reach through the existing EditTools and EditVoxels.
  Brushes reject locked and foreign-owned volumes and stop at tablet pointers.
  Completed strokes record compressed voxel data in the existing undo history.
  `Entities.isVoxelDataReady` reads the renderer state and dirty flags under its
  read lock; elapsed time or unchanged bytes do not establish completion.
  Pending workers, deletion and older runtimes report unavailable undo honestly.
- IMPORT accepts HTTP, HTTPS and ATP entity JSON URLs or the native file picker,
  optional coordinates and a domain/avatar host. It reports empty, failed and
  cancelled imports. Successful imports become the selection and enter history.

The surface sends namespaced `nativeCreate.*` QML messages through the existing
tablet connection. `modules/nativeCreateBridge.js` validates requests against
the active editor, current selection, ownership, lock state and permissions.
Property conversion, entity defaults, spawn placement and undo remain in
`edit.js`; the bridge does not implement a second entity editor.

Pico's numeric field focus still consumes both movement stick axes during a
preview transaction. Leaving the field records one undo command; hiding,
closing, permission changes and script shutdown release the mapping. Headset
text fields use the established keyboard ancestor properties. Touch fields use
the native IME. The desktop HTML pages and stronger viewport tools remain
available on desktop.

## Host verification

From the repository root:

```bash
node --test tests/javascript/test/mobile-create*.test.js
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

The JavaScript tests execute the production entity scan, native bridge and full
`edit.js` against substituted engine APIs. They verify actual entity operations,
Euler conversion, physics velocity reset, history, avatar host preservation,
imports, permission loss and lifecycle cleanup. The QML test invokes
`qmltestrunner` with real Qt Quick pointer and keyboard events at tablet and
320-pixel layouts, including nested typed fields and voxel brush controls. A
native host fixture compiles the actual readiness API, renderer readiness,
compression completion and update state-machine bodies with Qt read/write
locks; volume geometry, worker scheduling and packet sending are substituted.
It checks pending compression, completed bytes before Ready, dirty flags,
non-rendering entities and deletion. Qt Core development headers are required.
Qt Quick Test and Controls 2 are required for that test; the
Node wrapper explicitly reports a skip if the runner is unavailable.

## Artifact-bound device acceptance

Host checks are not physical-device evidence. For each named iOS, Phone and
Pico artifact, exercise the normal CREATE entry point in a writable test domain:

1. Create a shape, text and URL-backed model. Verify their world appearance and
   selection, including avatar-host creation with domain rez permission absent.
2. Refresh/filter LIST, select one entity and select multiple entities. Confirm
   other users' avatar entities are absent.
3. Enter text with the device keyboard, edit transforms and searchable typed
   model/audio/animation/lighting fields and a structured advanced property;
   lock/unlock and exercise undo/redo and delete/undo.
4. On Pico, adjust a focused numeric field with the stick, then hide the tablet
   and verify normal locomotion resumes. Confirm one undo reverses the preview.
5. Exercise duplicate, parent/unparent, grid, rotation, export and asset browsing
   with the appropriate touch or controller pointer. Validate external native
   file/asset dialogs on that client.
6. Import a local fixture and a URL fixture at default and explicit positions;
   undo/redo each. Exercise an invalid URL, empty import, load failure and file
   picker cancellation. Close the app while a picker is pending and verify a
   late result does not import anything.
7. Draw on PolyVox volumes with each shape, add/remove, click/continuous and
   ray/controller brush. Confirm diameter/reach, compressed world results,
   undo/redo, UI pointer suppression, lost permissions and locked/foreign volume
   rejection. A stalled or deleted volume must not record fabricated undo.
8. Revoke rez/avatar/lock permissions while editing. Verify readonly feedback,
   host-specific history guards and released input. Navigate away and reload the
   script; verify there are no duplicate handlers or retained input mappings.

Record the artifact revision, configuration, client and observed outcomes.
Do not mark the complete desktop property-form or voxel-brush experience as
device-verified from the native JSON editor or host tests alone.
