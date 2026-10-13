// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class DocumentTreeTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    private static class Source implements DocumentTree.Source {
        final Map<String,List<DocumentTree.Node>> children=new HashMap<>();
        final Map<String,byte[]> content=new HashMap<>();
        public List<DocumentTree.Node> children(String id,int maximum) { return children.getOrDefault(id,List.of()); }
        public InputStream open(String id) { return new ByteArrayInputStream(content.getOrDefault(id,new byte[0])); }
    }
    private static DocumentTree.Node node(String id,String name,boolean directory) {
        return new DocumentTree.Node(id,name,directory,0);
    }
    private static void denied(Source source,AtomicBoolean cancelled) throws Exception {
        Path destination=Files.createTempDirectory("document-tree-denied-");
        try {
            boolean failed=false;
            try { DocumentTree.copy(source,"root",destination,cancelled::get); }
            catch(IOException expected) { failed=true; }
            check(failed);
        } finally { remove(destination); }
    }
    private static void remove(Path destination) throws IOException {
        try (java.util.stream.Stream<Path> entries=Files.walk(destination)) {
            for(Path path:entries.sorted(Comparator.reverseOrder()).toArray(Path[]::new)) Files.delete(path);
        }
    }
    public static void main(String[] args) throws Exception {
        Source source=new Source();
        source.children.put("root",List.of(node("model","scene.gltf",false),node("textures","textures",true)));
        source.children.put("textures",List.of(node("texture","模型.png",false)));
        source.content.put("model","{\"uri\":\"textures/模型.png\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        source.content.put("texture",new byte[]{1,2,3});
        Path destination=Files.createTempDirectory("document-tree-retained-");
        try {
            DocumentTree.copy(source,"root",destination,()->false);
            check(Files.readString(destination.resolve("scene.gltf")).contains("textures/模型.png"));
            check(Arrays.equals(Files.readAllBytes(destination.resolve("textures/模型.png")),new byte[]{1,2,3}));
            check(!Files.isSymbolicLink(destination.resolve("textures/模型.png")));
        } finally { remove(destination); }
        Source invalid=new Source();
        invalid.children.put("root",List.of(node("escape","../escape",false)));denied(invalid,new AtomicBoolean());
        invalid.children.put("root",List.of(node("one","same",false),node("two","same",false)));denied(invalid,new AtomicBoolean());
        invalid.children.put("root",List.of(node("root","cycle",true)));denied(invalid,new AtomicBoolean());
        invalid.children.put("root",List.of(new DocumentTree.Node("huge","large.bin",false,DocumentCopy.MAX_FILE+1)));
        denied(invalid,new AtomicBoolean());
        List<DocumentTree.Node> many=new ArrayList<>();for(int i=0;i<33;++i) many.add(node("id"+i,"file"+i,false));
        invalid.children.put("root",many);denied(invalid,new AtomicBoolean());
        many=new ArrayList<>();for(int i=0;i<1025;++i) many.add(node("dir"+i,"folder"+i,true));
        invalid.children.put("root",many);denied(invalid,new AtomicBoolean());
        Source deep=new Source();String id="root";
        for(int i=0;i<17;++i) { deep.children.put(id,List.of(node("level"+i,"folder",true)));id="level"+i; }
        denied(deep,new AtomicBoolean());
        Source limit=new Source();id="root";
        for(int i=0;i<15;++i) { limit.children.put(id,List.of(node("component"+i,"folder",true)));id="component"+i; }
        limit.children.put(id,List.of(node("leaf","model.gltf",false)));
        destination=Files.createTempDirectory("document-tree-depth-limit-");
        try { DocumentTree.copy(limit,"root",destination,()->false); }
        finally { remove(destination); }
        limit.children.put(id,List.of(node("component16","folder",true)));
        limit.children.put("component16",List.of(node("leaf","model.gltf",false)));denied(limit,new AtomicBoolean());
        denied(source,new AtomicBoolean(true));
        AtomicBoolean cancelled=new AtomicBoolean();
        Source duringCopy=new Source() {
            @Override public InputStream open(String id) { cancelled.set(true); return new ByteArrayInputStream(new byte[]{1}); }
        };
        duringCopy.children.put("root",List.of(node("one","file",false)));denied(duringCopy,cancelled);
        System.out.println("PASS: actual retained hierarchy and relative model references; traversal, duplicate names, cycles, depth, enumeration, file limits and cancellation rejection");
    }
}
