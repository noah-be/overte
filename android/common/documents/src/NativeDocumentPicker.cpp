// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <FileDialogHelper.h>
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QHash>
#include <QMutex>
#include <QPointer>
#include <QRegularExpression>
#include <QStandardPaths>
#include <jni.h>
#include <atomic>

namespace {
std::atomic<JavaVM*> machine { nullptr };
std::atomic<jclass> backend { nullptr };
QMutex pendingMutex;
struct Pending { FileDialogHelper::DocumentSelection callback; bool multiple { false }; };
QHash<QString, Pending> pending;
QString importRoot() { return QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) + "/ImportedDocuments"; }
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
QString string(JNIEnv* env, jstring value, int maximum) {
    if (!value || env->GetStringLength(value) > maximum) return {};
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
QList<QUrl> validated(const QStringList& paths) {
    QList<QUrl> result;
    if (paths.size() > 32) return {};
    const QFileInfo root(importRoot());
    const auto canonicalRoot = root.canonicalFilePath();
    if (canonicalRoot.isEmpty() || !root.isDir() || root.isSymLink()) return {};
    qint64 total = 0; QString selectionPath;
    for (int index = 0; index < paths.size(); ++index) {
        const QFileInfo file(paths[index]);
        const QFileInfo part(file.absolutePath());
        const bool duplicate = QRegularExpression("^duplicate-[0-9]+$").match(part.fileName()).hasMatch();
        const QFileInfo selection(duplicate ? part.absolutePath() : part.filePath());
        const QFileInfo parent(selection.absolutePath());
        if (!file.isFile() || file.isSymLink() || !file.isReadable() || file.size() > 256LL * 1024 * 1024
                || file.canonicalFilePath() != paths[index] || part.isSymLink() || selection.isSymLink()
                || !part.isDir() || !selection.isDir()
                || !QRegularExpression("^selection-[0-9]+$").match(selection.fileName()).hasMatch()
                || parent.canonicalFilePath() != canonicalRoot || parent.isSymLink()
                || (total += file.size()) > 512LL * 1024 * 1024) return {};
        if (!selectionPath.isEmpty() && selection.canonicalFilePath() != selectionPath) return {};
        selectionPath = selection.canonicalFilePath();
        const auto url = QUrl::fromLocalFile(paths[index]); if (result.contains(url)) return {};
        result.append(url);
    }
    return result;
}
void complete(const QString& request, const QStringList& paths, const QString& error) {
    QPointer<QObject> receiver(QCoreApplication::instance()); if (!receiver) return;
    QMetaObject::invokeMethod(receiver, [request, paths, error] {
        Pending operation;
        { QMutexLocker guard(&pendingMutex); operation = pending.take(request); }
        if (!operation.callback) return;
        const auto urls = error.isEmpty() && (operation.multiple || paths.size() <= 1) ? validated(paths) : QList<QUrl>();
        operation.callback(urls, !error.isEmpty() ? error.left(256) :
                 !paths.isEmpty() && urls.size() != paths.size() ?
                 QStringLiteral("The document picker returned an invalid retained file.") : QString());
    }, Qt::QueuedConnection);
}
bool begin(const QString& request, const QString& caption, const QString& filter, bool multiple,
           FileDialogHelper::DocumentSelection callback) {
    if (!QRegularExpression("^[a-zA-Z0-9-]{1,128}$").match(request).hasMatch() || !callback) return false;
    const auto root = importRoot();
    if (!QDir().mkpath(root) || QFileInfo(root).isSymLink()) return false;
    Jni jni; if (!jni.env || !backend.load()) return false;
    { QMutexLocker guard(&pendingMutex); if (pending.contains(request)) return false; pending.insert(request, { std::move(callback), multiple }); }
    jstring id = jni.string(request), location = jni.string(QFileInfo(root).canonicalFilePath());
    jstring title = jni.string(caption.left(256)), types = jni.string(filter.left(4096));
    bool posted = false;
    if (id && location && title && types) {
        jvalue arguments[5]; arguments[0].l = id; arguments[1].l = location;
        arguments[2].l = title; arguments[3].l = types; arguments[4].z = multiple;
        posted = call("request", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Z)V", arguments);
    }
    if (jni.env->ExceptionCheck()) jni.env->ExceptionClear();
    for (auto value : { id, location, title, types }) if (value) jni.env->DeleteLocalRef(value);
    if (!posted) { QMutexLocker guard(&pendingMutex); pending.remove(request); }
    return posted;
}
void cancel(const QString& request) {
    { QMutexLocker guard(&pendingMutex); if (!pending.remove(request)) return; }
    Jni jni; if (!jni.env) return;
    auto id = jni.string(request); if (!id) return;
    jvalue argument; argument.l = id; call("cancel", "(Ljava/lang/String;)V", &argument);
    jni.env->DeleteLocalRef(id);
}
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_documents_DocumentAdapter_nativeInitialize(JNIEnv* env, jclass type) {
    JavaVM* vm = nullptr; if (env->GetJavaVM(&vm) != JNI_OK) return;
    if (!backend.load()) { auto reference = static_cast<jclass>(env->NewGlobalRef(type)); if (!reference) return; backend.store(reference); }
    machine.store(vm);
    FileDialogHelper::setDocumentPickerOperator(begin, cancel);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_documents_DocumentAdapter_nativeCompleted(
        JNIEnv* env, jclass, jstring request, jobjectArray paths, jstring error) {
    const auto id = string(env, request, 128); if (id.isEmpty()) return;
    const auto count = paths ? env->GetArrayLength(paths) : 0;
    QStringList files;
    if (count > 32) { complete(id, {}, QStringLiteral("The document selection exceeded 32 files.")); return; }
    for (int index = 0; index < count; ++index) {
        auto value = static_cast<jstring>(env->GetObjectArrayElement(paths, index));
        const auto path = string(env, value, 4096); if (value) env->DeleteLocalRef(value);
        if (path.isEmpty()) { complete(id, {}, QStringLiteral("The document picker returned an invalid path.")); return; }
        files.append(path);
    }
    complete(id, files, error && env->GetStringLength(error) > 4096 ?
             QStringLiteral("The document provider returned an invalid error response.") : string(env, error, 4096));
}
