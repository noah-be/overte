# Native Scripts and Assets contract

The same Qt Quick Controls 2 surfaces serve the normal desktop and tablet paths
on Qt5 and Qt6. The desktop window, hierarchical models, file filters, directory
navigation, selection, sorting, local save/overwrite checks, mapping mutations,
and baking controls remain available. Asset write permission restricts mutations;
it does not hide readable browsing or entity import. Entity import still requires
rez permission and delegates to the existing native entity creation path.

## Host verification

```sh
python3 tests/device/contracts/script_assets/test_script_assets_qml.py
OVERTE_NATIVE_QT_MAJOR=6 python3 tests/device/contracts/script_assets/test_script_assets_qml.py
node --test tests/javascript/test/mobile-script-assets.qml.test.js
python3 tests/run-project-tests.py --profile quick --timeout 240
```

The fixture loads the actual production files with the native QQml file selector,
including nested relative imports and desktop compatibility windows. Real
QStandardItemModel/QSortFilterProxyModel and FolderListModel objects execute tree,
selection, filtering, data changes and reset behavior. Actual pointer/key events
exercise buttons, the scaled in-dialog keyboard, Escape/Cancel, and local file
selection. The complete production FileDialogHelper compiles unchanged and opens
an actual desktop QFileDialog; the fixture types a real temporary filename and
asserts the resulting local URL, rather than merely accepting a method call.
The production Asset Browser menu block and complete Application route method
also execute with real QAction and explicit surface/login/HMD boundaries.

Script engines and asset networking are native QObject boundaries recording the
actual QML API calls and returning success/failure callbacks. The new Image API's
actual header declaration, complete implementation and grabbable constants compile
and execute through QML. Entity property storage, vector representation, session
lookup and generic addEntity are explicit unit boundaries. This proves forwarding,
position/session preservation and visible denial handling, not a complete entity
engine build or server authorization. The existing addEntity/addModelEntity
implementation remains responsible for production ownership and rez checks.

The registered JavaScript suite uses an available Qt5 kit or system Qt6. Both
explicit runs are required when reviewing compatibility with both versions.
Qt QuickTest, Quick, Widgets, Test, moc, pkg-config and a C++17 compiler are needed.
Qt5 can be selected with OVERTE_QT5_ROOT; the local default is ~/.local/overte-qt5/root.
The offscreen desktop plugin's window-manager warnings are host limitations.

## Native document provider contract

FileDialogHelper::setDocumentPickerOperator installs a platform open-document
adapter with request ID, caption, filter, multiple-selection flag, completion,
and a separate cancel operation. The completion returns a QList<QUrl> of fully
materialized, readable local files plus an optional error. Provider content URLs
must never enter the script or asset engines. Successful copies retain original
names/extensions and remain readable after helper/dialog destruction and async
script or upload startup. Adapters preserve successful copies; only failed or
canceled request directories are eligible for cleanup.

Mobile adapters enforce a maximum of 32 documents, 256 MiB per document, and
512 MiB total while reading metadata and actual bytes, with all-or-nothing
selection. Main validates these limits again, checks single-selection requests,
and rejects non-local/unreadable files. Desktop QFileDialog paths retain their
existing direct-file behavior without copying limits. Busy requests, cancellation,
late callbacks, owner destruction, copy retention and boundary violations execute
in the host test. Native provider UI is deliberately replaced only at its adapter
callback; it must be tested separately on the actual Android/iOS artifact.

A mobile product without an installed adapter reports the unavailable picker.
The existence or absence of Java dialog classes does not establish Qt Android QPA
provider behavior: Qt5 also implements Android file dialogs through C++ JNI.
This slice does not claim that a guessed QPA content URL is readable by the engine.
Android/iOS adapters and product lifecycle hooks arrive through their owners and
the regular parent hierarchy. Generic local save remains available; this is not
an OS document export adapter. Current Script and Asset callers request one file.
External glTF/OBJ textures, companion files and directory grants are not qualified
as complete mobile multi-file import by this host contract.

## Required product evidence

A current full native app build must verify the additive Image API against the
real generated entity properties and platform dependencies. Test normal Scripts
and Assets entries on device: URL/file loading, restart/stop, model and image rez,
read-only browsing, permitted upload/mapping/rename/delete/baking, controller or
touch targeting, keyboard text/cancel, provider return/cancel after foreground
changes, stale callbacks, and retained local copies. Bind device results to the
exact app revision/artifact. Host success supplies no APK/IPA, OS provider,
filesystem entitlement, live networking, headset rendering or device proof.
