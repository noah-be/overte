// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Real Setting::Handle and production LOD bodies. Only the asynchronous setting
// manager and frame-rate/display endpoints are substituted by a Qt INI seam.
#include <QCoreApplication>
#include <QSettings>
#include <QJsonDocument>
#include <QJsonObject>
#include <algorithm>
#include <cmath>
#include <mutex>
#include <iostream>
#include <vector>
#include "libraries/shared/src/SettingHandle.h"

Q_LOGGING_CATEGORY(settings_handle, "settings.handle")
QSettings* store;
namespace Setting {
void Interface::init() {
    _isInitialized = true;
    load();
}
void Interface::maybeInit() const {
    if (!_isInitialized) { const_cast<Interface*>(this)->init(); }
}
void Interface::load() {
    const auto value = store->value(_key);
    if (value.isValid()) { setVariant(value); }
}
void Interface::save() {
    if (_isSet) { store->setValue(_key, getVariant()); }
    else { store->remove(_key); }
    store->sync();
}
void Interface::deinit() { if (_isInitialized) { save(); } }
}

#if defined(TEST_IOS)
#define Q_OS_IOS
#elif defined(TEST_PHONE)
#define Q_OS_ANDROID
#define ANDROID_APP_PHONE_INTERFACE
#elif defined(TEST_PICO)
#define Q_OS_ANDROID
#endif

namespace hifi { namespace properties { const char* OCULUS_STORE = "oculus-store"; } }
const QString Settings::firstRun { "firstRun" };
#include "lod-declarations.inc"

class LODManager {
public:
    void loadSettings();
    void saveSettings();
    void setAutomaticLODAdjust(bool value);
    void setLODAngleDeg(float value);
    void setWorldDetailQuality(WorldDetailQuality quality, bool hmd);
    void setDesktopLODTargetFPS(float fps) { desktopFPS = fps; }
    void setHMDLODTargetFPS(float fps) { hmdFPS = fps; }
    void autoLODChanged() { ++notifications; }
    bool _automaticLODAdjust { DEFAULT_LOD_AUTO_ADJUST };
    float _lodHalfAngle { 0.0f };
    WorldDetailQuality _desktopWorldDetailQuality { DEFAULT_WORLD_DETAIL_QUALITY };
    WorldDetailQuality _hmdWorldDetailQuality { DEFAULT_WORLD_DETAIL_QUALITY };
    std::mutex _automaticLODLock;
    float desktopFPS {}, hmdFPS {};
    int notifications {};
};
#include "lod-methods.inc"

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    if (argc < 3) { return 2; }
    auto* settings = new QSettings(QString::fromLocal8Bit(argv[1]), QSettings::IniFormat);
    // Keep the backing store alive through static Handle destruction.
    store = settings;
    LODManager lod;
    lod.loadSettings();
    const QString action = QString::fromLocal8Bit(argv[2]);
    if (action == "user") {
        if (argc != 5) { return 2; }
        lod.setAutomaticLODAdjust(QString::fromLocal8Bit(argv[3]) == "true");
        lod.setLODAngleDeg(QString::fromLocal8Bit(argv[4]).toFloat());
    } else if (action == "save") {
        lod.saveSettings();
    } else if (action != "startup") { return 2; }
    QJsonObject result {{"automatic", lod._automaticLODAdjust},
        {"angle", glm::degrees(lod._lodHalfAngle) * 2.0f},
        {"nativeDefaultAngle", glm::degrees(getHalfAngleFromVisibilityDistance(DEFAULT_VISIBILITY_DISTANCE_FOR_UNIT_ELEMENT)) * 2.0f},
        {"desktopQuality", static_cast<int>(lod._desktopWorldDetailQuality)},
        {"hmdQuality", static_cast<int>(lod._hmdWorldDetailQuality)},
        {"desktopFPS", lod.desktopFPS}, {"hmdFPS", lod.hmdFPS},
        {"notifications", lod.notifications}};
    result.insert("storedAutomatic", store->contains("lodManager/automaticLODAdjust"));
    result.insert("storedAngle", store->contains("lodManager/lodHalfAngle"));
    std::cout << QJsonDocument(result).toJson(QJsonDocument::Compact).constData() << '\n';
}
