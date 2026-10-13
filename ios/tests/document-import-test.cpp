// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "ios/documents/DocumentImport.h"
#include <QBuffer>
#include <QCoreApplication>
#include <QTemporaryDir>
#include <cassert>
#include <thread>
using overte::ios::DocumentImport;
class Bytes : public QIODevice {
public:
    explicit Bytes(qint64 count,std::function<void()> tick={}) : _remaining(count),_tick(std::move(tick)) { open(ReadOnly); }
    bool atEnd() const override { return _remaining==0; }
    bool isSequential() const override { return true; }
protected:
    qint64 readData(char* data,qint64 count) override {
        if(_tick)_tick();
        const auto bytes=qMin(count,_remaining);memset(data,'x',bytes);_remaining-=bytes;return bytes;
    }
    qint64 writeData(const char*,qint64) override { return -1; }
private:qint64 _remaining;std::function<void()> _tick;
};
class Truncated : public Bytes {
public:
    Truncated() : Bytes(3) {}
    bool isSequential() const override { return false; }
    qint64 size() const override { return 6; }
};
bool copy(DocumentImport& batch,const QString& name,const QByteArray& data,QString& error) {
    QBuffer source;source.setData(data);assert(source.open(QIODevice::ReadOnly));return batch.copy(source,name,error);
}
void write(const QString& path,const QByteArray& data="bytes") {
    assert(QDir().mkpath(QFileInfo(path).absolutePath()));
    QFile file(path);assert(file.open(QIODevice::WriteOnly));assert(file.write(data)==data.size());
}
int main(int argc,char** argv) {
    QCoreApplication app(argc,argv);QTemporaryDir storage;assert(storage.isValid());QString error;
    QList<QUrl> saved;
    {
        DocumentImport batch(storage.path());
        assert(copy(batch,"model.gltf","{\"buffers\":[\"mesh.bin\"]}",error));
        assert(copy(batch,"mesh.bin",QByteArray("\0\1\2\3",4),error));
        assert(copy(batch,"model.gltf","second model",error));
        assert(copy(batch,QString::fromUtf8("日本語.js"),"print('ok')",error));
        saved=batch.urls();assert(saved.size()==4);
        assert(QFileInfo(saved[0].toLocalFile()).absolutePath()==QFileInfo(saved[1].toLocalFile()).absolutePath());
        assert(QFileInfo(saved[0].toLocalFile()).absolutePath()!=QFileInfo(saved[2].toLocalFile()).absolutePath());
        assert(QFileInfo(saved[2].toLocalFile()).fileName()=="model.gltf");
        assert(batch.commit());batch.cancel();assert(!batch.cancelled());
        assert(!copy(batch,"late.js","cannot revive",error));
    }
    QFile bytes(saved[1].toLocalFile());assert(bytes.open(QIODevice::ReadOnly));assert(bytes.readAll()==QByteArray("\0\1\2\3",4));
    for(const auto& url:saved)assert(QFileInfo(url.toLocalFile()).isFile());
    QString incomplete;
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();
        assert(copy(batch,"valid.js","valid",error));
        assert(!copy(batch,"../escape.js","bad",error));assert(!error.isEmpty());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();
        for(int i=0;i<DocumentImport::MAX_COUNT;i++)assert(copy(batch,QString::number(i)+".js","x",error));
        assert(!copy(batch,"33.js","x",error));assert(!error.isEmpty());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();
        Bytes tooLarge(DocumentImport::MAX_FILE+1);error.clear();
        assert(!batch.copy(tooLarge,"large.bin",error));assert(!error.isEmpty());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();
        Bytes first(DocumentImport::MAX_FILE),second(DocumentImport::MAX_FILE),overflow(1);error.clear();
        assert(batch.copy(first,"one.bin",error));assert(batch.copy(second,"two.bin",error));
        assert(!batch.copy(overflow,"three.bin",error));assert(!error.isEmpty());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();error.clear();
        Bytes changing(1024*1024,[&]{batch.cancel();});
        assert(!batch.copy(changing,"cancel.js",error));assert(batch.cancelled());assert(!batch.commit());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        const auto symlink=storage.path()+"/alias";assert(QFile::link(storage.path(),symlink));
        DocumentImport batch(symlink);error.clear();assert(!copy(batch,"denied.js","x",error));assert(!error.isEmpty());
    }
    QTemporaryDir source;assert(source.isValid());
    const auto project=source.path()+"/日本語 project";
    write(project+"/model.gltf","{\"buffers\":[{\"uri\":\"geometry/mesh.bin\"}]}");
    write(project+"/geometry/mesh.bin",QByteArray("\0\1\2",3));
    write(project+"/textures/mesh.bin","texture");
    write(project+"/.hidden.js","hidden");
    assert(QDir().mkpath(project+"/empty"));
    QString imported;
    {
        DocumentImport batch(storage.path());error.clear();
        assert(batch.copyDirectory(project,"日本語 project",error));
        assert(batch.urls().size()==1);imported=batch.urls().first().toLocalFile();
        assert(QFileInfo(imported).isDir());assert(QFileInfo(imported+"/empty").isDir());
        QFile mesh(imported+"/geometry/mesh.bin");assert(mesh.open(QIODevice::ReadOnly));assert(mesh.readAll()==QByteArray("\0\1\2",3));
        QFile texture(imported+"/textures/mesh.bin");assert(texture.open(QIODevice::ReadOnly));assert(texture.readAll()=="texture");
        assert(QFileInfo(imported+"/.hidden.js").isFile());assert(batch.commit());
    }
    assert(QFileInfo(imported+"/model.gltf").isFile());
    {
        DocumentImport batch(storage.path());error.clear();int reads=0;
        assert(batch.copyDirectory(project,"coordinated",error,{},[&](const QString& path,
            const std::function<bool(QIODevice&)>& consume,QString&) {
                ++reads;QFile input(path);assert(input.open(QIODevice::ReadOnly));return consume(input);
            }));
        assert(reads==4);assert(batch.commit());
        DocumentImport failed(storage.path());error.clear();
        assert(!failed.copyDirectory(project,"failed",error,{},[](const QString&,
            const std::function<bool(QIODevice&)>&,QString& error) { error="provider read failed";return false; }));
        assert(!error.isEmpty());assert(failed.urls().isEmpty());
    }
    {
        QTemporaryDir empty;DocumentImport batch(storage.path());error.clear();
        assert(batch.copyDirectory(empty.path(),"empty",error));assert(batch.urls().size()==1);assert(batch.commit());
    }
    for(const auto& name:QStringList{"../escape",".","..","a/b","a\\b",QString(QChar(0)),QString(QChar(1))}) {
        DocumentImport batch(storage.path());error.clear();assert(!batch.copyDirectory(project,name,error));assert(!error.isEmpty());
    }
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();error.clear();
        int checked=0;
        assert(!batch.copyDirectory(project,"cancelled",error,[&](const QString&,QString&) { if(++checked==2)batch.cancel();return true; }));
        assert(batch.cancelled());assert(batch.urls().isEmpty());assert(!batch.commit());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        DocumentImport batch(storage.path());incomplete=batch.directory();error.clear();
        assert(!batch.copyDirectory(project,"alias",error,[](const QString&,QString& error) { error="provider alias";return false; }));
        assert(!error.isEmpty());assert(batch.urls().isEmpty());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        QTemporaryDir links;assert(QFile::link(project,links.path()+"/alias"));
        DocumentImport batch(storage.path());error.clear();assert(!batch.copyDirectory(links.path(),"links",error));assert(!error.isEmpty());
    }
    {
        QTemporaryDir many;for(int i=0;i<DocumentImport::MAX_COUNT;i++)write(many.path()+"/"+QString::number(i));
        DocumentImport allowed(storage.path());error.clear();assert(allowed.copyDirectory(many.path(),"exact",error));assert(allowed.commit());
        write(many.path()+"/overflow");
        DocumentImport batch(storage.path());incomplete=batch.directory();error.clear();assert(!batch.copyDirectory(many.path(),"many",error));
        assert(!error.isEmpty());assert(batch.urls().isEmpty());
    }
    assert(!QFileInfo::exists(incomplete));
    {
        QTemporaryDir large;QFile file(large.path()+"/large.bin");assert(file.open(QIODevice::WriteOnly));
        assert(file.resize(DocumentImport::MAX_FILE+1));file.close();
        DocumentImport batch(storage.path());error.clear();assert(!batch.copyDirectory(large.path(),"large",error));assert(!error.isEmpty());
        assert(batch.urls().isEmpty());
    }
    {
        DocumentImport batch(storage.path());Truncated input;error.clear();
        assert(!batch.copy(input,"truncated.bin",error));assert(!error.isEmpty());assert(batch.urls().isEmpty());
    }
    {
        QTemporaryDir entries;
        for(int i=0;i<DocumentImport::MAX_ENTRIES;i++)assert(QDir().mkdir(entries.path()+"/"+QString::number(i)));
        DocumentImport allowed(storage.path());error.clear();assert(allowed.copyDirectory(entries.path(),"exact",error));assert(allowed.commit());
        assert(QDir().mkdir(entries.path()+"/overflow"));
        DocumentImport denied(storage.path());error.clear();assert(!denied.copyDirectory(entries.path(),"overflow",error));assert(!error.isEmpty());
    }
    {
        QTemporaryDir depth;QString path=depth.path();for(int i=0;i<DocumentImport::MAX_DEPTH;i++)path+="/level";
        assert(QDir().mkpath(path));
        DocumentImport allowed(storage.path());error.clear();assert(allowed.copyDirectory(depth.path(),"exact",error));assert(allowed.commit());
        write(path+"/too-deep");
        DocumentImport denied(storage.path());error.clear();assert(!denied.copyDirectory(depth.path(),"deep",error));assert(!error.isEmpty());
    }
    {
        QTemporaryDir unreadable;
        assert(QDir().mkdir(unreadable.path()+"/disappearing"));
        DocumentImport batch(storage.path());error.clear();
        assert(!batch.copyDirectory(unreadable.path(),"changed",error,[](const QString& path,QString&) {
            assert(QDir(path).removeRecursively());return true;
        }));
        assert(!error.isEmpty());assert(batch.urls().isEmpty());
    }
    {
        // Match iOS's system /var ancestor alias; an alias inside the selected
        // directory is rejected, but a platform ancestor cannot break imports.
        const auto ancestor=source.path()+"/system-alias";assert(QFile::link(storage.path(),ancestor));
        DocumentImport batch(ancestor);error.clear();assert(!batch.copyDirectory(project,"denied",error));
        assert(!error.isEmpty());
        const auto parentAlias=source.path()+"/parent-alias";assert(QFile::link(source.path(),parentAlias));
        DocumentImport normal(storage.path());error.clear();
        assert(normal.copyDirectory(parentAlias+"/日本語 project","safe",error));assert(normal.commit());
    }
    for(int i=0;i<1000;i++) {
        DocumentImport batch(storage.path());bool committed=false;
        std::thread writer([&]{committed=batch.commit();});std::thread cancel([&]{batch.cancel();});writer.join();cancel.join();
        assert(committed!=batch.cancelled());
    }
    puts("PASS: actual file/tree bytes, preserved hierarchy/hidden/empty folders, durable roots, file/entry/depth bounds, alias/traversal rejection, rollback, cancellation and atomic races");
}
