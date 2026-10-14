// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Execute production startup/load/preset/setter bodies with a real persistent
// Qt store. The Setting::Manager worker, GPU/platform profiler and display
// scheduler are explicit host boundaries, not simulated device evidence.
#include <QCoreApplication>
#include <QSettings>
#include <QVariant>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStringList>
#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <memory>
#include <cassert>
#include <iostream>
#include "interface/src/metrics/NativeMetrics.h"
#undef qApp
#define Q_OS_IOS
QSettings* store;
struct Lock {
    template<class F> void withReadLock(F f) { f(); }
    template<class F> void withWriteLock(F f) { f(); }
    template<class R,class F> R resultWithReadLock(F f) const { return f(); }
};
namespace Setting {
// Actual production method bodies call the normal typed setting interface.
// Use immediate QSettings commit here to observe bytes across process exits;
// this fixture does not qualify the production asynchronous writer queue.
template<class T> struct Handle {
    QString key; T fallback;
    Handle(QString name,T value):key(name),fallback(value) {}
    T get() const { return store->value(key,QVariant::fromValue(fallback)).template value<T>(); }
    void set(T value) { store->setValue(key,QVariant::fromValue(value)); }
};
}
class Settings {
    QSettings* _manager {store};
    QString getPath(const QString& name) const { return name; }
public:
    static const QString firstRun;
    QVariant value(const QString&,const QVariant&) const;
};
const QString Settings::firstRun {"firstRun"};
#include "settings-value.inc"
struct AntialiasingSetupConfig { enum Mode {NONE=0,TAA,FXAA,MODE_COUNT}; };
struct MakeLightingModelConfig {
    void setShadow(bool) {} void setBloom(bool) {} void setAmbientOcclusion(bool) {}
};
template<class F> void recursivelyUpdateLightingModel(const std::string&,F f) { MakeLightingModelConfig config; f(&config); }
void recursivelyUpdateAntialiasingMode(const std::string&,AntialiasingSetupConfig::Mode) {}
struct MenuOption { static constexpr int Shadows=0,AmbientOcclusion=1; };
struct Menu { static Menu* getInstance() { static Menu instance;return &instance; } void setIsOptionChecked(int,bool) {} };
template<class... T> void logIOSRuntimeMarker(T&&...) {}
struct Config { void setProperty(const char*,float) {} };
struct RenderConfig { Config* getConfig(const char*) { static Config c;return &c; } };
struct Engine { RenderConfig* getConfiguration() { static RenderConfig c;return &c; } };
enum WorldDetailQuality {WORLD_DETAIL_LOW,WORLD_DETAIL_MEDIUM,WORLD_DETAIL_HIGH};
struct LODManager {
    WorldDetailQuality _desktopWorldDetailQuality {WORLD_DETAIL_LOW},_hmdWorldDetailQuality {WORLD_DETAIL_LOW};
    bool _automaticLODAdjust {false};float _lodHalfAngle {0.1f};
    void setDesktopLODTargetFPS(float) {} void setHMDLODTargetFPS(float) {}
    void loadSettings();void saveSettings();void setWorldDetailQuality(WorldDetailQuality,bool);void setWorldDetailQuality(WorldDetailQuality);
    WorldDetailQuality getWorldDetailQuality() const;
    void worldDetailQualityChanged() {}
};
struct DependencyManager { template<class T> static T* get() { static T object;return &object; } };
int REFRESH_RATE_PROFILES[4][6] {};
class RefreshRateManager {
public:
    enum RefreshRateProfile {ECO,INTERACTIVE,REALTIME,CUSTOM,PROFILE_NUM};
    enum RefreshRateRegime {FOCUS_ACTIVE,FOCUS_INACTIVE,UNFOCUS,MINIMIZED,STARTUP,SHUTDOWN,REGIME_NUM};
    enum UXMode {DESKTOP,VR};
    static bool isValidRefreshRateProfile(RefreshRateProfile value) { return value>=ECO && value<PROFILE_NUM; }
    static bool isValidRefreshRateRegime(RefreshRateRegime value) { return value>=FOCUS_ACTIVE && value<=SHUTDOWN; }
    mutable Lock _refreshRateProfileSettingLock;
    RefreshRateProfile _refreshRateProfile {INTERACTIVE};
    Setting::Handle<int> _refreshRateProfileSetting {"refreshRateProfile",INTERACTIVE};
    std::array<Setting::Handle<int>,REGIME_NUM> _customRefreshRateSettings {{
        {"customRefreshRateFocusActive",60},{"customRefreshRateFocusInactive",60},
        {"customRefreshRateUnfocus",60},{"customRefreshRateMinimized",2},
        {"customRefreshRateStartup",30},{"customRefreshRateShutdown",30}}};
    void load() { _refreshRateProfile=static_cast<RefreshRateProfile>(_refreshRateProfileSetting.get());for(int i=0;i<REGIME_NUM;++i) rates[i]=_customRefreshRateSettings[i].get(); }
    int* rates {REFRESH_RATE_PROFILES[CUSTOM]};
    void updateRefreshRateController() const {}
    void setRefreshRateProfile(RefreshRateProfile);void setCustomRefreshRate(RefreshRateRegime,int);
};
RefreshRateManager refresh;
struct App {
    Engine* getRenderEngine() { static Engine e;return &e; }
    RefreshRateManager& getRefreshRateManager() { return refresh; }
    bool isHMDMode() const { return false; }
    QVariant property(const char*) const { return false; }
};
App* qApp;
Setting::Handle<bool> automaticLODAdjust("lodManager/automaticLODAdjust",false);
Setting::Handle<float> lodHalfAngle("lodManager/lodHalfAngle",0.1f);
Setting::Handle<int> desktopWorldDetailQuality("lodManager/desktopWorldDetailQuality",WORLD_DETAIL_MEDIUM);
Setting::Handle<int> hmdWorldDetailQuality("lodManager/hmdWorldDetailQuality",WORLD_DETAIL_MEDIUM);
namespace hifi { namespace properties { const char* OCULUS_STORE="oculus"; } }
const float QUALITY_TO_FPS_HMD[] {30,60,90},QUALITY_TO_FPS_DESKTOP[] {30,45,60};
#include "lod-methods.inc"
constexpr bool RENDER_FORWARD {false};
namespace render { struct Args { enum RenderMethod {DEFERRED,FORWARD}; }; }
class RenderScriptingInterface {
public:
    enum RenderMethod {DEFERRED,FORWARD};
    Lock _renderSettingLock;
    int _renderMethod {FORWARD};
    bool _shadowsEnabled {true},_hazeEnabled {true},_bloomEnabled {true},_ambientOcclusionEnabled {true};
    bool _localLightingEnabled {true},_proceduralMaterialsEnabled {true};
    AntialiasingSetupConfig::Mode _antialiasingMode {AntialiasingSetupConfig::NONE};
    float _viewportResolutionScale {0.8f};QString _fullScreenScreen;
    #include "render-settings.inc"
    static RenderScriptingInterface* getInstance() { static RenderScriptingInterface r;return &r; }
    QStringList getScreens() const { return {"display"}; }
    void setFullScreenScreen(const QString& screen) { _fullScreenScreen=screen; }
    void forceRenderMethod(RenderMethod value) { _renderMethod=value;_renderMethodSetting.set(value); }
    void setRenderMethod(RenderMethod value) { forceRenderMethod(value); }
    void forceHazeEnabled(bool value) { _hazeEnabled=value;_hazeEnabledSetting.set(value); }
    void setHazeEnabled(bool value) { forceHazeEnabled(value); }
    void forceLocalLightingEnabled(bool value) { _localLightingEnabled=value;_localLightingSetting.set(value); }
    void forceProceduralMaterialsEnabled(bool value) { _proceduralMaterialsEnabled=value;_proceduralMaterialsEnabledSetting.set(value); }
    bool getShadowsEnabled() const { return _shadowsEnabled; }
    bool getBloomEnabled() const { return _bloomEnabled; }
    bool getAmbientOcclusionEnabled() const { return _ambientOcclusionEnabled; }
    AntialiasingSetupConfig::Mode getAntialiasingMode() const { return _antialiasingMode; }
    float getViewportResolutionScale() const { return _viewportResolutionScale; }
    void settingsChanged() {}
    void loadSettings();
    void setShadowsEnabled(bool);void forceShadowsEnabled(bool);
    void setBloomEnabled(bool);void forceBloomEnabled(bool);
    void setAmbientOcclusionEnabled(bool);void forceAmbientOcclusionEnabled(bool);
    void setAntialiasingMode(AntialiasingSetupConfig::Mode);void forceAntialiasingMode(AntialiasingSetupConfig::Mode);
    void setViewportResolutionScale(float);void forceViewportResolutionScale(float);
};
#include "render-methods.inc"
namespace platform {
namespace Profiler {
    enum Tier {UNKNOWN,LOW_POWER,LOW,MID,HIGH,CUSTOM,NumTiers};
    Tier profilePlatform() { return HIGH; }
    bool isRenderMethodDeferredCapable() { return true; }
}
namespace keys { namespace display { const char* ppi="ppi"; } }
int getPrimaryDisplay() { return 0; }
std::map<std::string,float> getDisplay(int) { return {}; }
}
class PerformanceManager {
public:
    enum PerformancePreset {UNKNOWN,LOW_POWER,LOW,MID,HIGH,CUSTOM,PROFILE_COUNT};
    mutable Lock _performancePresetSettingLock;
    Setting::Handle<int> _performancePresetSetting {"performancePreset",UNKNOWN};
    static bool isValidPerformancePreset(int value) { return value>=UNKNOWN && value<=CUSTOM; }
    void setupPerformancePresetSettings(bool);void setPerformancePreset(PerformancePreset);
    PerformancePreset getPerformancePreset() const;void applyPerformancePreset(PerformancePreset);
};
#include "performance-methods.inc"
#include "refresh-methods.inc"
class Application {
    struct FirstRun { bool value;bool get() const { return value; } } _firstRun;
    PerformanceManager performance;
public:
    explicit Application(bool first):_firstRun{first} {}
    PerformanceManager& getPerformanceManager() { return performance; }
    RefreshRateManager& getRefreshRateManager() { return refresh; }
    void startup() {
        #include "startup.inc"
    }
};
int main(int argc,char** argv) {
    QCoreApplication app(argc,argv);assert(argc==4);
    QSettings persistent(argv[1],QSettings::IniFormat);store=&persistent;App context;qApp=&context;
    const QString action=QString::fromUtf8(argv[2]);const QString option=QString::fromUtf8(argv[3]);
    refresh.load();DependencyManager::get<LODManager>()->loadSettings();auto render=RenderScriptingInterface::getInstance();
    if(action=="seed") {
        const auto values=QJsonDocument::fromJson(option.toUtf8()).object();
        for(auto it=values.begin();it!=values.end();++it) persistent.setValue(it.key(),it.value().toVariant());
    } else if(action=="user") {
        render->loadSettings();
        PerformanceManager performance;performance.setPerformancePreset(PerformanceManager::CUSTOM);
        const bool first=option=="first";
        render->setShadowsEnabled(first);render->setBloomEnabled(!first);
        render->setAmbientOcclusionEnabled(first);
        render->setAntialiasingMode(first?AntialiasingSetupConfig::FXAA:AntialiasingSetupConfig::TAA);
        render->setViewportResolutionScale(first?1.4f:0.65f);
        DependencyManager::get<LODManager>()->setWorldDetailQuality(first?WORLD_DETAIL_HIGH:WORLD_DETAIL_MEDIUM);
        refresh.setRefreshRateProfile(first?RefreshRateManager::ECO:RefreshRateManager::CUSTOM);
        const int values[] {first?71:41,11,3,2,23,5};
        for(int i=0;i<RefreshRateManager::REGIME_NUM;++i) refresh.setCustomRefreshRate(static_cast<RefreshRateManager::RefreshRateRegime>(i),values[i]);
    } else {
        assert(action=="startup");Application application(option=="first");application.startup();
    }
    persistent.sync();assert(persistent.status()==QSettings::NoError);
    QJsonObject saved;
    const QStringList booleanKeys {"shadowsEnabled","bloomEnabled","ambientOcclusionEnabled",
        "iosViewportResolutionScaleDefaultApplied","hazeEnabled","localLightingEnabled","proceduralMaterialsEnabled",
        "lodManager/automaticLODAdjust"};
    for(const auto& key:persistent.allKeys()) {
        const auto value=persistent.value(key);
        if(booleanKeys.contains(key)) saved.insert(key,value.toBool());
        else if(key=="viewportResolutionScale" || key=="lodManager/lodHalfAngle") saved.insert(key,value.toDouble());
        else if(key=="fullScreenScreen") saved.insert(key,value.toString());
        else saved.insert(key,value.toInt());
    }
    QJsonObject result{{"stored",saved},{"runtime",QJsonObject{
        {"shadows",render->getShadowsEnabled()},{"bloom",render->getBloomEnabled()},
        {"ao",render->getAmbientOcclusionEnabled()},{"aa",render->getAntialiasingMode()},
        {"scale",render->getViewportResolutionScale()},{"lod",DependencyManager::get<LODManager>()->getWorldDetailQuality()},
        {"profile",refresh._refreshRateProfile},{"active",refresh.rates[0]},
        {"inactive",refresh.rates[1]},{"startup",refresh.rates[4]}}}};
    using namespace overte::metrics;Sample sample;sample.producer=Producer::IOS;sample.foreground=true;
    assert(iosFrameLimit(71,sample)==30);sample.thermal=Thermal::Nominal;assert(iosFrameLimit(71,sample)==71);
    sample.thermal=Thermal::Serious;assert(iosFrameLimit(71,sample)==30);
    sample.thermal=Thermal::Critical;assert(iosFrameLimit(71,sample)==15);
    sample.thermal=Thermal::Nominal;sample.lowPowerAvailable=true;sample.lowPower=true;assert(iosFrameLimit(71,sample)==30);
    std::cout<<QJsonDocument(result).toJson(QJsonDocument::Compact).constData()<<std::endl;
}
