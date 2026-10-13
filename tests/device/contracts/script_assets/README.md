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

The ordinary Application::loadDialog body and FileDialogListener execute with the
production TabletFileDialog, including main-file review, cancellation and expired
Application owner. The production ScriptManager::resolvePath resolves an actual
relative JavaScript include; Qt's JavaScript engine reads and evaluates both files.
This host adapter does not qualify Overte's full V8 engine, script consent or session.

The complete production uploadBundle implementation and AssetUpload execute through
QML, reading and hashing real files. An explicit asynchronous server peer receives
the uploaded bytes and materializes mappings in a temporary directory. Tests verify
valid glTF triangle buffer bytes, actual PNG decode, OBJ/MTL texture relationships,
main-last publication, errors, permission revocation, cancellation and page destruction.
This peer is a network boundary, not a live asset server or rendered-model qualification.
The single-file upload route and its existing destination/overwrite dialog remain
available separately. The Image and Model APIs' actual header declarations, complete
implementations and grabbable constants compile and execute through QML. Entity property storage, vector representation, session
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
an OS document export adapter.

## Main file and companion files

Normal script loading reviews a main JavaScript file and selected companions, then
passes the main local URL to the existing ScriptEngines load/consent route. Users
can select files across local subdirectories or choose a system folder. Folder
selection uses the additive DocumentTreePickerOperator, separate setter/cancel and
openDocumentTree(caption); the file operator ABI is unchanged. A tree completion
returns exactly one durable local directory URL. Platform adapters preserve original
names, hierarchy, hidden and empty directories and reject the whole selection on
copy errors or cancellation. Main checks actual files again: at most 32 files,
256 MiB per file, 512 MiB total, 1024 entries including directories and 16 relative
components including filename (root excluded), with no symbolic links or escapes.
No large second copy runs in the QML thread.

Asset bundle review chooses the main file and a destination root. The batch validates
unchanged relative names/root, uploads all bytes, and uses the existing SetMappingRequest
for companions before the main mapping. Write permission remains mandatory and is
checked before every operation. A known destination collision stops the batch;
concurrent server changes remain server-authoritative. Cancel and mapping failure
report the actual count of published mappings and stop further operations after an
in-flight request settles; this protocol provides no atomic rollback. Successful
local provider copies stay owned by the platform adapter for later script execution
and asynchronous uploads. The Add uploaded model action uses the existing rez path.
Read-only asset browse/import and rename/delete/mapping/baking remain available.

The focused test_obj_material_bundle.py compiles and executes the complete production
OBJSerializer::read, tokenizer, geometry/group, face, MTL and requestData bodies. Real
GLM and the production HFM Texture/Material/MeshPart value declarations are used;
GPU material setters, unrelated transform/sampler fields and model storage remain
explicit host boundaries. The produced HFM texture passes through the actual
NetworkMaterial::getTextureUrl body and its requested PNG bytes decode with Qt.
ATP/local paths, multiple MTL bases, all supported MTL texture fields, missing libraries
and the existing flattened-export fallback execute against an asynchronous local
ResourceManager provider boundary. Relative HFM filenames retain the explicit FST
texdir/textureBaseURL override; explicit external references retain their origin. This does not qualify GPU drawing or a live server.
Set OVERTE_TEST_GLM_INCLUDE to real GLM headers when they are not installed systemwide.

The standalone test_document_tree_abi.py executes the production Qt helper and
Offscreen bundle route with real files, separate tree/file operators, foreign-thread
completion, stale callbacks and owner destruction on Qt5/Qt6. Actual Android/iOS
folder grants, copying and provider UI remain separate platform/device evidence.

## Required product evidence

A current full native app build must verify the additive Image API against the
real generated entity properties and platform dependencies. Test normal Scripts
and Assets entries on device: URL/file loading, restart/stop, model and image rez,
read-only browsing, permitted upload/mapping/rename/delete/baking, controller or
touch targeting, keyboard text/cancel, provider return/cancel after foreground
changes, stale callbacks, and retained local copies. Bind device results to the
exact app revision/artifact. Host success supplies no APK/IPA, OS provider,
filesystem entitlement, live networking, headset rendering or device proof.
