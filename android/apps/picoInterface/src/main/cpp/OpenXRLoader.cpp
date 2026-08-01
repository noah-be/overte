#define XR_USE_PLATFORM_ANDROID

#include <jni.h>
#include <android/log.h>
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

namespace {
constexpr const char* LOG_TAG = "OvertePico";
JavaVM* loaderJavaVm = nullptr;
jobject loaderApplicationContext = nullptr;
jobject loaderActivity = nullptr;
}

extern "C" JavaVM* overtePicoOpenXRJavaVm() {
    return loaderJavaVm;
}

extern "C" jobject overtePicoOpenXRApplicationContext() {
    return loaderApplicationContext;
}

extern "C" jobject overtePicoOpenXRActivity() {
    return loaderActivity;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoInterfaceActivity_initializeOpenXRLoader(
        JNIEnv* env, jobject activity) {
    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) != JNI_OK) {
        __android_log_write(ANDROID_LOG_ERROR, LOG_TAG, "Could not obtain JavaVM");
        return JNI_FALSE;
    }
    loaderJavaVm = vm;

    loaderActivity = env->NewGlobalRef(activity);
    if (!loaderActivity) {
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not retain Android Activity");
        return JNI_FALSE;
    }

    jmethodID getApplicationContext = env->GetMethodID(
            env->GetObjectClass(activity),
            "getApplicationContext",
            "()Landroid/content/Context;");
    if (!getApplicationContext) {
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not find getApplicationContext");
        return JNI_FALSE;
    }

    jobject context = env->CallObjectMethod(activity, getApplicationContext);
    if (!context || env->ExceptionCheck()) {
        env->ExceptionClear();
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not obtain application Context");
        return JNI_FALSE;
    }

    PFN_xrInitializeLoaderKHR initializeLoader = nullptr;
    XrResult result = xrGetInstanceProcAddr(
            XR_NULL_HANDLE,
            "xrInitializeLoaderKHR",
            reinterpret_cast<PFN_xrVoidFunction*>(&initializeLoader));
    if (XR_FAILED(result) || !initializeLoader) {
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "xrInitializeLoaderKHR is unavailable");
        env->DeleteLocalRef(context);
        return JNI_FALSE;
    }

    loaderApplicationContext = env->NewGlobalRef(context);
    env->DeleteLocalRef(context);
    if (!loaderApplicationContext) {
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not retain application Context");
        return JNI_FALSE;
    }

    XrLoaderInitInfoAndroidKHR loaderInfo {
        XR_TYPE_LOADER_INIT_INFO_ANDROID_KHR,
        nullptr,
        vm,
        loaderApplicationContext
    };
    result = initializeLoader(
            reinterpret_cast<const XrLoaderInitInfoBaseHeaderKHR*>(&loaderInfo));

    if (XR_FAILED(result)) {
        env->DeleteGlobalRef(loaderApplicationContext);
        loaderApplicationContext = nullptr;
        env->DeleteGlobalRef(loaderActivity);
        loaderActivity = nullptr;
        __android_log_print(
                ANDROID_LOG_ERROR,
                LOG_TAG,
                "xrInitializeLoaderKHR failed: %d",
                result);
        return JNI_FALSE;
    }

    return JNI_TRUE;
}
