// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "ios/documents/DocumentImport.h"
#include <FileDialogHelper.h>
#include <QApplication>
#include <QTemporaryDir>
#include <QThread>
#include <cassert>
#include <cstdio>
#include <future>
#include <memory>
#include <thread>
using overte::ios::DocumentImport;
namespace {
QString storageRoot;
int fileCalls=0;
struct NativeBoundary {
    QString id;
    FileDialogHelper::DocumentSelection complete;
    DocumentImport files {storageRoot};
};
std::shared_ptr<NativeBoundary> pending;
// UIKit presentation and provider scheduling are OS-boundary fixtures. The
// production registration lines, actual copier and shared helper execute.
#include "picker-declarations.inc"
bool open(const QString&,QString,QString,bool,FileDialogHelper::DocumentSelection) { ++fileCalls;return false; }
bool openTree(const QString& id,const QString&,FileDialogHelper::DocumentSelection complete) {
    assert(QThread::currentThread()==qApp->thread());
    if(pending)return false;
    pending=std::make_shared<NativeBoundary>();pending->id=id;pending->complete=std::move(complete);return true;
}
void cancel(const QString& id) { if(pending && pending->id==id)pending->files.cancel(); }
void install() {
#include "picker-registration.inc"
}
void copySelected(std::shared_ptr<NativeBoundary> request,QString source,
    std::function<bool(const QString&,QString&)> validate={}) {
    QString error;QList<QUrl> urls;
    if(request->files.copyDirectory(source,"project",error,validate) && request->files.commit())urls=request->files.urls();
    else request->files.rollback();
    // The native adapter dispatches shared completion to Qt's owner, keeping
    // its request/copy lease alive until this exact queued return.
    QMetaObject::invokeMethod(qApp,[request,urls,error] {
        assert(QThread::currentThread()==qApp->thread());
        if(pending!=request)return;
        pending.reset();request->complete(urls,error);
    },Qt::QueuedConnection);
}
void drain() { QCoreApplication::processEvents();QCoreApplication::processEvents(); }
void write(const QString& path,const QByteArray& bytes) {
    assert(QDir().mkpath(QFileInfo(path).absolutePath()));QFile file(path);
    assert(file.open(QIODevice::WriteOnly));assert(file.write(bytes)==bytes.size());
}
}
int main(int argc,char** argv) {
    QApplication app(argc,argv);QTemporaryDir storage,source;assert(storage.isValid()&&source.isValid());
    storageRoot=storage.path();
    write(source.path()+"/main.js","Script.include('nested/helper.js');");
    write(source.path()+"/nested/helper.js","var answer=42;");assert(QDir().mkpath(source.path()+"/empty"));
    install();FileDialogHelper helper;int selected=0,failed=0,cancelled=0;QUrl root;
    QObject::connect(&helper,&FileDialogHelper::documentsSelected,[&](const QString&,const QList<QUrl>& urls) {
        assert(QThread::currentThread()==helper.thread());assert(urls.size()==1);root=urls.first();++selected;
    });
    QObject::connect(&helper,&FileDialogHelper::documentSelectionFailed,[&](const QString&,const QString& error) {assert(!error.isEmpty());++failed;});
    QObject::connect(&helper,&FileDialogHelper::documentSelectionCanceled,[&](const QString&) {++cancelled;});
    const auto first=helper.openDocumentTree("project");assert(!first.isEmpty());
    assert(helper.openDocuments("busy","*.js",false).isEmpty());
    auto firstRequest=pending;
    std::thread reader([firstRequest,path=source.path()] {copySelected(firstRequest,path);});reader.join();
    assert(selected==0);drain();assert(selected==1&&failed==0&&fileCalls==0&&!pending);
    const auto manifest=helper.documentBundle({},root);
    assert(manifest.value("error").toString().isEmpty());
    assert(manifest.value("relativePaths").toList().contains("nested/helper.js"));
    QFile script(root.toLocalFile()+"/nested/helper.js");assert(script.open(QIODevice::ReadOnly));assert(script.readAll()=="var answer=42;");
    assert(QFileInfo(root.toLocalFile()+"/empty").isDir());
    auto second=helper.openDocumentTree("cancel during copy");assert(!second.isEmpty()&&second!=first);
    auto cancelledRequest=pending;const auto partial=cancelledRequest->files.directory();
    std::promise<void> copying,resume;auto permit=resume.get_future();
    std::thread copyingWorker([&] {
        bool entered=false;
        copySelected(cancelledRequest,source.path(),[&](const QString&,QString&) {
            if(!entered) {entered=true;copying.set_value();permit.wait();}return true;
        });
    });
    copying.get_future().wait();assert(helper.cancelDocuments(second));assert(cancelled==1);
    // Shared cancellation clears its ID, but the native copy lease stays busy.
    assert(helper.openDocumentTree("retry while cancelling").isEmpty());
    resume.set_value();copyingWorker.join();drain();
    assert(selected==1&&failed==0&&!pending&&!QFileInfo::exists(partial));
    assert(QFileInfo(root.toLocalFile()+"/main.js").isFile());
    assert(QFile::link(source.path()+"/main.js",source.path()+"/alias.js"));
    assert(!helper.openDocumentTree("unsafe folder").isEmpty());auto unsafe=pending;
    std::thread unsafeWorker([unsafe,path=source.path()] {copySelected(unsafe,path);});unsafeWorker.join();drain();
    assert(failed==1&&selected==1&&!pending&&!QFileInfo::exists(unsafe->files.directory()));
    assert(QFile::remove(source.path()+"/alias.js"));
    auto* deleted=new FileDialogHelper;assert(!deleted->openDocumentTree("deleted owner").isEmpty());
    auto abandoned=pending;delete deleted;assert(abandoned->files.cancelled());
    std::thread lateWorker([abandoned,path=source.path()] {copySelected(abandoned,path);});lateWorker.join();drain();assert(!pending);
    assert(!helper.openDocumentTree("new request").isEmpty());auto current=pending;
    // A late prior native reply cannot replace this newer request.
    firstRequest->complete({root},{});drain();assert(selected==1&&pending==current);
    std::thread currentWorker([current,path=source.path()] {copySelected(current,path);});currentWorker.join();drain();assert(selected==2&&!pending);
    FileDialogHelper::setDocumentTreePickerOperator({},{});FileDialogHelper::setDocumentPickerOperator({},{});
    puts("PASS production iOS registration/owning-header ABI and copier/helper handoff, original hierarchy, owner queue, native lease, cancellation/rollback, stale replies and permanent resources; UIKit/provider boundary is a fixture");
}
