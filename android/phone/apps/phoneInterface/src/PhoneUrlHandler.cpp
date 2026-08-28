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

#include "AndroidHelper.h"
#include "PhoneLifecycleHandoff.h"
#include "PhonePendingHandoff.h"
#include "PhoneTouchUiMetrics.h"
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
        if (!phone::updateTouchUiRuntimeMetrics(touchUiMetricsMap(_pending))) {
            return;
        }
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

class PendingFlyingOverrideDelivery final : public QObject {
public:
    explicit PendingFlyingOverrideDelivery(QCoreApplication* application)
        : QObject(application) {
        auto& helper = AndroidHelper::instance();
        connect(&helper, &AndroidHelper::qtAppLoadComplete,
                this, [this]() { deliverIfReady(); });
    }

    void submit(int mode) {
        _pendingMode = mode;
        deliverIfReady();
    }

private:
    void deliverIfReady() {
        if (_pendingMode < -1 || !AndroidHelper::instance().isLoadComplete()) {
            return;
        }
        if (AndroidHelper::instance().setPhoneE2eFlyingEnabledOverride(
                _pendingMode)) {
            _pendingMode = NO_PENDING_MODE;
        }
    }

    static constexpr int NO_PENDING_MODE = -2;
    int _pendingMode { NO_PENDING_MODE };
};

PendingFlyingOverrideDelivery* flyingOverrideDelivery(
        QCoreApplication* application) {
    static QPointer<PendingFlyingOverrideDelivery> delivery;
    if (!delivery) {
        delivery = new PendingFlyingOverrideDelivery(application);
    }
    return delivery;
}

class PendingLifecycleDelivery final : public QObject {
public:
    explicit PendingLifecycleDelivery(QCoreApplication* application)
        : QObject(application) {
        auto& helper = AndroidHelper::instance();
        connect(&helper, &AndroidHelper::qtAppLoadComplete,
                this, [this]() { apply(_handoff.markReady()); });
        if (helper.isLoadComplete()) {
            apply(_handoff.markReady());
        }
    }

    void submit(bool foreground) {
        apply(_handoff.setForeground(foreground));
    }

private:
    static void apply(phone::LifecycleHandoff::Action action) {
        auto& helper = AndroidHelper::instance();
        switch (action) {
            case phone::LifecycleHandoff::Action::EnterBackground:
                helper.notifyEnterBackground();
                break;
            case phone::LifecycleHandoff::Action::EnterForeground:
                helper.notifyEnterForeground();
                break;
            case phone::LifecycleHandoff::Action::None:
                break;
        }
    }

    phone::LifecycleHandoff _handoff;
};

PendingLifecycleDelivery* lifecycleDelivery(QCoreApplication* application) {
    static QPointer<PendingLifecycleDelivery> delivery;
    if (!delivery) {
        delivery = new PendingLifecycleDelivery(application);
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

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneInterfaceActivity_nativeSetForegroundState(
        JNIEnv* /* env */, jclass /* activityClass */, jboolean foreground) {
    auto* application = QCoreApplication::instance();
    if (!application) {
        return JNI_FALSE;
    }

    // Activity callbacks run on Android's UI thread. Preserve their order but
    // hand ownership to Qt asynchronously, where AndroidHelper drives the
    // established Application background/foreground (including audio) paths.
    const bool ownedByNative = QMetaObject::invokeMethod(
        application,
        [application, foreground]() {
            lifecycleDelivery(application)->submit(foreground == JNI_TRUE);
        },
        Qt::QueuedConnection);
    return ownedByNative ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneInterfaceActivity_nativeSetE2eFlyingOverride(
        JNIEnv* /* env */, jclass /* activityClass */, jint mode) {
    auto* application = QCoreApplication::instance();
    if (!application || mode < -1 || mode > 1) {
        return JNI_FALSE;
    }

    // Android invokes this from Activity.onResume while Qt can still be
    // constructing its display surface. Taking ownership asynchronously keeps
    // the Android UI thread available to that startup path. The delivery waits
    // for Application's established load-complete boundary before touching the
    // avatar runtime.
    const bool ownedByNative = QMetaObject::invokeMethod(
        application,
        [application, mode]() {
            flyingOverrideDelivery(application)->submit(mode);
        },
        Qt::QueuedConnection);
    return ownedByNative ? JNI_TRUE : JNI_FALSE;
}
