#include "PicoWebViewItem.h"

#include <QHoverEvent>
#include <QHash>
#include <QMouseEvent>
#include <QMutexLocker>
#include <QQmlEngine>
#include <QQuickImageProvider>
#include <QWheelEvent>
#include <QtQml/qqml.h>
#include <jni.h>
#include <android/log.h>

extern "C" JavaVM* overtePicoOpenXRJavaVm();

namespace {
constexpr const char* CLASS_NAME = "org/overte/pico/OffscreenWebView";
QMutex itemRegistryMutex;
QHash<jlong, PicoWebViewItem*> itemRegistry;

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
        JavaVM* vm = overtePicoOpenXRJavaVm();
        if (!vm) { return; }
        if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
            attached = vm->AttachCurrentThread(&env, nullptr) == JNI_OK;
        }
    }
    ~JniScope() {
        if (attached) { overtePicoOpenXRJavaVm()->DetachCurrentThread(); }
    }
};

void callStatic(const char* name, const char* signature, jvalue* args) {
    JniScope jni;
    if (!jni.env) { return; }
    jclass clazz = jni.env->FindClass(CLASS_NAME);
    if (!clazz) {
        __android_log_print(ANDROID_LOG_ERROR, "OverteWebEntity", "Cannot find Java WebView bridge class");
        jni.env->ExceptionClear();
        return;
    }
    jmethodID method = jni.env->GetStaticMethodID(clazz, name, signature);
    if (method) {
        jni.env->CallStaticVoidMethodA(clazz, method, args);
    } else {
        __android_log_print(ANDROID_LOG_ERROR, "OverteWebEntity", "Cannot find Java WebView bridge method %s", name);
    }
    if (jni.env->ExceptionCheck()) {
        __android_log_print(ANDROID_LOG_ERROR, "OverteWebEntity", "Java WebView bridge method %s failed", name);
        jni.env->ExceptionDescribe();
        jni.env->ExceptionClear();
    }
    jni.env->DeleteLocalRef(clazz);
}

void registerPicoWebViewType() {
    qmlRegisterType<PicoWebViewItem>("Overte.Pico", 1, 0, "PicoWebView");
}
}
Q_COREAPP_STARTUP_FUNCTION(registerPicoWebViewType)

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
    jvalue args[1]; args[0].j = reinterpret_cast<jlong>(this);
    callStatic("destroy", "(J)V", args);
}

void PicoWebViewItem::setUrl(const QString& value) {
    if (_url == value) { return; }
    _url = value;
    emit urlChanged();
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
    createWebView();
}

void PicoWebViewItem::componentComplete() {
    QQuickItem::componentComplete();
    if (auto* engine = qmlEngine(this); engine && !engine->imageProvider("pico-web")) {
        engine->addImageProvider("pico-web", new PicoWebImageProvider);
    }
    createWebView();
}

void PicoWebViewItem::createWebView() {
    if (!isComponentComplete()) { return; }
    JniScope jni;
    if (!jni.env) { return; }
    jstring url = jni.env->NewString(reinterpret_cast<const jchar*>(_url.utf16()), _url.size());
    jstring agent = jni.env->NewString(reinterpret_cast<const jchar*>(_userAgent.utf16()), _userAgent.size());
    jvalue args[5];
    args[0].j = reinterpret_cast<jlong>(this); args[1].i = pixelWidth(); args[2].i = pixelHeight();
    args[3].l = url; args[4].l = agent;
    callStatic("create", "(JIILjava/lang/String;Ljava/lang/String;)V", args);
    jni.env->DeleteLocalRef(url); jni.env->DeleteLocalRef(agent);
}

QImage PicoWebViewItem::frameImage() const {
    QMutexLocker locker(&_imageMutex);
    return _image;
}

QString PicoWebViewItem::frameSource() const {
    quint64 frameSerial { 0 };
    {
        QMutexLocker locker(&_imageMutex);
        if (_image.isNull() || !qAlpha(_image.pixel(_image.width() / 2, _image.height() / 2))) {
            return {};
        }
        frameSerial = _frameSerial;
    }
    return QStringLiteral("image://pico-web/%1/%2")
        .arg(reinterpret_cast<quintptr>(this), 0, 16).arg(frameSerial);
}

void PicoWebViewItem::acceptFrame(const void* pixels, int width, int height) {
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

void PicoWebViewItem::hoverEnterEvent(QHoverEvent* e) { sendPointer(7, e->posF()); e->accept(); }
void PicoWebViewItem::hoverMoveEvent(QHoverEvent* e) { sendPointer(7, e->posF()); e->accept(); }
void PicoWebViewItem::hoverLeaveEvent(QHoverEvent* e) { sendPointer(10, e->posF()); e->accept(); }
void PicoWebViewItem::mousePressEvent(QMouseEvent* e) { sendPointer(0, e->localPos()); e->accept(); }
void PicoWebViewItem::mouseMoveEvent(QMouseEvent* e) { sendPointer(2, e->localPos()); e->accept(); }
void PicoWebViewItem::mouseReleaseEvent(QMouseEvent* e) { sendPointer(1, e->localPos()); e->accept(); }
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
    args[1].f = webPosition.x(); args[2].f = webPosition.y(); args[3].f = e->angleDelta().y() / 120.0f;
    callStatic("scroll", "(JFFF)V", args); e->accept();
}

extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_OffscreenWebView_nativeFrame(JNIEnv* env, jclass, jlong handle,
                                                   jobject buffer, jint width, jint height) {
    QMutexLocker locker(&itemRegistryMutex);
    auto* item = itemRegistry.value(handle, nullptr);
    if (item && buffer) { item->acceptFrame(env->GetDirectBufferAddress(buffer), width, height); }
}
