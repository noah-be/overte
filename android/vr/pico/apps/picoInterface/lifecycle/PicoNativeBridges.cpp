// SPDX-License-Identifier: Apache-2.0
#include "PicoNativeBridges.h"
#include <jni.h>

extern "C" JavaVM* overtePicoOpenXRJavaVm();
extern "C" jobject overtePicoOpenXRAcquireActivity(JNIEnv*);

extern "C" jboolean Java_org_overte_pico_PicoClientVisibility_publish(JNIEnv*, jclass, jlong, jboolean);
extern "C" jboolean Java_org_overte_pico_PicoAccessibilityBridge_nativeRequestFrame(
    JNIEnv*, jclass, jobject, jint, jint, jint);
extern "C" jboolean Java_org_overte_pico_PicoAccessibilityBridge_nativePerformAction(
    JNIEnv*, jclass, jint, jstring, jstring);

namespace overte::pico {
namespace {
class Environment {
public:
    explicit Environment(JavaVM* vm) : _vm(vm) {
        if (!vm) { return; }
        const auto result = vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
        if (result == JNI_EDETACHED) {
#ifdef __ANDROID__
            attached = vm->AttachCurrentThread(&env, nullptr) == JNI_OK;
#else
            attached = vm->AttachCurrentThread(reinterpret_cast<void**>(&env), nullptr) == JNI_OK;
#endif
            if (!attached) { env = nullptr; }
        } else if (result != JNI_OK) { env = nullptr; }
        if (env && env->PushLocalFrame(32) < 0) { env->ExceptionClear(); env = nullptr; }
    }
    ~Environment() {
        if (env) { env->PopLocalFrame(nullptr); }
        if (attached) { _vm->DetachCurrentThread(); }
    }
    JNIEnv* env { nullptr };
private:
    JavaVM* _vm;
    bool attached { false };
};
}
bool installNativeBridges() {
    // Qt loads the full client through its own loader. Android's app loader
    // cannot resolve that DSO's JNI exports merely by their Java_* names.
    // Bind the exact app classes after the full client is actually loaded;
    // the existing Java retry retains the latest lifecycle observation.
    Environment scope(overtePicoOpenXRJavaVm());
    auto env = scope.env;
    if (!env) { return false; }
    jobject activity = overtePicoOpenXRAcquireActivity(env);
    if (!activity) { if (env->ExceptionCheck()) { env->ExceptionClear(); } return false; }
    const auto activityClass = env->GetObjectClass(activity);
    const auto localActivity = env->NewLocalRef(activity);
    env->DeleteGlobalRef(activity);
    // Context.getClassLoader() can differ from the actual Activity class's
    // loader under Qt. Resolve the classes beside the live Activity itself.
    const auto classClass = activityClass ? env->GetObjectClass(activityClass) : nullptr;
    const auto getLoader = classClass
        ? env->GetMethodID(classClass, "getClassLoader", "()Ljava/lang/ClassLoader;") : nullptr;
    const auto loader = getLoader ? env->CallObjectMethod(activityClass, getLoader) : nullptr;
    if (env->ExceptionCheck()) { env->ExceptionClear(); return false; }
    if (!loader) { return false; }
    const auto loaderClass = env->GetObjectClass(loader);
    const auto loadClass = loaderClass
        ? env->GetMethodID(loaderClass, "loadClass", "(Ljava/lang/String;)Ljava/lang/Class;") : nullptr;
    if (env->ExceptionCheck()) { env->ExceptionClear(); return false; }
    if (!loadClass) { return false; }
    const auto bind = [&](const char* name, JNINativeMethod* methods, jint count) -> jclass {
        const auto className = env->NewStringUTF(name);
        const auto klass = className
            ? static_cast<jclass>(env->CallObjectMethod(loader, loadClass, className)) : nullptr;
        if (env->ExceptionCheck()) { env->ExceptionClear(); return nullptr; }
        if (!klass) { return nullptr; }
        const bool ok = env->RegisterNatives(klass, methods, count) == JNI_OK;
        if (env->ExceptionCheck()) { env->ExceptionClear(); return nullptr; }
        return ok ? klass : nullptr;
    };
    JNINativeMethod visibility[] = {
        { const_cast<char*>("publish"), const_cast<char*>("(JZ)Z"),
          reinterpret_cast<void*>(&Java_org_overte_pico_PicoClientVisibility_publish) },
    };
    JNINativeMethod accessibility[] = {
        { const_cast<char*>("nativeRequestFrame"), const_cast<char*>("(Lorg/overte/pico/PicoAccessibilityBridge;III)Z"),
          reinterpret_cast<void*>(&Java_org_overte_pico_PicoAccessibilityBridge_nativeRequestFrame) },
        { const_cast<char*>("nativePerformAction"), const_cast<char*>("(ILjava/lang/String;Ljava/lang/String;)Z"),
          reinterpret_cast<void*>(&Java_org_overte_pico_PicoAccessibilityBridge_nativePerformAction) },
    };
    const auto visibilityClass = bind("org.overte.pico.PicoClientVisibility", visibility, 1);
    const auto accessibilityClass = bind("org.overte.pico.PicoAccessibilityBridge", accessibility, 2);
    if (!visibilityClass || !accessibilityClass || !localActivity) { return false; }
    const auto ready = env->GetStaticMethodID(visibilityClass, "nativeBindingsReady", "(Ljava/lang/Object;)Z");
    if (env->ExceptionCheck()) { env->ExceptionClear(); return false; }
    if (!ready) { return false; }
    const bool admitted = env->CallStaticBooleanMethod(visibilityClass, ready, localActivity) == JNI_TRUE;
    if (env->ExceptionCheck()) { env->ExceptionClear(); return false; }
    // Admission is still distinct from GUI-thread application. That receiver
    // applies the existing generation and combined visibility gates.
    return admitted;
}
}
