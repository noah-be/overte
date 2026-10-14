#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Whole production Qt5 item/QML and real JVM JNI; Android WebView is a declared boundary."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
SOURCE = ROOT / "android/vr/pico/apps/picoInterface/src/PicoWebViewItem.cpp"


class LegacyWebQtTest(unittest.TestCase):
    def test_actual_qt_visibility_focus_frames_and_jni_epochs(self):
        qt = Path(os.environ.get("OVERTE_QT5_ROOT", str(Path.home() / ".local/overte-qt5/root")))
        environment = os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"}
        libraries = []
        if (qt / "usr/lib64/pkgconfig/Qt5Quick.pc").is_file():
            environment.update({"PKG_CONFIG_PATH": str(qt / "usr/lib64/pkgconfig"),
                                "PKG_CONFIG_SYSROOT_DIR": str(qt), "LD_LIBRARY_PATH": str(qt / "usr/lib64"),
                                "QML2_IMPORT_PATH": str(qt / "usr/lib64/qt5/qml"),
                                "QT_PLUGIN_PATH": str(qt / "usr/lib64/qt5/plugins")})
            tools = qt / "usr/lib64/qt5/bin"
            libraries = ["-L" + str(qt / "usr/lib64")]
        else:
            tools = Path(subprocess.check_output(["pkg-config", "--variable=host_bins", "Qt5Core"],
                                                 env=environment, text=True).strip())
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt5Quick"],
                                                   env=environment, text=True))
        jdk = Path(os.environ.get("JAVA_HOME", "/usr/lib/jvm/temurin-21-jdk"))
        with tempfile.TemporaryDirectory(prefix="pico-legacy-qt-jni-") as temporary:
            stage = Path(temporary)
            source = SOURCE
            qml = ROOT / "interface/resources/qml/+android_picoInterface/Web3DSurface.qml"
            original = os.environ.get("OVERTE_PICO_EDITOR_ORIGINAL") == "1"
            if original:
                source = stage / "original/src/PicoWebViewItem.cpp"
                source.parent.mkdir(parents=True)
                (source.parent.parent / "security").symlink_to(SOURCE.parent.parent / "security", target_is_directory=True)
                for name in ("PicoWebViewItem.cpp", "PicoWebViewItem.h"):
                    (source.parent / name).write_bytes(subprocess.check_output([
                        "git", "show", "5275305b6d4b97ae260baa668a57fdb01daabbc6:" +
                        str((SOURCE.parent / name).relative_to(ROOT))], cwd=ROOT))
                qml = stage / "original/qml/+android_picoInterface/Web3DSurface.qml"
                qml.parent.mkdir(parents=True)
                for name in ("Web3DSurface.qml", "PicoLegacyWebSurface.qml"):
                    (qml.parent / name).write_bytes(subprocess.check_output([
                        "git", "show", "5275305b6d4b97ae260baa668a57fdb01daabbc6:" +
                        "interface/resources/qml/+android_picoInterface/" + name], cwd=ROOT))
            controls = stage / "imports/controlsUit"
            controls.mkdir(parents=True)
            (controls / "qmldir").write_text("module controlsUit\nKeyboard 1.0 Keyboard.qml\n")
            # Actual wrapper/native item are exercised; the HMD keyboard renderer
            # is an explicit framework boundary, not a physical keyboard result.
            (controls / "Keyboard.qml").write_text("import QtQuick 2.7\nItem { property bool raised: false; property bool numeric: false; property bool password: false; height: raised ? 180 : 0 }\n")
            java = stage / "OffscreenWebView.java"
            # No Android calls are simulated as browser success. This peer only
            # records JNI commands and sends explicit lifecycle/frame callbacks.
            java.write_text('''package org.overte.pico;
import java.nio.ByteBuffer;
public class OffscreenWebView {
    public static long handle, epoch;
    public static int creates, destroys, visibility, focuses, edits, key, pointers;
    public static String text, committedText, composingText;
    public static boolean composing;
    public static boolean visible;
    private static native void nativeCreationFinished(long handle, boolean created);
    public static native void nativeLifecycle(long handle, long epoch, boolean rendering);
    public static native void nativeFrame(long handle, long epoch, ByteBuffer pixels, int width, int height);
    public static native void nativeEditorState(long handle,long epoch,long revision,boolean focused,boolean numeric,boolean password);
    public static void create(long h,int w,int height,String url,String agent,boolean background) {
        handle=h; epoch=0; ++creates; nativeCreationFinished(h,true);
    }
    public static void setVisible(long h,boolean value) { ++visibility; visible=value; nativeLifecycle(h,++epoch,value); }
    public static void destroy(long h) { ++destroys; }
    public static void load(long h,String url) { nativeLifecycle(h,++epoch,false); nativeLifecycle(h,++epoch,true); }
    public static void editText(long h,String value,boolean composition) { ++edits; text=value; composing=composition; if(composition) composingText=value; else committedText=value; }
    public static void editKey(long h,int value) { key=value; }
    public static void setUserAgent(long h,String agent) {}
    public static void setUseBackground(long h,boolean background) {}
    public static void resize(long h,int w,int height) {}
    public static void focus(long h,boolean value) { ++focuses; }
    public static void pointer(long h,int action,float x,float y) { ++pointers; }
}
''')
            subprocess.run([str(jdk / "bin/javac"), "-d", temporary, str(java)], check=True, timeout=30)
            cpp = stage / "probe.cpp"
            cpp.write_text(r'''
#include "PicoWebViewItem.h"
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QTimer>
#include <QEventLoop>
#include <QPointer>
#include <jni.h>
#include <cassert>
#include <cstdio>
#include <vector>
extern "C" {
void Java_org_overte_pico_OffscreenWebView_nativeInitialize(JNIEnv*,jclass);
void Java_org_overte_pico_OffscreenWebView_nativeCreationFinished(JNIEnv*,jclass,jlong,jboolean);
void Java_org_overte_pico_OffscreenWebView_nativeLifecycle(JNIEnv*,jclass,jlong,jlong,jboolean);
void Java_org_overte_pico_OffscreenWebView_nativeFrame(JNIEnv*,jclass,jlong,jlong,jobject,jint,jint);
#ifdef PICO_EDITOR_TEST
void Java_org_overte_pico_OffscreenWebView_nativeEditorState(JNIEnv*,jclass,jlong,jlong,jlong,jboolean,jboolean,jboolean);
#endif
}
extern "C" int __android_log_write(int, const char*, const char*) { return 0; }
static void settle(int milliseconds=20) {
    QEventLoop loop; QTimer::singleShot(milliseconds,&loop,&QEventLoop::quit); loop.exec();
}
int main(int argc,char** argv) {
    QGuiApplication app(argc,argv);
    JavaVM* vm=nullptr; JNIEnv* env=nullptr;
    QByteArray cp="-Djava.class.path="+QByteArray(argv[1]);
    JavaVMOption option; option.optionString=cp.data();
    JavaVMInitArgs args{}; args.version=JNI_VERSION_1_6; args.nOptions=1; args.options=&option;
    assert(JNI_CreateJavaVM(&vm,reinterpret_cast<void**>(&env),&args)==JNI_OK);
    jclass peer=env->FindClass("org/overte/pico/OffscreenWebView"); assert(peer);
    JNINativeMethod callbacks[]={
        {const_cast<char*>("nativeCreationFinished"),const_cast<char*>("(JZ)V"),reinterpret_cast<void*>(Java_org_overte_pico_OffscreenWebView_nativeCreationFinished)},
        {const_cast<char*>("nativeLifecycle"),const_cast<char*>("(JJZ)V"),reinterpret_cast<void*>(Java_org_overte_pico_OffscreenWebView_nativeLifecycle)},
        {const_cast<char*>("nativeFrame"),const_cast<char*>("(JJLjava/nio/ByteBuffer;II)V"),reinterpret_cast<void*>(Java_org_overte_pico_OffscreenWebView_nativeFrame)}
    };
    assert(env->RegisterNatives(peer,callbacks,3)==JNI_OK);
#ifdef PICO_EDITOR_TEST
    JNINativeMethod editorCallback={const_cast<char*>("nativeEditorState"),const_cast<char*>("(JJJZZZ)V"),reinterpret_cast<void*>(Java_org_overte_pico_OffscreenWebView_nativeEditorState)};
    assert(env->RegisterNatives(peer,&editorCallback,1)==JNI_OK);
#endif
    Java_org_overte_pico_OffscreenWebView_nativeInitialize(env,peer);
    auto field=[&](const char* name,const char* signature) { auto id=env->GetStaticFieldID(peer,name,signature); assert(id); return id; };
    QQmlEngine engine;
    engine.addImportPath(QString::fromLocal8Bit(argv[3]));
    QQmlComponent component(&engine,QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));
    if(component.isError()) { std::fprintf(stderr,"%s\n",qPrintable(component.errorString())); return 1; }
    QObject* object=component.createWithInitialProperties({{"url", "data:text/html,<input>"}}); assert(object);
    auto* root=qobject_cast<QQuickItem*>(object); assert(root);
    QQuickWindow window; window.setGeometry(0,0,640,600);
    root->setParentItem(window.contentItem()); window.show();
    root->setWidth(640); root->setHeight(600); settle();
    auto* item=root->findChild<PicoWebViewItem*>(); assert(item && item->rendering());
    auto* legacy=root->property("item").value<QObject*>(); assert(legacy);
    // Genuine original caller failure: the legacy item property remains null,
    // so the outer production surface cannot unfocus or inspect its native editor.
    assert(legacy->property("item").value<QObject*>()==item);
    jlong handle=env->GetStaticLongField(peer,field("handle","J"));
    jlong epoch=env->GetStaticLongField(peer,field("epoch","J")); assert(handle>0 && epoch>0);
    std::vector<uint32_t> pixels(64*64,0xff44aa22);
    jobject buffer=env->NewDirectByteBuffer(pixels.data(),pixels.size()*sizeof(uint32_t)); assert(buffer);
    auto frame=[&](jlong h,jlong e) {
        auto method=env->GetStaticMethodID(peer,"nativeFrame","(JJLjava/nio/ByteBuffer;II)V"); assert(method);
        env->CallStaticVoidMethod(peer,method,h,e,buffer,64,64); assert(!env->ExceptionCheck());
    };
    frame(handle,epoch); assert(!item->frameImage().isNull() && !item->frameSource().isEmpty()); settle(140);
    // A real Qt focus transition is not an application/media lifecycle change.
    int visibility=env->GetStaticIntField(peer,field("visibility","I"));
    item->forceActiveFocus(); item->setFocus(false); settle();
    assert(item->rendering() && env->GetStaticIntField(peer,field("visibility","I"))==visibility);
    assert(env->GetStaticIntField(peer,field("focuses","I"))>=2);
#ifdef PICO_EDITOR_TEST
    jlong revision=100;
    int editorSignals=0;
    QObject::connect(item,&PicoWebViewItem::editorStateChanged,[&] { ++editorSignals; });
    auto editor=[&](jlong h,jlong e,jlong r,bool f,bool n,bool p) {
        auto method=env->GetStaticMethodID(peer,"nativeEditorState","(JJJZZZ)V"); assert(method);
        env->CallStaticVoidMethod(peer,method,h,e,r,f,n,p); assert(!env->ExceptionCheck());
        settle();
    };
    // Android provider metadata is a declared boundary; actual JNI/Qt/QML execute.
    QMouseEvent down(QEvent::MouseButtonPress,QPointF(20,30),Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
    QMouseEvent up(QEvent::MouseButtonRelease,QPointF(20,30),Qt::LeftButton,Qt::NoButton,Qt::NoModifier);
    QCoreApplication::sendEvent(item,&down); QCoreApplication::sendEvent(item,&up);
    assert(item->hasActiveFocus() && env->GetStaticIntField(peer,field("pointers","I"))==2);
    editor(handle,epoch,++revision,true,false,false);
    assert(item->editorFocused() && root->property("keyboardRaised").toBool());
    assert(!root->property("punctuationMode").toBool() && !root->property("passwordField").toBool());
    assert(item->height()==420);
    editor(handle,epoch,++revision,true,true,true);
    assert(root->property("punctuationMode").toBool() && root->property("passwordField").toBool());
    int beforeSignals=editorSignals;
    editor(handle,epoch,revision-1,false,false,false);
    editor(handle,epoch-1,revision+10,false,false,false);
    assert(editorSignals==beforeSignals && root->property("keyboardRaised").toBool());
    QInputMethodEvent textEvent; textEvent.setCommitString(QString::fromUtf8("Unicode \xc3\x84\xf0\x9f\x99\x82"));
    QCoreApplication::sendEvent(item,&textEvent);
    int edits=env->GetStaticIntField(peer,field("edits","I")); assert(edits==2);
    auto textField=[&](const char* name) {
        auto text=static_cast<jstring>(env->GetStaticObjectField(peer,field(name,"Ljava/lang/String;"))); assert(text);
        const jchar* chars=env->GetStringChars(text,nullptr); assert(chars);
        QString value=QString::fromUtf16(chars,env->GetStringLength(text)); env->ReleaseStringChars(text,chars); env->DeleteLocalRef(text); return value;
    };
    assert(textField("committedText")==textEvent.commitString());
    QInputMethodEvent composition(QString::fromUtf8("pr\xc3\xa9"),{}); QCoreApplication::sendEvent(item,&composition);
    assert(env->GetStaticBooleanField(peer,field("composing","Z")));
    assert(textField("composingText")==composition.preeditString());
    QInputMethodEvent forbidden; forbidden.setCommitString("no replacement",1,1); QCoreApplication::sendEvent(item,&forbidden);
    assert(env->GetStaticIntField(peer,field("edits","I"))==edits+1);
    QKeyEvent backspace(QEvent::KeyPress,Qt::Key_Backspace,Qt::NoModifier); QCoreApplication::sendEvent(item,&backspace);
    assert(env->GetStaticIntField(peer,field("key","I"))==67);
    editor(handle,epoch,++revision,false,false,false);
    assert(!root->property("keyboardRaised").toBool() && item->height()==600);
    item->forceActiveFocus(); editor(handle,epoch,++revision,true,false,true);
    root->setProperty("keyboardRaised",false); settle();
    assert(!item->hasActiveFocus() && !item->editorFocused());
    item->forceActiveFocus(); editor(handle,epoch,++revision,true,false,false);
    const jlong replacedHandle=handle, replacedEpoch=epoch;
    QPointer<PicoWebViewItem> replacedItem=item;
    root->setProperty("url","data:text/html,<textarea></textarea>"); settle();
    assert(replacedItem.isNull()); // the real legacy loader replaces its native item
    item=root->findChild<PicoWebViewItem*>(); assert(item && item->rendering());
    assert(!root->property("keyboardRaised").toBool());
    editor(replacedHandle,replacedEpoch,++revision,true,true,true);
    assert(!root->property("keyboardRaised").toBool()); // dead source handle is fenced
    handle=env->GetStaticLongField(peer,field("handle","J"));
    epoch=env->GetStaticLongField(peer,field("epoch","J"));
    item->forceActiveFocus(); editor(handle,epoch,++revision,true,false,false);
    assert(root->property("keyboardRaised").toBool());
#endif
    root->setVisible(false); assert(!item->rendering()); frame(handle,epoch);
#ifdef PICO_EDITOR_TEST
    assert(!item->editorFocused() && !root->property("keyboardRaised").toBool());
#endif
    assert(item->frameImage().isNull() && item->frameSource().isEmpty()); settle();
    assert(!env->GetStaticBooleanField(peer,field("visible","Z")));
    root->setVisible(true); settle(); assert(item->rendering());
    frame(handle,epoch); assert(item->frameImage().isNull());
    epoch=env->GetStaticLongField(peer,field("epoch","J")); frame(handle,epoch);
    assert(!item->frameImage().isNull());
    // Native foreground suspension stops polling even while the QQuick item stays visible.
    Java_org_overte_pico_OffscreenWebView_nativeLifecycle(env,peer,handle,++epoch,false); settle();
    assert(root->isVisible() && !item->rendering() && item->frameSource().isEmpty());
    frame(handle,epoch-1); assert(item->frameImage().isNull());
    Java_org_overte_pico_OffscreenWebView_nativeLifecycle(env,peer,handle,epoch,true); settle();
    assert(!item->rendering()); // an equal stopped epoch cannot reopen
    Java_org_overte_pico_OffscreenWebView_nativeLifecycle(env,peer,handle,++epoch,true); settle();
    assert(item->rendering()); frame(handle,epoch); assert(!item->frameImage().isNull());
    root->setEnabled(false); assert(!item->rendering()); frame(handle,epoch);
    assert(item->frameImage().isNull());
    root->setEnabled(true); settle();
    // Destruction rejects queued lifecycle/creation/frame callbacks by the exact native handle.
    Java_org_overte_pico_OffscreenWebView_nativeCreationFinished(env,peer,handle,true);
    delete object;
    Java_org_overte_pico_OffscreenWebView_nativeLifecycle(env,peer,handle,epoch+10,true);
    frame(handle,epoch+10); settle();
    assert(env->GetStaticIntField(peer,field("destroys","I"))>=1);
    env->DeleteLocalRef(buffer);
    std::puts("PASS whole production Qt5 item/QML, real JNI callbacks, focus/hide/background/show/dead epochs; no Android browser or MP4 proof");
}
''')
            subprocess.run([str(tools / "moc"), str(source.with_suffix(".h")), "-o", str(stage / "moc.cpp")], check=True)
            binary = stage / "probe"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-UNDEBUG", str(source), str(cpp), str(stage / "moc.cpp"),
                            "-I" + str(source.parent), "-I" + str(jdk / "include"), "-I" + str(jdk / "include/linux"),
                            "-I" + str(Path(__file__).parent / "native-stubs"), "-L" + str(jdk / "lib/server"),
                            "-Wl,-rpath," + str(jdk / "lib/server"), "-ljvm", *libraries,
                            "-o", str(binary), *flags, *([] if original else ["-DPICO_EDITOR_TEST"])], env=environment, check=True, timeout=90)
            subprocess.run([str(binary), temporary,
                            str(qml), str(stage / "imports")],
                           env=environment, check=True, timeout=20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
