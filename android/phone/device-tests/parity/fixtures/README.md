# Original Phone companion fixtures

All files here are original Apache-2.0 test data, with no third-party artwork.
Copy the complete directories to a harmless location offered by the actual
Android document provider; retain nested names. Folder selection and main-file
review are part of the journey. No fixture automatically changes the test
catalog, system preferences, accounts or acceptance registry.

* `script-bundle/main.js` includes two ordinary nested client scripts. Running
  it creates one cyan local cube two metres in front of the avatar and a
  `P2 SCRIPT` tablet button. Pressing that button changes its colour to orange.
  Stopping the script disconnects the button and removes only its cube/button.
  A missing include must not be mistaken for a successful local import.
* `gltf-bundle/main.gltf` uses external `mesh/triangle.bin` geometry/UV/normal
  bytes and `textures/checker.png`. It should render a two-sided triangle with
  distinct cyan/magenta regions. Do not replace it with a self-contained GLB.
* `obj-bundle/main.obj` references `materials/palette.mtl`; that material in
  turn uses `../textures/checker.png`. The four-vertex quad should display
  distinct cyan/magenta regions. A white/flat or missing texture is a failure
  even if the model and all uploaded hashes exist.

Record the chosen main file, relative companion inventory and visible result.
For a negative control, remove the texture or nested include from a separate
copy, never from the original fixture. Cancellation/denial/upload failure must
have an honest outcome and must not publish a truncated primary mapping.
These files are device input, not native parser/render acceptance.
