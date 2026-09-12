// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QThread>
#include <QPointer>
#include <QLoggingCategory>
Q_LOGGING_CATEGORY(audioclient,"overte.test.audio-mute")
#include <cassert>
#include <thread>
#include <iostream>
#include "libraries/audio-client/src/IOSAudioPermission.h"
#ifdef ACTUAL_IOS_ADAPTER
#include "ios/audio/IOSAudioAdapter.h"
struct Native:overte::ios::NativeAudioOperations {
 bool captures=false;int starts=0;
 bool activate(bool capture,std::function<bool()> current)override{++starts;captures=capture&&current();return current();}
 bool deactivate()override{captures=false;return true;}
 overte::audio::Permission permission()override{return overte::audio::Permission::Granted;}
 void requestPermission(std::function<bool()> current, std::function<void(overte::audio::Permission)> done)override{
  done(current() ? permission() : overte::audio::Permission::Unknown);
 }
};
#else
struct Adapter:overte::audio::IOSAudioSessionAdapter {
 bool capture=true;int starts=0;
 bool microphonePermissionGranted()override{return capture;}
 void requestMicrophonePermission()override{}
 bool activate()override{return true;}
 bool deactivate()override{capture=false;return true;}
 void muted(bool value)override{++starts;capture=!value;}
};
#endif
class AudioClient:public QObject {
public:
 bool _isMuted=false;int signalCount=0,refreshes=0;
 void refreshIOSAudioInput(){++refreshes;}
 void muteToggled(bool value){assert(QThread::currentThread()==thread());assert(value==_isMuted);++signalCount;}
 void setMuted(bool,bool=true);
};
// Only the extracted production method selects iOS branches; host Qt stays host Qt.
#define Q_OS_IOS
#include "mute.inc"
#include "startup.inc"
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);
#ifdef ACTUAL_IOS_ADAPTER
 auto native=std::make_shared<Native>();auto adapter=std::make_shared<overte::ios::IOSAudioAdapter>(native);
 adapter->foreground(true);assert(adapter->activate());assert(adapter->microphonePermissionGranted());
#else
 auto adapter=std::make_shared<Adapter>();
#endif
 assert(overte::audio::installIOSAudioSessionAdapter(adapter));
 AudioClient client;assert(overteIOSMicrophonePermissionGranted());
 std::thread worker([&]{client.setMuted(true);});worker.join();
 assert(!client._isMuted&&overteIOSMicrophonePermissionGranted());
 QCoreApplication::processEvents();assert(client._isMuted&&client.signalCount==1&&!overteIOSMicrophonePermissionGranted());
 client.setMuted(false,false);assert(!client._isMuted&&client.signalCount==1&&overteIOSMicrophonePermissionGranted());
 client.setMuted(false);assert(client.signalCount==1);
 QPointer<AudioClient> doomed=new AudioClient;
 std::thread pending([&]{doomed->setMuted(true);});pending.join();delete doomed.data();
 QCoreApplication::processEvents();assert(!doomed&&overteIOSMicrophonePermissionGranted());
 // Initial muted state must survive activation rather than requesting capture.
 initialAudio(true);assert(!overteIOSMicrophonePermissionGranted());
 overteIOSSetAudioMuted(false);assert(overteIOSMicrophonePermissionGranted());
#ifdef ACTUAL_IOS_ADAPTER
 std::cout<<"PASS actual AudioClient mute -> Shared bridge -> actual IOSAudioAdapter, Qt queue/cancellation; OS operations are fixtures\n";
#else
 std::cout<<"PASS actual AudioClient mute -> Shared bridge, Qt queue/cancellation; adapter is a fixture\n";
#endif
}
