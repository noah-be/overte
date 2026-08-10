#include "PicoWebViewItem.h"

#include <QHoverEvent>
#include <QHash>
#include <QMouseEvent>
#include <QMutexLocker>
#include <QPointer>
#include <QQmlEngine>
#include <QQuickImageProvider>
#include <QTimer>
#include <QWheelEvent>
#include <QtQml/qqml.h>
#include <jni.h>
#include <android/log.h>

#include <limits>
#include <atomic>

namespace {
QMutex itemRegistryMutex;
QHash<jlong, PicoWebViewItem*> itemRegistry;
std::atomic<JavaVM*> webViewJavaVm { nullptr };
std::atomic<jclass> webViewClass { nullptr };

class PicoWebImageProvider : public QQuickImageProvider {
public:
    PicoWebImageProvider() : QQuickImageProvider(Image) { }
    QImage requestImage(const QString& id, QSize* size, const QSize& requestedSize) override {
        bool ok { false };
        const auto handle = id.section('/', 0, 0).toLongLong(&ok, 16);
        QImage image;
        if (ok) {
            QMutexLocker locker(&itemRegistryMutex);
            if (auto* item = itemRegistry.value(handle, nullptr)) {
                image = item->frameImage();
            }
        }
        if (size) { *size = image.size(); }
        return requestedSize.isValid() ? image.scaled(requestedSize) : image;
    }
};

struct JniScope {
    JNIEnv* env { nullptr };
    bool attached { false };
    JniScope() {
        JavaVM* vm = webViewJavaVm.load(std::memory_order_acquire);
        if (!vm) { return; }
        if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
            attached = vm->AttachCurrentThread(&env, nullptr) == JNI_OK;
        }
    }
    ~JniScope() {
        JavaVM* vm = webViewJavaVm.load(std::memory_order_acquire);
        if (attached && vm) { vm->DetachCurrentThread(); }
    }
};

bool callStatic(const char* name, const char* signature, jvalue* args) {
    JniScope jni;
    if (!jni.env) { return false; }
    jclass clazz = webViewClass.load(std::memory_order_acquire);
    if (!clazz) {
        __android_log_print(ANDROID_LOG_ERROR, "OverteWebEntity", "Java WebView bridge is not initialized");
        return false;
    }
    jmethodID method = jni.env->GetStaticMethodID(clazz, name, signature);
    if (method) {
        jni.env->CallStaticVoidMethodA(clazz, method, args);
    } else {
        __android_log_print(ANDROID_LOG_ERROR, "OverteWebEntity", "Cannot find Java WebView bridge method %s", name);
        if (jni.env->ExceptionCheck()) {
            jni.env->ExceptionClear();
        }
        return false;
    }
    if (jni.env->ExceptionCheck()) {
        __android_log_print(ANDROID_LOG_ERROR, "OverteWebEntity", "Java WebView bridge method %s failed", name);
        jni.env->ExceptionDescribe();
        jni.env->ExceptionClear();
        return false;
    }
    return true;
}

void registerPicoWebViewType() {
    qmlRegisterType<PicoWebViewItem>("Overte.Pico", 1, 0, "PicoWebView");
}
}
Q_COREAPP_STARTUP_FUNCTION(registerPicoWebViewType)

extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_OffscreenWebView_nativeInitialize(
        JNIEnv* environment, jclass inputClass) {
    JavaVM* vm { nullptr };
    if (environment->GetJavaVM(&vm) != JNI_OK) {
        return;
    }
    auto globalClass = static_cast<jclass>(environment->NewGlobalRef(inputClass));
    if (!globalClass) {
        return;
    }
    webViewJavaVm.store(vm, std::memory_order_release);
    jclass expected { nullptr };
    if (!webViewClass.compare_exchange_strong(
            expected, globalClass, std::memory_order_acq_rel)) {
        environment->DeleteGlobalRef(globalClass);
    }
}

