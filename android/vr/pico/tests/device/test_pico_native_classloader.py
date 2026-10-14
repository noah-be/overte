"""Real JVM/Qt regression for a full-client DSO in a different Java loader."""
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import re

ROOT=Path(__file__).resolve().parents[5]
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
    static native String document();
    static native String snapshot();
    static native String tree();
    static native String cancelTreeOwner();
    static native boolean treeCompleted();
    static native boolean completed();
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
            Class<?> activityClass=loader.loadClass("org.overte.pico.PicoInterfaceActivity");
            Object activity=activityClass.getConstructor(ClassLoader.class).newInstance(PicoLoaderTest.class.getClassLoader());
            need(activityClass.getMethod("getClassLoader").invoke(activity)!=activity.getClass().getClassLoader(),
                "Context loader and actual Activity loader must differ in this regression");
            Class<?> hostClass=loader.loadClass("org.overte.pico.PicoNativeDocumentHost");
            Method hostAttach=hostClass.getDeclaredMethod("attach",activityClass);hostAttach.setAccessible(true);
            Method hostForeground=hostClass.getDeclaredMethod("foreground",boolean.class);hostForeground.setAccessible(true);
            Method hostReady=hostClass.getDeclaredMethod("nativeBindingsReady",Object.class);hostReady.setAccessible(true);
            Method hostDetach=hostClass.getDeclaredMethod("detach");hostDetach.setAccessible(true);
            Method hostFocus=hostClass.getDeclaredMethod("windowFocus");hostFocus.setAccessible(true);
            Method hostResult=hostClass.getDeclaredMethod("activityResult",int.class,int.class,loader.loadClass("android.content.Intent"));hostResult.setAccessible(true);
            Method hostActive=hostClass.getDeclaredMethod("isForeground");hostActive.setAccessible(true);
            Object host=hostAttach.invoke(null,activity);hostForeground.invoke(host,true);
            need(!(Boolean)hostActive.invoke(host),"native readiness cannot be manufactured by resume");
            attach.invoke(null,activity);foreground.invoke(null,activity,true);
            need((Integer)handler.getMethod("pendingCount").invoke(null)==1,"foreign DSO must initially be unresolved");
            need(!observed(),"failed JNI lookup must not manufacture a foreground receipt");
            owner(activity);
            need(install(),"exact Activity class loader must bind both full-client bridges");
            need((Integer)handler.getMethod("pendingCount").invoke(null)==0,
                "native binding must deliver retained state without draining Android's delayed callback");
            need(!observed(),"queued JNI admission is not an applied foreground observation");
            events();need(observed(),"actual native receiver must observe resume");
            Class<?> docs=loader.loadClass("org.overte.documents.DocumentAdapter");
            Class<?> shots=loader.loadClass("org.overte.snapshot.SnapshotAdapter");
            need(docs.getField("initialized").getInt(null)==0,"admitted initialization must wait for Android main");
            handler.getMethod("drainPosted").invoke(null);
            need((Boolean)hostActive.invoke(host),"real host becomes foreground only after readiness");
            need(docs.getField("initialized").getInt(null)==1 && shots.getField("initialized").getInt(null)==1,
                "both exact registered native initializers must execute");
            String request=document();
            need(!request.isEmpty() && request.equals(docs.getField("requestId").get(null)),"actual helper must issue JNI document request");
            String ticket=snapshot();
            need(!ticket.isEmpty() && Long.parseLong(ticket)==shots.getField("ticket").getLong(null),"actual Snapshot must issue JNI export request");
            docs.getMethod("finish").invoke(null);shots.getMethod("finish").invoke(null);
            need(!completed(),"native callbacks must wait for Qt owner thread");
            events();need(completed(),"registered document and Snapshot callbacks must reach actual Qt owners");
            String treeRequest=tree();
            need(!treeRequest.isEmpty() && treeRequest.equals(docs.getField("requestId").get(null)),"actual helper must issue the additive tree JNI request");
            docs.getMethod("finishTree").invoke(null);
            need(!treeCompleted(),"tree completion must queue back to the Qt owner");
            events();need(treeCompleted(),"tree hierarchy must survive JNI validation and the actual helper manifest");
            String canceledTree=cancelTreeOwner();
            need(!canceledTree.isEmpty() && canceledTree.equals(docs.getField("canceledId").get(null)),"destroyed tree owner must cancel the original nonempty JNI ID");
            docs.getMethod("finishTree").invoke(null);events();
            need(treeCompleted(),"late canceled tree callback must not publish another selection");
            need((Boolean)hostResult.invoke(host,73,0,null),"document result must route through its immutable host");
            need((Boolean)hostResult.invoke(host,74,0,null),"Snapshot result must route through its immutable host");
            need(!(Boolean)hostResult.invoke(host,75,0,null),"unowned result must continue to the next handler");
            hostForeground.invoke(host,false);need(!(Boolean)hostActive.invoke(host),"pause blocks focus without cancelling chooser");
            hostFocus.invoke(host);need(docs.getField("detached").getInt(null)==0,"pause alone must preserve intentional chooser");
            hostForeground.invoke(host,true);activityClass.getField("focused").setBoolean(activity,false);
            need(!(Boolean)hostActive.invoke(host),"resume without genuine focus cannot deliver");
            activityClass.getField("focused").setBoolean(activity,true);hostFocus.invoke(host);
            need((Boolean)hostActive.invoke(host),"focus return restores the same owner");
            need(install(),"repeated native readiness is idempotent");handler.getMethod("drainPosted").invoke(null);
            need(docs.getField("initialized").getInt(null)==1,"duplicate readiness cannot reinitialize leases");
            Object replacement=activityClass.getConstructor(ClassLoader.class).newInstance(PicoLoaderTest.class.getClassLoader());
            Object replacementHost=hostAttach.invoke(null,replacement);
            need(!(Boolean)hostReady.invoke(null,activity),"stale Activity readiness must be discarded");
            need(!(Boolean)hostResult.invoke(host,73,0,null),"stale owner must not consume replacement results");
            hostForeground.invoke(replacementHost,true);attach.invoke(null,replacement);owner(replacement);
            handler.getMethod("drainPosted").invoke(null);
            need((Boolean)hostActive.invoke(replacementHost),"recreated Activity must reuse true binding receipt without repeating native application setup");
            need(docs.getField("initialized").getInt(null)==2,"replacement lease must initialize exactly once");
            need(install(),"repeated install on recreated owner stays idempotent");
            hostDetach.invoke(host);need((Boolean)hostActive.invoke(replacementHost),"late old detach must not revoke replacement");
            hostDetach.invoke(replacementHost);need(!(Boolean)hostActive.invoke(replacementHost),"actual destruction revokes foreground");
            need(!(Boolean)hostReady.invoke(null,replacement),"destroyed owner cannot initialize again");
            Object deferred=activityClass.getConstructor(ClassLoader.class).newInstance(PicoLoaderTest.class.getClassLoader());
            Object deferredHost=hostAttach.invoke(null,deferred);attach.invoke(null,deferred);owner(deferred);
            need(install(),"ready scheduling for another owner must be admitted");
            Object next=activityClass.getConstructor(ClassLoader.class).newInstance(PicoLoaderTest.class.getClassLoader());
            Object nextHost=hostAttach.invoke(null,next);hostDetach.invoke(nextHost);
            handler.getMethod("drainPosted").invoke(null);
            need(docs.getField("initialized").getInt(null)==2,"queued obsolete initialization must never acquire a lease");
            need(!(Boolean)hostActive.invoke(deferredHost) && !(Boolean)hostReady.invoke(null,deferred),"old deferred owner stays revoked");
            hostDetach.invoke(nextHost);
            try(URLClassLoader bad=new URLClassLoader(new java.net.URL[]{Path.of(args[2]).toUri().toURL()},null)) {
                Class<?> badActivity=bad.loadClass("org.overte.pico.PicoInterfaceActivity");
                Object badOwner=badActivity.getConstructor(ClassLoader.class).newInstance(PicoLoaderTest.class.getClassLoader());
                Class<?> badHost=bad.loadClass("org.overte.pico.PicoNativeDocumentHost");
                Method badAttach=badHost.getDeclaredMethod("attach",badActivity);badAttach.setAccessible(true);badAttach.invoke(null,badOwner);
                owner(badOwner);need(!install(),"changed Java native callback descriptor must fail closed before readiness");
                bad.loadClass("android.os.Handler").getMethod("drainPosted").invoke(null);
                need(bad.loadClass("org.overte.documents.DocumentAdapter").getField("initialized").getInt(null)==0,"bad ABI cannot acquire document lease");
            }
            foreground.invoke(null,activity,false);events();need(!observed(),"actual native receiver must observe pause");
        } finally { shutdown(); }
    }
}
'''

CPP=r'''
#include <QCoreApplication>
#include <QApplication>
#include <QEvent>
#include <QDir>
#include <QFile>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlFileSelector>
#include <QElapsedTimer>
#include <QThread>
#include <FileDialogHelper.h>
#include <NativeSnapshotAdapter.h>
#include <SnapshotStorage.h>
#include <memory>
#include <cassert>
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
static std::unique_ptr<FileDialogHelper> documents;
static std::unique_ptr<NativeSnapshotAdapter> snapshots;
static int documentResults=0, snapshotResults=0, treeResults=0;
static QString treeRoot;
static QString imported;
static jstring javaString(JNIEnv* env,const QString& value){return env->NewString(reinterpret_cast<const jchar*>(value.utf16()),value.size());}
static QCoreApplication* application=nullptr;
// The native executable owns the GUI application and its process-main thread.
// A Java launcher creates a different JavaMain pthread; Qt's offscreen exit
// objects can outlive that pthread's adopted QThreadData on Qt 6.4.
extern "C" void picoLoaderCreateApplication(int& argc,char** argv){
    assert(!application);application=new Application(argc,argv);
}
extern "C" void picoLoaderDestroyApplication(){
    assert(application && application->thread()==QThread::currentThread());
    assert(!documents && !snapshots && !activity);
    delete application;application=nullptr;
}
namespace overte::lifecycle {void observeNativeVisibility(bool foreground){visible=foreground;}}
extern "C" JavaVM* overtePicoOpenXRJavaVm(){return vm;}
extern "C" jobject overtePicoOpenXRAcquireActivity(JNIEnv* env){return activity?env->NewGlobalRef(activity):nullptr;}
// Accessibility engine effects are outside this lifecycle/class-loader test.
extern "C" jboolean Java_org_overte_pico_PicoAccessibilityBridge_nativeRequestFrame(JNIEnv*,jclass,jobject,jint,jint,jint){return JNI_FALSE;}
extern "C" jboolean Java_org_overte_pico_PicoAccessibilityBridge_nativePerformAction(JNIEnv*,jclass,jint,jstring,jstring){return JNI_FALSE;}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_initialize(JNIEnv* env,jclass){env->GetJavaVM(&vm);
assert(application && QCoreApplication::instance()==application && application->thread()==QThread::currentThread());
application->setApplicationName("pico-native-loader");
QQmlEngine engine;QQmlFileSelector selector(&engine);selector.setExtraSelectors({"android_picoInterface","android"});
QQmlComponent surface(&engine,QUrl::fromLocalFile(QStringLiteral("@@ROOT@@/interface/resources/qml/controls/SnapshotPlatformBackend.qml")));
QElapsedTimer load;load.start();while(surface.isLoading() && load.elapsed()<5000)QCoreApplication::processEvents();
std::unique_ptr<QObject> selected(surface.create());
if(!selected || !selected->findChild<NativeSnapshotAdapter*>() || selected->property("capabilities").toStringList()!=QStringList({"save","share"}))qFatal("Actual Pico/Android selector must create native Snapshot backend");
documents=std::make_unique<FileDialogHelper>();snapshots=std::make_unique<NativeSnapshotAdapter>();
QObject::connect(documents.get(),&FileDialogHelper::documentsSelected,[](QString,QList<QUrl> files){if(files.size()!=1)return;
if(files[0].toLocalFile()==imported)++documentResults;
if(files[0].toLocalFile()==treeRoot){
const auto manifest=documents->documentBundle({},files[0]);
const auto paths=manifest.value("relativePaths").toList();
if(manifest.value("error").toString().isEmpty() && paths.size()==2 && paths.contains(QString("scripts/main.js")) && paths.contains(QString("scripts/lib/helper.js")))++treeResults;
}});
QObject::connect(snapshots.get(),&NativeSnapshotAdapter::completed,[](QString,QString status,QString){if(status=="success")++snapshotResults;});}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_owner(JNIEnv* env,jclass,jobject value){if(activity)env->DeleteGlobalRef(activity);activity=env->NewGlobalRef(value);}
extern "C" JNIEXPORT jboolean JNICALL Java_PicoLoaderTest_install(JNIEnv*,jclass){return overte::pico::installNativeBridges()?JNI_TRUE:JNI_FALSE;}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_events(JNIEnv*,jclass){for(int i=0;i<4;++i)QCoreApplication::processEvents();}
extern "C" JNIEXPORT jboolean JNICALL Java_PicoLoaderTest_observed(JNIEnv*,jclass){return visible?JNI_TRUE:JNI_FALSE;}
extern "C" JNIEXPORT jstring JNICALL Java_PicoLoaderTest_document(JNIEnv* env,jclass){
    const auto root=QStandardPaths::writableLocation(QStandardPaths::AppDataLocation)+"/ImportedDocuments/selection-321";
    if(!QDir().mkpath(root))return javaString(env,{});
    QFile file(root+"/mock.js");if(!file.open(QFile::WriteOnly))return javaString(env,{});file.write("print('retained')");file.close();imported=file.fileName();
    return javaString(env,documents->openDocuments("Scripts","Scripts (*.js)",false));
}
extern "C" JNIEXPORT jstring JNICALL Java_PicoLoaderTest_tree(JNIEnv* env,jclass){
    treeRoot=QStandardPaths::writableLocation(QStandardPaths::AppDataLocation)+"/ImportedDocuments/selection-322/bundle";
    if(!QDir().mkpath(treeRoot+"/scripts/lib"))return javaString(env,{});
    for(const auto& path:{QString("scripts/main.js"),QString("scripts/lib/helper.js")}){
        QFile file(treeRoot+"/"+path);if(!file.open(QFile::WriteOnly))return javaString(env,{});
        file.write(path.endsWith("main.js")?"Script.include('lib/helper.js');":"var answer = 42;");
    }
    return javaString(env,documents->openDocumentTree("Script and companion folder"));
}
extern "C" JNIEXPORT jstring JNICALL Java_PicoLoaderTest_cancelTreeOwner(JNIEnv* env,jclass){
    auto temporary=std::make_unique<FileDialogHelper>();
    const auto request=temporary->openDocumentTree("Canceled companion folder");
    temporary.reset();return javaString(env,request);
}
extern "C" JNIEXPORT jboolean JNICALL Java_PicoLoaderTest_treeCompleted(JNIEnv*,jclass){return treeResults==1;}
extern "C" JNIEXPORT jstring JNICALL Java_PicoLoaderTest_snapshot(JNIEnv* env,jclass){
    const auto root=overte::snapshot::storageRoot();if(!QDir().mkpath(root))return javaString(env,{});
    QFile file(root+"/capture.png");if(!file.open(QFile::WriteOnly))return javaString(env,{});file.write("image-test");file.close();
    return javaString(env,snapshots->request(file.fileName(),"save"));
}
extern "C" JNIEXPORT jboolean JNICALL Java_PicoLoaderTest_completed(JNIEnv*,jclass){return documentResults==1 && snapshotResults==1;}
extern "C" JNIEXPORT void JNICALL Java_PicoLoaderTest_shutdown(JNIEnv* env,jclass){if(activity)env->DeleteGlobalRef(activity);activity=nullptr;snapshots.reset();documents.reset();}
'''

LAUNCHER_CPP=r'''
#include <jni.h>
#include <cassert>
#include <string>
#include <iostream>
extern "C" void picoLoaderCreateApplication(int&,char**);
extern "C" void picoLoaderDestroyApplication();

