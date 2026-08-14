//
// Runtime URL hand-off from Android's activity thread to the Qt application.
//

#include <jni.h>

#include <utility>

#include <QCoreApplication>
#include <QMetaObject>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QThread>
#include <QVariantMap>

#include <DependencyManager.h>
#include "AndroidHelper.h"
#include "PhonePendingHandoff.h"
#include "PhoneTouchUiMetrics.h"
#include "ui/TabletScriptingInterface.h"
#include "ui/PhoneDialogRouter.h"

namespace {

QString fromJavaString(JNIEnv* env, jstring value) {
    if (!env || !value) {
        return {};
    }

    const jchar* characters = env->GetStringChars(value, nullptr);
    if (!characters) {
        // GetStringChars may leave an OutOfMemoryError pending. Do not perform
        // further JNI work in that case; Java will receive the exception.
        return {};
    }

    const jsize length = env->GetStringLength(value);
    const QString result = QString::fromUtf16(
        reinterpret_cast<const ushort*>(characters), length);
    env->ReleaseStringChars(value, characters);
    return result;
}

// One application-owned delivery object preserves "latest pending URL" while
// native startup is incomplete. AndroidHelper's load-complete notification is
// emitted only after Application has installed its Android connections and
// startup services, making it a stronger boundary than dependency existence.
class PendingUrlDelivery final : public QObject {
public:
    explicit PendingUrlDelivery(QCoreApplication* application) : QObject(application) {
        auto& helper = AndroidHelper::instance();
        connect(&helper, &AndroidHelper::qtAppLoadComplete,
                this, [this]() { deliverIfReady(); });
    }

    void submit(QString url) {
        const bool valid = !url.isEmpty();
        _pending.replace(std::move(url), valid);
        deliverIfReady();
    }

private:
    void deliverIfReady() {
        QString url;
        if (!_pending.takeIfReady(AndroidHelper::instance().isLoadComplete(), url)) {
            return;
        }
        // Keep the established Application canAcceptURL/acceptURL policy as
        // the sole navigation boundary. Supported phone links have already
        // been normalized to the native hifi scheme by Java.
        AndroidHelper::instance().processURL(url);
    }

    phone::PendingHandoff<QString> _pending;
};

PendingUrlDelivery* urlDelivery(QCoreApplication* application) {
    static QPointer<PendingUrlDelivery> delivery;
    if (!delivery) {
        delivery = new PendingUrlDelivery(application);
    }
    return delivery;
}

QVariantMap touchUiMetricsMap(const phone::TouchUiMetrics& metrics) {
    QVariantMap result;
    result.insert("valid", metrics.valid);
    result.insert("surfaceWidth", metrics.surfaceWidth);
    result.insert("surfaceHeight", metrics.surfaceHeight);
    result.insert("safeInsetLeft", metrics.safeInsetLeft);
    result.insert("safeInsetTop", metrics.safeInsetTop);
    result.insert("safeInsetRight", metrics.safeInsetRight);
    result.insert("safeInsetBottom", metrics.safeInsetBottom);
    result.insert("imeInsetBottom", metrics.imeInsetBottom);
    result.insert("density", metrics.density);
    result.insert("fontScale", metrics.fontScale);
    result.insert("contentScale", metrics.contentScale);
    result.insert("keyboardVisible", metrics.keyboardVisible);
    result.insert("hoverSupported", metrics.hoverSupported);
    result.insert("hardwareKeyboardSupported", metrics.hardwareKeyboardSupported);
    result.insert("hapticsSupported", metrics.hapticsSupported);
    result.insert("landscape", metrics.surfaceWidth >= metrics.surfaceHeight);
    return result;
}

class PendingTouchUiMetricsDelivery final : public QObject {
public:
    explicit PendingTouchUiMetricsDelivery(QCoreApplication* application)
        : QObject(application) {
        auto& helper = AndroidHelper::instance();
        connect(&helper, &AndroidHelper::qtAppLoadComplete,
                this, [this]() { deliverIfReady(); });
    }