PicoWebViewItem::PicoWebViewItem(QQuickItem* parent) : QQuickItem(parent) {
    QMutexLocker locker(&itemRegistryMutex);
    itemRegistry.insert(reinterpret_cast<jlong>(this), this);
    setAcceptHoverEvents(true);
    setAcceptedMouseButtons(Qt::LeftButton);
}

PicoWebViewItem::~PicoWebViewItem() {
    {
        QMutexLocker locker(&itemRegistryMutex);
        itemRegistry.remove(reinterpret_cast<jlong>(this));
    }
    if (_webViewCreated) {
        jvalue args[1]; args[0].j = reinterpret_cast<jlong>(this);
        callStatic("destroy", "(J)V", args);
    }
}

void PicoWebViewItem::setUrl(const QString& value) {
    if (_url == value) { return; }
    _url = value;
    emit urlChanged();
    if (!_webViewCreated) { return; }
    JniScope jni;
    if (!jni.env) { return; }
    jstring url = jni.env->NewString(reinterpret_cast<const jchar*>(_url.utf16()), _url.size());
    jvalue args[2]; args[0].j = reinterpret_cast<jlong>(this); args[1].l = url;
    callStatic("load", "(JLjava/lang/String;)V", args);
    jni.env->DeleteLocalRef(url);
}

void PicoWebViewItem::setUserAgent(const QString& value) {
    if (_userAgent == value) { return; }
    _userAgent = value;
    if (_webViewCreated) {
        JniScope jni;
        if (!jni.env) { return; }
        jstring agent = jni.env->NewString(
            reinterpret_cast<const jchar*>(_userAgent.utf16()), _userAgent.size());
        if (!agent) {
            if (jni.env->ExceptionCheck()) { jni.env->ExceptionClear(); }
            return;
        }
        jvalue args[2]; args[0].j = reinterpret_cast<jlong>(this); args[1].l = agent;
        callStatic("setUserAgent", "(JLjava/lang/String;)V", args);
        jni.env->DeleteLocalRef(agent);
    }
}

void PicoWebViewItem::setUseBackground(bool value) {
    if (_useBackground == value) { return; }
    _useBackground = value;
    emit useBackgroundChanged();
    if (_webViewCreated) {
        jvalue args[2];
        args[0].j = reinterpret_cast<jlong>(this);
        args[1].z = _useBackground;
        callStatic("setUseBackground", "(JZ)V", args);
    }
}

void PicoWebViewItem::componentComplete() {
    QQuickItem::componentComplete();
    if (auto* engine = qmlEngine(this); engine && !engine->imageProvider("pico-web")) {
        engine->addImageProvider("pico-web", new PicoWebImageProvider);
    }
    createWebView();
}

void PicoWebViewItem::createWebView() {
    // QML completes Web3DOverlay items at 1x1 before the entity renderer
    // assigns the real texture size. Loading a page into that provisional
    // viewport makes Android WebView retain an incorrect mobile zoom even
    // after resize, so defer creation until useful geometry exists.
    if (!isComponentComplete() || _webViewCreated || _webViewCreationPending ||
            pixelWidth() <= 1 || pixelHeight() <= 1) { return; }
    JniScope jni;
    if (!jni.env) {
        scheduleCreationRetry();
        return;
    }
    jstring url = jni.env->NewString(reinterpret_cast<const jchar*>(_url.utf16()), _url.size());
    jstring agent = jni.env->NewString(reinterpret_cast<const jchar*>(_userAgent.utf16()), _userAgent.size());
    if (!url || !agent) {
        if (jni.env->ExceptionCheck()) { jni.env->ExceptionClear(); }
        if (url) { jni.env->DeleteLocalRef(url); }
        if (agent) { jni.env->DeleteLocalRef(agent); }
        scheduleCreationRetry();
        return;
    }
    jvalue args[6];
    args[0].j = reinterpret_cast<jlong>(this); args[1].i = pixelWidth(); args[2].i = pixelHeight();
    args[3].l = url; args[4].l = agent; args[5].z = _useBackground;
    _webViewCreationPending = callStatic(
        "create", "(JIILjava/lang/String;Ljava/lang/String;Z)V", args);
    jni.env->DeleteLocalRef(url); jni.env->DeleteLocalRef(agent);
    if (!_webViewCreationPending) {
        scheduleCreationRetry();
    }
}