int main(int argc,char** argv){
    assert(argc==5);
    const std::string library=argv[1], application=argv[2], invalid=argv[3];
    std::string classPath=std::string("-Djava.class.path=")+argv[4];
    picoLoaderCreateApplication(argc,argv);
    JavaVMOption options[]={{classPath.data(),nullptr},
        {const_cast<char*>("-Xcheck:jni"),nullptr},
        {const_cast<char*>("-XX:-CreateCoredumpOnCrash"),nullptr}};
    JavaVMInitArgs arguments {JNI_VERSION_1_8,3,options,JNI_FALSE};
    JavaVM* vm=nullptr;JNIEnv* env=nullptr;
    assert(JNI_CreateJavaVM(&vm,reinterpret_cast<void**>(&env),&arguments)==JNI_OK);
    jclass driver=env->FindClass("PicoLoaderTest");
    if(env->ExceptionCheck())env->ExceptionDescribe();
    assert(driver && !env->ExceptionCheck());
    jmethodID main=env->GetStaticMethodID(driver,"main","([Ljava/lang/String;)V");
    assert(main && !env->ExceptionCheck());
    jclass stringClass=env->FindClass("java/lang/String");
    assert(stringClass && !env->ExceptionCheck());
    jobjectArray values=env->NewObjectArray(3,stringClass,nullptr);
    assert(values && !env->ExceptionCheck());
    int index=0;
    for(const auto& value:{library,application,invalid}){
        jstring text=env->NewStringUTF(value.c_str());assert(text);
        env->SetObjectArrayElement(values,index++,text);env->DeleteLocalRef(text);
        assert(!env->ExceptionCheck());
    }
    // Java still System.load()s the full-client DSO and exercises two genuine
    // URLClassLoaders. Only its GUI-process ownership boundary is corrected.
    env->CallStaticVoidMethod(driver,main,values);
    const bool passed=!env->ExceptionCheck();
    if(!passed){env->ExceptionDescribe();env->ExceptionClear();}
    env->DeleteLocalRef(values);env->DeleteLocalRef(stringClass);env->DeleteLocalRef(driver);
    // Release Qt-owned receivers while JNI cancellation is still usable.
    // The GUI thread itself stays alive through JVM and process-exit cleanup.
    picoLoaderDestroyApplication();
    assert(vm->DestroyJavaVM()==JNI_OK);
    if(passed)std::cout<<"PASS native GUI main owns QApplication through real JVM/ClassLoader/DSO test and ordered teardown\n";
    return passed?0:1;
}
'''


class PicoNativeClassLoaderTest(unittest.TestCase):
    def test_missing_symbol_in_another_loader_is_bound_to_the_real_application_class(self):
        jdk=Path(shutil.which('javac')).resolve().parents[1]
        major=os.environ.get('OVERTE_NATIVE_QT_MAJOR','6')
        environment=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'}
        libraries=[]
        if major=='5':
            qt=Path(os.environ.get('OVERTE_QT5_ROOT',str(Path.home()/'.local/overte-qt5/root')))
            if (qt/'usr/lib64/pkgconfig/Qt5Widgets.pc').is_file():
                environment.update(PKG_CONFIG_PATH=str(qt/'usr/lib64/pkgconfig'),PKG_CONFIG_SYSROOT_DIR=str(qt),
                    LD_LIBRARY_PATH=str(qt/'usr/lib64'),QT_PLUGIN_PATH=str(qt/'usr/lib64/qt5/plugins'),QML2_IMPORT_PATH=str(qt/'usr/lib64/qt5/qml'))
                libraries=['-L'+str(qt/'usr/lib64')]
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',
            *['Qt'+major+name for name in ('Widgets','Qml','Quick')]],env=environment,text=True))
        with tempfile.TemporaryDirectory(prefix='pico-loader-regression-') as scratch:
            root=Path(scratch);application=root/'application';application.mkdir()
            (root/'PicoLoaderTest.java').write_text(JAVA)
            (root/'launcher.cpp').write_text(LAUNCHER_CPP)
            events=(ROOT/'interface/src/Application_Events.cpp').read_text()
            prelude=events.split('bool Application::event(QEvent* event) {',1)[1].split(
                '    if ((event->type() == QEvent::InputMethod',1)[0]
            (root/'driver.cpp').write_text(CPP.replace('@@ACTUAL_EVENT_PRELUDE@@',prelude).replace('@@ROOT@@',str(ROOT)))
            (root/'PicoInterfaceActivity.java').write_text('''package org.overte.pico;
