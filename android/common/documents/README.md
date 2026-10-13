# Android native document selection

This owning-parent module installs the main `FileDialogHelper` operator from
`libraries/ui/src/FileDialogHelper.h`. `overte_target_documents(target)` adds the
actual JNI endpoint and links `ui`; apply `target.gradle` with
`ext.overteDocumentsRoot` for Java sources. No new external dependency is added.
The common Web `WebFilePickerState` allocates unique OS request codes across
embedded browsers, snapshot exports and document imports.

A product supplies an immutable `DocumentHost` and calls `DocumentAdapter`
`initialize` only after its Qt/native UI is ready, `foreground` on real resume
and window focus, `detach` on destruction and `activityResult` before other result
handlers. ACTION_OPEN_DOCUMENT is the actual selection path. The request ID,
Activity owner and epoch never migrate to another Activity or helper. OS returns
remain pending until the same Activity is genuinely foreground. Explicit helper
cancellation/destruction revokes the request; late returns are discarded.

ContentResolver copies every selected provider document into native-owned
`QStandardPaths::AppDataLocation/ImportedDocuments/selection-…/<index>/<name>`.
The copied files retain valid original DISPLAY_NAME names, Unicode and file
extensions, including duplicate names in separate per-index directories. Missing,
unsafe or unrepresentable names fail visibly. Qt extension filters are checked
against the actual display name; the native picker remains broad because provider
MIME types are not reliable for JavaScript and model formats. Provider URLs and
filesystem root setters never enter the script or asset engine.

Selection is complete or fails: maximum 32 documents, 256 MiB per document and
512 MiB total. Metadata size is advisory; actual copied bytes enforce limits.
Streams must flush and close before success. Empty documents are valid. Copy,
close, provider permission, extension and limit failures are reported; no partial
selection is delivered. Failed or cancelled request directories are removed;
successfully handed-off app-owned local copies remain available after the helper
or picker ends. Native Qt rechecks canonical readable regular files, retained
root ownership, symbolic-link escapes, counts, sizes and selection mode before
returning local QUrls on the Qt thread.

`python3 android/common/documents/tests/run.py` compiles and executes real
portable name/filter/copy/limit/cancellation tests. `--android-jar ...` compiles
all production Java against an actual SDK artifact. `--native --qt-root ...`
compiles the actual main FileDialogHelper, Android endpoint and JNI against Qt
and a host JVM; only the OS picker endpoint is a declared fixture. Before main
propagation, `--helper-root ...` can reference the highest-owner Main promotion
for isolated host checks. Product builds use the in-tree parent source.

Host tests do not qualify OS/provider metadata, permission behavior, Activity
rotation, actual asset/script loading or APK packaging. Those need a full
source-bound product build and real provider/device acceptance.
