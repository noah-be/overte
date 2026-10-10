"""Real JVM/Qt regression for a full-client DSO in a different Java loader."""
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/'android/vr/pico/apps/picoInterface'
STUBS=ROOT/'android/vr/pico/tests/device'

JAVA=r'''
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.Method;
public class PicoLoaderTest {
    static native void initialize();
    static native void owner(Object activity);
    static native boolean install();
    static native void events();
    static native boolean observed();
    static native void shutdown();
    static void need(boolean value,String reason) { if(!value)throw new AssertionError(reason); }
    public static void main(String[] args)throws Exception {
        System.load(args[0]);
        initialize();
        try(URLClassLoader loader=new URLClassLoader(new java.net.URL[]{Path.of(args[1]).toUri().toURL()},null)) {
            need(!install(),"missing native Activity must fail closed");
            Class<?> visibility=loader.loadClass("org.overte.pico.PicoClientVisibility");
            Class<?> handler=loader.loadClass("android.os.Handler");
            Method attach=visibility.getDeclaredMethod("attach",Object.class);attach.setAccessible(true);
            Method foreground=visibility.getDeclaredMethod("foreground",Object.class,boolean.class);foreground.setAccessible(true);
            Class<?> activityClass=loader.loadClass("org.overte.pico.PicoLoaderActivity");
            Object activity=activityClass.getConstructor(ClassLoader.class).newInstance(PicoLoaderTest.class.getClassLoader());
            need(activityClass.getMethod("getClassLoader").invoke(activity)!=activity.getClass().getClassLoader(),
                "Context loader and actual Activity loader must differ in this regression");
            attach.invoke(null,activity);foreground.invoke(null,activity,true);
            need((Integer)handler.getMethod("pendingCount").invoke(null)==1,"foreign DSO must initially be unresolved");
            need(!observed(),"failed JNI lookup must not manufacture a foreground receipt");
            owner(activity);
            need(install(),"exact Activity class loader must bind both full-client bridges");
            need((Integer)handler.getMethod("pendingCount").invoke(null)==0,
                "native binding must deliver retained state without draining Android's delayed callback");
            need(!observed(),"queued JNI admission is not an applied foreground observation");
            events();need(observed(),"actual native receiver must observe resume");
            foreground.invoke(null,activity,false);events();need(!observed(),"actual native receiver must observe pause");
        } finally { shutdown(); }
    }
}
'''

CPP=r'''
#include <QCoreApplication>
#include <QApplication>
#include <QEvent>
#include <jni.h>
#include "PicoNativeBridges.h"
// Only the desktop menu boundary is controlled here. Execute the actual
// Application event prelude against real Qt queued-call delivery.
struct Menu { static void* getInstance() { return nullptr; } };
class Application : public QApplication {
public:
    using QApplication::QApplication;
protected:
    bool event(QEvent* event) override {
        @@ACTUAL_EVENT_PRELUDE@@
        return QApplication::event(event);
    }
private:
    bool _aboutToQuit { false };
    bool _isMenuInitialized { true };
};
static JavaVM* vm=nullptr;
static jobject activity=nullptr;
static bool visible=false;
static QCoreApplication* application=nullptr;
static int count=1;
static char name[]="pico-loader-test";
static char* arguments[]={name,nullptr};
namespace overte::lifecycle {void observeNativeVisibility(bool foreground){visible=foreground;}}
extern "C" JavaVM* overtePicoOpenXRJavaVm(){return vm;}
extern "C" jobject overtePicoOpenXRAcquireActivity(JNIEnv* env){return activity?env->NewGlobalRef(activity):nullptr;}
// Accessibility engine effects are outside this lifecycle/class-loader test.
extern "C" jboolean Java_org_overte_pico_PicoAccessibilityBridge_nativeRequestFrame(JNIEnv*,jclass,jobject,jint,jint,jint){return JNI_FALSE;}
extern "C" jboolean Java_org_overte_pico_PicoAccessibilityBridge_nativePerformAction(JNIEnv*,jclass,jint,jstring,jstring){return JNI_FALSE;}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_initialize(JNIEnv* env,jclass){env->GetJavaVM(&vm);application=new Application(count,arguments);}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_owner(JNIEnv* env,jclass,jobject value){activity=env->NewGlobalRef(value);}
extern "C" JNIEXPORT jboolean JNICALL Java_PicoLoaderTest_install(JNIEnv*,jclass){return overte::pico::installNativeBridges()?JNI_TRUE:JNI_FALSE;}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_events(JNIEnv*,jclass){QCoreApplication::processEvents();}
extern "C" JNIEXPORT jboolean JNICALL Java_PicoLoaderTest_observed(JNIEnv*,jclass){return visible?JNI_TRUE:JNI_FALSE;}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_shutdown(JNIEnv* env,jclass){if(activity)env->DeleteGlobalRef(activity);activity=nullptr;delete application;application=nullptr;}
'''