public class PicoInterfaceActivity extends android.app.Activity {
    private static PicoInterfaceActivity current;
    public boolean focused=true;
    static PicoInterfaceActivity getInstance() { return current; }
    public boolean hasWindowFocus() { return focused; }
    public boolean isFinishing() { return false; }
    private final ClassLoader contextLoader;
    public PicoInterfaceActivity(ClassLoader contextLoader) { this.contextLoader=contextLoader; current=this; }
    public ClassLoader getClassLoader() { return contextLoader; }
}''')
            (root/'PicoAccessibilityBridge.java').write_text('''package org.overte.pico;
public class PicoAccessibilityBridge {
    private static native boolean nativeRequestFrame(PicoAccessibilityBridge receiver,int width,int height,int generation);
    private static native boolean nativePerformAction(int identifier,String action,String text);
}''')
            (root/'Activity.java').write_text('package android.app; public class Activity {}')
            (root/'Intent.java').write_text('package android.content; public class Intent {}')
            def native_boundary(boundary,module,name):
                actual=(ROOT/'android/common'/module/'java/org/overte'/module/(name+'.java')).read_text()
                natives=re.findall(r'private static native [^;]+;',actual)
                self.assertEqual(2,len(natives),'Both actual shared Java native callbacks must be declared')
                return re.sub(r'    private static native [^;]+;\n','',boundary).replace(
                    'public final class '+name+' {','public final class '+name+' {\n    '+'\n    '.join(natives))
            document_java=native_boundary(DOCUMENT_BOUNDARY,'documents','DocumentAdapter')
            snapshot_java=native_boundary(SNAPSHOT_BOUNDARY,'snapshot','SnapshotAdapter')
            (root/'DocumentAdapter.java').write_text(document_java)
            (root/'SnapshotAdapter.java').write_text(snapshot_java)
            java=APP/'src/main/java/org/overte/pico'
            subprocess.run(['javac','-d',str(application),str(java/'PicoClientVisibility.java'),str(java/'PicoNativeDocumentHost.java'),
                str(java/'RedactingDiagnostics.java'),str(ROOT/'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                str(root/'PicoAccessibilityBridge.java'),str(root/'PicoInterfaceActivity.java'),
                str(root/'Activity.java'),str(root/'Intent.java'),str(root/'DocumentAdapter.java'),str(root/'SnapshotAdapter.java'),
                str(ROOT/'android/common/documents/java/org/overte/documents/DocumentHost.java'),
                str(ROOT/'android/common/snapshot/java/org/overte/snapshot/SnapshotHost.java'),
                *map(str,(STUBS/'visibility-stubs').rglob('*.java')),
                str(STUBS/'java-stubs/android/util/Log.java')],check=True,timeout=25)
            invalid=root/'invalid-abi';shutil.copytree(application,invalid)
            changed=document_java.replace('String[] paths','String path').replace('new String[]{root+"/selection-321/mock.js"}','root+"/selection-321/mock.js"').replace('new String[]{root+"/selection-322/bundle"}','root+"/selection-322/bundle"')
            self.assertNotEqual(document_java,changed,'Negative callback fixture must actually change the ABI')
            (root/'DocumentAdapter.java').write_text(changed)
            subprocess.run(['javac','-cp',str(invalid),'-d',str(invalid),str(root/'DocumentAdapter.java')],check=True,timeout=25)
            subprocess.run(['javac','-d',str(root),str(root/'PicoLoaderTest.java')],check=True,timeout=25)
            r8=os.environ.get('PICO_R8_JAR')
            if r8:
                self.check_ready_shrinker(root,application,jdk,Path(r8))
            ui=ROOT/'libraries/ui/src';snapshot=ROOT/'android/common/snapshot/src'
            moc=Path(subprocess.check_output(['pkg-config','--variable=libexecdir' if major=='6' else '--variable=host_bins','Qt'+major+'Core'],env=environment,text=True).strip())/'moc'
            for header,name in ((ui/'FileDialogHelper.h','documents'),(snapshot/'NativeSnapshotAdapter.h','snapshots')):
                subprocess.run([str(moc),str(header),'-o',str(root/(name+'-moc.cpp'))],check=True)
            # Retain strict diagnostics for Pico-owned native bridges; the shared
            # Qt5-compatible adapters currently produce Qt6/GCC header deprecations.
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fPIC','-fsyntax-only',
                '-I'+str(jdk/'include'),'-I'+str(jdk/'include/linux'),'-I'+str(ROOT/'interface/src'),
                str(APP/'lifecycle/PicoNativeBridges.cpp'),str(APP/'lifecycle/PicoClientVisibility.cpp'),*flags],
                env=environment,check=True,timeout=30)
            library=root/'libfull-client.so'
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-fPIC','-shared','-pthread',
                '-I'+str(jdk/'include'),'-I'+str(jdk/'include/linux'),'-I'+str(ROOT/'interface/src'),
                '-I'+str(APP/'lifecycle'),str(APP/'lifecycle/PicoNativeBridges.cpp'),
                str(APP/'lifecycle/PicoClientVisibility.cpp'),str(root/'driver.cpp'),
                str(ROOT/'android/common/documents/src/NativeDocumentPicker.cpp'),str(snapshot/'NativeSnapshotAdapter.cpp'),
                str(ui/'FileDialogHelper.cpp'),str(ui/'ui/Logging.cpp'),str(root/'documents-moc.cpp'),str(root/'snapshots-moc.cpp'),
                '-I'+str(ui),'-I'+str(snapshot),'-I'+str(ROOT/'interface/src/ui'),'-o',str(library),*libraries,*flags],
                env=environment,check=True,timeout=45)
            launcher=root/'pico-loader-test'
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-pthread',
                '-I'+str(jdk/'include'),'-I'+str(jdk/'include/linux'),str(root/'launcher.cpp'),
                '-L'+str(root),'-lfull-client','-Wl,-rpath,'+str(root),
                '-L'+str(jdk/'lib/server'),'-ljvm','-Wl,-rpath,'+str(jdk/'lib/server'),
                '-o',str(launcher)],env=environment,check=True,timeout=30)
            completed=subprocess.run([str(launcher),str(library),str(application),str(invalid),str(root)],capture_output=True,text=True,timeout=15,
                env=environment|{'XDG_DATA_HOME':str(root/'data')})
            self.assertEqual(0,completed.returncode,(completed.stdout+completed.stderr)[-4000:])
            self.assertIn('PASS native GUI main owns QApplication',completed.stdout,
                'The real JVM journey and native GUI-owned teardown must both finish')
            print('PASS Qt'+major+': actual selected Pico Snapshot, file/tree/export JNI, hierarchy, owner cancellation and immutable Activity lifecycle; OS endpoints are fixtures')


    def check_ready_shrinker(self, root, application, jdk, r8):
        # Only the Pico readiness declarations are qualified here. Activity,
        # Android scheduling and provider endpoints are the same explicit host
        # fixtures as the foreign-loader test, not AGP or product bytecode.
        runtime=root/'java-base.jar'
        with zipfile.ZipFile(jdk/'jmods/java.base.jmod') as source, zipfile.ZipFile(runtime,'w') as target:
            for name in source.namelist():
                if name.startswith('classes/') and name.endswith('.class') and not name.endswith('module-info.class'):
                    target.writestr(name[8:],source.read(name))
        program=root/'readiness-input.jar'
        subprocess.run(['jar','cf',str(program),'-C',str(application),'.'],check=True)
        retained=root/'readiness-retained.jar';control=root/'readiness-unprotected.jar'
        command=['java','-cp',str(r8),'com.android.tools.r8.R8','--release','--classfile','--lib',str(runtime)]
        subprocess.run([*command,'--output',str(control),str(program)],check=True,timeout=45)
        with zipfile.ZipFile(control) as removed:
            self.assertNotIn('org/overte/pico/PicoNativeDocumentHost.class',removed.namelist(),
                'negative control must lose the Java-unreachable readiness host')
        subprocess.run([*command,'--pg-conf',str(APP/'proguard-rules.pro'),'--output',str(retained),str(program)],
            check=True,timeout=45)
        for name in ('PicoNativeDocumentHost','PicoClientVisibility'):
            methods=subprocess.check_output(['javap','-p','-s','-classpath',str(retained),'org.overte.pico.'+name],text=True)
            self.assertRegex(methods,r'nativeBindingsReady\(java.lang.Object\);\s+descriptor: \(Ljava/lang/Object;\)Z')
        print('PASS actual R8: both production Pico readiness descriptors survive; unprotected host is removed; Android boundaries remain fixtures')


DOCUMENT_BOUNDARY=r'''
package org.overte.documents;
import android.content.Intent;
public final class DocumentAdapter {
    private static native void nativeInitialize();
    private static native void nativeCompleted(String id,String[] paths,String error);
    public static int initialized, detached;
    public static String requestId, root, canceledId;
    private static DocumentHost current;
    public static void initialize(DocumentHost host){current=host;++initialized;nativeInitialize();}
    public static void foreground(DocumentHost host){if(current!=host)throw new AssertionError("foreign document owner");}
    public static void detach(DocumentHost host){if(current==host){++detached;current=null;}}
    public static boolean activityResult(DocumentHost host,int code,int result,Intent data){return current==host && code==73;}
    public static void request(String id,String directory,String caption,String filter,boolean multiple){requestId=id;root=directory;}
    public static void requestTree(String id,String directory,String caption){requestId=id;root=directory;}
    public static void cancel(String id){canceledId=id;}
    public static void finish(){nativeCompleted(requestId,new String[]{root+"/selection-321/mock.js"},"");}
    public static void finishTree(){nativeCompleted(requestId,new String[]{root+"/selection-322/bundle"},"");}
}
'''
SNAPSHOT_BOUNDARY=r'''
package org.overte.snapshot;
import android.content.Intent;
public final class SnapshotAdapter {
    private static native void nativeInitialize();
    private static native void nativeCompleted(long handle,long ticket,String status,String error);
    public static int initialized, detached;
    public static long handle,ticket;
    private static SnapshotHost current;
    public static void initialize(SnapshotHost host){current=host;++initialized;nativeInitialize();}
    public static void foreground(SnapshotHost host){if(current!=host)throw new AssertionError("foreign snapshot owner");}
    public static void detach(SnapshotHost host){if(current==host){++detached;current=null;}}
    public static boolean activityResult(SnapshotHost host,int code,int result,Intent data){return current==host && code==74;}
    public static void request(long h,long t,String root,String path,String action){handle=h;ticket=t;}
    public static void cancel(long h,long t){}
    public static void finish(){nativeCompleted(handle,ticket,"success","");}
}
'''
if __name__=='__main__':unittest.main()
