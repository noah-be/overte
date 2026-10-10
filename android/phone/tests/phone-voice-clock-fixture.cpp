// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Production methods are inserted by the runner. OS and device operations are fixtures.
#include <QCoreApplication>
#include <QThread>
#include <QTimer>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QMutex>
#include <QMutexLocker>
#include <QVariantMap>
#include <QDebug>
#include <cassert>
#include <memory>
#include <functional>
#include <vector>
#include "VoiceTestSignal.h"
#define Q_OS_ANDROID
bool picoMicTraceEnabled(){return false;}
constexpr quint64 USECS_PER_SECOND=1000000;
quint64 usecTimestampNow(){return 0;}
namespace AudioConstants { constexpr int SAMPLE_RATE=24000, NETWORK_FRAME_SAMPLES_PER_CHANNEL=240, SAMPLE_SIZE=2, STEREO=2, MONO=1; }
namespace QAudio { enum State {ActiveState,StoppedState,SuspendedState}; enum Error {NoError}; enum Mode {AudioInput,AudioOutput}; }
namespace overte::security { enum class DiagnosticEvent {Redacted}; int diagnosticEvent(DiagnosticEvent){return 0;} }
struct Lock:QMutexLocker<QMutex>{explicit Lock(QMutex& mutex):QMutexLocker<QMutex>(&mutex){}};
using HifiQtAudioDevice=int;
using QAudioDeviceInfo=int;
struct HifiAudioDeviceInfo {int id=0;int getDevice()const{return id;}void setDevice(int v){id=v;}};
struct DeviceSource:QObject {void stop(){}QAudio::Error error()const{return QAudio::NoError;}QAudio::State state()const{return QAudio::ActiveState;}};
struct Resource {};
struct AudioGate {
    explicit AudioGate(int, int) {}
    bool render(int16_t*,int16_t*,int) {return true;}
    bool removeDC(int16_t*,int16_t*,int) {return true;}
};
struct Transform {void setTranslation(int){}void setRotation(int){}};
enum class PacketType {MicrophoneAudioWithEcho,MicrophoneAudioNoEcho,SilentAudioFrame};
struct Counter {void increment(){}void sentPacket(){}};
struct Encoder {void encode(const QByteArray& input,QByteArray& output){output=input;}};
class AudioClient:public QObject {
public:
 QMutex _checkDevicesMutex,_deviceMutex,_checkPeakValuesMutex;
 QTimer* _checkDevicesTimer=nullptr;QTimer* _checkPeakValuesTimer=nullptr;
 bool _audioLifecycleRunning=true,_isMuted=false,_isStereoInput=false,_audioPaused=false;
 bool _isNoiseGateEnabled=false,_isNoiseReductionAutomatic=false,_audioGateOpen=true,_shouldEchoToServer=false;
 float _lastInputLoudness=0,_lastRawInputLoudness=0,_lastSmoothedRawInputLoudness=0,_noiseReductionThreshold=0;
 DeviceSource* _audioInput=nullptr;
 QObject* _inputDevice=nullptr;
 QTimer* _dummyAudioInput=nullptr;
 Resource* _inputToNetworkResampler=nullptr,*_loopbackResampler=nullptr;
 AudioGate* _audioGate=nullptr;
 QByteArray _loopbackPendingAudio,_inputRingBuffer;
 int _numInputCallbackBytes=0;
 std::uint64_t _iosInputRevision=0;
 HifiAudioDeviceInfo _inputDeviceInfo;
 QString _selectedCodecName;
 Encoder* _encoder=nullptr;
 Counter _silentOutbound,_audioOutbound,_stats;
 int _outgoingAvatarAudioSequenceNumber=0,avatarBoundingBoxCorner=0,avatarBoundingBoxScale=0;
 std::function<int()> _positionGetter=[]{return 0;},_orientationGetter=[]{return 0;};
 std::vector<QByteArray> packets;
 std::vector<PacketType> packetTypes;
 QTimer _checkInputTimer; bool _shouldRestartInputSetup=false;
 void checkInputTimeout(){}
 HifiAudioDeviceInfo defaultAudioDeviceForMode(QAudio::Mode,QString){return {1};}
 void deviceChanged(QAudio::Mode,HifiAudioDeviceInfo){}
 void inputLoudnessChanged(float,bool){}
 void muteToggled(bool){}
 void inputReceived(QByteArray&){}
 void noiseGateOpened(){}
 void noiseGateClosed(){}
 float loudnessToLevel(float value){return value;}
 void emitAudioPacket(const char* bytes,int size,int,bool,Transform,int,int,PacketType type,QString){packets.emplace_back(bytes,size);packetTypes.push_back(type);}
 VOICE_MEMBERS
 bool prepareVoiceTest();
 bool sendVoiceTest(const std::array<int,12>&);
 void resetVoiceTest();
 void touchVoiceTest();
 QVariantMap voiceTestStatus()const;
 void handleAudioInput(QByteArray&);
 void setMuted(bool,bool emitSignal=true);
 void stop();
 bool switchOutputToAudioDevice(HifiAudioDeviceInfo,bool){return true;}
 bool switchInputToAudioDevice(HifiAudioDeviceInfo,bool isShutdownRequest=false);
};
VOICE_METHODS
AUDIO_INPUT_METHOD
MUTE_METHOD
STOP_METHOD
INPUT_SHUTDOWN_PREFIX
 // The normal-start remainder is a controllable device fixture. It deliberately
 // supplies no readyRead callbacks, reproducing an input handle without progress.
 (void)supportedFormat;
 _inputDeviceInfo=inputDeviceInfo;
 return true;
}
void waitMs(int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();}
int main(int argc,char**argv){
 QCoreApplication app(argc,argv);
 AudioClient audio;
 const std::array<int,12> symbols={0,1,2,3,4,5,6,7,0,1,2,3};
 assert(!audio.sendVoiceTest(symbols));
 audio._audioInput=new DeviceSource;audio._inputDevice=new QObject(&audio);
 audio._dummyAudioInput=new QTimer(&audio);audio._dummyAudioInput->start(10);
 audio._audioGate=new AudioGate(24000,1);
 assert(audio.prepareVoiceTest());assert(!audio.prepareVoiceTest());
 audio.setMuted(true);audio.switchInputToAudioDevice({},true);
 assert(!audio._audioInput && !audio._dummyAudioInput && !audio._audioGate);
 assert(audio.sendVoiceTest(symbols));
 waitMs(5100);
 assert(!audio._voiceTestSignal.active() && audio._voiceTestSignal.frames()==VoiceTestSignal::FRAMES);
 assert(!audio.packets.empty());
 for(const auto& pcm:audio.packets){assert(pcm==QByteArray(pcm.size(),0));}
 for(auto type:audio.packetTypes){assert(type==PacketType::SilentAudioFrame || type==PacketType::MicrophoneAudioNoEcho);}
 auto status=audio.voiceTestStatus();assert(status["sourceClockActive"].toBool());
 audio.resetVoiceTest();auto count=audio.packets.size();waitMs(40);assert(audio.packets.size()==count);
 assert(!audio.voiceTestStatus()["sourceClockActive"].toBool());
 audio.setMuted(false);audio.packets.clear();assert(audio.prepareVoiceTest());assert(audio.sendVoiceTest(symbols));
 QByteArray physical(480,42);const auto before=audio._voiceTestSignal.frames();
 audio.handleAudioInput(physical);assert(audio._voiceTestSignal.frames()==before && audio.packets.empty());
 waitMs(5100);assert(audio._voiceTestSignal.frames()==VoiceTestSignal::FRAMES);
 bool audible=false;for(const auto& pcm:audio.packets){audible|=pcm!=QByteArray(pcm.size(),0);}assert(audible);
 audio.resetVoiceTest();
 // A paused Android audio lifecycle cancels the source and retains incomplete progress.
 assert(audio.prepareVoiceTest());assert(audio.sendVoiceTest(symbols));waitMs(40);
 audio._audioPaused=true;waitMs(30);status=audio.voiceTestStatus();
 assert(!status["sourceClockActive"].toBool());assert(status["frames"].toInt()<VoiceTestSignal::FRAMES);
 assert(status["sourceError"].toString()=="voice-source-lifecycle-stopped");
 assert(!audio.prepareVoiceTest());assert(audio._isMuted);
 audio._audioPaused=false;audio.resetVoiceTest();audio.setMuted(false);
 assert(audio.prepareVoiceTest());assert(audio.sendVoiceTest(symbols));
 // Clock stalls are failures rather than accelerated or truncated challenges.
 QThread::msleep(150);audio.handleVoiceTestInput();status=audio.voiceTestStatus();
 assert(status["sourceError"].toString()=="voice-source-clock-late");assert(status["frames"].toInt()<VoiceTestSignal::FRAMES);
 audio.resetVoiceTest();assert(audio.prepareVoiceTest());audio._voiceTestLeaseTimer->start(20);waitMs(40);
 assert(audio.voiceTestStatus()["sourceError"].toString()=="voice-source-lease-expired");assert(audio._isMuted);
 audio.resetVoiceTest();assert(audio.prepareVoiceTest());assert(audio.sendVoiceTest(symbols));
 audio.stop();waitMs(30);assert(!audio._voiceTestSignal.active());
 assert(audio.voiceTestStatus()["frames"].toInt()<VoiceTestSignal::FRAMES);
 assert(audio.voiceTestStatus()["sourceError"].toString()=="voice-source-lifecycle-stopped");
 assert(!audio.voiceTestStatus()["sourceClockActive"].toBool());audio.resetVoiceTest();
}
