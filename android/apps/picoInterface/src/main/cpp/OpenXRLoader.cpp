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
    jobject newActivity = env->NewGlobalRef(activity);
    if (!newActivity) {
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not retain Android Activity");
        return JNI_FALSE;
    }

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
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not inspect Android Activity");
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
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not find getApplicationContext");
        return JNI_FALSE;
    }

    jobject context = env->CallObjectMethod(activity, getApplicationContext);
    if (!context || env->ExceptionCheck()) {
        env->ExceptionClear();
        if (context) {
            env->DeleteLocalRef(context);
        }
        env->DeleteGlobalRef(newActivity);
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not obtain application Context");
        return JNI_FALSE;
    }

    jobject newApplicationContext = env->NewGlobalRef(context);
    env->DeleteLocalRef(context);
    if (!newApplicationContext) {
        env->DeleteGlobalRef(newActivity);
        __android_log_write(
                ANDROID_LOG_ERROR, LOG_TAG, "Could not retain application Context");
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
        __android_log_print(
                ANDROID_LOG_ERROR,
                LOG_TAG,
                "xrInitializeLoaderKHR failed: %d",
                result);
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
    // A superseded Activity can finish after its replacement has initialized.
    // Release only the global reference that represents this exact instance.
    if (loaderActivity && env->IsSameObject(loaderActivity, activity)) {
        env->DeleteGlobalRef(loaderActivity);
        loaderActivity = nullptr;
    }
}