class PicoNativeClassLoaderTest(unittest.TestCase):
    def test_missing_symbol_in_another_loader_is_bound_to_the_real_application_class(self):
        jdk=Path(shutil.which('javac')).resolve().parents[1]
        flags=shlex.split(subprocess.run(['pkg-config','--cflags','--libs','Qt6Widgets'],
            capture_output=True,text=True,check=True).stdout)
        with tempfile.TemporaryDirectory(prefix='pico-loader-regression-') as scratch:
            root=Path(scratch);application=root/'application';application.mkdir()
            (root/'PicoLoaderTest.java').write_text(JAVA)
            events=(ROOT/'interface/src/Application_Events.cpp').read_text()
            prelude=events.split('bool Application::event(QEvent* event) {',1)[1].split(
                '    if ((event->type() == QEvent::InputMethod',1)[0]
            (root/'driver.cpp').write_text(CPP.replace('@@ACTUAL_EVENT_PRELUDE@@',prelude))
            (root/'PicoLoaderActivity.java').write_text('''package org.overte.pico;
public class PicoLoaderActivity {
    private final ClassLoader contextLoader;
    public PicoLoaderActivity(ClassLoader contextLoader) { this.contextLoader=contextLoader; }
    public ClassLoader getClassLoader() { return contextLoader; }
}''')
            (root/'PicoAccessibilityBridge.java').write_text('''package org.overte.pico;
public class PicoAccessibilityBridge {
    private static native boolean nativeRequestFrame(PicoAccessibilityBridge receiver,int width,int height,int generation);
    private static native boolean nativePerformAction(int identifier,String action,String text);
}''')
            java=APP/'src/main/java/org/overte/pico'
            subprocess.run(['javac','-d',str(application),str(java/'PicoClientVisibility.java'),
                str(java/'RedactingDiagnostics.java'),str(ROOT/'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                str(root/'PicoAccessibilityBridge.java'),str(root/'PicoLoaderActivity.java'),
                *map(str,(STUBS/'visibility-stubs').rglob('*.java')),
                str(STUBS/'java-stubs/android/util/Log.java')],check=True,timeout=25)
            subprocess.run(['javac','-d',str(root),str(root/'PicoLoaderTest.java')],check=True,timeout=25)
            library=root/'libfull-client.so'
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fPIC','-shared','-pthread',
                '-I'+str(jdk/'include'),'-I'+str(jdk/'include/linux'),'-I'+str(ROOT/'interface/src'),
                '-I'+str(APP/'lifecycle'),str(APP/'lifecycle/PicoNativeBridges.cpp'),
                str(APP/'lifecycle/PicoClientVisibility.cpp'),str(root/'driver.cpp'),'-o',str(library),*flags],
                check=True,timeout=45)
            completed=subprocess.run(['java','-XX:-CreateCoredumpOnCrash','-cp',str(root),
                'PicoLoaderTest',str(library),str(application)],capture_output=True,text=True,timeout=15,
                env=os.environ|{'QT_QPA_PLATFORM':'offscreen'})
            self.assertEqual(0,completed.returncode,(completed.stdout+completed.stderr)[-4000:])


if __name__=='__main__':unittest.main()
