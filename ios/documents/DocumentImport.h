// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSet>
#include <QUrl>
#include <QUuid>
#include <atomic>
#include <algorithm>
#include <functional>
#include <filesystem>

namespace overte::ios {
// Used by the coordinated native provider reader. Never grants provider or
// security-scoped URLs to the script engine; only complete durable local files.
class DocumentImport {
public:
    // Synchronous only: native coordination owns the read until consume returns.
    using ReadFile=std::function<bool(const QString&,const std::function<bool(QIODevice&)>&,QString&)>;
    static constexpr int MAX_COUNT=32;
    static constexpr int MAX_ENTRIES=1024, MAX_DEPTH=16;
    static constexpr qint64 MAX_FILE=256LL*1024*1024, MAX_TOTAL=512LL*1024*1024;
    explicit DocumentImport(const QString& nativeRoot) :
        _directory(QDir(nativeRoot).filePath("selection-"+QUuid::createUuid().toString(QUuid::WithoutBraces))) {}
    ~DocumentImport() { if(_state.load()!=Committed) { rollback(); } }
    void cancel() { unsigned active=Active;_state.compare_exchange_strong(active,Cancelled); }
    bool cancelled() const { return _state.load()==Cancelled; }
    bool commit() { unsigned active=Active;return _state.compare_exchange_strong(active,Committed); }
    const QList<QUrl>& urls() const { return _urls; }
    QString directory() const { return _directory; }
    void rollback() { if(QFileInfo(_directory).isDir() && !QFileInfo(_directory).isSymLink()) { QDir(_directory).removeRecursively(); } }
    bool copy(QIODevice& source,const QString& name,QString& error) {
        if(_state.load()!=Active) { return false; }
        if(_urls.size()>=MAX_COUNT) { error="The selection exceeds the 32-file import limit.";return false; }
        if(!safeName(name)) {
            error="The document provider returned an unsafe file name.";return false;
        }
        const auto root=QFileInfo(QFileInfo(_directory).absolutePath());
        if(root.isSymLink() || (!root.exists() && !QDir().mkpath(root.absoluteFilePath())) ||
            !QDir().mkpath(_directory) || QFileInfo(_directory).isSymLink()) {
            error="The imported-document storage could not be created.";return false;
        }
        QString parent=_directory;
        // APFS may compare case or Unicode normalization differently from
        // QString. Check the real destination too; never overwrite a sibling.
        if(_names.contains(name) || QFileInfo::exists(QDir(parent).filePath(name))) {
            parent=QDir(_directory).filePath("duplicate-"+QUuid::createUuid().toString(QUuid::WithoutBraces));
            if(!QDir().mkdir(parent)) { error="The duplicate document could not be stored.";return false; }
        }
        const auto destination=QDir(parent).filePath(name);
        if(!writeFile(source,destination,error))return false;
        _names.insert(name);_urls.append(QUrl::fromLocalFile(QFileInfo(destination).canonicalFilePath()));
        return true;
    }
    // The native reader holds the chosen directory's security scope and read
    // coordination for this entire bounded traversal. Provider validation also
    // rejects aliases that QFileInfo cannot distinguish from regular files.
    bool copyDirectory(const QString& sourceRoot,const QString& name,QString& error,
        const std::function<bool(const QString&,QString&)>& validate={},const ReadFile& readFile={}) {
        if(_state.load()!=Active)return false;
        const QFileInfo root(sourceRoot);
        if(!_urls.isEmpty() || !safeName(name) || !root.isDir() || root.isSymLink() || root.canonicalFilePath().isEmpty()) {
            error="The selected folder is unsafe or is not a readable directory.";return false;
        }
        const QFileInfo storage(QFileInfo(_directory).absolutePath());
        if(storage.isSymLink() || (!storage.exists() && !QDir().mkpath(storage.absoluteFilePath())) ||
            !QDir().mkdir(_directory)) {
            error="The imported-document storage could not be created.";return false;
        }
        const auto destination=QDir(_directory).filePath(name);
        if(!QDir().mkdir(destination)) { error="The imported folder could not be created.";return false; }
        // iOS itself aliases /var to /private/var. Normalize system ancestors
        // once; links inside the selected tree are still rejected entry by entry.
        const auto canonicalSource=root.canonicalFilePath();
        const auto destinationRoot=QFileInfo(destination).canonicalFilePath();
        int entries=0,files=0;
        QSet<QString> directories;
        // Unlike a QDirIterator, this iterator exposes enumeration errors.
        // An unreadable subtree must fail the entire import, never vanish.
        std::error_code enumerationError;
        std::filesystem::recursive_directory_iterator iterator(QFile::encodeName(canonicalSource).constData(),enumerationError),end;
        for(;iterator!=end;iterator.increment(enumerationError)) {
            if(enumerationError)break;
            if(cancelled())return false;
            if(++entries>MAX_ENTRIES) { error="The folder exceeds the 1024-entry import limit.";return false; }
            const QFileInfo entry(QFile::decodeName(iterator->path().native().c_str()));
            const auto relative=QDir(canonicalSource).relativeFilePath(entry.absoluteFilePath());
            const auto components=relative.split('/');
            if(components.size()>MAX_DEPTH || std::any_of(components.begin(),components.end(),[](const QString& part){return !safeName(part);}) ||
                entry.isSymLink() || (!entry.isDir() && !entry.isFile()) ||
                entry.canonicalFilePath()!=entry.absoluteFilePath() ||
                !entry.canonicalFilePath().startsWith(canonicalSource+"/")) {
                error="The folder contains an unsafe path, alias, or more than 16 path components.";return false;
            }
            if(validate && !validate(entry.absoluteFilePath(),error))return false;
            const auto destination=QDir(destinationRoot).filePath(relative);
            if(QFileInfo::exists(destination)) {
                // The recursive iterator visits a directory before its children. Every
                // source entry must get an original, distinct destination.
                error="The folder contains names that collide in local storage.";return false;
            }
            const auto parent=QFileInfo(destination).absolutePath();
            if(parent!=destinationRoot && !directories.contains(parent)) {
                error="The folder hierarchy changed while it was being read.";return false;
            }
            if(QFileInfo(parent).isSymLink() || QFileInfo(parent).canonicalFilePath()!=parent) {
                error="The imported folder contains an unsafe destination.";return false;
            }
            if(entry.isDir()) {
                if(!QDir().mkdir(destination)) { error="The imported folder could not be created.";return false; }
                directories.insert(destination);
            } else {
                if(++files>MAX_COUNT) { error="The folder exceeds the 32-file import limit.";return false; }
                const std::function<bool(QIODevice&)> consume=[this,destination,&error](QIODevice& input) {
                    return !cancelled() && writeFile(input,destination,error);
                };
                if(readFile) {
                    if(!readFile(entry.absoluteFilePath(),consume,error))return false;
                } else {
                    QFile input(entry.absoluteFilePath());
                    if(!input.open(QIODevice::ReadOnly)) { error="A selected folder file could not be read.";return false; }
                    if(!consume(input))return false;
                }
            }
        }
        if(enumerationError) { error="The document provider could not enumerate the complete folder.";return false; }
        if(cancelled())return false;
        _urls.append(QUrl::fromLocalFile(QFileInfo(destinationRoot).canonicalFilePath()));
        return true;
    }
private:
    static bool safeName(const QString& name) {
        return !name.isEmpty() && name!="." && name!=".." && !name.contains('/') && !name.contains('\\') &&
            !name.contains(QChar(0)) && !std::any_of(name.begin(),name.end(),[](QChar c){return c.category()==QChar::Other_Control;});
    }
    bool writeFile(QIODevice& source,const QString& destination,QString& error) {
        const auto expected=source.isSequential() ? qint64(-1) : source.size()-source.pos();
        if(expected>MAX_FILE || expected>MAX_TOTAL-_total) {
            error="The selection exceeds the 256 MiB per-file or 512 MiB total import limit.";return false;
        }
        QFile output(destination);
        if(!output.open(QIODevice::WriteOnly|QIODevice::NewOnly)) { error="The imported document could not be created.";return false; }
        qint64 copied=0;
        while(!source.atEnd()) {
            if(cancelled()) { return false; }
            auto chunk=source.read(64*1024);
            if(chunk.isEmpty()) { error="The document provider did not return the complete file.";return false; }
            if(chunk.size()>MAX_FILE-copied || chunk.size()>MAX_TOTAL-_total) {
                error="The selection exceeds the 256 MiB per-file or 512 MiB total import limit.";return false;
            }
            if(output.write(chunk)!=chunk.size()) { error="There is not enough space to import this document.";return false; }
            copied+=chunk.size();_total+=chunk.size();
        }
        if(!output.flush() || cancelled()) { if(!cancelled())error="The imported document could not be saved.";return false; }
        output.close();
        if(QFileInfo(destination).size()!=copied || (expected>=0 && copied!=expected)) { error="The imported document is incomplete.";return false; }
        return true;
    }
    enum : unsigned {Active,Cancelled,Committed};
    std::atomic<unsigned> _state {Active};
    QString _directory;
    QSet<QString> _names;
    QList<QUrl> _urls;
    qint64 _total {0};
};
} // namespace overte::ios
