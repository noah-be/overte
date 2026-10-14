// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <jni.h>
#include <cassert>
#include <iostream>
extern "C" void Java_org_overte_web_EmbeddedWebView_nativeInitialize(JNIEnv*, jclass);
extern "C" void Java_org_overte_web_EmbeddedWebView_nativeForeground(JNIEnv*, jclass, jboolean);

int main(int argc, char** argv) {
    assert(argc == 2 || argc == 3);
    const bool incompatible = argc == 3;
    QGuiApplication app(argc, argv);
    std::string classPath = std::string("-Djava.class.path=") + argv[1];
    JavaVMOption option { classPath.data(), nullptr };
    JavaVMInitArgs arguments { JNI_VERSION_1_8, 1, &option, JNI_FALSE };
    JavaVM* vm = nullptr; JNIEnv* env = nullptr;
    assert(JNI_CreateJavaVM(&vm, reinterpret_cast<void**>(&env), &arguments) == JNI_OK);
    jclass production = env->FindClass("org/overte/web/EmbeddedWebView");
    if (env->ExceptionCheck()) env->ExceptionDescribe();
    assert(production);
    Java_org_overte_web_EmbeddedWebView_nativeInitialize(env, production);
    Java_org_overte_web_EmbeddedWebView_nativeForeground(env, production, JNI_TRUE);
    {
        QQmlEngine engine;
        QQmlComponent component(&engine);
        component.setData("import QtQuick 2.7\nimport Overte.Android 1.0\nNativeWebView { width: 360; height: 240; sourceIdentity: 'pico:jni'; url: 'https://example.invalid/pico-jni'; userAgent: 'Pico JNI production binding test' }", QUrl());
        QObject* surface = component.create();
        assert(surface);
        jclass probe = env->FindClass("org/overte/pico/tests/JniCreateProbe");
        assert(probe);
        jmethodID verify = env->GetStaticMethodID(probe, "verify", "()Z");
        assert(verify);
        bool captured = env->CallStaticBooleanMethod(probe, verify);
        if (env->ExceptionCheck()) env->ExceptionDescribe();
        assert(!env->ExceptionCheck() && captured != incompatible);
        delete surface;
    }
    std::cout << (incompatible ? "PASS production JNI rejects previous create ABI without the editor argument\n" : "PASS actual Pico-linked C++ JNI resolves production Java create and forwards separate bridge/editor scripts; Android scheduling boundary substituted\n");
    vm->DestroyJavaVM();
}
