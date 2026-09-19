#define XR_USE_PLATFORM_ANDROID

#include <jni.h>
#include "../../../security/RedactingDiagnostics.h"
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#include <mutex>

namespace {
JavaVM* loaderJavaVm = nullptr;
jobject loaderApplicationContext = nullptr;
jobject loaderActivity = nullptr;
std::mutex loaderMutex;
}

extern "C" JavaVM* overtePicoOpenXRJavaVm() {
    std::lock_guard<std::mutex> guard(loaderMutex);
    return loaderJavaVm;
}

extern "C" jobject overtePicoOpenXRAcquireActivity(JNIEnv* env) {
    std::lock_guard<std::mutex> guard(loaderMutex);
    return loaderActivity ? env->NewGlobalRef(loaderActivity) : nullptr;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoInterfaceActivity_initializeOpenXRLoader(
        JNIEnv* env, jobject activity) {
    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) != JNI_OK) {
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }
    jobject newActivity = env->NewGlobalRef(activity);
    if (!newActivity) {
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }

    // Serialize process-global loader publication with Activity teardown. Any
    // native consumer obtains its own global reference while holding this lock.
    std::lock_guard<std::mutex> guard(loaderMutex);

    // The loader is process-global while Android may recreate the Activity.
    // Keep the initialized application context and only refresh the Activity
    // reference instead of asking the runtime to initialize twice.
    if (loaderJavaVm == vm && loaderApplicationContext) {
        if (loaderActivity) {
            env->DeleteGlobalRef(loaderActivity);
        }
        loaderActivity = newActivity;
        return JNI_TRUE;
    }

    jclass activityClass = env->GetObjectClass(activity);
    if (!activityClass) {
        env->DeleteGlobalRef(newActivity);
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }
    jmethodID getApplicationContext = env->GetMethodID(
            activityClass,
            "getApplicationContext",
            "()Landroid/content/Context;");
    env->DeleteLocalRef(activityClass);
    if (!getApplicationContext) {
        if (env->ExceptionCheck()) {
            env->ExceptionClear();
        }
        env->DeleteGlobalRef(newActivity);
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }

    jobject context = env->CallObjectMethod(activity, getApplicationContext);
    if (!context || env->ExceptionCheck()) {
        env->ExceptionClear();
        if (context) {
            env->DeleteLocalRef(context);
        }
        env->DeleteGlobalRef(newActivity);
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }

    jobject newApplicationContext = env->NewGlobalRef(context);
    env->DeleteLocalRef(context);
    if (!newApplicationContext) {
        env->DeleteGlobalRef(newActivity);
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }

    PFN_xrInitializeLoaderKHR initializeLoader = nullptr;
    XrResult result = xrGetInstanceProcAddr(
            XR_NULL_HANDLE,
            "xrInitializeLoaderKHR",
            reinterpret_cast<PFN_xrVoidFunction*>(&initializeLoader));
    if (XR_FAILED(result) || !initializeLoader) {
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        env->DeleteGlobalRef(newApplicationContext);
        env->DeleteGlobalRef(newActivity);
        return JNI_FALSE;
    }

    XrLoaderInitInfoAndroidKHR loaderInfo {
        XR_TYPE_LOADER_INIT_INFO_ANDROID_KHR,
        nullptr,
        vm,
        newApplicationContext
    };
    result = initializeLoader(
            reinterpret_cast<const XrLoaderInitInfoBaseHeaderKHR*>(&loaderInfo));

    if (XR_FAILED(result)) {
        env->DeleteGlobalRef(newApplicationContext);
        env->DeleteGlobalRef(newActivity);
        overte::pico::diagnosticError(overte::security::DiagnosticEvent::Redacted);
        return JNI_FALSE;
    }

    // Publish a fully initialized set only after every operation succeeds.
    // Activity recreation may invoke this again in the same process.
    if (loaderApplicationContext) {
        env->DeleteGlobalRef(loaderApplicationContext);
    }
    if (loaderActivity) {
        env->DeleteGlobalRef(loaderActivity);
    }
    loaderJavaVm = vm;
    loaderApplicationContext = newApplicationContext;
    loaderActivity = newActivity;

    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoInterfaceActivity_releaseOpenXRActivity(
        JNIEnv* env, jobject activity) {
    std::lock_guard<std::mutex> guard(loaderMutex);
    // A superseded Activity can finish after its replacement has initialized.
    // Release only the global reference that represents this exact instance.
    if (loaderActivity && env->IsSameObject(loaderActivity, activity)) {
        env->DeleteGlobalRef(loaderActivity);
        loaderActivity = nullptr;
    }
}
