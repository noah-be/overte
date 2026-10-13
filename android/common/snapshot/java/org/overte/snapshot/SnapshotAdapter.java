// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.ClipData;
import android.content.ComponentName;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import androidx.core.content.FileProvider;
import org.overte.web.WebFilePickerState;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Actual Android export operations; a launch is never treated as completed saving. */
public final class SnapshotAdapter {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ExecutorService IO = Executors.newSingleThreadExecutor(task -> {
        Thread thread = new Thread(task, "OverteSnapshotExport"); thread.setDaemon(true); return thread;
    });
    private static WeakReference<SnapshotHost> host = new WeakReference<>(null);
    private static long generation;
    private static Request active;
    private static final String CHOSEN = "org.overte.snapshot.CHOSEN";
    private static native void nativeInitialize();
    private static native void nativeCompleted(long handle, long ticket, String status, String error);
    private SnapshotAdapter() { }

    public static void initialize(SnapshotHost owner) {
        MAIN.post(() -> {
            if (owner == null || owner.activity() == null || host.get() == owner) return;
            cancelActive();
            if (generation == Long.MAX_VALUE) return;
            ++generation; host = new WeakReference<>(owner); nativeInitialize();
        });
    }
    public static void foreground(SnapshotHost owner) {
        MAIN.post(() -> {
            if (host.get() != owner || active == null || !owner.isForeground()) return;
            Request request = active;
            request.picker.deliver(true);
            deliver(request);
        });
    }
    public static void detach(SnapshotHost owner) {
        MAIN.post(() -> {
            if (host.get() != owner) return;
            cancelActive(); host.clear();
            if (generation < Long.MAX_VALUE) ++generation;
        });
    }
    public static void request(long handle, long ticket, String root, String path, String action) {
        MAIN.post(() -> {
            SnapshotHost owner = host.get();
            if (active != null || owner == null || !owner.isForeground() || owner.activity().isFinishing()) {
                nativeCompleted(handle, ticket, "error", "Snapshot export is unavailable while another operation or Activity is active."); return;
            }
            try {
                File file = SnapshotFilePolicy.validate(root, path);
                File platformRoot = new File(owner.activity().getFilesDir(), "Snapshots").getCanonicalFile();
                if (!platformRoot.equals(new File(root).getCanonicalFile())) throw new IOException("Unknown snapshot root");
                if (!"save".equals(action) && !"share".equals(action)) throw new IOException("Unknown action");
                Request pending = new Request(handle, ticket, generation, owner, file, root, action);
                active = pending;
                if ("share".equals(action)) share(pending);
                else if (Build.VERSION.SDK_INT >= 29) IO.execute(() -> saveMediaStore(pending));
                else saveDocument(pending);
            } catch (IOException | RuntimeException failure) {
                if (active != null && active.lease.handle == handle && active.lease.ticket == ticket)
                    finish(active, "error", "The snapshot could not be exported.");
                else nativeCompleted(handle, ticket, "error", "The snapshot could not be exported.");
            }
        });
    }
    public static void cancel(long handle, long ticket) {
        MAIN.post(() -> {
            if (active != null && active.lease.handle == handle && active.lease.ticket == ticket) cancelActive();
        });
    }
    private static boolean current(Request request) {
        return active == request && request.lease.accepts(request.lease.handle, request.lease.ticket, generation, host.get());
    }
    private static void cancelActive() {
        Request request = active;
        if (request == null) return;
        active = null;
        if (!request.lease.abort(request.lease.handle, request.lease.ticket, request.lease.generation, request.owner)) return;
        request.picker.cancel();
        if (request.chosenCallback != null) request.chosenCallback.cancel();
        nativeCompleted(request.lease.handle, request.lease.ticket, "cancelled", "");
    }
    private static void finish(Request request, String status, String error) {
        MAIN.post(() -> {
            if (!current(request)) return;
            request.status = status; request.error = error; deliver(request);
        });
    }
    private static void deliver(Request request) {
        if (!current(request) || request.status == null || !request.owner.isForeground()) return;
        if (!request.lease.close(request.lease.handle, request.lease.ticket, generation, host.get())) return;
        active = null;
        if (request.chosenCallback != null) request.chosenCallback.cancel();
        nativeCompleted(request.lease.handle, request.lease.ticket, request.status, request.error);
    }
    private static final class Request {
        final SnapshotLease lease;
        final SnapshotHost owner;
        final File file;
        final String root, action;
        final ContentResolver resolver;
        final WebFilePickerState<Uri> picker = new WebFilePickerState<>();
        PendingIntent chosenCallback;
        boolean chosen;
        String status, error;
        Request(long handle, long ticket, long generation, SnapshotHost owner, File file, String root, String action) {
            lease = new SnapshotLease(handle, ticket, generation, owner); this.owner = owner;
            this.file = file; this.root = root; this.action = action; resolver = owner.activity().getContentResolver();
        }
    }
    private static int picker(Request request) throws IOException {
        int code = request.picker.begin(uri -> {
            if (!current(request)) return;
            if ("share".equals(request.action)) MAIN.post(() -> finish(request, request.chosen ? "success" : "cancelled", ""));
            else if (uri == null) finish(request, "cancelled", "");
            else IO.execute(() -> saveUri(request, uri));
        });
        if (code == 0) throw new IOException("Picker unavailable");
        return code;
    }
    private static void saveDocument(Request request) throws IOException {
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
            .setType(SnapshotFilePolicy.mime(request.file)).putExtra(Intent.EXTRA_TITLE, request.file.getName());
        request.owner.activity().startActivityForResult(intent, picker(request));
    }
    private static void share(Request request) throws IOException {
        Activity activity = request.owner.activity();
        Uri uri = FileProvider.getUriForFile(activity, activity.getPackageName() + ".snapshot.files", request.file);
        if (!"content".equals(uri.getScheme())) throw new IOException("Provider unavailable");
        Intent send = new Intent(Intent.ACTION_SEND).setType(SnapshotFilePolicy.mime(request.file))
            .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        send.setClipData(ClipData.newUri(request.resolver, "Snapshot", uri));
        int code = picker(request);
        Intent selected = new Intent(activity, SnapshotShareReceiver.class).setAction(CHOSEN)
            .putExtra("handle", request.lease.handle).putExtra("ticket", request.lease.ticket)
            .putExtra("generation", request.lease.generation);
        int flags = PendingIntent.FLAG_CANCEL_CURRENT | PendingIntent.FLAG_ONE_SHOT;
        if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
        request.chosenCallback = PendingIntent.getBroadcast(activity, code, selected, flags);
        Intent chooser = Intent.createChooser(send, "Share snapshot", request.chosenCallback.getIntentSender());
        chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); chooser.setClipData(send.getClipData());
        activity.startActivityForResult(chooser, code);
    }
    static void shareChosen(Context context, Intent intent) {
        MAIN.post(() -> {
            Request request = active;
            if (request == null || !current(request) || !"share".equals(request.action) || intent == null
                    || !CHOSEN.equals(intent.getAction()) || !context.getPackageName().equals(request.owner.activity().getPackageName())
                    || intent.getLongExtra("handle", 0) != request.lease.handle
                    || intent.getLongExtra("ticket", 0) != request.lease.ticket
                    || intent.getLongExtra("generation", 0) != request.lease.generation) return;
            Object component = intent.getParcelableExtra(Intent.EXTRA_CHOSEN_COMPONENT);
            if (component instanceof ComponentName) request.chosen = true;
        });
    }
    public static boolean activityResult(SnapshotHost owner, int requestCode, int resultCode, Intent data) {
        Request request = active;
        if (host.get() != owner || request == null || !current(request) || !request.picker.owns(requestCode)) return false;
        Uri selected = resultCode == Activity.RESULT_OK && data != null ? data.getData() : null;
        if (selected != null && (!"content".equals(selected.getScheme()) || selected.getAuthority() == null)) selected = null;
        // Android returns before actual Activity/window-focus restoration; never rebind the callback.
        return request.picker.receive(requestCode, selected, false);
    }
    private static void copy(Request request, Uri uri) throws IOException {
        SnapshotFilePolicy.validate(request.root, request.file.getPath());
        try (InputStream input = Files.newInputStream(request.file.toPath(), StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            SnapshotCopy.copy(input, request.resolver.openOutputStream(uri, "w"), request.lease::cancelled);
        }
    }
    private static void saveUri(Request request, Uri uri) {
        try { copy(request, uri); finish(request, "success", ""); }
        catch (IOException | RuntimeException failure) { finish(request, "error", "The snapshot could not be saved."); }
    }
    private static void saveMediaStore(Request request) {
        Uri uri = null; boolean published = false;
        try {
            if (request.lease.cancelled()) return;
            ContentValues values = new ContentValues();
            values.put(MediaStore.Images.Media.DISPLAY_NAME, request.file.getName());
            values.put(MediaStore.Images.Media.MIME_TYPE, SnapshotFilePolicy.mime(request.file));
            values.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/Overte");
            values.put(MediaStore.Images.Media.IS_PENDING, 1);
            uri = request.resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new IOException("MediaStore unavailable");
            copy(request, uri);
            if (request.lease.cancelled()) throw new IOException("Cancelled export");
            values.clear(); values.put(MediaStore.Images.Media.IS_PENDING, 0);
            if (request.resolver.update(uri, values, null, null) != 1) throw new IOException("Publish failed");
            published = true; finish(request, "success", "");
        } catch (IOException | RuntimeException failure) {
            finish(request, "error", "The snapshot could not be saved.");
        } finally {
            if (uri != null && (!published || request.lease.cancelled())) {
                try { request.resolver.delete(uri, null, null); } catch (RuntimeException ignored) { /* No paths or destination URIs are logged. */ }
            }
        }
    }
}
