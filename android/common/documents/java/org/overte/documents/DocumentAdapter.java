// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;

import android.app.Activity;
import android.content.ClipData;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.os.CancellationSignal;
import android.provider.OpenableColumns;
import android.provider.DocumentsContract;
import org.overte.web.WebFilePickerState;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.LinkOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Content URLs remain native; successful complete app-owned copies outlive the picker. */
public final class DocumentAdapter {
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static final ExecutorService IO=Executors.newSingleThreadExecutor(task -> {
        Thread thread=new Thread(task,"OverteDocumentImport"); thread.setDaemon(true); return thread;
    });
    private static WeakReference<DocumentHost> host=new WeakReference<>(null);
    private static long generation;
    private static Request active;
    private static native void nativeInitialize();
    private static native void nativeCompleted(String request, String[] paths, String error);
    private DocumentAdapter() { }
    public static void initialize(DocumentHost owner) {
        MAIN.post(() -> {
            if (owner == null || owner.activity() == null || host.get() == owner) return;
            cancelActive(); if (generation == Long.MAX_VALUE) return;
            ++generation; host=new WeakReference<>(owner); nativeInitialize();
        });
    }
    public static void foreground(DocumentHost owner) {
        MAIN.post(() -> {
            if (host.get() != owner || active == null || !owner.isForeground()) return;
            Request request=active; request.picker.deliver(true); deliver(request);
        });
    }
    public static void detach(DocumentHost owner) {
        MAIN.post(() -> {
            if (host.get() != owner) return;
            cancelActive(); host.clear(); if (generation < Long.MAX_VALUE) ++generation;
        });
    }
    private static final class Request {
        final String id; final DocumentHost owner; final long generation;
        final File root; final boolean multiple, tree; final String filter;
        final ContentResolver resolver;
        final AtomicBoolean cancelled=new AtomicBoolean();
        final CancellationSignal cancellation=new CancellationSignal();
        final WebFilePickerState<Uri[]> picker=new WebFilePickerState<>();
        boolean finished; String[] paths; String error; Path directory;
        Request(String id, DocumentHost owner, File root, boolean multiple, String filter, boolean tree) {
            this.id=id; this.owner=owner; this.root=root; this.multiple=multiple; this.filter=filter; this.tree=tree;
            generation=DocumentAdapter.generation; resolver=owner.activity().getContentResolver();
        }
    }
    private static boolean current(Request request) {
        return active == request && request.owner == host.get() && request.generation == generation && !request.cancelled.get();
    }
    public static void request(String id, String root, String caption, String filter, boolean multiple) {
        request(id,root,caption,filter,multiple,false);
    }
    public static void requestTree(String id, String root, String caption) {
        request(id,root,caption,"",false,true);
    }
    private static void request(String id, String root, String caption, String filter, boolean multiple, boolean tree) {
        MAIN.post(() -> {
            DocumentHost owner=host.get();
            if (active != null || owner == null || !owner.isForeground() || owner.activity().isFinishing()) {
                nativeCompleted(id,new String[0],"Document selection needs an available foreground Activity."); return;
            }
            try {
                if (id == null || !id.matches("[a-zA-Z0-9-]{1,128}")) throw new IOException("Invalid document request.");
                File owned=new File(root).getCanonicalFile();
                if (!owned.equals(new File(owner.activity().getFilesDir(),"ImportedDocuments").getCanonicalFile())
                        || Files.isSymbolicLink(new File(root).toPath()) || !owned.isDirectory())
                    throw new IOException("The document import directory is unavailable.");
                Request request=new Request(id,owner,owned,multiple,filter,tree); active=request;
                int code=request.picker.begin(values -> {
                    if (!current(request) || request.finished) return;
                    if (values == null) finish(request,new String[0],"");
                    else IO.execute(() -> { if (request.tree) materializeTree(request,values[0]); else materialize(request,values); });
                });
                if (code == 0) throw new IOException("No document picker is available.");
                // Qt filters use file extensions; providers may advertise inconsistent MIME
                // types for scripts/models. Preserve broad native selection and exact names.
                Intent picker=tree ? new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
                    : new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                        .setType("*/*").putExtra(Intent.EXTRA_ALLOW_MULTIPLE,multiple);
                picker.putExtra(Intent.EXTRA_TITLE,caption == null ? "Select documents" : caption.substring(0,Math.min(256,caption.length())));
                owner.activity().startActivityForResult(picker,code);
            } catch (IOException | RuntimeException failure) {
                if (active != null && active.id.equals(id)) finish(active,new String[0],"The document picker could not be opened.");
                else nativeCompleted(id,new String[0],"The document picker could not be opened.");
            }
        });
    }
    public static void cancel(String id) { MAIN.post(() -> { if (active != null && active.id.equals(id)) cancelActive(); }); }
    private static void cancelActive() {
        Request request=active; if (request == null) return;
        active=null; request.cancelled.set(true); request.picker.cancel(); request.cancellation.cancel();
        nativeCompleted(request.id,new String[0],"");
        // The worker removes its own partial directory after observing cancellation.
        IO.execute(() -> remove(request.directory));
    }
    public static boolean activityResult(DocumentHost owner, int code, int result, Intent data) {
        Request request=active;
        if (host.get() != owner || request == null || !current(request) || !request.picker.owns(code)) return false;
        ArrayList<Uri> selected=new ArrayList<>(); String failure=null;
        if (result == Activity.RESULT_OK && data != null) {
            ClipData clips=data.getClipData(); int count=clips == null ? (data.getData() == null ? 0 : 1) : clips.getItemCount();
            if (count > DocumentCopy.MAX_DOCUMENTS || !request.multiple && count > 1)
                failure="Select at most 32 documents within the requested selection mode.";
            else for (int index=0; index<count; ++index) {
                Uri value=clips == null ? data.getData() : clips.getItemAt(index).getUri();
                if (value == null || !"content".equals(value.getScheme()) || value.getAuthority() == null
                        || request.tree && !DocumentsContract.isTreeUri(value)) {
                    failure="The document picker did not return readable provider documents."; break;
                }
                selected.add(value);
            }
        }
        if (failure != null) { finish(request,new String[0],failure); request.picker.receive(code,null,false); return true; }
        return request.picker.receive(code,selected.isEmpty() ? null : selected.toArray(new Uri[0]),false);
    }
    private static String name(Request request, Uri uri) throws IOException {
        try (Cursor cursor=request.resolver.query(uri,new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE},null,null,null,request.cancellation)) {
            if (cursor == null || !cursor.moveToFirst()) throw new DocumentCopy.Failure("The document provider returned no file metadata.");
            int size=cursor.getColumnIndex(OpenableColumns.SIZE), name=cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
            if (size >= 0 && !cursor.isNull(size) && cursor.getLong(size) > DocumentCopy.MAX_FILE)
                throw new DocumentCopy.Failure("A selected document exceeds 256 MiB.");
            String displayName=DocumentCopy.name(name < 0 || cursor.isNull(name) ? null : cursor.getString(name));
            if (!DocumentCopy.matchesFilter(displayName,request.filter))
                throw new DocumentCopy.Failure("Select a document with a supported file extension.");
            return displayName;
        }
    }
    private static void materialize(Request request, Uri[] selected) {
        Path directory=null; boolean succeeded=false;
        try {
            if (request.cancelled.get()) return;
            directory=Files.createTempDirectory(request.root.toPath(),"selection-"); request.directory=directory;
            ArrayList<String> names=new ArrayList<>();
            for (Uri uri:selected) {
                if (request.cancelled.get()) throw new DocumentCopy.Failure("Document selection was cancelled.");
                names.add(name(request,uri));
            }
            java.util.List<Path> destinations=DocumentCopy.destinations(directory,names);
            ArrayList<String> paths=new ArrayList<>(); long total=0;
            for (int index=0; index<selected.length; ++index) {
                if (request.cancelled.get()) throw new IOException("Document selection was cancelled.");
                // Unique names remain siblings; duplicate names never overwrite each other.
                Path destination=destinations.get(index);
                try (InputStream input=input(request,selected[index])) {
                    total += DocumentCopy.copy(input,Files.newOutputStream(destination,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE,
                        LinkOption.NOFOLLOW_LINKS),DocumentCopy.MAX_TOTAL-total,request.cancelled::get);
                }
                paths.add(destination.toFile().getCanonicalPath());
            }
            if (request.cancelled.get()) throw new IOException("Document selection was cancelled.");
            succeeded=true; finish(request,paths.toArray(new String[0]),"");
        } catch (DocumentCopy.Failure failure) { finish(request,new String[0],failure.getMessage()); }
        catch (IOException | RuntimeException failure) { finish(request,new String[0],"The selected documents could not be read and retained."); }
        finally { if (!succeeded || request.cancelled.get()) remove(directory); }
    }
    private static void materializeTree(Request request, Uri tree) {
        Path directory=null; boolean succeeded=false;
        try {
            if (request.cancelled.get()) return;
            String rootId=DocumentsContract.getTreeDocumentId(tree);
            Uri rootUri=DocumentsContract.buildDocumentUriUsingTree(tree,rootId);
            String rootName;
            try (Cursor cursor=request.resolver.query(rootUri,new String[]{DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                    DocumentsContract.Document.COLUMN_MIME_TYPE},null,null,null,request.cancellation)) {
                if (cursor == null || !cursor.moveToFirst() || !DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(1)))
                    throw new DocumentCopy.Failure("The provider did not return a readable directory.");
                rootName=DocumentCopy.name(cursor.getString(0));
            }
            directory=Files.createTempDirectory(request.root.toPath(),"selection-"); request.directory=directory;
            Path destination=Files.createDirectory(directory.resolve(rootName));
            DocumentTree.copy(new DocumentTree.Source() {
                public java.util.List<DocumentTree.Node> children(String id, int maximum) throws IOException {
                    Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,id);
                    ArrayList<DocumentTree.Node> result=new ArrayList<>();
                    try (Cursor cursor=request.resolver.query(children,new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                            DocumentsContract.Document.COLUMN_DISPLAY_NAME,DocumentsContract.Document.COLUMN_MIME_TYPE,
                            DocumentsContract.Document.COLUMN_SIZE,DocumentsContract.Document.COLUMN_FLAGS},null,null,null,request.cancellation)) {
                        if (cursor == null) throw new DocumentCopy.Failure("The provider directory could not be enumerated.");
                        while (cursor.moveToNext()) {
                            if (request.cancelled.get()) throw new DocumentCopy.Failure("Document selection was cancelled.");
                            if (result.size() >= maximum)
                                throw new DocumentCopy.Failure("The selected directory exceeds 1024 entries.");
                            if (!cursor.isNull(4) && (cursor.getLong(4) & DocumentsContract.Document.FLAG_VIRTUAL_DOCUMENT) != 0)
                                throw new DocumentCopy.Failure("Virtual documents cannot be retained as regular files.");
                            result.add(new DocumentTree.Node(cursor.getString(0),cursor.getString(1),
                                DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(2)),cursor.isNull(3) ? -1 : cursor.getLong(3)));
                        }
                    }
                    return result;
                }
                public InputStream open(String id) throws IOException {
                    return input(request,DocumentsContract.buildDocumentUriUsingTree(tree,id));
                }
            },rootId,destination,request.cancelled::get);
            succeeded=true; finish(request,new String[]{destination.toFile().getCanonicalPath()},"");
        } catch (DocumentCopy.Failure failure) { finish(request,new String[0],failure.getMessage()); }
        catch (IOException | RuntimeException failure) { finish(request,new String[0],"The selected directory could not be read and retained."); }
        finally { if (!succeeded || request.cancelled.get()) remove(directory); }
    }
    private static InputStream input(Request request, Uri uri) throws IOException {
        AssetFileDescriptor descriptor=request.resolver.openAssetFileDescriptor(uri,"r",request.cancellation);
        if (descriptor == null) throw new DocumentCopy.Failure("The selected document could not be opened.");
        try { return descriptor.createInputStream(); }
        catch (IOException | RuntimeException failure) { descriptor.close(); throw failure; }
    }
    private static void remove(Path directory) {
        if (directory == null) return;
        try (java.util.stream.Stream<Path> paths=Files.walk(directory)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> { try { Files.deleteIfExists(path); } catch (IOException ignored) { } });
        } catch (IOException ignored) { /* No provider URLs or private paths are logged. */ }
    }
    private static void finish(Request request, String[] paths, String error) {
        MAIN.post(() -> {
            if (!current(request)) { if (paths.length > 0) IO.execute(() -> remove(request.directory)); return; }
            request.finished=true; request.paths=paths; request.error=error == null ? "The document selection failed." : error;
            deliver(request);
        });
    }
    private static void deliver(Request request) {
        if (!current(request) || !request.finished || !request.owner.isForeground()) return;
        active=null; nativeCompleted(request.id,request.paths,request.error);
    }
}
