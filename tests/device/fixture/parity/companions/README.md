# Shared Create, Scripts and Assets inputs

Use these identical original Apache-2.0 inputs on iOS, Android Phone and Pico.
They contain no third-party artwork, account data or device selector. The
manifest binds every input byte. These files provide useful test content;
they do not prove import, script execution, rendering or device acceptance.

Keep every directory and nested relative name when copying inputs to a
harmless location offered by the actual Files/document provider. The existing
[fixture server](../../serve.py) also serves them under `/parity/companions/`.
Use the lab address and port already recorded for the shared web reference.
Serving these files does not grant permission or install a client script.

Run each journey on the deliberately selected source/artifact and retain the
UTC date, installed-byte binding, OS/provider version and actual screen/file
observations. Use normal app entries and consent. Never substitute a debug
probe or a canned state for a useful outcome. Keep credential entry out of
recordings and remove only content created by the test.

## Create

Open **Create** and its ordinary import control. Choose `create-entities.json`
through the OS chooser or enter its fixture-server URL. Choose the intended
host and position in the normal import review. The input has two unlocked,
collisionless entities: a cyan cube and a dark text panel saying
`Shared parity: cube + text`. It contains no script or external URL.

Observe both imported entities in the world and list; select and rename one,
change its position, delete it and undo. Separately exercise primitive/model/
image creation and a voxel/tool operation. Repeat import or an edit in a
controlled domain without permission: an actionable denial must leave no
unauthorized mutation. This import fixture does not qualify the rest of Create.
Delete only the imported/test-created entities afterward. The existing
controlled six-entity scene remains unchanged.

## Scripts

Open **Running Scripts**, choose the complete `script-bundle` folder through
the real provider and review `main.js` as the main script. It includes two
ordinary nested files. Running it creates one local cyan cube two metres in
front of the avatar and a `P2 SCRIPT` tablet button. Press that button and
observe the same cube turn orange. Stop the script: its cube and button must
disappear. Restart and repeat; there must be one cube/button, with no orphan
callbacks. Test From URL separately using the server's `script-bundle/main.js`.

Make a separate negative copy with a nested include missing. Failure must be
useful and cannot count as successful bundle execution. Cancel the provider
and replace/close the owner while selection is pending; no late selection may
launch a script. Preserve required local copies for the script's lifetime.

## Assets

Open the ordinary **Asset Browser**, choose the complete model bundle with
companions and explicitly review its main file. Upload to the controlled
domain, then add the uploaded model through the normal UI.

- `gltf-bundle/main.gltf` needs external `mesh/triangle.bin` and
  `textures/checker.png`. Observe a two-sided triangle with distinct cyan and
  magenta texture regions. A self-contained GLB cannot replace this input.
- `obj-bundle/main.obj` needs `materials/palette.mtl`, whose texture reference
  is `../textures/checker.png`. Observe a quad with distinct cyan and magenta
  regions. A white or untextured mesh is a failure even when upload hashes match.

Make a separate negative copy with the texture missing. Also cancel the
provider, deny upload permission and interrupt a companion upload using the
existing controlled failure mechanism. Whole-selection/companion failure must
not publish a truncated primary mapping. Inspect the real rendered material,
not only filenames, copied hashes or a success notification. Clean up only the
test entities and test mappings; preserve input copies while still in use.

The actual native picker, script/resource policy, provider lifecycle, parser,
upload permissions and renderer are under test. Host fixture checks and HTTP
availability establish input integrity only. Record unsupported behavior as an
open observation rather than replacing the workflow with a simpler one.
