# Android snapshot export

`overte_target_snapshot(target)` adds the native Qt adapter. Apply `target.gradle`
with `ext.overteSnapshotRoot` pointing at this directory for Java/resources and
AndroidX Core 1.1.0 (already in the pinned WebKit dependency graph).
`Overte.Android 1.0 / NativeSnapshotAdapter` provides `capabilities`, `busy`,
`error`, `request(path, action)`, `cancel(ticket)` and
`completed(ticket, status, error)`. The Android-selected
`controls/SnapshotPlatformBackend.qml` exposes the shared application contract.

The native adapter uses the main-owned `SnapshotStorage.h` default root and
`exportPath(path)` validation; QML cannot change that root. Java independently
checks the same direct regular child under `Activity.getFilesDir()/Snapshots`.
Only existing PNG/JPEG/WebP/GIF files of 1 byte through 256 MiB are exported.
Traversal, symbolic links, nested children and external paths are rejected.

Each product supplies an immutable `SnapshotHost`, calls `initialize` after the
Qt/native library is ready, `foreground` after resume/window focus, and `detach`
on Activity destruction. Forward `onActivityResult` to `activityResult` before
other handlers. A return is held until the same Activity regains genuine focus;
instance, request and Activity generations prevent late return rebinding.
Pause alone does not cancel an intentional system chooser. Explicit cancellation
and Activity destruction revoke the active lease. Qt completions run on the
adapter's owner thread and ignore old tickets or destroyed instances.

Add these non-exported components inside each product application manifest:

```xml
<provider android:name="org.overte.snapshot.SnapshotFileProvider"
    android:authorities="${applicationId}.snapshot.files"
    android:exported="false" android:grantUriPermissions="true">
    <meta-data android:name="android.support.FILE_PROVIDER_PATHS"
        android:resource="@xml/overte_snapshot_paths" />
</provider>
<receiver android:name="org.overte.snapshot.SnapshotShareReceiver"
    android:exported="false" />
```

The provider grants only the selected original file beneath `files/Snapshots`.
Sharing uses ACTION_SEND, a content URI, ClipData and a narrow read grant. The
explicit chooser selection callback and return to the owning Activity establish
successful system handoff; this does not claim that the recipient saved a copy.
The original capture remains available. Cancellation is reported distinctly.

Saving on API 29+ writes a pending MediaStore image, flushes and closes its
stream, then checks publication succeeded before reporting success. Failed or
cancelled owned MediaStore rows are removed. Older supported Android versions
use ACTION_CREATE_DOCUMENT; success requires actual destination copying and
close. Failure of a user-selected document is reported without deleting a
potentially pre-existing user document. No storage permission, file URI, broad
filesystem grant or external browser is used.

Run `python3 android/common/snapshot/tests/run.py` for compiled portable file,
lease and stream behavior. `--native --qt-root ...` compiles the actual C++/moc,
QML wrapper and JNI against a real host JVM; only the OS export endpoint is an
explicit fixture. `--android-jar ... --core-jar ...` compiles every production
Java class against the real SDK and AndroidX artifacts. Before main propagation,
`--storage-include ...` may reference the owning parent header for isolated host
checks; production builds always use the in-tree main-owned header.

These checks do not establish APK packaging, provider configuration on an actual
phone, MediaStore behavior, chooser delivery ordering or device lifecycle
acceptance. Those require a complete source-bound product build and real device
Save/Share/cancel/failure tests.
