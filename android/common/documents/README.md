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
handlers. ACTION_OPEN_DOCUMENT selects files; the additive native
`DocumentTreePickerOperator` uses ACTION_OPEN_DOCUMENT_TREE for an explicit
directory choice. The existing file operator ABI is unchanged. The request ID,
Activity owner and epoch never migrate to another Activity or helper. OS returns
remain pending until the same Activity is genuinely foreground. Explicit helper
cancellation/destruction revokes the request; late returns are discarded.

ContentResolver copies every selected provider document into native-owned
`QStandardPaths::AppDataLocation/ImportedDocuments/selection-…/<name>`.
The copied files retain valid original DISPLAY_NAME names, Unicode and file
extensions. Unique names remain siblings so explicitly selected relative resources
stay together; duplicate names use distinct `duplicate-…` subdirectories. This
does not imply permission to an entire original project directory or qualified
multi-file model import through individual file selection. Missing,
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

Directory selection preserves the chosen display name and every relative child
name in one retained app-owned directory. Completion returns exactly one local
directory URL. Copies enforce the same 32-file/256-MiB/512-MiB limits plus at
most 1024 entries and 16 relative path components, including each file name but
excluding the selected root. Enumeration is bounded before recursive copying;
duplicate sibling names, provider-ID cycles, virtual documents, unsafe names,
oversized metadata or actual bytes, and permission/write/close failures reject
the entire selection. Java and native Qt independently reject unsafe hierarchy
or symlink/containment violations. Provider queries and stream opening receive
the request's CancellationSignal; descriptor streams preserve asset sections
and automatically close their underlying descriptor, as defined by the
[Android descriptor API](https://developer.android.com/reference/android/content/res/AssetFileDescriptor#createInputStream()).
Cancel/detach keeps the original request lifetime and removes partial copies.
Successfully returned hierarchies remain readable after the picker ends;
provider URLs never escape to the runtime. Actual model/script use and provider
behavior still require the product/device acceptance below.

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

## JNI names in release builds

The Gradle helper applies this module's `proguard-rules.pro` to every build type.
Only the Java entry class called by native JNI is retained by name with its
methods; other implementation classes remain eligible for R8 optimization.
Do not remove these rules when enabling release minification.

`android/common/tests/jni-shrinker-test.py` optionally compiles all three real
Java endpoints against Android SDK/AndroidX artifacts, optimizes them with an
explicit R8 JAR and checks every native lookup and callback descriptor. An
unprotected negative control loses the endpoints. Supply `--r8-jar`,
`--android-jar`, `--webkit-jar`, `--core-jar` and `--annotation-jar`; the JDK is
discovered from `javac`, or set with `--java-home`. JVM classfile output uses the
actual JDK LambdaMetafactory declaration because Android's API stub omits it.
This host check does not qualify the product's AGP release APK or device runtime.
