// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.function.BooleanSupplier;

/** Provider metadata is advisory: count actual bytes and close before success. */
final class DocumentCopy {
    static final class Failure extends IOException { Failure(String message) { super(message); } }
    static final int MAX_DOCUMENTS = 32;
    static final long MAX_FILE = 256L * 1024 * 1024, MAX_TOTAL = 512L * 1024 * 1024;
    static String name(String value) throws IOException {
        if (value == null || value.isEmpty() || value.equals(".") || value.equals("..")
                || value.indexOf('/') >= 0 || value.indexOf('\\') >= 0
                || value.getBytes(StandardCharsets.UTF_8).length > 255)
            throw new Failure("The document provider returned an unusable file name.");
        for (int index=0; index<value.length(); ++index) {
            if (Character.isISOControl(value.charAt(index)))
                throw new Failure("The document provider returned an unusable file name.");
        }
        return value;
    }
    static boolean matchesFilter(String name, String filter) {
        if (filter == null || filter.isEmpty() || filter.contains("(*)") || filter.contains("*.*")) return true;
        java.util.regex.Matcher patterns=java.util.regex.Pattern.compile("\\*\\.([a-zA-Z0-9_.+-]+)").matcher(filter);
        String lower=name.toLowerCase(java.util.Locale.ROOT); boolean specified=false;
        while(patterns.find()) { specified=true; if(lower.endsWith("."+patterns.group(1).toLowerCase(java.util.Locale.ROOT))) return true; }
        return !specified;
    }
    static java.util.List<java.nio.file.Path> destinations(java.nio.file.Path directory, java.util.List<String> names) throws IOException {
        if (names.size() > MAX_DOCUMENTS) throw new Failure("Select at most 32 documents.");
        java.util.Map<String,Integer> frequencies=new java.util.HashMap<>();
        for (String value:names) frequencies.merge(name(value),1,Integer::sum);
        java.util.ArrayList<java.nio.file.Path> result=new java.util.ArrayList<>();
        for (String value:names) {
            java.nio.file.Path parent=directory;
            if (frequencies.get(value) > 1) {
                do {
                    parent=java.nio.file.Files.createTempDirectory(directory,"duplicate-");
                    if (!frequencies.containsKey(parent.getFileName().toString())) break;
                    java.nio.file.Files.delete(parent);
                } while (true);
            }
            result.add(parent.resolve(value));
        }
        return result;
    }
    static long copy(InputStream input, OutputStream output, long remaining, BooleanSupplier cancelled) throws IOException {
        try (InputStream source=input; OutputStream destination=output) {
            if (source == null || destination == null) throw new Failure("The selected document could not be opened.");
            byte[] buffer=new byte[65536]; long total=0; int count;
            while ((count=source.read(buffer)) != -1) {
                total += count;
                if (total > MAX_FILE || total > remaining)
                    throw new Failure("Selected documents exceed 256 MiB per file or 512 MiB in total.");
                if (cancelled.getAsBoolean()) throw new Failure("Document selection was cancelled.");
                destination.write(buffer,0,count);
            }
            if (cancelled.getAsBoolean()) throw new Failure("Document selection was cancelled.");
            destination.flush(); return total;
        }
    }
}
