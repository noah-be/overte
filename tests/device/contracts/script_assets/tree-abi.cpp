// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <QApplication>
#include <QTemporaryDir>
#include <QFile>
#include <QDir>
#include <QThread>
#include <cassert>
#include <cstdio>
#include <thread>
#include "FileDialogHelper.h"
// Offscreen surface creation is replaced; the actual additive route body executes.
class ModalDialogListener { };
struct OffscreenUi {
    QVariantMap properties;
    ModalDialogListener listener;
    static ModalDialogListener* getOpenFileBundleAsync(const QString&,const QString&,const QString&);
    ModalDialogListener* fileDialogAsync(const QVariantMap& p){properties=p;return &listener;}
};
struct DependencyManager {template<class T>static T* get(){static T value;return &value;}};
#include "offscreen-bundle-route.inc"
int main(int argc,char** argv){
    QApplication application(argc,argv);
    QTemporaryDir folder;
    QDir(folder.path()).mkdir("nested");
    auto write=[&](QString name,QByteArray bytes){QFile file(folder.path()+"/"+name);assert(file.open(QFile::WriteOnly));assert(file.write(bytes)==bytes.size());};
    write("main.js","Script.include('nested/helper.js');");write("nested/helper.js","var answer=42;");
    const auto root=QUrl::fromLocalFile(folder.path());
    FileDialogHelper helper;
    auto bundle=helper.documentBundle({},root);
    assert(bundle.value("error").toString().isEmpty());
    assert(bundle.value("relativePaths").toList().contains("nested/helper.js"));
    QFile::link(folder.path()+"/main.js",folder.path()+"/alias.js");
    assert(!helper.documentBundle({},root).value("error").toString().isEmpty());QFile::remove(folder.path()+"/alias.js");
    QList<FileDialogHelper::DocumentSelection> replies;
    int fileCalls=0,selected=0,failed=0,canceled=0;
    FileDialogHelper::setDocumentPickerOperator([&](const QString&,const QString&,const QString&,bool,FileDialogHelper::DocumentSelection){++fileCalls;return true;},{});
    FileDialogHelper::setDocumentTreePickerOperator([&](const QString&,const QString&,FileDialogHelper::DocumentSelection done){replies.append(done);return true;},[&](const QString&){++canceled;});
    QObject::connect(&helper,&FileDialogHelper::documentsSelected,[&](const QString&,const QList<QUrl>& urls){assert(QThread::currentThread()==helper.thread());assert(urls==QList<QUrl>{root});++selected;});
    QObject::connect(&helper,&FileDialogHelper::documentSelectionFailed,[&](const QString&,const QString&){++failed;});
    auto first=helper.openDocumentTree("folder");assert(!first.isEmpty());assert(helper.openDocuments("busy","*",false).isEmpty());
    replies[0]({QUrl::fromLocalFile(folder.path()+"/main.js")},{});QCoreApplication::processEvents();assert(failed==1&&selected==0);
    auto second=helper.openDocumentTree("folder");assert(first!=second);assert(helper.cancelDocuments(second));
    replies[1]({root},{});QCoreApplication::processEvents();assert(selected==0&&canceled==1);
    auto third=helper.openDocumentTree("folder");assert(!third.isEmpty());
    std::thread completion([&]{replies[2]({root},{});});completion.join();assert(selected==0);QCoreApplication::processEvents();assert(selected==1);
    auto* deleted=new FileDialogHelper;deleted->openDocumentTree("deleted");
    FileDialogHelper::setDocumentTreePickerOperator({},{});delete deleted;
    replies[3]({root},{});QCoreApplication::processEvents();assert(canceled==2&&fileCalls==0);
    FileDialogHelper::setDocumentPickerOperator({},{});
    OffscreenUi::getOpenFileBundleAsync("Script",folder.path(),"\\.js$");
    const auto properties=DependencyManager::get<OffscreenUi>()->properties;
    assert(properties.value("bundleMode").toBool()&&properties.value("primaryFilter")=="\\.js$");
    assert(properties.value("dir").toUrl()==root);
    std::puts("PASS actual tree ABI, hierarchy/symlink, separate file operator, request/owner cancellation, queued completion and Offscreen bundle route");
}
