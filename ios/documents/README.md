# iOS system document selection

The startup adapter installs the shared `FileDialogHelper` file and directory
picker operators and their cancellation callbacks. It uses
`UIDocumentPickerViewController` with explicit user selection,
not a QPA provider assumption. It retains one native chooser/copy lease and
returns the same request through the helper's completion callback on the Qt
owner. Closing the helper, cancellation, or backgrounding invalidates the
selection. Late returns cannot revive a cancelled request.

Each provider URL is read under `NSFileCoordinator` while its security scope is
active. Reads happen off the UIKit main queue. Cancellation also cancels pending
coordination; an in-progress copy keeps its lease until it unwinds. No scoped
provider URL or bookmark enters QML, script execution, or asset loading.

Complete copies live permanently in the native app-data
`ImportedDocuments/selection-<id>` directory. Unique original file names share
that directory, preserving selected sibling references. Duplicate original
names receive separate `duplicate-<id>` subdirectories without overwriting or
renaming their files. The entire selection fails with a visible error if it
exceeds 32 files, 256 MiB per file, or 512 MiB total. Partial and cancelled
selections are removed and never returned. File selection rejects folders and
aliases. A successful committed selection survives helper destruction.

Directory selection uses `UTTypeFolder` and returns exactly one permanent local
directory URL. Its copy preserves the chosen root name, relative directories,
file names, hidden entries, and empty directories. The same file/byte limits
apply, with at most 1024 entries (files and directories) and 16 relative path
components including each file name; the selected root is not counted. The
bounded production iterator reports enumeration errors. Symlinks, aliases,
unsafe paths, destination name collisions, short reads, and unreadable or
vanishing subtrees fail the complete selection instead of returning a subset.
The native reader retains the selected root's security scope and prepares a
top-level directory batch throughout traversal and copying. It coordinates the
directory traversal and each child file read using the same `NSFileCoordinator`,
following Apple's [batch coordination contract](https://developer.apple.com/documentation/foundation/nsfilecoordinator/prepare(forreadingitemsat:options:writingitemsat:options:error:byaccessor:)).
A directory-only read would not coordinate every child's contents. Each provider
read supplies a synchronous continuation to the same tested byte copier, which
reads file data inside the coordinator's accessor. Qt's owner receives completion
only after that lease unwinds. Application shutdown also requests cancellation.

The typed picker initializer and `UTTypeFolder` are available since iOS 14,
below this client's iOS 17 minimum, according to Apple's public
[picker initializer](https://developer.apple.com/documentation/uikit/uidocumentpickerviewcontroller/init(foropeningcontenttypes:ascopy:))
and [folder type](https://developer.apple.com/documentation/uniformtypeidentifiers/uttype-swift.struct/folder)
declarations. This availability inspection is not an Apple SDK compilation.

The production Core copier is exercised by the mandatory iOS host gate,
including actual file and tree bytes, relative resources, hidden and empty
directories, names, siblings, duplicates, exact bounds, cancellation, incomplete
reads, enumeration errors and rollback. UIKit, cloud-provider materialization
and coordination, native picker presentation, and
security-scoped access still require the coordinated Apple SDK build and device
qualification. Real directory-provider selection and model/script loading from
its returned hierarchy have not been qualified by this host fixture. The
additive `FileDialogHelper` tree ABI is integrated through Main to Apple to iOS.
The mandatory `document-picker-handoff-test.py` compiles the native production
registration lines and endpoint signatures against that in-tree header, then
executes the actual copier and shared helper with a fixture at the UIKit/provider
boundary. It checks the preserved script hierarchy, owner-queue completion,
copy-lease cancellation, full rollback, stale replies and permanent resource
bytes. It does not compile the complete Objective-C++ endpoint or execute UIKit.

The full `ios/tests/run-tests.sh` qualification also requires the shared
`test_obj_material_bundle.py` with Qt6 and real GLM headers. It executes the
production OBJ/MTL parser and texture URL consumer, including nested resources,
decoded image bytes and preserved FST texture-base overrides. Qt5 compatibility
uses `OVERTE_NATIVE_QT_MAJOR=5` in the shared test. Resource providers and renderer
storage remain explicit host boundaries; physical imported-model rendering is
still separate. See the [host test guide](../../tests/PROJECT_TESTING.md).