void PicoWebViewItem::scheduleCreationRetry() {
    constexpr uint8_t MAX_CREATION_RETRIES { 3 };
    _webViewCreationPending = false;
    if (_webViewCreated || _webViewCreationRetryScheduled ||
            _webViewCreationRetries >= MAX_CREATION_RETRIES) {
        return;
    }
    ++_webViewCreationRetries;
    _webViewCreationRetryScheduled = true;
    QTimer::singleShot(1000, this, [this] {
        _webViewCreationRetryScheduled = false;
        createWebView();
    });
}

void PicoWebViewItem::acceptCreationResult(bool created) {
    _webViewCreationPending = false;
    _webViewCreated = created;
    if (!created) {
        scheduleCreationRetry();
        return;
    }
    _webViewCreationRetries = 0;

    // URL and properties may have changed while Java was creating the WebView.
    // Reapply the current state after registration so no pending update is lost.
    setUseBackground(_useBackground);
    JniScope jni;
    if (!jni.env) { return; }
    jstring url = jni.env->NewString(
        reinterpret_cast<const jchar*>(_url.utf16()), _url.size());
    jstring agent = jni.env->NewString(
        reinterpret_cast<const jchar*>(_userAgent.utf16()), _userAgent.size());
    if (!url || !agent) {
        if (jni.env->ExceptionCheck()) { jni.env->ExceptionClear(); }
        if (url) { jni.env->DeleteLocalRef(url); }
        if (agent) { jni.env->DeleteLocalRef(agent); }
        return;
    }
    jvalue loadArgs[2]; loadArgs[0].j = reinterpret_cast<jlong>(this); loadArgs[1].l = url;
    callStatic("load", "(JLjava/lang/String;)V", loadArgs);
    jvalue agentArgs[2]; agentArgs[0].j = reinterpret_cast<jlong>(this); agentArgs[1].l = agent;
    callStatic("setUserAgent", "(JLjava/lang/String;)V", agentArgs);
    jvalue backgroundArgs[2]; backgroundArgs[0].j = reinterpret_cast<jlong>(this);
    backgroundArgs[1].z = _useBackground;
    callStatic("setUseBackground", "(JZ)V", backgroundArgs);
    jvalue resizeArgs[3]; resizeArgs[0].j = reinterpret_cast<jlong>(this);
    resizeArgs[1].i = pixelWidth(); resizeArgs[2].i = pixelHeight();
    callStatic("resize", "(JII)V", resizeArgs);
    jni.env->DeleteLocalRef(url);
    jni.env->DeleteLocalRef(agent);
}

QImage PicoWebViewItem::frameImage() const {
    QMutexLocker locker(&_imageMutex);
    return _image;
}

QString PicoWebViewItem::frameSource() const {
    quint64 frameSerial { 0 };
    {
        QMutexLocker locker(&_imageMutex);
        // Transparency is valid Web content. In particular, a page may use a
        // transparent background or leave its centre empty while still drawing
        // controls elsewhere. The presence of a copied frame, rather than one
        // arbitrarily sampled pixel, is the readiness signal.
        if (_image.isNull()) {
            return {};
        }
        frameSerial = _frameSerial;
    }
    return QStringLiteral("image://pico-web/%1/%2")
        .arg(reinterpret_cast<quintptr>(this), 0, 16).arg(frameSerial);
}

void PicoWebViewItem::acceptFrame(const void* pixels, qsizetype byteCount, int width, int height) {
    constexpr qsizetype BYTES_PER_PIXEL { 4 };
    if (!pixels || width <= 0 || height <= 0 ||
            width > std::numeric_limits<qsizetype>::max() / height / BYTES_PER_PIXEL ||
            byteCount < static_cast<qsizetype>(width) * height * BYTES_PER_PIXEL) {
        return;
    }
    {
        QMutexLocker locker(&_imageMutex);
        _image = QImage(static_cast<const uchar*>(pixels), width, height,
                        QImage::Format_ARGB32).copy();
        ++_frameSerial;
    }
}