    void submit(const phone::TouchUiMetrics& metrics) {
        _pending = metrics;
        _hasPending = metrics.valid;
        deliverIfReady();
    }

private:
    void deliverIfReady() {
        if (!_hasPending || !AndroidHelper::instance().isLoadComplete()) {
            return;
        }
        auto tablet = DependencyManager::get<TabletScriptingInterface>();
        if (!tablet) {
            return;
        }
        tablet->setTouchUiRuntimeMetrics(touchUiMetricsMap(_pending));
        _hasPending = false;
    }

    phone::TouchUiMetrics _pending;
    bool _hasPending { false };
};

PendingTouchUiMetricsDelivery* touchUiMetricsDelivery(QCoreApplication* application) {
    static QPointer<PendingTouchUiMetricsDelivery> delivery;
    if (!delivery) {
        delivery = new PendingTouchUiMetricsDelivery(application);
    }
    return delivery;
}

} // namespace

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneInterfaceActivity_nativeProcessUrl(
        JNIEnv* env, jclass /* activityClass */, jstring value) {
    const QString url = fromJavaString(env, value).trimmed();
    auto* application = QCoreApplication::instance();
    if (url.isEmpty() || !application) {
        return JNI_FALSE;
    }

    // Transfer ownership to Qt instead of blocking Android's UI thread during
    // native startup. The native owner retains only the latest pending URL and
    // waits for Application's established load-complete boundary.
    const bool ownedByNative = QMetaObject::invokeMethod(
        application,
        [application, url]() {
            urlDelivery(application)->submit(url);
        },
        Qt::QueuedConnection);
    return ownedByNative ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneInterfaceActivity_nativeHandleBack(
        JNIEnv* /* env */, jclass /* activityClass */) {
    auto* application = QCoreApplication::instance();
    if (!application) {
        return JNI_FALSE;
    }

    bool consumed { false };
    const auto closePhoneUi = [&consumed]() {
        consumed = phone::closeTopmostDialog();
    };

    bool invoked { true };
    if (QThread::currentThread() == application->thread()) {
        closePhoneUi();
    } else {
        invoked = QMetaObject::invokeMethod(
            application, closePhoneUi, Qt::BlockingQueuedConnection);
    }
    return invoked && consumed ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneInterfaceActivity_nativeUpdateTouchUiMetrics(
        JNIEnv* /* env */,
        jclass /* activityClass */,
        jint surfaceWidth,
        jint surfaceHeight,
        jint safeInsetLeft,
        jint safeInsetTop,
        jint safeInsetRight,
        jint safeInsetBottom,
        jint imeInsetBottom,
        jfloat density,
        jfloat fontScale,
        jfloat contentScale,
        jboolean keyboardVisible,
        jboolean hoverSupported,
        jboolean hardwareKeyboardSupported,
        jboolean hapticsSupported) {
    const auto metrics = phone::TouchUiMetrics::fromUntrusted(
        surfaceWidth,
        surfaceHeight,
        safeInsetLeft,
        safeInsetTop,
        safeInsetRight,
        safeInsetBottom,
        imeInsetBottom,
        density,
        fontScale,
        contentScale,
        keyboardVisible == JNI_TRUE,
        hoverSupported == JNI_TRUE,
        hardwareKeyboardSupported == JNI_TRUE,
        hapticsSupported == JNI_TRUE);
    auto* application = QCoreApplication::instance();
    if (!metrics.valid || !application) {
        return JNI_FALSE;
    }

    const bool ownedByNative = QMetaObject::invokeMethod(
        application,
        [application, metrics]() {
            touchUiMetricsDelivery(application)->submit(metrics);
        },
        Qt::QueuedConnection);
    return ownedByNative ? JNI_TRUE : JNI_FALSE;
}
