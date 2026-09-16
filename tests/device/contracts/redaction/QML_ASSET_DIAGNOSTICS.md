# Asset and retained-view diagnostics

Both desktop and Tablet AssetServer components emit fixed event descriptions for
delete, rename, upload, world insertion and baking changes. They do not format
asset paths, file URLs, names, mapping lists or free-form server errors into logs.
The unconditional upload error/path print is removed. Card thumbnail and Tablet
WebEngine load-failure diagnostics likewise use fixed text. The failed web-load
path no longer even converts the failed URL for logging.

Asset-operation arguments and user-facing error dialogs retain their existing
values. A known destination folder now ends the rename function after showing
the error; it cannot proceed to Assets.renameMapping. Delete/rename error boxes
are local variables rather than shared implicit globals.

Focused tests execute the exact delete, rename, upload and web loading functions,
Card's actual status handler, and every diagnostic expression in both asset
components under host JavaScript with a network namespace. Assets, dialog signals,
timers, models and browser/QML objects are explicit seams. Tests cover success,
server error, upload cancellation, duplicate upload admission, timer completion,
folder-name normalization, collision refusal and thumbnail fallback. Private-value
canaries remain absent from logs while operation arguments remain intact.
The actual previous source fails the canary checks; removal of the collision
return independently fails the no-rename assertion.

This is not a complete Qt QML/window or native WebEngine/asset execution test.
Dialogs deliberately display the requested operation's paths and errors; screenshot
and export privacy are not accepted by these checks. Existing internal web/entity
JavaScript console payloads are retained. Full startup/third-party/crash/export
privacy, retained surfaces and original39 platform acceptance remain open.
