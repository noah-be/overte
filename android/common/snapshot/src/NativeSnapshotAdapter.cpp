// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "NativeSnapshotAdapter.h"
#include <SnapshotStorage.h>
#include <QCoreApplication>
#include <QFileInfo>
#include <QHash>
#include <QMutex>
#include <QPointer>
#include <QThread>
#include <QTimer>
#include <QtQml>
#include <jni.h>
#include <atomic>
#include <limits>

namespace {
QMutex registryMutex;
QHash<jlong, NativeSnapshotAdapter*> registry;
jlong nextHandle { 1 }, nextRequest { 1 };
std::atomic<JavaVM*> machine { nullptr };
std::atomic<jclass> backend { nullptr };
struct Jni {
    JNIEnv* env { nullptr }; bool attached { false };
    Jni() {
        auto* vm = machine.load(); if (!vm) return;
        if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
#if defined(Q_OS_ANDROID)
            attached = vm->AttachCurrentThread(&env, nullptr) == JNI_OK;
#else
            attached = vm->AttachCurrentThread(reinterpret_cast<void**>(&env), nullptr) == JNI_OK;
#endif
        }
    }
    ~Jni() { if (attached && machine.load()) machine.load()->DetachCurrentThread(); }
    jstring string(const QString& text) const {
        return env ? env->NewString(reinterpret_cast<const jchar*>(text.utf16()), text.size()) : nullptr;
    }
};
QString string(JNIEnv* env, jstring value) {
    if (!value) return {};
    const auto* text = env->GetStringChars(value, nullptr); if (!text) return {};
    QString result = QString::fromUtf16(reinterpret_cast<const ushort*>(text), env->GetStringLength(value));
    env->ReleaseStringChars(value, text); return result;
}
bool call(const char* method, const char* signature, jvalue* arguments) {
    Jni jni; if (!jni.env || !backend.load()) return false;
    auto id = jni.env->GetStaticMethodID(backend.load(), method, signature);
    if (id) jni.env->CallStaticVoidMethodA(backend.load(), id, arguments);
    bool valid = id && !jni.env->ExceptionCheck();
    if (jni.env->ExceptionCheck()) jni.env->ExceptionClear();
    return valid;
}
qint64 allocate(jlong& counter) {
    if (counter <= 0) return 0;
    const auto value = counter;
    counter = value == std::numeric_limits<jlong>::max() ? 0 : value + 1;
    return value;
}
void registerType() { qmlRegisterType<NativeSnapshotAdapter>("Overte.Android", 1, 0, "NativeSnapshotAdapter"); }
}
Q_COREAPP_STARTUP_FUNCTION(registerType)

NativeSnapshotAdapter::NativeSnapshotAdapter(QObject* parent) : QObject(parent) {
    QMutexLocker guard(&registryMutex); _handle = allocate(nextHandle);
    if (_handle) registry.insert(_handle, this);
}
NativeSnapshotAdapter::~NativeSnapshotAdapter() {
    if (_request) { jvalue arguments[2]; arguments[0].j = _handle; arguments[1].j = _request; call("cancel", "(JJ)V", arguments); }
    QMutexLocker guard(&registryMutex); registry.remove(_handle);
}
QString NativeSnapshotAdapter::request(const QString& path, const QString& action) {
    if (QThread::currentThread() != thread()) return {};
    if (_request) { _error = tr("A snapshot operation is already active."); emit stateChanged(); return {}; }
    { QMutexLocker guard(&registryMutex); _request = _handle ? allocate(nextRequest) : 0; }
    if (!_request) { _error = tr("Snapshot export is unavailable."); emit stateChanged(); return {}; }
    _error.clear(); emit stateChanged();
    const auto ticket = _request;
    const QString canonical = overte::snapshot::exportPath(path);
    const QString root = QFileInfo(overte::snapshot::storageRoot()).canonicalFilePath();
    bool posted = false;
    if (!canonical.isEmpty() && !root.isEmpty() && (action == "save" || action == "share")) {
        Jni jni;
        if (jni.env) {
            jstring rootText = jni.string(root), fileText = jni.string(canonical), actionText = jni.string(action);
            if (rootText && fileText && actionText) {
                jvalue arguments[5]; arguments[0].j = _handle; arguments[1].j = ticket;
                arguments[2].l = rootText; arguments[3].l = fileText; arguments[4].l = actionText;
                posted = call("request", "(JJLjava/lang/String;Ljava/lang/String;Ljava/lang/String;)V", arguments);
            }
            if (jni.env->ExceptionCheck()) jni.env->ExceptionClear();
            if (rootText) jni.env->DeleteLocalRef(rootText);
            if (fileText) jni.env->DeleteLocalRef(fileText);
            if (actionText) jni.env->DeleteLocalRef(actionText);
        }
    }
    if (!posted) QTimer::singleShot(0, this, [this, ticket] { complete(ticket, "error", tr("The snapshot could not be exported. Check the image and active Android Activity.")); });
    return QString::number(ticket);
}
void NativeSnapshotAdapter::cancel(const QString& ticket) {
    if (!_request || ticket != QString::number(_request) || QThread::currentThread() != thread()) return;
    jvalue arguments[2]; arguments[0].j = _handle; arguments[1].j = _request;
    call("cancel", "(JJ)V", arguments);
    complete(_request, "cancelled", {});
}
void NativeSnapshotAdapter::acceptCompletion(qint64 ticket, const QString& status, const QString& error) {
    QPointer<NativeSnapshotAdapter> self(this);
    QMetaObject::invokeMethod(this, [self, ticket, status, error] { if (self) self->complete(ticket, status, error); }, Qt::QueuedConnection);
}
void NativeSnapshotAdapter::complete(qint64 ticket, const QString& status, const QString& error) {
    if (!ticket || ticket != _request || QThread::currentThread() != thread()) return;
    const QString outcome = status == "success" || status == "cancelled" ? status : "error";
    _request = 0; _error = outcome == "error" ? error.left(256) : QString();
    if (outcome == "error" && _error.isEmpty()) _error = tr("The snapshot could not be exported.");
    emit stateChanged(); emit completed(QString::number(ticket), outcome, _error);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_snapshot_SnapshotAdapter_nativeInitialize(JNIEnv* env, jclass type) {
    JavaVM* vm = nullptr; if (env->GetJavaVM(&vm) != JNI_OK) return;
    if (!backend.load()) { auto reference = static_cast<jclass>(env->NewGlobalRef(type)); if (!reference) return; backend.store(reference); }
    machine.store(vm);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_snapshot_SnapshotAdapter_nativeCompleted(
        JNIEnv* env, jclass, jlong handle, jlong ticket, jstring status, jstring error) {
    const auto outcome = string(env, status), message = string(env, error);
    QMutexLocker guard(&registryMutex);
    if (auto* item = registry.value(handle)) item->acceptCompletion(ticket, outcome, message);
}
