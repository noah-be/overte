// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.BooleanSupplier;

/** Copy a bounded provider hierarchy; only app-owned regular paths escape this boundary. */
final class DocumentTree {
    static final int MAX_NODES = 1024, MAX_DEPTH = 16;
    static final class Node {
        final String id, name; final boolean directory; final long size;
        Node(String id, String name, boolean directory, long size) {
            this.id=id; this.name=name; this.directory=directory; this.size=size;
        }
    }
    interface Source {
        List<Node> children(String directory, int maximum) throws IOException;
        InputStream open(String document) throws IOException;
    }
    private final Source source;
    private final BooleanSupplier cancelled;
    private final Set<String> visited=new HashSet<>();
    private int nodes, files;
    private long total;
    private DocumentTree(Source source, BooleanSupplier cancelled) { this.source=source; this.cancelled=cancelled; }
    static void copy(Source source, String rootId, Path destination, BooleanSupplier cancelled) throws IOException {
        if (source == null || rootId == null || rootId.isEmpty() || Files.isSymbolicLink(destination)
                || !Files.isDirectory(destination,LinkOption.NOFOLLOW_LINKS))
            throw new DocumentCopy.Failure("The selected document directory is unavailable.");
        DocumentTree operation=new DocumentTree(source,cancelled);
        operation.visited.add(rootId);
        operation.directory(rootId,destination,0);
    }
    private void directory(String id, Path parent, int depth) throws IOException {
        check();
        if (depth > MAX_DEPTH) throw new DocumentCopy.Failure("The selected directory exceeds 16 relative path components.");
        List<Node> children=source.children(id,MAX_NODES-nodes);
        if (children == null || children.size() > MAX_NODES-nodes)
            throw new DocumentCopy.Failure("The selected directory exceeds 1024 entries.");
        nodes += children.size();
        Set<String> names=new HashSet<>();
        for (Node node:children) {
            check();
            if (node == null || node.id == null || node.id.isEmpty() || !visited.add(node.id)
                    || !names.add(DocumentCopy.name(node.name)))
                throw new DocumentCopy.Failure("The document provider returned an ambiguous directory.");
            if (depth+1 > MAX_DEPTH) throw new DocumentCopy.Failure("The selected directory exceeds 16 relative path components.");
            Path path=parent.resolve(node.name);
            if (path.toString().length() > 4096) throw new DocumentCopy.Failure("The selected directory contains an excessively long path.");
            if (node.directory) {
                Files.createDirectory(path);
                directory(node.id,path,depth+1);
            } else {
                if (++files > DocumentCopy.MAX_DOCUMENTS || node.size > DocumentCopy.MAX_FILE)
                    throw new DocumentCopy.Failure("Select a directory with at most 32 files of at most 256 MiB each.");
                try (InputStream input=source.open(node.id)) {
                    total += DocumentCopy.copy(input,Files.newOutputStream(path,StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS),DocumentCopy.MAX_TOTAL-total,cancelled);
                }
            }
        }
        check();
    }
    private void check() throws IOException {
        if (cancelled.getAsBoolean()) throw new DocumentCopy.Failure("Document selection was cancelled.");
    }
}
