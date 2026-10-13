// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "NativeSnapshotAdapter.h"
#include <SnapshotStorage.h>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QDir>
#include <QFile>
#include <QTemporaryDir>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QThread>
#include <QElapsedTimer>
#include <jni.h>
#include <thread>
#include <memory>
#include <cassert>

extern "C" void Java_org_overte_snapshot_SnapshotAdapter_nativeInitialize(JNIEnv*, jclass);
extern "C" void Java_org_overte_snapshot_SnapshotAdapter_nativeCompleted(JNIEnv*, jclass, jlong, jlong, jstring, jstring);
int main(int argc, char** argv) {
    QTemporaryDir storage; assert(storage.isValid()); qputenv("XDG_DATA_HOME", storage.path().toUtf8());
    QGuiApplication app(argc, argv); app.setApplicationName("snapshot-owner-test");
    JavaVM* vm = nullptr; JNIEnv* env = nullptr;
    QByteArray classpath = "-Djava.class.path=" + QByteArray(argv[1]);
    JavaVMOption option; option.optionString = classpath.data();
    JavaVMInitArgs settings {}; settings.version = JNI_VERSION_1_8; settings.nOptions = 1; settings.options = &option;
    assert(JNI_CreateJavaVM(&vm, reinterpret_cast<void**>(&env), &settings) == JNI_OK);
    auto boundary = env->FindClass("SnapshotBoundary"); assert(boundary);
    Java_org_overte_snapshot_SnapshotAdapter_nativeInitialize(env, boundary);
    assert(QDir().mkpath(overte::snapshot::storageRoot()));
    QFile image(QDir(overte::snapshot::storageRoot()).filePath("capture.png"));
    assert(image.open(QFile::WriteOnly)); image.write("snapshot-test"); image.close();
    const auto canonical = overte::snapshot::exportPath(image.fileName()); assert(!canonical.isEmpty());
    NativeSnapshotAdapter adapter;
    int completed = 0; QString lastTicket, lastStatus;
    QObject::connect(&adapter, &NativeSnapshotAdapter::completed, [&](const QString& ticket, const QString& status, const QString&) {
        assert(QThread::currentThread() == adapter.thread()); ++completed; lastTicket = ticket; lastStatus = status;
    });
    const auto first = adapter.request(canonical, "save"); assert(!first.isEmpty() && adapter.busy());
    assert(adapter.request(canonical, "share").isEmpty());
    auto handleField = env->GetStaticFieldID(boundary, "handle", "J"), ticketField = env->GetStaticFieldID(boundary, "ticket", "J");
    auto handle = env->GetStaticLongField(boundary, handleField); assert(handle > 0 && env->GetStaticLongField(boundary, ticketField) == first.toLongLong());
    std::thread callback([&] {
        JNIEnv* worker = nullptr; assert(vm->AttachCurrentThread(reinterpret_cast<void**>(&worker), nullptr) == JNI_OK);
        auto success = worker->NewStringUTF("success"), empty = worker->NewStringUTF("");
        Java_org_overte_snapshot_SnapshotAdapter_nativeCompleted(worker, nullptr, handle, first.toLongLong(), success, empty);
        worker->DeleteLocalRef(success); worker->DeleteLocalRef(empty); vm->DetachCurrentThread();
    }); callback.join();
    assert(adapter.busy() && completed == 0); QCoreApplication::processEvents();
    assert(!adapter.busy() && completed == 1 && lastTicket == first && lastStatus == "success");
    const auto second = adapter.request(canonical, "share"); assert(second.toLongLong() > first.toLongLong());
    adapter.acceptCompletion(first.toLongLong(), "success", {}); QCoreApplication::processEvents();
    assert(adapter.busy() && completed == 1);
    adapter.cancel(first); assert(adapter.busy()); adapter.cancel(second);
    assert(!adapter.busy() && completed == 2 && lastStatus == "cancelled");
    auto cancelled = env->GetStaticFieldID(boundary, "cancelled", "J"); assert(env->GetStaticLongField(boundary, cancelled) == second.toLongLong());
    adapter.acceptCompletion(second.toLongLong(), "success", {}); QCoreApplication::processEvents(); assert(completed == 2);
    auto invalid = adapter.request(storage.filePath("foreign.png"), "save"); QCoreApplication::processEvents();
    assert(!invalid.isEmpty() && completed == 3 && lastTicket == invalid && lastStatus == "error");
    assert(!adapter.error().isEmpty());
    auto discarded = std::make_unique<NativeSnapshotAdapter>(); auto old = discarded->request(canonical, "share");
    const auto oldHandle = env->GetStaticLongField(boundary, handleField); discarded.reset();
    auto success = env->NewStringUTF("success"), empty = env->NewStringUTF("");
    Java_org_overte_snapshot_SnapshotAdapter_nativeCompleted(env, nullptr, oldHandle, old.toLongLong(), success, empty);
    env->DeleteLocalRef(success); env->DeleteLocalRef(empty); QCoreApplication::processEvents();
    QQmlEngine engine; QQmlComponent component(&engine, QUrl::fromLocalFile(argv[2]));
    QElapsedTimer load; load.start();
    while (component.isLoading() && load.elapsed() < 5000) QCoreApplication::processEvents();
    if (!component.isReady()) for (const auto& error : component.errors()) fprintf(stderr, "%s\n", qPrintable(error.toString()));
    assert(component.isReady());
    std::unique_ptr<QObject> wrapper(component.create()); assert(wrapper);
    assert(wrapper->property("capabilities").toStringList() == QStringList({ "save", "share" }));
    assert(wrapper->findChild<NativeSnapshotAdapter*>());
    puts("PASS: production Qt/QML snapshot adapter, actual JNI commands and owner-thread callback lifetime; OS exporter is a fixture");
    // Native adapter destructors still use the VM; process teardown follows Qt ownership.
    return 0;
}
