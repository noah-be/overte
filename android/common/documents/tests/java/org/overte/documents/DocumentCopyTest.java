// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;
import java.io.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class DocumentCopyTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    private static void denied(String name) throws Exception {
        boolean failed=false; try { DocumentCopy.name(name); } catch(IOException expected) { failed=true; } check(failed);
    }
    public static void main(String[] args) throws Exception {
        check(DocumentCopy.MAX_DOCUMENTS==32 && DocumentCopy.MAX_FILE==268435456 && DocumentCopy.MAX_TOTAL==536870912);
        for(String name : new String[]{"User script #?.js","模型.glb","space name.FBX","duplicate.png"})
            check(DocumentCopy.name(name).equals(name));
        for(String name : new String[]{"", ".", "..", "../escape.js", "folder/file.js", "folder\\file.js", "bad\n.js", "x".repeat(256)}) denied(name);
        denied(null); denied("模型".repeat(86));
        check(DocumentCopy.matchesFilter("Mixed.GLB","Models (*.gltf *.glb *.fbx)"));
        check(!DocumentCopy.matchesFilter("bad.js","Models (*.gltf *.glb *.fbx)"));
        check(DocumentCopy.matchesFilter("actual.txt","All files (*)"));
        check(DocumentCopy.matchesFilter("archive.TAR.GZ","Archives (*.tar.gz)"));
        java.nio.file.Path folder=java.nio.file.Files.createTempDirectory("document-layout-");
        try {
            java.util.List<java.nio.file.Path> unique=DocumentCopy.destinations(folder,java.util.List.of("scene.gltf","mesh.bin","texture.png"));
            for (java.nio.file.Path file:unique) check(file.getParent().equals(folder));
            java.util.List<java.nio.file.Path> duplicates=DocumentCopy.destinations(folder,java.util.List.of("scene.gltf","same.png","same.png"));
            check(duplicates.get(0).getParent().equals(folder));
            check(!duplicates.get(1).equals(duplicates.get(2)) && !duplicates.get(1).getParent().equals(folder));
            check(duplicates.get(1).getFileName().toString().equals("same.png") && duplicates.get(2).getFileName().toString().equals("same.png"));
            java.nio.file.Files.delete(duplicates.get(1).getParent());java.nio.file.Files.delete(duplicates.get(2).getParent());
        } finally { java.nio.file.Files.delete(folder); }
        final boolean[] closed={false}; ByteArrayOutputStream output=new ByteArrayOutputStream() {
            @Override public void close() { closed[0]=true; }
        };
        check(DocumentCopy.copy(new ByteArrayInputStream(new byte[]{1,2,3}),output,3,()->false)==3);
        check(closed[0] && java.util.Arrays.equals(output.toByteArray(),new byte[]{1,2,3}));
        check(DocumentCopy.copy(new ByteArrayInputStream(new byte[0]),new ByteArrayOutputStream(),0,()->false)==0);
        boolean failed=false;
        try { DocumentCopy.copy(new ByteArrayInputStream(new byte[]{1,2,3}),new ByteArrayOutputStream(),2,()->false); }
        catch(DocumentCopy.Failure expected) { failed=true; } check(failed);
        failed=false;
        try { DocumentCopy.copy(new ByteArrayInputStream(new byte[]{1}),new ByteArrayOutputStream(),1,()->true); }
        catch(DocumentCopy.Failure expected) { failed=true; } check(failed);
        failed=false;
        try { DocumentCopy.copy(new ByteArrayInputStream(new byte[]{1}),new OutputStream() {
            @Override public void write(int value) throws IOException { throw new IOException("write"); }
        },1,()->false); } catch(IOException expected) { failed=true; } check(failed);
        failed=false;
        try { DocumentCopy.copy(new ByteArrayInputStream(new byte[]{1}),new ByteArrayOutputStream() {
            @Override public void close() throws IOException { throw new IOException("close"); }
        },1,()->false); } catch(IOException expected) { failed=true; } check(failed);
        InputStream large=new InputStream() {
            long remaining=DocumentCopy.MAX_FILE+1;
            @Override public int read() { if(remaining-- > 0) return 1; return -1; }
            @Override public int read(byte[] buffer) {
                if(remaining<=0) return -1; int count=(int)Math.min(remaining,buffer.length); remaining-=count; return count;
            }
        };
        failed=false;
        try { DocumentCopy.copy(large,OutputStream.nullOutputStream(),DocumentCopy.MAX_TOTAL,()->false); }
        catch(DocumentCopy.Failure expected) { failed=true; } check(failed);
        AtomicBoolean revoked=new AtomicBoolean(); failed=false;
        try { DocumentCopy.copy(new ByteArrayInputStream(new byte[]{1}),new OutputStream() {
            @Override public void write(int value) { revoked.set(true); }
        },1,revoked::get); } catch(DocumentCopy.Failure expected) { failed=true; } check(failed);
        System.out.println("PASS: actual document name preservation, byte limits, complete stream close, empty documents, cancellation and write failures");
    }
}