int PicoWebViewItem::pixelWidth() const { return qMax(1, qRound(width())); }
int PicoWebViewItem::pixelHeight() const { return qMax(1, qRound(height())); }

void PicoWebViewItem::geometryChanged(const QRectF& n, const QRectF& o) {
    QQuickItem::geometryChanged(n, o);
    if (n.size().toSize() != o.size().toSize()) {
        if (!_webViewCreated) {
            createWebView();
            return;
        }
        jvalue args[3]; args[0].j = reinterpret_cast<jlong>(this);
        args[1].i = pixelWidth(); args[2].i = pixelHeight();
        callStatic("resize", "(JII)V", args);
    }
}

void PicoWebViewItem::sendPointer(int action, const QPointF& p) {
    QPointF webPosition = p;
    {
        QMutexLocker locker(&_imageMutex);
        if (!_image.isNull() && width() > 0.0 && height() > 0.0) {
            webPosition.setX(p.x() * _image.width() / width());
            webPosition.setY(p.y() * _image.height() / height());
        }
    }
    jvalue args[4]; args[0].j = reinterpret_cast<jlong>(this); args[1].i = action;
    args[2].f = webPosition.x(); args[3].f = webPosition.y();
    callStatic("pointer", "(JIFF)V", args);
}

void PicoWebViewItem::hoverEnterEvent(QHoverEvent* e) { sendPointer(9, e->posF()); e->accept(); }
void PicoWebViewItem::hoverMoveEvent(QHoverEvent* e) { sendPointer(7, e->posF()); e->accept(); }
void PicoWebViewItem::hoverLeaveEvent(QHoverEvent* e) { sendPointer(10, e->posF()); e->accept(); }
void PicoWebViewItem::mousePressEvent(QMouseEvent* e) {
    _pointerPressed = true;
    sendPointer(0, e->localPos());
    e->accept();
}
void PicoWebViewItem::mouseMoveEvent(QMouseEvent* e) { sendPointer(2, e->localPos()); e->accept(); }
void PicoWebViewItem::mouseReleaseEvent(QMouseEvent* e) {
    sendPointer(1, e->localPos());
    _pointerPressed = false;
    e->accept();
}
void PicoWebViewItem::mouseUngrabEvent() {
    if (_pointerPressed) {
        sendPointer(3, QPointF());
        _pointerPressed = false;
    }
}
void PicoWebViewItem::wheelEvent(QWheelEvent* e) {
    QPointF webPosition = e->position();
    {
        QMutexLocker locker(&_imageMutex);
        if (!_image.isNull() && width() > 0.0 && height() > 0.0) {
            webPosition.setX(webPosition.x() * _image.width() / width());
            webPosition.setY(webPosition.y() * _image.height() / height());
        }
    }
    jvalue args[4]; args[0].j = reinterpret_cast<jlong>(this);
    args[1].f = webPosition.x(); args[2].f = webPosition.y();
    args[3].f = e->angleDelta().y() / 120.0f;
    callStatic("scroll", "(JFFF)V", args); e->accept();
}

extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_OffscreenWebView_nativeFrame(JNIEnv* env, jclass, jlong handle,
                                                   jobject buffer, jint width, jint height) {
    QMutexLocker locker(&itemRegistryMutex);
    auto* item = itemRegistry.value(handle, nullptr);
    if (item && buffer) {
        item->acceptFrame(env->GetDirectBufferAddress(buffer),
                          env->GetDirectBufferCapacity(buffer), width, height);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_OffscreenWebView_nativeCreationFinished(
        JNIEnv*, jclass, jlong handle, jboolean created) {
    QMutexLocker locker(&itemRegistryMutex);
    QPointer<PicoWebViewItem> item(itemRegistry.value(handle, nullptr));
    if (item) {
        QMetaObject::invokeMethod(item, [item, created] {
            if (item) { item->acceptCreationResult(created); }
        }, Qt::QueuedConnection);
    }
}
