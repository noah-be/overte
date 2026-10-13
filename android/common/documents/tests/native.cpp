// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <FileDialogHelper.h>
#include <QApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QTemporaryDir>
#include <QThread>
#include <jni.h>
#include <cassert>
#include <thread>
#include <memory>
extern "C" void Java_org_overte_documents_DocumentAdapter_nativeInitialize(JNIEnv*, jclass);
extern "C" void Java_org_overte_documents_DocumentAdapter_nativeCompleted(JNIEnv*, jclass, jstring, jobjectArray, jstring);
static void drain() { for(int i=0;i<4;++i) QCoreApplication::processEvents(); }
static void result(JNIEnv* env, const QString& request, const QStringList& paths, const QString& error={}) {
    auto id=env->NewString(reinterpret_cast<const jchar*>(request.utf16()),request.size());
    auto type=env->FindClass("java/lang/String"); auto files=env->NewObjectArray(paths.size(),type,nullptr);
    for(int i=0;i<paths.size();++i) {
        auto path=env->NewString(reinterpret_cast<const jchar*>(paths[i].utf16()),paths[i].size());
        env->SetObjectArrayElement(files,i,path); env->DeleteLocalRef(path);
    }
    auto failure=env->NewString(reinterpret_cast<const jchar*>(error.utf16()),error.size());
    Java_org_overte_documents_DocumentAdapter_nativeCompleted(env,nullptr,id,files,failure);
    env->DeleteLocalRef(id);env->DeleteLocalRef(type);env->DeleteLocalRef(files);env->DeleteLocalRef(failure);
}
int main(int argc,char** argv) {
    QTemporaryDir storage; assert(storage.isValid());qputenv("XDG_DATA_HOME",storage.path().toUtf8());
    QApplication app(argc,argv);app.setApplicationName("document-owner-test");
    JavaVM* vm=nullptr;JNIEnv* env=nullptr;QByteArray classpath="-Djava.class.path="+QByteArray(argv[1]);
    JavaVMOption option;option.optionString=classpath.data();JavaVMInitArgs settings{};
    settings.version=JNI_VERSION_1_8;settings.nOptions=1;settings.options=&option;
    assert(JNI_CreateJavaVM(&vm,reinterpret_cast<void**>(&env),&settings)==JNI_OK);
    auto backend=env->FindClass("DocumentBoundary");assert(backend);
    Java_org_overte_documents_DocumentAdapter_nativeInitialize(env,backend);
    FileDialogHelper helper;int selected=0,cancelled=0,failed=0;QList<QUrl> urls;
    QObject::connect(&helper,&FileDialogHelper::documentsSelected,[&](QString,QList<QUrl> paths) {
        assert(QThread::currentThread()==helper.thread());++selected;urls=paths;
    });
    QObject::connect(&helper,&FileDialogHelper::documentSelectionCanceled,[&](QString){++cancelled;});
    QObject::connect(&helper,&FileDialogHelper::documentSelectionFailed,[&](QString,QString error){assert(!error.isEmpty());++failed;});
    auto first=helper.openDocuments("Select scripts","Scripts (*.js)",true);assert(!first.isEmpty());
    assert(helper.openDocuments("busy",{},false).isEmpty());
    auto field=env->GetStaticFieldID(backend,"root","Ljava/lang/String;");
    auto value=static_cast<jstring>(env->GetStaticObjectField(backend,field));
    auto chars=env->GetStringChars(value,nullptr);QString root=QString::fromUtf16(reinterpret_cast<const ushort*>(chars),env->GetStringLength(value));
    env->ReleaseStringChars(value,chars);env->DeleteLocalRef(value);
    assert(root.endsWith("/ImportedDocuments"));assert(env->GetStaticBooleanField(backend,env->GetStaticFieldID(backend,"multiple","Z")));
    const auto part=root+"/selection-123";assert(QDir().mkpath(part));
    QFile document(part+"/User 模型 script #?.js");assert(document.open(QFile::WriteOnly));document.write("print('retained')");document.close();
    const auto path=QFileInfo(document).canonicalFilePath();
    std::thread worker([&]{JNIEnv* thread=nullptr;assert(vm->AttachCurrentThread(reinterpret_cast<void**>(&thread),nullptr)==JNI_OK);
        result(thread,first,{path});vm->DetachCurrentThread();});worker.join();
    assert(selected==0);drain();assert(selected==1 && urls.size()==1 && urls[0].toLocalFile()==path);
    assert(QFileInfo(urls[0].toLocalFile()).fileName()=="User 模型 script #?.js");
    auto next=helper.openDocuments("again",{},false);assert(!next.isEmpty());
    assert(!helper.cancelDocuments(first));assert(helper.cancelDocuments(next));assert(cancelled==1);
    result(env,next,{path});drain();assert(selected==1 && cancelled==1);
    auto foreign=helper.openDocuments("foreign",{},false);result(env,foreign,{storage.filePath("foreign.glb")});drain();assert(failed==1);
    auto aliasPath=part+"/alias.js";assert(QFile::link(path,aliasPath));
    auto alias=helper.openDocuments("alias",{},false);result(env,alias,{aliasPath});drain();assert(failed==2);
    auto wrong=helper.openDocuments("wrong order",{},false);result(env,wrong,{path,path});drain();assert(failed==3);
    auto huge=helper.openDocuments("too many",{},true);QStringList many;for(int i=0;i<33;++i)many.append(path);
    result(env,huge,many);drain();assert(failed==4);
    const auto secondPart=root+"/selection-123";assert(QDir().mkpath(secondPart));
    QFile secondFile(secondPart+"/second script.js");assert(secondFile.open(QFile::WriteOnly));secondFile.write("second");secondFile.close();
    const auto secondPath=QFileInfo(secondFile).canonicalFilePath();
    auto single=helper.openDocuments("single",{},false);result(env,single,{path,secondPath});drain();assert(failed==5);
    auto multiple=helper.openDocuments("multiple",{},true);result(env,multiple,{path,secondPath});drain();assert(selected==2 && urls.size()==2);
    const auto duplicatePart=root+"/selection-123/duplicate-123";assert(QDir().mkpath(duplicatePart));
    QFile duplicateFile(duplicatePart+"/second script.js");assert(duplicateFile.open(QFile::WriteOnly));duplicateFile.write("duplicate");duplicateFile.close();
    auto duplicates=helper.openDocuments("duplicates",{},true);
    result(env,duplicates,{secondPath,QFileInfo(duplicateFile).canonicalFilePath()});drain();assert(selected==3 && urls.size()==2);
    auto gone=std::make_unique<FileDialogHelper>();auto old=gone->openDocuments("destroy",{},false);assert(!old.isEmpty());gone.reset();
    result(env,old,{path});drain();assert(selected==3 && QFileInfo(path).isReadable());
    puts("PASS: actual Main FileDialogHelper, Android JNI operator, Qt-owner callbacks, retained Unicode-safe paths, cancellation and late/foreign rejection; OS endpoint is a fixture");
}
