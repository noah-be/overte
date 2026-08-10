//
//  Application.cpp
//  interface/src
//
//  Created by Andrzej Kapolka on 5/10/13.
//  Copyright 2013 High Fidelity, Inc.
//  Copyright 2020 Vircadia contributors.
//  Copyright 2022-2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#include "Application.h"

#include <cmath>

#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
#include <QDesktopWidget>
#endif
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QDateTime>
#include <QSaveFile>
#include <QtGui/QClipboard>
#include <QtNetwork/QLocalSocket>
#include <QtNetwork/QLocalServer>
#include <QtNetwork/QSslCertificate>
#include <QtNetwork/QSslConfiguration>
#include <QtQuick/QQuickWindow>
#include <QWidget>
#ifdef Q_OS_ANDROID
#include <QLoggingCategory>
#include <sys/system_properties.h>
#endif

#include <AccountManager.h>
#include <AddressManager.h>
#include <AnimationCacheScriptingInterface.h>
#include <AnimDebugDraw.h>
#include <AvatarBookmarks.h>
#include <audio/AudioScope.h>
#include <avatar/AvatarManager.h>
#include <avatar/AvatarPackager.h>
#include <avatar/GrabManager.h>
#include <BuildInfo.h>
#include <controllers/ScriptingInterface.h>
#include <controllers/UserInputMapper.h>
#include <CrashHelpers.h>
#include <DebugDraw.h>
#include <DesktopPreviewProvider.h>
#include <display-plugins/CompositorHelper.h>
#include <display-plugins/DisplayPlugin.h>
#include <DomainAccountManager.h>
#include <EntityScriptServerLogClient.h>
#include <FramebufferCache.h>
#include <gl/GLHelpers.h>
#include <GPUIdent.h>
#include <graphics-scripting/GraphicsScriptingInterface.h>
#include <hfm/ModelFormatRegistry.h>
#include <input-plugins/InputPlugin.h>
#include <input-plugins/KeyboardMouseDevice.h>
#include <LocationScriptingInterface.h>
#include <LogHandler.h>
#include <MainWindow.h>
#include <MessagesClient.h>
#include <material-networking/TextureCacheScriptingInterface.h>
#include <model-networking/ModelCacheScriptingInterface.h>
#include <networking/CloseEventSender.h>
#include <OffscreenUi.h>
#include <PickManager.h>
#include <platform/Platform.h>
#include <platform/PlatformKeys.h>
#include <platform/backend/PlatformInstance.h>
#include <plugins/OculusPlatformPlugin.h>
#include <plugins/PluginManager.h>
#include <plugins/PluginUtils.h>
#include <plugins/SteamClientPlugin.h>
#include <Preferences.h>
#include <procedural/MaterialCacheScriptingInterface.h>
#include <QmlFragmentClass.h>
#include <QmlWebWindowClass.h>
#include <QmlWindowClass.h>
#include <raypick/PickScriptingInterface.h>
#include <raypick/PointerScriptingInterface.h>
#include <raypick/RayPickScriptingInterface.h>
#include <recording/RecordingScriptingInterface.h>
#include <render/EngineStats.h>
#include <ResourceScriptingInterface.h>
#include <ResourceCache.h>
#include <ResourceRequest.h>
#include <SandboxUtils.h>
#include <SceneScriptingInterface.h>
#include <ScriptEngines.h>
#include <scripting/AccountServicesScriptingInterface.h>
#include <scripting/Audio.h>
#include <scripting/ClipboardScriptingInterface.h>
#include <scripting/ControllerScriptingInterface.h>
#include <scripting/DesktopScriptingInterface.h>
#include <scripting/HMDScriptingInterface.h>
#include <scripting/KeyboardScriptingInterface.h>
#include <scripting/MenuScriptingInterface.h>
#include <scripting/PerformanceScriptingInterface.h>
#include <scripting/PlatformInfoScriptingInterface.h>
#include <scripting/RatesScriptingInterface.h>
#include <scripting/RenderScriptingInterface.h>
#include <scripting/SelectionScriptingInterface.h>
#include <scripting/SettingsScriptingInterface.h>
#include <scripting/TestScriptingInterface.h>
#include <scripting/WindowScriptingInterface.h>
#include <scripting/OSCScriptingInterface.h>
#ifndef Q_OS_ANDROID
#include <shared/FileLogger.h>
#endif
#include <shared/GlobalAppProperties.h>
#include <shared/PlatformHelper.h>
#include <shared/QtHelpers.h>
#include <SoundCacheScriptingInterface.h>
#include <StatTracker.h>
#include <ui/AvatarInputs.h>
#include <ui/AnimStats.h>
#include <ui/TabletScriptingInterface.h>
#include <ui/Keyboard.h>
#include <ui/OctreeStatsProvider.h>
#include <ui/OffscreenQmlSurfaceCache.h>
#include <ui/Snapshot.h>
#include <ui/SnapshotAnimated.h>
#include <ui/StandAloneJSConsole.h>
#include <ui/Stats.h>
#include <ui/ToolbarScriptingInterface.h>
#include <UserActivityLogger.h>
#include <UserActivityLoggerScriptingInterface.h>
#include <UsersScriptingInterface.h>

#include "AboutUtil.h"
#include "ApplicationEventHandler.h"
#include "AudioClient.h"
#include "DeadlockWatchdog.h"
#include "GLCanvas.h"
#include "LocationBookmarks.h"
#include "LODManager.h"
#include "Menu.h"
#include "ResourceRequestObserver.h"
#if defined(Q_OS_MAC) || defined(Q_OS_WIN)
#include "SpeechRecognizer.h"
#endif
#include "Util.h"
#ifndef USE_GL
#include "vk/VKWindow.h"
#endif

#if defined(Q_OS_WIN)
#include "WindowsSystemInfo.h"

// On Windows PC, NVidia Optimus laptop, we want to enable NVIDIA GPU
// FIXME seems to be broken.
extern "C" {
 _declspec(dllexport) DWORD NvOptimusEnablement = 0x00000001;
}
#endif

#if defined(Q_OS_MAC)
// On Mac OS, disable App Nap to prevent audio glitches while running in the background
#include "AppNapDisabler.h"
static AppNapDisabler appNapDisabler;   // disabled, while in scope
#endif

#if defined(Q_OS_ANDROID)
#include "ui/PhoneGraphicsPolicy.h"
#include <android/log.h>
#endif

// For processing on QThreadPool, we target a number of threads after reserving some
// based on how many are being consumed by the application and the display plugin.  However,
// we will never drop below the 'min' value
static const int MIN_PROCESSING_THREAD_POOL_SIZE = 2;
static const int ENTITY_SERVER_CONNECTION_TIMEOUT = 5000;

const float DEFAULT_HMD_TABLET_SCALE_PERCENT = 60.0f;
const float DEFAULT_DESKTOP_TABLET_SCALE_PERCENT = 75.0f;
const bool DEFAULT_DESKTOP_TABLET_BECOMES_TOOLBAR = true;
const bool DEFAULT_HMD_TABLET_BECOMES_TOOLBAR = false;
const bool DEFAULT_PREFER_STYLUS_OVER_LASER = false;
const bool DEFAULT_PREFER_AVATAR_FINGER_OVER_STYLUS = false;
const bool DEFAULT_MOUSE_CAPTURE_VR = false;
const bool DEFAULT_SHOW_GRAPHICS_ICON = true;
const bool DEFAULT_MINI_TABLET_ENABLED = false;
const bool DEFAULT_AWAY_STATE_WHEN_FOCUS_LOST_IN_VR_ENABLED = true;

static const quint64 TOO_LONG_SINCE_LAST_SEND_DOWNSTREAM_AUDIO_STATS = 1 * USECS_PER_SECOND;

static const QString DESKTOP_LOCATION = QStandardPaths::writableLocation(QStandardPaths::DesktopLocation);
static const QString KEEP_ME_LOGGED_IN_SETTING_NAME = "keepMeLoggedIn";
const QString DEFAULT_CURSOR_NAME = "SYSTEM";

Setting::Handle<int> sessionRunTime { "sessionRunTime", 0 };

void messageHandler(QtMsgType type, const QMessageLogContext& context, const QString& message) {
    QString logMessage = LogHandler::getInstance().printMessage((LogMsgType) type, context, message);

    if (!logMessage.isEmpty()) {
#ifdef Q_OS_ANDROID
        const char * local=logMessage.toStdString().c_str();
        switch (type) {
            case QtDebugMsg:
                __android_log_write(ANDROID_LOG_DEBUG,"Interface",local);
                break;
            case QtInfoMsg:
                __android_log_write(ANDROID_LOG_INFO,"Interface",local);
                break;
            case QtWarningMsg:
                __android_log_write(ANDROID_LOG_WARN,"Interface",local);
                break;
            case QtCriticalMsg:
                __android_log_write(ANDROID_LOG_ERROR,"Interface",local);
                break;
            case QtFatalMsg:
            default:
                __android_log_write(ANDROID_LOG_FATAL,"Interface",local);
                abort();
        }
#else
        qApp->getLogger()->addMessage(qPrintable(logMessage));
#endif
    }
}

Application::Application(
    int& argc, char** argv,
    QElapsedTimer& startupTimer
) :
    QApplication(argc, argv),
#ifdef USE_GL
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    _window(new MainWindow(desktop())),
#else
    _window(new MainWindow()),
#endif
#else
    _vkWindow(new VKWindow()),
    _vkWindowWrapper(QWidget::createWindowContainer(_vkWindow)),
    _window(new MainWindow(_vkWindowWrapper)),
#endif
    // Menu needs to be initialized before other initializers. Otherwise deadlock happens on qApp->getWindow()->menuBar().
    _isMenuInitialized(initMenu()),
#ifndef Q_OS_ANDROID
    _logger(new FileLogger(this)),
#endif
    _sessionRunTimer(startupTimer),
    _lastNackTime(usecTimestampNow()),
    _lastSendDownstreamAudioStats(usecTimestampNow()),
    _useDiscordPresence("useDiscordPresence", true),
    _firstRun(Settings::firstRun, true),
    _previousScriptLocation("LastScriptLocation", DESKTOP_LOCATION),
    _previousPreferredDisplayMode("previousPreferredDisplayMode", 0),
    // UI
    _hmdTabletScale("hmdTabletScale", DEFAULT_HMD_TABLET_SCALE_PERCENT),
    _desktopTabletScale("desktopTabletScale", DEFAULT_DESKTOP_TABLET_SCALE_PERCENT),
    _desktopTabletBecomesToolbarSetting("desktopTabletBecomesToolbar", DEFAULT_DESKTOP_TABLET_BECOMES_TOOLBAR),
    _hmdTabletBecomesToolbarSetting("hmdTabletBecomesToolbar", DEFAULT_HMD_TABLET_BECOMES_TOOLBAR),
    _preferStylusOverLaserSetting("preferStylusOverLaser", DEFAULT_PREFER_STYLUS_OVER_LASER),
    _preferAvatarFingerOverStylusSetting("preferAvatarFingerOverStylus", DEFAULT_PREFER_AVATAR_FINGER_OVER_STYLUS),
    _defaultMouseCaptureVR("defaultMouseCaptureVR", DEFAULT_MOUSE_CAPTURE_VR),
    _constrainToolbarPosition("toolbar/constrainToolbarToCenterX", true),
    _awayStateWhenFocusLostInVREnabled("awayStateWhenFocusLostInVREnabled", DEFAULT_AWAY_STATE_WHEN_FOCUS_LOST_IN_VR_ENABLED),
    _preferredCursor("preferredCursor", DEFAULT_CURSOR_NAME),
    _darkTheme("darkTheme", true),
    _miniTabletEnabledSetting("miniTabletEnabled", DEFAULT_MINI_TABLET_ENABLED),
    // Entities
    _maxOctreePacketsPerSecond("maxOctreePPS", DEFAULT_MAX_OCTREE_PPS),
    _maxOctreePPS(_maxOctreePacketsPerSecond.get()),
    // Camera
    _fieldOfView("fieldOfView", DEFAULT_FIELD_OF_VIEW_DEGREES),
    _cameraClippingEnabled("cameraClippingEnabled", false)
{
#ifdef Q_OS_ANDROID
    // Qt's generic Unix CA search paths do not include Android's system trust
    // store. Import it before AccountManager starts HTTPS requests.
    auto sslConfiguration = QSslConfiguration::defaultConfiguration();
    QList<QSslCertificate> androidSystemCAs;
    const QDir androidCaDirectory("/system/etc/security/cacerts");
    for (const auto& fileName : androidCaDirectory.entryList(QDir::Files)) {
        QFile certificateFile(androidCaDirectory.filePath(fileName));
        if (certificateFile.open(QIODevice::ReadOnly)) {
            androidSystemCAs.append(
                QSslCertificate::fromData(certificateFile.readAll(), QSsl::Pem));
        }
    }
    sslConfiguration.addCaCertificates(androidSystemCAs);
    QSslConfiguration::setDefaultConfiguration(sslConfiguration);
    qInfo() << "Loaded Android system CA certificates:" << androidSystemCAs.size();
#endif

    setProperty(hifi::properties::CRASHED, _previousSessionCrashed);

    LogHandler::getInstance().moveToThread(thread());
    LogHandler::getInstance().setupRepeatedMessageFlusher();
    qInstallMessageHandler(messageHandler);

    DependencyManager::set<PathUtils>();
}

Application::~Application() {
    // remove avatars from physics engine
    if (auto avatarManager = DependencyManager::get<AvatarManager>()) {
        // AvatarManager may not yet exist in case of an early exit

        avatarManager->clearOtherAvatars();
        auto myCharacterController = getMyAvatar()->getCharacterController();
        myCharacterController->clearDetailedMotionStates();

        PhysicsEngine::Transaction transaction;
        avatarManager->buildPhysicsTransaction(transaction);
        _physicsEngine->processTransaction(transaction);
        avatarManager->handleProcessedPhysicsTransaction(transaction);
        avatarManager->deleteAllAvatars();
    }

    if (_physicsEngine) {
        _physicsEngine->setCharacterController(nullptr);
    }

    // the _shapeManager should have zero references
    _shapeManager.collectGarbage();
    assert(_shapeManager.getNumShapes() == 0);

    if (_graphicsEngine) {
        // shutdown graphics engine
        _graphicsEngine->shutdown();
    }

    _gameWorkload.shutdown();

    DependencyManager::destroy<Preferences>();
    PlatformHelper::shutdown();

    if (_entityClipboard) {
        _entityClipboard->eraseAllOctreeElements();
        _entityClipboard.reset();
    }

    if (_octreeProcessor) {
        _octreeProcessor->terminate();
    }

    if (_entityEditSender) {
        _entityEditSender->terminate();
    }

    if (auto pluginManager = PluginManager::getInstance()) {
        if (auto steamClient = pluginManager->getSteamClientPlugin()) {
            steamClient->shutdown();
        }

        if (auto oculusPlatform = pluginManager->getOculusPlatformPlugin()) {
            oculusPlatform->shutdown();
        }
    }

    DependencyManager::destroy<PluginManager>();

    DependencyManager::destroy<CompositorHelper>(); // must be destroyed before the FramebufferCache

    DependencyManager::destroy<SoundCacheScriptingInterface>();

    DependencyManager::destroy<AudioInjectorManager>();
    DependencyManager::destroy<AvatarManager>();
    DependencyManager::destroy<AnimationCacheScriptingInterface>();
    DependencyManager::destroy<AnimationCache>();
    DependencyManager::destroy<FramebufferCache>();
    DependencyManager::destroy<MaterialCacheScriptingInterface>();
    DependencyManager::destroy<MaterialCache>();
    DependencyManager::destroy<TextureCacheScriptingInterface>();
    DependencyManager::destroy<TextureCache>();
    DependencyManager::destroy<ModelCacheScriptingInterface>();
    DependencyManager::destroy<ModelCache>();
    DependencyManager::destroy<ModelFormatRegistry>();
    DependencyManager::destroy<ScriptCache>();
    DependencyManager::destroy<SoundCacheScriptingInterface>();
    DependencyManager::destroy<SoundCache>();
    DependencyManager::destroy<OctreeStatsProvider>();
    DependencyManager::destroy<GeometryCache>();

    if (auto resourceManager = DependencyManager::get<ResourceManager>()) {
        resourceManager->cleanup();
    }

    // remove the NodeList from the DependencyManager
    DependencyManager::destroy<NodeList>();

#if 0
    ConnexionClient::getInstance().destroy();
#endif
    // The window takes ownership of the menu, so this has the side effect of destroying it.
    _window->setMenuBar(nullptr);

    _window->deleteLater();

    // make sure that the quit event has finished sending before we take the application down
    if (auto closeEventSender = DependencyManager::get<CloseEventSender>()) {
        while (!closeEventSender->hasFinishedQuitEvent() && !closeEventSender->hasTimedOutQuitEvent()) {
            // sleep a little so we're not spinning at 100%
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        // quit the thread used by the closure event sender
        closeEventSender->thread()->quit();
    }

    // Can't log to file past this point, FileLogger about to be deleted
    qInstallMessageHandler(LogHandler::verboseMessageHandler);

#ifdef Q_OS_MAC
    // 26 Feb 2021 - Tried re-enabling this call but OSX still crashes on exit.
    //
    // 10/16/2019 - Disabling this call. This causes known crashes (A), and it is not
    // fully understood whether it might cause other unknown crashes (B).
    //
    // (A) Although we try to shutdown the ScriptEngine threads in onAboutToQuit, there is
    // currently no guarantee that they have stopped. Waiting on them to stop has so far appeared to
    // never return on Mac, causing the application to hang on shutdown. Because ScriptEngines
    // may still be running, they may end up receiving events that are triggered from this processEvents call,
    // and then try to access resources that are no longer available at this point in time.
    // If the ScriptEngine threads were fully destroyed before getting here, this would
    // not be an issue.
    //
    // (B) It seems likely that a bunch of potential event handlers are dependent on Application
    // and other common dependencies to be available and not destroyed or in the middle of being
    // destroyed.


    // Clear the event queue before application is totally destructed.
    // This will drain the messasge queue of pending "deleteLaters" queued up
    // during shutdown of the script engines.
    // We do this here because there is a possiblty that [NSApplication terminate:]
    // will be called during processEvents which will invoke all static destructors.
    // We want to postpone this utill the last possible moment.
    //QCoreApplication::processEvents();
#endif
}

bool Application::isServerlessMode() const {
    auto tree = getEntities()->getTree();
    if (tree) {
        return tree->isServerlessMode();
    }

    return false;
}

QString Application::getUserAgent() {
    if (QThread::currentThread() != thread()) {
        QString userAgent;

        BLOCKING_INVOKE_METHOD(this, "getUserAgent", Q_RETURN_ARG(QString, userAgent));

        return userAgent;
    }

    QString userAgent = NetworkingConstants::OVERTE_USER_AGENT + "/" + BuildInfo::VERSION + "; "
        + QSysInfo::productType() + " " + QSysInfo::productVersion() + ")";

    auto formatPluginName = [](QString name) -> QString { return name.trimmed().replace(" ", "-");  };

    // For each plugin, add to userAgent
    const auto& displayPlugins = PluginManager::getInstance()->getDisplayPlugins();
    for (const auto& dp : displayPlugins) {
        if (dp->isActive() && dp->isHmd()) {
            userAgent += " " + formatPluginName(dp->getName());
        }
    }
    const auto& inputPlugins = PluginManager::getInstance()->getInputPlugins();
    for (const auto& ip : inputPlugins) {
        if (ip->isActive()) {
            userAgent += " " + formatPluginName(ip->getName());
        }
    }
    // for codecs, we include all of them, even if not active
    const auto& codecPlugins = PluginManager::getInstance()->getCodecPlugins();
    for (const auto& cp : codecPlugins) {
        userAgent += " " + formatPluginName(cp->getName());
    }

    return userAgent;
}

static const QString CONTENT_SET_NAME_QUERY_PARAM = "name";
void Application::replaceDomainContent(const QString& url, const QString& itemName) {
    qCDebug(interfaceapp) << "Attempting to replace domain content";
    QUrl msgUrl(url);
    QUrlQuery urlQuery(msgUrl.query());
    urlQuery.addQueryItem(CONTENT_SET_NAME_QUERY_PARAM, itemName);
    msgUrl.setQuery(urlQuery.query(QUrl::QUrl::FullyEncoded));
    QByteArray urlData(msgUrl.toString(QUrl::QUrl::FullyEncoded).toUtf8());
    auto limitedNodeList = DependencyManager::get<NodeList>();
    const auto& domainHandler = limitedNodeList->getDomainHandler();

    auto octreeFilePacket = NLPacket::create(PacketType::DomainContentReplacementFromUrl, urlData.size(), true);
    octreeFilePacket->write(urlData);
    limitedNodeList->sendPacket(std::move(octreeFilePacket), domainHandler.getSockAddr());

    auto addressManager = DependencyManager::get<AddressManager>();
    addressManager->handleLookupString(DOMAIN_SPAWNING_POINT);
    QString newHomeAddress = addressManager->getHost() + DOMAIN_SPAWNING_POINT;
    qCDebug(interfaceapp) << "Setting new home bookmark to: " << newHomeAddress;
    DependencyManager::get<LocationBookmarks>()->setHomeLocationToAddress(newHomeAddress);
}

void Application::openDirectory(const QString& path) {
    if (QThread::currentThread() != thread()) {
        QMetaObject::invokeMethod(this, "openDirectory", Q_ARG(const QString&, path));
        return;
    }

    QString dirPath = path;
#if defined(Q_OS_WIN)
    const QString FILE_SCHEME = "file:///";
#else
    const QString FILE_SCHEME = "file://";
#endif
    if (dirPath.startsWith(FILE_SCHEME)) {
        dirPath.remove(0, FILE_SCHEME.length());
    }
    QFileInfo fileInfo(dirPath);
    if (fileInfo.isDir()) {
        auto scheme = QUrl(path).scheme();
        QDesktopServices::unsetUrlHandler(scheme);
        QDesktopServices::openUrl(path);
        QDesktopServices::setUrlHandler(scheme, this, "showUrlHandler");
    }
}

void Application::forceLoginWithTokens(const QString& tokens) {
    DependencyManager::get<AccountManager>()->setAccessTokens(tokens);
    Setting::Handle<bool>(KEEP_ME_LOGGED_IN_SETTING_NAME, true).set(true);
}

void Application::setConfigFileURL(const QString& fileUrl) {
    DependencyManager::get<AccountManager>()->setConfigFileURL(fileUrl);
}

void Application::loadAvatarScripts(const QVector<QString>& urls) {
    auto scriptEngines = DependencyManager::get<ScriptEngines>();
    auto runningScripts = scriptEngines->getRunningScripts();
    for (auto url : urls) {
        int index = runningScripts.indexOf(url);
        if (index < 0) {
            auto scriptEnginePointer = scriptEngines->loadScript(url, false);
            if (scriptEnginePointer) {
                scriptEnginePointer->setType(ScriptManager::Type::AVATAR);
            }
        }
    }
}

void Application::unloadAvatarScripts() {
    auto scriptEngines = DependencyManager::get<ScriptEngines>();
    auto urls = scriptEngines->getRunningScripts();
    for (auto url : urls) {
        auto scriptEngine = scriptEngines->getScriptEngine(url);
        if (scriptEngine->getType() == ScriptManager::Type::AVATAR) {
            scriptEngines->stopScript(url, false);
        }
    }
}

void Application::copyToClipboard(const QString& text) {
    if (QThread::currentThread() != qApp->thread()) {
        QMetaObject::invokeMethod(this, "copyToClipboard");
        return;
    }

    // assume that the address is being copied because the user wants a shareable address
    QApplication::clipboard()->setText(text);
}

void Application::registerScriptEngineWithApplicationServices(ScriptManagerPointer& scriptManager) {
    auto scriptEngine = scriptManager->engine();
    auto scopeGuard = scriptEngine->getScopeGuard();
    auto* sgp = scopeGuard.get();
    scriptManager->setEmitScriptUpdatesFunction([this]() {
        SharedNodePointer entityServerNode = DependencyManager::get<NodeList>()->soloNodeOfType(NodeType::EntityServer);
        return !entityServerNode || isPhysicsEnabled();
    });

    // setup the packet sender of the script engine's scripting interfaces so
    // we can use the same ones from the application.
    auto entityScriptingInterface = DependencyManager::get<EntityScriptingInterface>();
    entityScriptingInterface->setPacketSender(_entityEditSender.get());
    entityScriptingInterface->setEntityTree(getEntities()->getTree());

    if (property(hifi::properties::TEST).isValid()) {
        scriptEngine->registerGlobalObject(sgp, "Test", TestScriptingInterface::getInstance());
    }

    scriptEngine->registerGlobalObject(sgp, "PlatformInfo", PlatformInfoScriptingInterface::getInstance());
    scriptEngine->registerGlobalObject(sgp, "Rates", new RatesScriptingInterface(this));

    scriptEngine->registerGlobalObject(sgp, "AvatarList", DependencyManager::get<AvatarManager>().data());

    scriptEngine->registerGlobalObject(sgp, "Camera", &_myCamera);

#if defined(Q_OS_MAC) || defined(Q_OS_WIN)
    scriptEngine->registerGlobalObject(sgp, "SpeechRecognizer", DependencyManager::get<SpeechRecognizer>().data());
#endif

    ClipboardScriptingInterface* clipboardScriptable = new ClipboardScriptingInterface();
    scriptEngine->registerGlobalObject(sgp, "Clipboard", clipboardScriptable);
    connect(scriptManager.get(), &ScriptManager::finished, clipboardScriptable, &ClipboardScriptingInterface::deleteLater);

    scriptEngine->registerGlobalObject(sgp, "Overlays", &_overlays);

    bool clientScript = scriptManager->isClientScript();

#if !defined(DISABLE_QML)
    scriptEngine->registerGlobalObject(sgp, "OffscreenFlags", getOffscreenUI()->getFlags());
    if (clientScript) {
        scriptEngine->registerGlobalObject(sgp, "Desktop", DependencyManager::get<DesktopScriptingInterface>().data());
    } else {
        auto desktopScriptingInterface = new DesktopScriptingInterface(nullptr, true);
        scriptEngine->registerGlobalObject(sgp, "Desktop", desktopScriptingInterface);
        if (QThread::currentThread() != thread()) {
            desktopScriptingInterface->moveToThread(thread());
        }
    }
#endif

    scriptEngine->registerGlobalObject(sgp, "Toolbars", DependencyManager::get<ToolbarScriptingInterface>().data());

    scriptEngine->registerGlobalObject(sgp, "Tablet", DependencyManager::get<TabletScriptingInterface>().data());
    // FIXME remove these deprecated names for the tablet scripting interface
    scriptEngine->registerGlobalObject(sgp, "tabletInterface", DependencyManager::get<TabletScriptingInterface>().data());

    auto toolbarScriptingInterface = DependencyManager::get<ToolbarScriptingInterface>().data();
    DependencyManager::get<TabletScriptingInterface>().data()->setToolbarScriptingInterface(toolbarScriptingInterface);

    scriptEngine->registerGlobalObject(sgp, "Window", DependencyManager::get<WindowScriptingInterface>().data());
    scriptEngine->registerGetterSetter(sgp, "location", LocationScriptingInterface::locationGetter,
                        LocationScriptingInterface::locationSetter, "Window");
    // register `location` on the global object.
    scriptEngine->registerGetterSetter(sgp, "location", LocationScriptingInterface::locationGetter,
                                       LocationScriptingInterface::locationSetter);

    scriptEngine->registerFunction(sgp, "OverlayWindow", clientScript ? QmlWindowClass::constructor : QmlWindowClass::restricted_constructor);
#if !defined(Q_OS_ANDROID) && !defined(DISABLE_QML)
    scriptEngine->registerFunction(sgp, "OverlayWebWindow", clientScript ? QmlWebWindowClass::constructor : QmlWebWindowClass::restricted_constructor);
#endif
    scriptEngine->registerFunction(sgp, "QmlFragment", clientScript ? QmlFragmentClass::constructor : QmlFragmentClass::restricted_constructor);

    scriptEngine->registerGlobalObject(sgp, "Menu", MenuScriptingInterface::getInstance());
    scriptEngine->registerGlobalObject(sgp, "DesktopPreviewProvider", DependencyManager::get<DesktopPreviewProvider>().data());
#if !defined(DISABLE_QML)
    scriptEngine->registerGlobalObject(sgp, "Stats", Stats::getInstance());
#endif
    scriptEngine->registerGlobalObject(sgp, "Settings", SettingsScriptingInterface::getInstance());
    scriptEngine->registerGlobalObject(sgp, "Snapshot", DependencyManager::get<Snapshot>().data());
    scriptEngine->registerGlobalObject(sgp, "AudioStats", DependencyManager::get<AudioClient>()->getStats().data());
    scriptEngine->registerGlobalObject(sgp, "AudioScope", DependencyManager::get<AudioScope>().data());
    scriptEngine->registerGlobalObject(sgp, "AvatarBookmarks", DependencyManager::get<AvatarBookmarks>().data());
    scriptEngine->registerGlobalObject(sgp, "LocationBookmarks", DependencyManager::get<LocationBookmarks>().data());

    scriptEngine->registerGlobalObject(sgp, "RayPick", DependencyManager::get<RayPickScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "Picks", DependencyManager::get<PickScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "Pointers", DependencyManager::get<PointerScriptingInterface>().data());

    // Caches
    scriptEngine->registerGlobalObject(sgp, "AnimationCache", DependencyManager::get<AnimationCacheScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "TextureCache", DependencyManager::get<TextureCacheScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "MaterialCache", DependencyManager::get<MaterialCacheScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "ModelCache", DependencyManager::get<ModelCacheScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "SoundCache", DependencyManager::get<SoundCacheScriptingInterface>().data());

    scriptEngine->registerGlobalObject(sgp, "DialogsManager", _dialogsManagerScriptingInterface);

    scriptEngine->registerGlobalObject(sgp, "Account", AccountServicesScriptingInterface::getInstance()); // DEPRECATED - TO BE REMOVED
    scriptEngine->registerGlobalObject(sgp, "GlobalServices", AccountServicesScriptingInterface::getInstance()); // DEPRECATED - TO BE REMOVED
    scriptEngine->registerGlobalObject(sgp, "AccountServices", AccountServicesScriptingInterface::getInstance());

    scriptEngine->registerGlobalObject(sgp, "AvatarManager", DependencyManager::get<AvatarManager>().data());

    scriptEngine->registerGlobalObject(sgp, "LODManager", DependencyManager::get<LODManager>().data());

    scriptEngine->registerGlobalObject(sgp, "Keyboard", DependencyManager::get<KeyboardScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "Performance", new PerformanceScriptingInterface());

    scriptEngine->registerGlobalObject(sgp, "Paths", DependencyManager::get<PathUtils>().data());

    scriptEngine->registerGlobalObject(sgp, "HMD", DependencyManager::get<HMDScriptingInterface>().data());
    scriptEngine->registerFunction(sgp, "HMD", "getHUDLookAtPosition2D", HMDScriptingInterface::getHUDLookAtPosition2D, 0);
    scriptEngine->registerFunction(sgp, "HMD", "getHUDLookAtPosition3D", HMDScriptingInterface::getHUDLookAtPosition3D, 0);

    scriptEngine->registerGlobalObject(sgp, "Scene", DependencyManager::get<SceneScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "Render", RenderScriptingInterface::getInstance());
    scriptEngine->registerGlobalObject(sgp, "Workload", _gameWorkload._engine->getConfiguration().get());

    scriptEngine->registerGlobalObject(sgp, "Graphics", DependencyManager::get<GraphicsScriptingInterface>().data());

    scriptEngine->registerGlobalObject(sgp, "OSCSocket", DependencyManager::get<OSCScriptingInterface>().data());
    scriptEngine->registerFunction(sgp, "OSCSocket", "sendPacket", OSCScriptingInterface::sendPacket, 0);

    scriptEngine->registerGlobalObject(sgp, "ScriptDiscoveryService", DependencyManager::get<ScriptEngines>().data());
    scriptEngine->registerGlobalObject(sgp, "Reticle", getApplicationCompositor().getReticleInterface());

    scriptEngine->registerGlobalObject(sgp, "UserActivityLogger", DependencyManager::get<UserActivityLoggerScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "Users", DependencyManager::get<UsersScriptingInterface>().data());

    if (auto steamClient = PluginManager::getInstance()->getSteamClientPlugin()) {
        scriptEngine->registerGlobalObject(sgp, "Steam", new SteamScriptingInterface(scriptManager.get(), steamClient.get()));
    }
    auto scriptingInterface = DependencyManager::get<controller::ScriptingInterface>();
    scriptEngine->registerGlobalObject(sgp, "Controller", scriptingInterface.data());

    {
        auto connection = std::make_shared<QMetaObject::Connection>();
        *connection = scriptManager->connect(scriptManager.get(), &ScriptManager::scriptEnding, [this, scriptManager, connection]() {
            // Request removal of controller routes with callbacks to a given script engine
            auto userInputMapper = DependencyManager::get<UserInputMapper>();
            // scheduleScriptEndpointCleanup will have the last instance of shared pointer to script manager
            // so script manager will get deleted as soon as cleanup is done
            userInputMapper->scheduleScriptEndpointCleanup(scriptManager);
            QObject::disconnect(*connection);
        });
    }

    UserInputMapper::registerControllerTypes(scriptEngine.get());

    auto recordingInterface = DependencyManager::get<RecordingScriptingInterface>();
    scriptEngine->registerGlobalObject(sgp, "Recording", recordingInterface.data());

    auto entityScriptServerLog = DependencyManager::get<EntityScriptServerLogClient>();
    scriptEngine->registerGlobalObject(sgp, "EntityScriptServerLog", entityScriptServerLog.data());
    scriptEngine->registerGlobalObject(sgp, "AvatarInputs", AvatarInputs::getInstance());
    scriptEngine->registerGlobalObject(sgp, "Selection", DependencyManager::get<SelectionScriptingInterface>().data());
    scriptEngine->registerGlobalObject(sgp, "AddressManager", DependencyManager::get<AddressManager>().data());
    scriptEngine->registerGlobalObject(sgp, "About", AboutUtil::getInstance());
    scriptEngine->registerGlobalObject(sgp, "HifiAbout", AboutUtil::getInstance());  // Deprecated.
    scriptEngine->registerGlobalObject(sgp, "ResourceRequestObserver", DependencyManager::get<ResourceRequestObserver>().data());

    // connect this script engines printedMessage signal to the global ScriptEngines these various messages
    auto scriptEngines = DependencyManager::get<ScriptEngines>().data();
    connect(scriptManager.get(), &ScriptManager::printedMessage, scriptEngines, &ScriptEngines::onPrintedMessage);
    connect(scriptManager.get(), &ScriptManager::errorMessage, scriptEngines, &ScriptEngines::onErrorMessage);
    connect(scriptManager.get(), &ScriptManager::warningMessage, scriptEngines, &ScriptEngines::onWarningMessage);
    connect(scriptManager.get(), &ScriptManager::infoMessage, scriptEngines, &ScriptEngines::onInfoMessage);
    connect(scriptManager.get(), &ScriptManager::clearDebugWindow, scriptEngines, &ScriptEngines::onClearDebugWindow);
}

// Snapshots
void Application::addSnapshotOperator(const SnapshotOperator& snapshotOperator) {
    std::lock_guard<std::mutex> lock(_snapshotMutex);
    _snapshotOperators.push(snapshotOperator);
    _hasPrimarySnapshot = _hasPrimarySnapshot || std::get<2>(snapshotOperator);
}

bool Application::takeSnapshotOperators(std::queue<SnapshotOperator>& snapshotOperators) {
    std::lock_guard<std::mutex> lock(_snapshotMutex);
    bool hasPrimarySnapshot = _hasPrimarySnapshot;
    _hasPrimarySnapshot = false;
    _snapshotOperators.swap(snapshotOperators);
    return hasPrimarySnapshot;
}

void Application::takeSnapshot(bool notify, bool includeAnimated, float aspectRatio, const QString& filename) {
    addSnapshotOperator(std::make_tuple([notify, includeAnimated, aspectRatio, filename](const QImage& snapshot) {
        qApp->postLambdaEvent([snapshot, notify, includeAnimated, aspectRatio, filename] {
            QString path = DependencyManager::get<Snapshot>()->saveSnapshot(snapshot, filename, TestScriptingInterface::getInstance()->getTestResultsLocation());

            // If we're not doing an animated snapshot as well...
            if (!includeAnimated) {
                if (!path.isEmpty()) {
                    // Tell the dependency manager that the capture of the still snapshot has taken place.
                    emit DependencyManager::get<WindowScriptingInterface>()->stillSnapshotTaken(path, notify);
                }
            } else if (!SnapshotAnimated::isAlreadyTakingSnapshotAnimated()) {
                // Get an animated GIF snapshot and save it
                SnapshotAnimated::saveSnapshotAnimated(path, aspectRatio, DependencyManager::get<WindowScriptingInterface>());
            }
        });
    }, aspectRatio, true));
}

void Application::takeSecondaryCameraSnapshot(const bool& notify, const QString& filename) {
    addSnapshotOperator(std::make_tuple([notify, filename](const QImage& snapshot) {
        qApp->postLambdaEvent([snapshot, notify, filename] {
            QString snapshotPath = DependencyManager::get<Snapshot>()->saveSnapshot(snapshot, filename, TestScriptingInterface::getInstance()->getTestResultsLocation());

            emit DependencyManager::get<WindowScriptingInterface>()->stillSnapshotTaken(snapshotPath, notify);
        });
    }, 0.0f, false));
}

void Application::takeSecondaryCamera360Snapshot(const glm::vec3& cameraPosition, const bool& cubemapOutputFormat, const bool& notify, const QString& filename) {
    postLambdaEvent([notify, filename, cubemapOutputFormat, cameraPosition] {
        DependencyManager::get<Snapshot>()->save360Snapshot(cameraPosition, cubemapOutputFormat, notify, filename);
    });
}

void Application::shareSnapshot(const QString& path, const QUrl& href) {
    postLambdaEvent([path, href] {
        // not much to do here, everything is done in snapshot code...
        DependencyManager::get<Snapshot>()->uploadSnapshot(path, href);
    });
}

#if defined(Q_OS_ANDROID)
void Application::beforeEnterBackground() {
    auto nodeList = DependencyManager::get<NodeList>();
    nodeList->setSendDomainServerCheckInEnabled(false);
    nodeList->reset("Entering background", true);
    clearDomainOctreeDetails();
}

void Application::enterBackground() {
    QMetaObject::invokeMethod(DependencyManager::get<AudioClient>().data(),
                              "stop", Qt::BlockingQueuedConnection);
// Quest only supports one plugin which can't be deactivated currently
#if !defined(ANDROID_APP_QUEST_INTERFACE)
    if (getActiveDisplayPlugin()->isActive()) {
        getActiveDisplayPlugin()->deactivate();
    }
#endif
}

void Application::enterForeground() {
    QMetaObject::invokeMethod(DependencyManager::get<AudioClient>().data(),
                                  "start", Qt::BlockingQueuedConnection);
// Quest only supports one plugin which can't be deactivated currently
#if !defined(ANDROID_APP_QUEST_INTERFACE)
    if (!getActiveDisplayPlugin() || getActiveDisplayPlugin()->isActive() || !getActiveDisplayPlugin()->activate()) {
        qWarning() << "Could not re-activate display plugin";
    }
#endif
    auto nodeList = DependencyManager::get<NodeList>();
    nodeList->setSendDomainServerCheckInEnabled(true);
}

void Application::toggleAwayMode(){
    QKeyEvent event = QKeyEvent (QEvent::KeyPress, Qt::Key_Escape, Qt::NoModifier);
    QCoreApplication::sendEvent (this, &event);
}
#endif

// FIXME?  perhaps two, one for the main thread and one for the offscreen UI rendering thread?
static const int UI_RESERVED_THREADS = 1;
// Windows won't let you have all the cores
static const int OS_RESERVED_THREADS = 1;
void Application::updateThreadPoolCount() const {
    auto reservedThreads = UI_RESERVED_THREADS + OS_RESERVED_THREADS + _displayPlugin->getRequiredThreadCount();
    auto availableThreads = QThread::idealThreadCount() - reservedThreads;
    auto threadPoolSize = std::max(MIN_PROCESSING_THREAD_POOL_SIZE, availableThreads);
    qCDebug(interfaceapp) << "Ideal Thread Count " << QThread::idealThreadCount();
    qCDebug(interfaceapp) << "Reserved threads " << reservedThreads;
    qCDebug(interfaceapp) << "Setting thread pool size to " << threadPoolSize;
    QThreadPool::globalInstance()->setMaxThreadCount(threadPoolSize);
}

void Application::gotoTutorial() {
    const QString TUTORIAL_ADDRESS = "file:///~/serverless/tutorial.json";
    qCInfo(interfaceapp) << "Loading tutorial domain from" << TUTORIAL_ADDRESS;
    DependencyManager::get<AddressManager>()->handleLookupString(TUTORIAL_ADDRESS);
}

void Application::goToErrorDomainURL(QUrl errorDomainURL) {
    // disable physics until we have enough information about our new location to not cause craziness.
    setIsServerlessMode(errorDomainURL.scheme() != URL_SCHEME_OVERTE);
    if (isServerlessMode()) {
        loadErrorDomain(errorDomainURL);
    }
    updateWindowTitle();
}

void Application::handleLocalServerConnection() const {
    auto server = qobject_cast<QLocalServer*>(sender());
    Q_ASSERT(server != nullptr);

    qCDebug(interfaceapp) << "Got connection on local server from additional instance - waiting for parameters";

    auto socket = server->nextPendingConnection();

    connect(socket, &QLocalSocket::readyRead, this, &Application::readArgumentsFromLocalSocket);

    qApp->getWindow()->raise();
#ifdef USE_GL
    qApp->getWindow()->activateWindow(); //VKTODO
#endif
}

void Application::readArgumentsFromLocalSocket() const {
    auto socket = qobject_cast<QLocalSocket*>(sender());
    Q_ASSERT(socket != nullptr);

    auto message = socket->readAll();
    socket->deleteLater();

    qCDebug(interfaceapp) << "Read from connection: " << message;

    // If we received a message, try to open it as a URL
    if (message.length() > 0) {
        DependencyManager::get<AddressManager>()->handleLookupString(QString::fromUtf8(message));
    }
}

void Application::showUrlHandler(const QUrl& url) {
    if (QThread::currentThread() != thread()) {
        QMetaObject::invokeMethod(this, "showUrlHandler", Q_ARG(const QUrl&, url));
        return;
    }

    ModalDialogListener* dlg = OffscreenUi::asyncQuestion("Confirm openUrl", "Do you recognize this path or code and want to open or execute it: " + url.toDisplayString());
    QObject::connect(dlg, &ModalDialogListener::response, this, [=, this](QVariant answer) {
        QObject::disconnect(dlg, &ModalDialogListener::response, this, nullptr);
        if (QMessageBox::Yes == static_cast<QMessageBox::StandardButton>(answer.toInt())) {
            // Unset the handler, open the URL, and the reset the handler
            QDesktopServices::unsetUrlHandler(url.scheme());
            QDesktopServices::openUrl(url);
            QDesktopServices::setUrlHandler(url.scheme(), this, "showUrlHandler");
        }
    });
}

void Application::hmdVisibleChanged(bool visible) {
    // TODO
    // calling start and stop will change audio input and ouput to default audio devices.
    // we need to add a pause/unpause functionality to AudioClient for this to work properly
#if 0
    if (visible) {
        QMetaObject::invokeMethod(DependencyManager::get<AudioClient>().data(), "start", Qt::QueuedConnection);
    } else {
        QMetaObject::invokeMethod(DependencyManager::get<AudioClient>().data(), "stop", Qt::QueuedConnection);
    }
#endif
}

void Application::reloadResourceCaches() {
    resetPhysicsReadyInformation();

    // Query the octree to refresh everything in view
    _queryExpiry = SteadyClock::now();
    _octreeQuery.incrementConnectionID();

    queryOctree(NodeType::EntityServer, PacketType::EntityQuery);

    getMyAvatar()->prepareAvatarEntityDataForReload();
    // Clear the entities and their renderables
    getEntities()->clear();

    DependencyManager::get<AssetClient>()->clearCache();
    //It's already cleared in reloadAllScripts so I'm not sure this is necessary.
    //DependencyManager::get<ScriptCache>()->clearCache();

    // Clear all the resource caches
    DependencyManager::get<ResourceCacheSharedItems>()->clear();
    DependencyManager::get<AnimationCache>()->refreshAll();
    DependencyManager::get<SoundCache>()->refreshAll();
    DependencyManager::get<MaterialCache>()->refreshAll();
    DependencyManager::get<ModelCache>()->refreshAll();
    ShaderCache::instance().refreshAll();
    DependencyManager::get<TextureCache>()->refreshAll();
    DependencyManager::get<recording::ClipCache>()->refreshAll();

    DependencyManager::get<NodeList>()->reset("Reloading resources");  // Force redownload of .fst models

    DependencyManager::get<ScriptEngines>()->reloadAllScripts();
    getOffscreenUI()->clearCache();

    DependencyManager::get<Keyboard>()->createKeyboard();

    getMyAvatar()->resetFullAvatarURL();
}

void Application::updateHeartbeat() const {
    DeadlockWatchdogThread::updateHeartbeat();
}

void Application::deadlockApplication() {
    qCDebug(interfaceapp) << "Intentionally deadlocked Interface";
    // Using a loop that will *technically* eventually exit (in ~600 billion years)
    // to avoid compiler warnings about a loop that will never exit
    for (uint64_t i = 1; i != 0; ++i) {
        QThread::sleep(1);
    }
}

// cause main thread to be unresponsive for 35 seconds
void Application::unresponsiveApplication() {
    // to avoid compiler warnings about a loop that will never exit
    uint64_t start = usecTimestampNow();
    uint64_t UNRESPONSIVE_FOR_SECONDS = 35;
    uint64_t UNRESPONSIVE_FOR_USECS = UNRESPONSIVE_FOR_SECONDS * USECS_PER_SECOND;
    qCDebug(interfaceapp) << "Intentionally cause Interface to be unresponsive for " << UNRESPONSIVE_FOR_SECONDS << " seconds";
    while (usecTimestampNow() - start < UNRESPONSIVE_FOR_USECS) {
        QThread::sleep(1);
    }
}

// used to test "shutdown" crash annotation.
void Application::crashOnShutdown() {
    qDebug() << "crashOnShutdown(), ON PURPOSE!";
    _crashOnShutdown = true;
    quit();
}

void Application::rotationModeChanged() const {
    if (!Menu::getInstance()->isOptionChecked(MenuOption::CenterPlayerInView)) {
        getMyAvatar()->setHeadPitch(0);
    }
}

void Application::setIsServerlessMode(bool serverlessDomain) {
    DependencyManager::get<NodeList>()->setSendDomainServerCheckInEnabled(!serverlessDomain);
    auto tree = getEntities()->getTree();
    if (tree) {
        tree->setIsServerlessMode(serverlessDomain);
        _waitForServerlessToBeSet = false;
    }
}

std::map<QString, QString> Application::prepareServerlessDomainContents(QUrl domainURL, QByteArray data) {
    QUuid serverlessSessionID = QUuid::createUuid();
    getMyAvatar()->setSessionUUID(serverlessSessionID);
    auto nodeList = DependencyManager::get<NodeList>();
    nodeList->setSessionUUID(serverlessSessionID);

    // there is no domain-server to tell us our permissions, so enable all
    NodePermissions permissions;
    permissions.setAll(true);
    nodeList->setPermissions(permissions);

    // FIXME: Lock the main tree and import directly into it.
    EntityTreePointer tmpTree(std::make_shared<EntityTree>());
    tmpTree->setIsServerlessMode(true);
    tmpTree->createRootElement();
    auto myAvatar = getMyAvatar();
    tmpTree->setMyAvatar(myAvatar);
    bool success = tmpTree->readFromByteArray(domainURL.toString(), data);
    if (success) {
        tmpTree->reaverageOctreeElements();
        tmpTree->sendEntities(_entityEditSender.get(), getEntities()->getTree(), "domain", 0, 0, 0);
    }
    std::map<QString, QString> namedPaths = tmpTree->getNamedPaths();

    // we must manually eraseAllOctreeElements(false) else the tmpTree will mem-leak
    tmpTree->eraseAllOctreeElements(false);

    return namedPaths;
}

void Application::loadServerlessDomain(QUrl domainURL) {
    if (QThread::currentThread() != thread()) {
        QMetaObject::invokeMethod(this, "loadServerlessDomain", Q_ARG(QUrl, domainURL));
        return;
    }

    if (domainURL.isEmpty()) {
        return;
    }

    QString trimmedUrl = domainURL.toString().trimmed();
    bool DEFAULT_IS_OBSERVABLE = true;
    const qint64 DEFAULT_CALLER_ID = -1;
    auto request = DependencyManager::get<ResourceManager>()->createResourceRequest(
        this, trimmedUrl, DEFAULT_IS_OBSERVABLE, DEFAULT_CALLER_ID, "Application::loadServerlessDomain");

    if (!request) {
        return;
    }

    connect(request, &ResourceRequest::finished, this, [=, this]() {
        if (request->getResult() == ResourceRequest::Success) {
            auto namedPaths = prepareServerlessDomainContents(domainURL, request->getData());
            auto nodeList = DependencyManager::get<NodeList>();
            nodeList->getDomainHandler().connectedToServerless(namedPaths);
            _octreeProcessor->getFullSceneReceivedCounter()++;
        }
        request->deleteLater();
    });
    request->send();
}

void Application::loadErrorDomain(QUrl domainURL) {
    if (QThread::currentThread() != thread()) {
        QMetaObject::invokeMethod(this, "loadErrorDomain", Q_ARG(QUrl, domainURL));
        return;
    }

    loadServerlessDomain(domainURL);
}

void Application::setIsInterstitialMode(bool interstitialMode) {
#if defined(ANDROID_APP_PICO_INTERFACE)
    if (interstitialMode && _picoLoadingDismissedByUser) {
        return;
    }
#endif
    bool enableInterstitial = DependencyManager::get<NodeList>()->getDomainHandler().getInterstitialModeEnabled();
#if defined(ANDROID_APP_PICO_INTERFACE)
    // Always permit an already-visible Pico interstitial to close. Domain
    // settings can disable future interstitials while this one is finishing.
    enableInterstitial = enableInterstitial || (!interstitialMode && _interstitialMode);
#endif
    if (enableInterstitial) {
        if (_interstitialMode != interstitialMode) {
            _interstitialMode = interstitialMode;
            emit interstitialModeChanged(_interstitialMode);

            DependencyManager::get<AudioClient>()->setAudioPaused(_interstitialMode);
            DependencyManager::get<AvatarManager>()->setMyAvatarDataPacketsPaused(_interstitialMode);
#if defined(ANDROID_APP_PICO_INTERFACE)
            _picoLoadingWorldProgress = 0.0f;
            _picoLoadingResourceProgress = 0.0f;
            _picoLoadingSequenceProgress = 0.0f;
            _picoLoadingLastAdvance = 0;
            _picoLoadingLastRecovery = 0;
            _picoLoadingRecoveryAttempts = 0;
            _picoLoadingConnectedAt = 0;
            _picoLoadingFinalizingAt = 0;
            _picoLoadingPhysicsEnabledAt = 0;
            _picoLoadingPhysicsPresentFrame = 0;
            _picoLoadingReadyAt = 0;
            _picoLoadingReadyPresentFrame = 0;
            _picoLoadingCandidatePhaseSince = 0;
            _picoLoadingDisplayedProgress = 0.0f;
            _picoLoadingDisplayedPhase = -1;
            _picoLoadingCandidatePhase = -1;
            _picoLoadingTextureMemoryReady = false;
            _picoLoadingGpuFallbackUsed = false;
            _picoLoadingWasConnected = false;
            // Keep a manual dismissal latched while leaving the interstitial. Otherwise
            // the false transition below clears the flag before a subsequent
            // setIsInterstitialMode(true) can honor it. Domain switches reset this
            // state explicitly in clearDomainOctreeDetails().
            if (interstitialMode) {
                _picoLoadingDismissedByUser = false;
                _picoLoadingDismissButtonWasPressed = false;
            }
            if (_graphicsEngine) {
                _graphicsEngine->setLoadingState(
                    _interstitialMode, GraphicsEngine::LoadingPhase::STARTING,
                    _interstitialMode ? 0.03f : 1.0f);
            }
#endif
        }
    }
}

void Application::updateVerboseLogging() {
    auto menu = Menu::getInstance();
    if (!menu) {
        return;
    }
    bool enable = menu->isOptionChecked(MenuOption::VerboseLogging);

    QString rules =
        "hifi.*.info=%1\n"
        "hifi.audio-stream.debug=false\n"
        "hifi.audio-stream.info=false";
    rules = rules.arg(enable ? "true" : "false");
    QLoggingCategory::setFilterRules(rules);
}

static const QString CACHEBUST_SCRIPT_REQUIRE_SETTING_NAME = "cachebustScriptRequire";
void Application::setCachebustRequire() {
    auto menu = Menu::getInstance();
    if (!menu) {
        return;
    }
    bool enable = menu->isOptionChecked(MenuOption::CachebustRequire);

    Setting::Handle<bool>{ CACHEBUST_SCRIPT_REQUIRE_SETTING_NAME, false }.set(enable);
}

QString Application::getGraphicsCardType() {
    return GPUIdent::getInstance()->getName();
}

bool Application::gpuTextureMemSizeStable() {
    auto renderConfig = qApp->getRenderEngine()->getConfiguration();
    auto renderStats = renderConfig->getConfig<render::EngineStats>("Stats");

    qint64 textureResourceGPUMemSize = renderStats->textureResourceGPUMemSize;
#if !defined(ANDROID_APP_PICO_INTERFACE)
    qint64 texturePopulatedGPUMemSize = renderStats->textureResourcePopulatedGPUMemSize;
#endif
    qint64 textureTransferSize = renderStats->texturePendingGPUTransferSize;

    if (_gpuTextureMemSizeAtLastCheck == textureResourceGPUMemSize) {
        _gpuTextureMemSizeStabilityCount++;
    } else {
        _gpuTextureMemSizeStabilityCount = 0;
    }
    _gpuTextureMemSizeAtLastCheck = textureResourceGPUMemSize;

    if (_gpuTextureMemSizeStabilityCount >= _minimumGPUTextureMemSizeStabilityCount) {
#if defined(ANDROID_APP_PICO_INTERFACE)
        // Android texture streaming intentionally keeps some requested mip levels non-resident. Waiting for
        // requested and populated memory to match can therefore deadlock the Pico loading screen forever.
        // Stable allocation and an empty transfer queue are the reliable completion signals on this client.
        return textureTransferSize == 0;
#else
        return textureResourceGPUMemSize == texturePopulatedGPUMemSize && textureTransferSize == 0;
#endif
    }
    return false;
}

void Application::runTests() {
    runTimingTests();
    runUnitTests();
}

void Application::resetPhysicsReadyInformation() {
    // we've changed domains or cleared out caches or something.  we no longer know enough about the
    // collision information of nearby entities to make running bullet be safe.
    _octreeProcessor->getFullSceneReceivedCounter() = 0;
    _fullSceneCounterAtLastPhysicsCheck = 0;
    _gpuTextureMemSizeStabilityCount = 0;
    _gpuTextureMemSizeAtLastCheck = 0;
    _physicsEnabled = false;
    _octreeProcessor->stopSafeLanding();
}

static const QString ACTIVE_DISPLAY_PLUGIN_SETTING_NAME = "activeDisplayPlugin";
void Application::onAboutToQuit() {
    auto &ch = CrashHandler::getInstance();
    ch.setAnnotation("shutdown", "1");

    // quickly save AvatarEntityData before the EntityTree is dismantled
    getMyAvatar()->saveAvatarEntityDataToSettings();

    emit beforeAboutToQuit();

    if (getLoginDialogPoppedUp() && _firstRun.get()) {
        _firstRun.set(false);
    }

    for(const auto& inputPlugin : PluginManager::getInstance()->getInputPlugins()) {
        if (inputPlugin->isActive()) {
            inputPlugin->deactivate();
        }
    }

    // The active display plugin needs to be loaded before the menu system is active,
    // so its persisted explicitly here
    Setting::Handle<QString>{ ACTIVE_DISPLAY_PLUGIN_SETTING_NAME }.set(getActiveDisplayPlugin()->getName());

    getActiveDisplayPlugin()->deactivate();
    if (_autoSwitchDisplayModeSupportedHMDPlugin
        && _autoSwitchDisplayModeSupportedHMDPlugin->isSessionActive()) {
        _autoSwitchDisplayModeSupportedHMDPlugin->endSession();
    }
    // use the CloseEventSender via a QThread to send an event that says the user asked for the app to close
    DependencyManager::get<CloseEventSender>()->startThread();

    // Hide Running Scripts dialog so that it gets destroyed in an orderly manner; prevents warnings at shutdown.
#if !defined(DISABLE_QML)
    getOffscreenUI()->hide("RunningScripts");
#endif

    _aboutToQuit = true;

    cleanupBeforeQuit();

    if (_crashOnShutdown) {
        // triggered by crash menu
        crash::nullDeref();
    }

    getRefreshRateManager().setRefreshRateRegime(RefreshRateManager::RefreshRateRegime::SHUTDOWN);
}

void Application::loadSettings(const QCommandLineParser& parser) {

    sessionRunTime.set(0); // Just clean living. We're about to saveSettings, which will update value.
    DependencyManager::get<AudioClient>()->loadSettings();
    DependencyManager::get<LODManager>()->loadSettings();

    auto menu = Menu::getInstance();
    menu->loadSettings();

    // override the menu option show overlays to always be true on startup
    menu->setIsOptionChecked(MenuOption::Overlays, true);

    // If there is a preferred plugin, we probably messed it up with the menu settings, so fix it.
    auto pluginManager = PluginManager::getInstance();
    auto plugins = pluginManager->getPreferredDisplayPlugins();
    if (plugins.size() > 0) {
        for (auto plugin : plugins) {
            if (auto action = menu->getActionForOption(plugin->getName())) {
                action->setChecked(true);
                action->trigger();
                // Find and activated highest priority plugin, bail for the rest
                break;
            }
        }
    }

    bool isFirstPerson = false;
    if (parser.isSet("no-launcher")) {
        const auto& displayPlugins = pluginManager->getDisplayPlugins();
        for (const auto& plugin : displayPlugins) {
            if (!plugin->isHmd()) {
                if (auto action = menu->getActionForOption(plugin->getName())) {
                    action->setChecked(true);
                    action->trigger();
                    break;
                }
            }
        }
        isFirstPerson = (qApp->isHMDMode());
    } else {
        if (_firstRun.get()) {
            // If this is our first run, and no preferred devices were set, default to
            // an HMD device if available.
            const auto& displayPlugins = pluginManager->getDisplayPlugins();
            for (const auto& plugin : displayPlugins) {
                if (plugin->isHmd()) {
                    if (auto action = menu->getActionForOption(plugin->getName())) {
                        action->setChecked(true);
                        action->trigger();
                        break;
                    }
                }
            }
            isFirstPerson = (qApp->isHMDMode());
        } else {
            // if this is not the first run, the camera will be initialized differently depending on user settings
            if (qApp->isHMDMode()) {
                // if the HMD is active, use first-person camera, unless the appropriate setting is checked
                isFirstPerson = menu->isOptionChecked(MenuOption::FirstPersonHMD);
            } else {
                // if HMD is not active, only use first person if the menu option is checked
                isFirstPerson = menu->isOptionChecked(MenuOption::FirstPersonLookAt);
            }
        }
    }

    // Load settings of the RenderScritpingInterface
    // Do that explicitely before being used
    RenderScriptingInterface::getInstance()->loadSettings();

    // Setup the PerformanceManager which will enforce the several settings to match the Preset
    // On the first run, the Preset is evaluated from the
    getPerformanceManager().setupPerformancePresetSettings(_firstRun.get());

#if defined(Q_OS_ANDROID)
    auto renderSettings = RenderScriptingInterface::getInstance();
    // Standalone headsets need a predictable baseline. The desktop platform
    // tier can otherwise enable these passes even though Pico has no UI
    // controls exposing the individual settings.
    renderSettings->setShadowsEnabled(false);
    renderSettings->setBloomEnabled(false);
    renderSettings->setAmbientOcclusionEnabled(false);
    DependencyManager::get<LODManager>()->setWorldDetailQuality(WORLD_DETAIL_LOW);

#if defined(ANDROID_APP_PHONE_INTERFACE)
    // Phones are passively cooled and share system/GPU memory. Prefer a
    // predictable MVP baseline. Apply it after the performance preset so a
    // first-run preset cannot immediately restore the desktop values.
    constexpr float PHONE_DEFAULT_VIEWPORT_RESOLUTION_SCALE { 0.65f };
    constexpr float PHONE_MIN_VIEWPORT_RESOLUTION_SCALE { 0.5f };
    constexpr float PHONE_MAX_VIEWPORT_RESOLUTION_SCALE { 0.7f };
    float phoneViewportResolutionScale { PHONE_DEFAULT_VIEWPORT_RESOLUTION_SCALE };
    char phoneRenderScaleValue[PROP_VALUE_MAX] {};
    if (__system_property_get("debug.overte.phone_render_scale", phoneRenderScaleValue) > 0) {
        phoneViewportResolutionScale = phone::graphics::parseClampedFloat(
            phoneRenderScaleValue, PHONE_DEFAULT_VIEWPORT_RESOLUTION_SCALE,
            PHONE_MIN_VIEWPORT_RESOLUTION_SCALE, PHONE_MAX_VIEWPORT_RESOLUTION_SCALE);
    }
    const auto phoneBoolOverride = [](const char* propertyName, bool fallback) {
        char propertyValue[PROP_VALUE_MAX] {};
        if (__system_property_get(propertyName, propertyValue) <= 0) {
            return fallback;
        }
        return phone::graphics::parseBoolOverride(propertyValue, fallback);
    };
    const bool phoneHazeEnabled = phoneBoolOverride("debug.overte.phone_haze", false);
    const bool phoneLocalLightsEnabled = phoneBoolOverride("debug.overte.phone_local_lights", false);
    constexpr int PHONE_TARGET_FPS { 30 };
    renderSettings->setRenderMethod(RenderScriptingInterface::RenderMethod::FORWARD);
    renderSettings->setAntialiasingMode(AntialiasingSetupConfig::Mode::NONE);
    renderSettings->setHazeEnabled(phoneHazeEnabled);
    renderSettings->setLocalLightingEnabled(phoneLocalLightsEnabled);
    renderSettings->setProceduralMaterialsEnabled(false);
    renderSettings->setViewportResolutionScale(phoneViewportResolutionScale);

    auto& phoneRefreshRateManager = getRefreshRateManager();
    phoneRefreshRateManager.setCustomRefreshRate(RefreshRateManager::RefreshRateRegime::FOCUS_ACTIVE, PHONE_TARGET_FPS);
    phoneRefreshRateManager.setCustomRefreshRate(RefreshRateManager::RefreshRateRegime::FOCUS_INACTIVE, PHONE_TARGET_FPS);
    phoneRefreshRateManager.setCustomRefreshRate(RefreshRateManager::RefreshRateRegime::STARTUP, PHONE_TARGET_FPS);
    phoneRefreshRateManager.setRefreshRateProfile(RefreshRateManager::RefreshRateProfile::CUSTOM);

    auto renderConfig = qApp->getRenderEngine()->getConfiguration();
    constexpr int PHONE_FORWARD_MSAA_SAMPLES { 1 };
    int configuredForwardBuffers { 0 };
    const QStringList viewNames { "RenderMainView", "RenderSecondView" };
    for (const auto& viewName : viewNames) {
        const QString forwardBufferName =
            viewName + ".RenderForwardTask.PreparePrimaryBufferForward";
        if (auto forwardBufferConfig = renderConfig->getConfig(forwardBufferName)) {
            if (forwardBufferConfig->setProperty("numSamples", PHONE_FORWARD_MSAA_SAMPLES)) {
                ++configuredForwardBuffers;
            }
        }
    }

    // A single cell avoids clustering work while local lighting is disabled.
    // Restore the renderer's normal grid for the explicit local-light A/B path;
    // packing every visible light into one uint8-counted cell is not correct.
    const int phoneLightClusterGridDimension = phoneLocalLightsEnabled ? 14 : 1;
    int configuredLightClusterGrids { 0 };
    for (const auto& viewName : viewNames) {
        const QString lightClusteringName =
            viewName + ".RenderForwardTask.LightClustering";
        if (auto lightClusteringConfig = renderConfig->getConfig(lightClusteringName)) {
            const bool configuredX =
                lightClusteringConfig->setProperty("dimX", phoneLightClusterGridDimension);
            const bool configuredY =
                lightClusteringConfig->setProperty("dimY", phoneLightClusterGridDimension);
            const bool configuredZ =
                lightClusteringConfig->setProperty("dimZ", phoneLightClusterGridDimension);
            if (configuredX && configuredY && configuredZ) {
                ++configuredLightClusterGrids;
            }
        }
    }

    int disabledMirrorViews { 0 };
    for (const auto& viewName : viewNames) {
        constexpr size_t MIRROR_VIEWS_PER_LEVEL { 3 };
        for (size_t mirrorIndex = 0; mirrorIndex < MIRROR_VIEWS_PER_LEVEL; ++mirrorIndex) {
            const QString mirrorName = viewName + ".RenderMirrorView" +
                QString::number(mirrorIndex) + "Depth0";
            if (auto mirrorConfig = renderConfig->getConfig(mirrorName)) {
                if (mirrorConfig->setProperty("enabled", false)) {
                    ++disabledMirrorViews;
                }
            }
        }
    }
    qCInfo(interfaceapp) << "PHONE_GRAPHICS_PROFILE"
                         << "targetFps" << PHONE_TARGET_FPS
                         << "renderScale" << renderSettings->getViewportResolutionScale()
                         << "forwardMsaaSamples" << PHONE_FORWARD_MSAA_SAMPLES
                         << "configuredForwardBuffers" << configuredForwardBuffers
                         << "lightClusterGridDimension" << phoneLightClusterGridDimension
                         << "configuredLightClusterGrids" << configuredLightClusterGrids
                         << "forward" << (renderSettings->getRenderMethod() == RenderScriptingInterface::RenderMethod::FORWARD)
                         << "antialiasing" << (renderSettings->getAntialiasingMode() != AntialiasingSetupConfig::Mode::NONE)
                         << "shadows" << renderSettings->getShadowsEnabled()
                         << "haze" << renderSettings->getHazeEnabled()
                         << "bloom" << renderSettings->getBloomEnabled()
                         << "ambientOcclusion" << renderSettings->getAmbientOcclusionEnabled()
                         << "localLights" << renderSettings->getLocalLightingEnabled()
                         << "proceduralMaterials" << renderSettings->getProceduralMaterialsEnabled()
                         << "disabledMirrorViews" << disabledMirrorViews
                         << "worldDetail" << WORLD_DETAIL_LOW
                         << "downloadLimit" << ResourceCache::getRequestLimit();
    __android_log_print(ANDROID_LOG_INFO, "OvertePhoneGraphics",
        "profile_render_scale=%.2f profile_target_fps=%d profile_forward_msaa_samples=%d profile_haze=%d profile_local_lights=%d",
        static_cast<double>(renderSettings->getViewportResolutionScale()), PHONE_TARGET_FPS,
        PHONE_FORWARD_MSAA_SAMPLES, phoneHazeEnabled ? 1 : 0, phoneLocalLightsEnabled ? 1 : 0);
#endif

#if defined(ANDROID_APP_PICO_INTERFACE)
    // Opt-in, process-start power profile for controlled Pico A/B tests. It
    // deliberately leaves viewport and OpenXR swapchain resolution unchanged.
    // adb shell setprop debug.overte.power_profile 1
    char picoPowerProfileValue[PROP_VALUE_MAX] {};
    const QString picoPowerProfile = __system_property_get(
        "debug.overte.power_profile", picoPowerProfileValue) > 0
        ? QString::fromLatin1(picoPowerProfileValue).trimmed().toLower()
        : QString();
    const bool picoPowerProfileEnabled = picoPowerProfile == "1" ||
        picoPowerProfile == "on" || picoPowerProfile == "enabled";
    const auto picoBoolOverride = [](const char* property, bool fallback) {
        char value[PROP_VALUE_MAX] {};
        if (__system_property_get(property, value) <= 0) {
            return fallback;
        }
        const QString requested = QString::fromLatin1(value).trimmed().toLower();
        if (requested == "1" || requested == "on" || requested == "true" || requested == "enabled") {
            return true;
        }
        if (requested == "0" || requested == "off" || requested == "false" || requested == "disabled") {
            return false;
        }
        return fallback;
    };
    const bool shadowsEnabled = picoBoolOverride("debug.overte.shadows", false);
    const bool bloomEnabled = picoBoolOverride("debug.overte.bloom", false);
    const bool ambientOcclusionEnabled = picoBoolOverride("debug.overte.ambient_occlusion", false);
    const bool hazeEnabled = picoBoolOverride("debug.overte.haze", !picoPowerProfileEnabled);
    const bool localLightsEnabled = picoBoolOverride("debug.overte.local_lights", !picoPowerProfileEnabled);
    const bool proceduralMaterialsEnabled = picoBoolOverride(
        "debug.overte.procedural_materials", !picoPowerProfileEnabled);
    const bool mirrorViewsEnabled = picoBoolOverride("debug.overte.mirror_views", !picoPowerProfileEnabled);

    renderSettings->setShadowsEnabled(shadowsEnabled);
    renderSettings->setBloomEnabled(bloomEnabled);
    renderSettings->setAmbientOcclusionEnabled(ambientOcclusionEnabled);
    renderSettings->setHazeEnabled(hazeEnabled);
    renderSettings->setLocalLightingEnabled(localLightsEnabled);
    renderSettings->setProceduralMaterialsEnabled(proceduralMaterialsEnabled);
    renderSettings->setAntialiasingMode(AntialiasingSetupConfig::Mode::NONE);
    int disabledMirrorViews { 0 };
    if (!mirrorViewsEnabled) {
        renderSettings->setRenderMethod(RenderScriptingInterface::RenderMethod::FORWARD);

        // Do not render recursive world mirrors. The normal main stereo view
        // remains untouched; mirror surfaces simply retain their fallback.
        auto renderConfig = qApp->getRenderEngine()->getConfiguration();
        const QStringList viewNames { "RenderMainView", "RenderSecondView" };
        for (const auto& viewName : viewNames) {
            constexpr size_t MIRROR_VIEWS_PER_LEVEL { 3 };
            for (size_t mirrorIndex = 0; mirrorIndex < MIRROR_VIEWS_PER_LEVEL; ++mirrorIndex) {
                const QString mirrorName = viewName + ".RenderMirrorView" +
                    QString::number(mirrorIndex) + "Depth0";
                if (auto mirrorConfig = renderConfig->getConfig(mirrorName)) {
                    if (mirrorConfig->setProperty("enabled", false)) {
                        ++disabledMirrorViews;
                    }
                }
            }
        }
    } else {
        // Restore the known Pico baseline after an A/B profile run. The public
        // render setters persist values, so leaving this implicit would make a
        // later "profile off" run inherit parts of the power profile.
        renderSettings->setRenderMethod(RenderScriptingInterface::RenderMethod::FORWARD);
    }
    qCInfo(interfaceapp) << "PICO_POWER_PROFILE" << (picoPowerProfileEnabled ? "enabled" : "disabled")
                         << "renderScale" << renderSettings->getViewportResolutionScale()
                         << "forward" << (renderSettings->getRenderMethod() == RenderScriptingInterface::RenderMethod::FORWARD)
                         << "shadows" << renderSettings->getShadowsEnabled()
                         << "haze" << renderSettings->getHazeEnabled()
                         << "bloom" << renderSettings->getBloomEnabled()
                         << "ambientOcclusion" << renderSettings->getAmbientOcclusionEnabled()
                         << "localLights" << renderSettings->getLocalLightingEnabled()
                         << "proceduralMaterials" << renderSettings->getProceduralMaterialsEnabled()
                         << "disabledMirrorViews" << disabledMirrorViews;
#endif
#endif

    // finish initializing the camera, based on everything we checked above. Third person camera will be used if no settings
    // dictated that we should be in first person
    Menu::getInstance()->setIsOptionChecked(MenuOption::FirstPersonLookAt, isFirstPerson);
    Menu::getInstance()->setIsOptionChecked(MenuOption::ThirdPerson, !isFirstPerson);
#if defined(ANDROID_APP_PHONE_INTERFACE)
    // The native desktop menu bar is neither reachable nor appropriate in
    // Android's fullscreen activity. Phone controls live in the touch UI.
    Menu::getInstance()->setVisible(false);
#else
    Menu::getInstance()->setVisible(_menuBarVisible.get());
#endif
    _myCamera.setMode((isFirstPerson) ? CAMERA_MODE_FIRST_PERSON_LOOK_AT : CAMERA_MODE_LOOK_AT);
    cameraMenuChanged();

    if (!isFirstPerson) {
        // When camera changes from first person to third person, boom distance may be set to ZOOM_MIN so it needs to be reset to default.
        getMyAvatar()->setBoomLength(MyAvatar::ZOOM_DEFAULT);
    }
    const auto& inputs = pluginManager->getInputPlugins();
    for (const auto& plugin : inputs) {
        if (!plugin->isActive()) {
            plugin->activate();
        }
    }

    QSharedPointer<scripting::Audio> audioScriptingInterface = qSharedPointerDynamicCast<scripting::Audio>(DependencyManager::get<AudioScriptingInterface>());
    if (audioScriptingInterface) {
        audioScriptingInterface->loadData();
    }

    getMyAvatar()->loadData();

    auto bucketEnum = QMetaEnum::fromType<ExternalResource::Bucket>();
    auto externalResource = ExternalResource::getInstance();

    for (int i = 0; i < bucketEnum.keyCount(); i++) {
        const char* keyName = bucketEnum.key(i);
        QString setting("ExternalResource/");
        setting += keyName;
        auto bucket = static_cast<ExternalResource::Bucket>(bucketEnum.keyToValue(keyName));
        Setting::Handle<QString> url(setting, externalResource->getBase(bucket));
        externalResource->setBase(bucket, url.get());
    }

    // the setter function isn't called, so update the theme colors now
    updateThemeColors();

    _settingsLoaded = true;
}

void Application::saveSettings() const {
    sessionRunTime.set(_sessionRunTimer.elapsed() / MSECS_PER_SECOND);
    DependencyManager::get<AudioClient>()->saveSettings();
    DependencyManager::get<LODManager>()->saveSettings();

    QSharedPointer<scripting::Audio> audioScriptingInterface = qSharedPointerDynamicCast<scripting::Audio>(DependencyManager::get<AudioScriptingInterface>());
    if (audioScriptingInterface) {
        audioScriptingInterface->saveData();
    }

    Menu::getInstance()->saveSettings();
    getMyAvatar()->saveData();
    PluginManager::getInstance()->saveSettings();

    // Don't save external resource paths until such time as there's UI to select or set alternatives. Otherwise new default
    // values won't be used unless Interface.json entries are manually remove or Interface.json is deleted.
    /*
    auto bucketEnum = QMetaEnum::fromType<ExternalResource::Bucket>();
    auto externalResource = ExternalResource::getInstance();

    for (int i = 0; i < bucketEnum.keyCount(); i++) {
        const char* keyName = bucketEnum.key(i);
        QString setting("ExternalResource/");
        setting += keyName;
        auto bucket = static_cast<ExternalResource::Bucket>(bucketEnum.keyToValue(keyName));
        Setting::Handle<QString> url(setting, externalResource->getBase(bucket));
        url.set(externalResource->getBase(bucket));
    }
    */
}

// This is currently not used, but could be invoked if the user wants to go to the place embedded in an
// Interface-taken snapshot. (It was developed for drag and drop, before we had asset-server loading or in-world browsers.)
bool Application::acceptSnapshot(const QString& urlString) {
    QUrl url(urlString);
    QString snapshotPath = url.toLocalFile();

    SnapshotMetaData* snapshotData = DependencyManager::get<Snapshot>()->parseSnapshotData(snapshotPath);
    if (snapshotData) {
        if (!snapshotData->getURL().toString().isEmpty()) {
            DependencyManager::get<AddressManager>()->handleLookupString(snapshotData->getURL().toString());
        }
    } else {
        OffscreenUi::asyncWarning("", "No location details were found in the file\n" +
                             snapshotPath + "\nTry dragging in an authentic Hifi snapshot.");
    }
    return true;
}

void Application::setSessionUUID(const QUuid& sessionUUID) const {
    Physics::setSessionUUID(sessionUUID);
}

void Application::domainURLChanged(QUrl domainURL) {
    // disable physics until we have enough information about our new location to not cause craziness.
    setIsServerlessMode(domainURL.scheme() != URL_SCHEME_OVERTE);
    if (isServerlessMode()) {
        loadServerlessDomain(domainURL);
    }
    updateWindowTitle();
}

void Application::domainConnectionRefused(const QString& reasonMessage, int reasonCodeInt, const QString& extraInfo) {
    DomainHandler::ConnectionRefusedReason reasonCode = static_cast<DomainHandler::ConnectionRefusedReason>(reasonCodeInt);

    if (reasonCode == DomainHandler::ConnectionRefusedReason::TooManyUsers && !extraInfo.isEmpty()) {
        DependencyManager::get<AddressManager>()->handleLookupString(extraInfo);
        return;
    }

    switch (reasonCode) {
        case DomainHandler::ConnectionRefusedReason::ProtocolMismatch:
        case DomainHandler::ConnectionRefusedReason::TooManyUsers:
        case DomainHandler::ConnectionRefusedReason::Unknown: {
            QString message = "Unable to connect to the location you are visiting.\n";
            message += reasonMessage;
            OffscreenUi::asyncWarning("", message);
            getMyAvatar()->setWorldVelocity(glm::vec3(0.0f));
            break;
        }
        default:
            // nothing to do.
            break;
    }
}

void Application::updateWindowTitle() const {
    auto nodeList = DependencyManager::get<NodeList>();
    auto accountManager = DependencyManager::get<AccountManager>();
    auto domainAccountManager = DependencyManager::get<DomainAccountManager>();
    auto isInErrorState = nodeList->getDomainHandler().isInErrorState();
    bool isMetaverseLoggedIn = accountManager->isLoggedIn();
    bool hasDomainLogIn = domainAccountManager->hasLogIn();
    bool isDomainLoggedIn = domainAccountManager->isLoggedIn();
    QString authedDomainName = domainAccountManager->getAuthedDomainName();

    QString buildVersion = " - Overte - " +
                           (BuildInfo::BUILD_TYPE == BuildInfo::BuildType::Stable ? QString("Version") : QString("Build")) +
                           " " + applicationVersion();

    QString connectionStatus = isInErrorState                               ? " (ERROR CONNECTING)"
                               : nodeList->getDomainHandler().isConnected() ? ""
                                                                            : " (NOT CONNECTED)";

    QString metaverseUsername = accountManager->getAccountInfo().getUsername();
    QString domainUsername = domainAccountManager->getUsername();

    auto& ch = CrashHandler::getInstance();
    ch.setAnnotation("sentry[user][username]", metaverseUsername.toStdString());

    QString currentPlaceName;
    if (isServerlessMode()) {
        if (isInErrorState) {
            currentPlaceName = "Serverless: " + nodeList->getDomainHandler().getErrorDomainURL().toString();
        } else {
            currentPlaceName = "Serverless: " + DependencyManager::get<AddressManager>()->getDomainURL().toString();
        }
    } else {
        currentPlaceName = DependencyManager::get<AddressManager>()->getDomainURL().host();
        if (currentPlaceName.isEmpty()) {
            currentPlaceName = nodeList->getDomainHandler().getHostname();
        }
    }

    QString metaverseDetails;
    if (isMetaverseLoggedIn) {
        metaverseDetails = " (Directory Services: Connected to " + MetaverseAPI::getCurrentMetaverseServerURL().toString() +
                           " as " + metaverseUsername + ")";
    } else {
        metaverseDetails = " (Directory Services: Not Logged In)";
    }

    QString domainDetails;
    if (hasDomainLogIn) {
        if (currentPlaceName == authedDomainName && isDomainLoggedIn) {
            domainDetails = " (Domain: Logged in as " + domainUsername + ")";
        } else {
            domainDetails = " (Domain: Not Logged In)";
        }
    } else {
        domainDetails = "";
    }

    QString title = currentPlaceName + connectionStatus + metaverseDetails + domainDetails + buildVersion;

#ifndef _WIN32
    // crashes with vs2013/win32
    qCDebug(interfaceapp, "Application title set to: %s", title.toStdString().c_str());
#endif
    _window->setWindowTitle(title);

    // updateTitleWindow gets called whenever there's a change regarding the domain, so rather
    // than placing this within domainURLChanged, it's placed here to cover the other potential cases.
    DependencyManager::get<MessagesClient>()->sendLocalMessage("Toolbar-DomainChanged", "");
}

void Application::nodeAdded(SharedNodePointer node) {
    if (node->getType() == NodeType::EntityServer) {
        if (_failedToConnectToEntityServer && !_entityServerConnectionTimer.isActive()) {
            _octreeProcessor->stopSafeLanding();
            _failedToConnectToEntityServer = false;
        } else if (_entityServerConnectionTimer.isActive()) {
            _entityServerConnectionTimer.stop();
        }
        _octreeProcessor->startSafeLanding();
        _entityServerConnectionTimer.setInterval(ENTITY_SERVER_CONNECTION_TIMEOUT);
        _entityServerConnectionTimer.start();
    }
}

void Application::nodeActivated(SharedNodePointer node) {
    if (node->getType() == NodeType::AssetServer) {
        // asset server just connected - check if we have the asset browser showing

#if !defined(DISABLE_QML)
        auto offscreenUi = getOffscreenUI();
        if (offscreenUi) {
            auto nodeList = DependencyManager::get<NodeList>();

            if (nodeList->getThisNodeCanWriteAssets()) {
                // call reload on the shown asset browser dialog to get the mappings (if permissions allow)
                auto assetDialog = offscreenUi ? offscreenUi->getRootItem()->findChild<QQuickItem*>("AssetServer") : nullptr;
                if (assetDialog) {
                    QMetaObject::invokeMethod(assetDialog, "reload");
                }
            } else {
                // we switched to an Asset Server that we can't modify, hide the Asset Browser
                offscreenUi->hide("AssetServer");
            }
        }
#endif
    }

    // If we get a new EntityServer activated, reset lastQueried time
    // so we will do a proper query during update
    if (node->getType() == NodeType::EntityServer) {
        _queryExpiry = SteadyClock::now();
        _octreeQuery.incrementConnectionID();
#if defined(Q_OS_IOS) || defined(OVERTE_IOS)
        qInfo().noquote() << "OVERTE_IOS_ENTITY_GATE entity_server_active"
                          << "node=" << node->getUUID().toString(QUuid::WithoutBraces);
#endif

        if  (!_failedToConnectToEntityServer) {
            _entityServerConnectionTimer.stop();
        }
    }

    if (node->getType() == NodeType::AudioMixer && !isInterstitialMode()) {
        DependencyManager::get<AudioClient>()->negotiateAudioFormat();
    }

    if (node->getType() == NodeType::AvatarMixer) {
        _queryExpiry = SteadyClock::now();

        // new avatar mixer, send off our identity packet on next update loop
        // Reset skeletonModelUrl if the last server modified our choice.
        // Override the avatar url (but not model name) here too.
        if (_avatarOverrideUrl.isValid()) {
            getMyAvatar()->useFullAvatarURL(_avatarOverrideUrl);
        }

        if (getMyAvatar()->getFullAvatarURLFromPreferences() != getMyAvatar()->getSkeletonModelURL()) {
            getMyAvatar()->resetFullAvatarURL();
        }
        getMyAvatar()->markIdentityDataChanged();
        getMyAvatar()->resetLastSent();

        if (!isInterstitialMode()) {
            // transmit a "sendAll" packet to the AvatarMixer we just connected to.
            getMyAvatar()->sendAvatarDataPacket(true);
        }
    }
}

void Application::nodeKilled(SharedNodePointer node) {
    // These are here because connecting NodeList::nodeKilled to OctreePacketProcessor::nodeKilled doesn't work:
    // OctreePacketProcessor::nodeKilled is not being called when NodeList::nodeKilled is emitted.
    // This may have to do with GenericThread::threadRoutine() blocking the QThread event loop

    _octreeProcessor->nodeKilled(node);

    _entityEditSender->nodeKilled(node);

    if (node->getType() == NodeType::AudioMixer) {
        QMetaObject::invokeMethod(DependencyManager::get<AudioClient>().data(), "audioMixerKilled");
    } else if (node->getType() == NodeType::EntityServer) {
        // we lost an entity server, clear all of the domain octree details
#if defined(ANDROID_APP_PICO_INTERFACE)
        // Once the player is already in a playable world, an entity-server reconnect is not a
        // domain change. Keep the current scene and controls active while the server reconnects;
        // clearing the octree here re-entered the full loading interstitial a few seconds later.
        if (_physicsEnabled) {
            qCWarning(interfaceapp) << "Pico entity server disconnected; keeping playable scene during reconnect";
            return;
        }
#endif
        clearDomainOctreeDetails(false);
    } else if (node->getType() == NodeType::AssetServer) {
        // asset server going away - check if we have the asset browser showing

#if !defined(DISABLE_QML)
        auto offscreenUi = getOffscreenUI();
        auto assetDialog = offscreenUi ? offscreenUi->getRootItem()->findChild<QQuickItem*>("AssetServer") : nullptr;

        if (assetDialog) {
            // call reload on the shown asset browser dialog
            QMetaObject::invokeMethod(assetDialog, "clear");
        }
#endif
    }
}

void Application::handleSandboxStatus(QNetworkReply* reply) {
    PROFILE_RANGE(render, __FUNCTION__);

    bool sandboxIsRunning = SandboxUtils::readStatus(reply->readAll());

    enum HandControllerType {
        Vive,
        Oculus
    };
    static const std::map<HandControllerType, int> MIN_CONTENT_VERSION = {
        { Vive, 1 },
        { Oculus, 27 }
    };

    // Get sandbox content set version
    auto acDirPath = PathUtils::getAppDataPath() + "../../" + BuildInfo::MODIFIED_ORGANIZATION + "/assignment-client/";
    auto contentVersionPath = acDirPath + "content-version.txt";
    qCDebug(interfaceapp) << "Checking " << contentVersionPath << " for content version";
    int contentVersion = 0;
    QFile contentVersionFile(contentVersionPath);
    if (contentVersionFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QString line = contentVersionFile.readAll();
        contentVersion = line.toInt(); // returns 0 if conversion fails
    }

    // Get controller availability
#ifdef ANDROID_APP_QUEST_INTERFACE
    bool hasHandControllers = true;
#else
    bool hasHandControllers = false;
    if (PluginUtils::isViveControllerAvailable() || PluginUtils::isOculusTouchControllerAvailable()) {
        hasHandControllers = true;
    }
#endif

    // Check HMD use (may be technically available without being in use)
    bool hasHMD = PluginUtils::isHMDAvailable();
    bool isUsingHMD = _displayPlugin->isHmd();
    bool isUsingHMDAndHandControllers = hasHMD && hasHandControllers && isUsingHMD;

    qCDebug(interfaceapp) << "HMD:" << hasHMD << ", Hand Controllers: " << hasHandControllers << ", Using HMD: " << isUsingHMDAndHandControllers;

    QString addressLookupString;

#if defined(ANDROID_APP_PICO_INTERFACE)
    // The Pico app is deployed with a dedicated LAN domain containing the
    // measured ultra-optimized spawn scene. Use it for every ordinary launch
    // (explicit command-line URLs still take precedence).
    static const QString PICO_DEFAULT_STARTUP_ADDRESS =
        QStringLiteral("hifi://192.168.188.180:40502/155.084,-98.5,-397.328");
#endif

    // when --url in command line, teleport to location
    if (!_urlParam.isEmpty()) { // Not sure if format supported by isValid().
        if (_urlParam.scheme() == URL_SCHEME_OVERTEAPP) {
            Setting::Handle<QVariant>("startUpApp").set(_urlParam.path());
        } else {
            addressLookupString = _urlParam.toString();
        }
    }

#if defined(ANDROID_APP_PICO_INTERFACE)
    if (_urlParam.isEmpty()) {
        addressLookupString = PICO_DEFAULT_STARTUP_ADDRESS;
    }
#endif

    static const QString SENT_TO_PREVIOUS_LOCATION = "previous_location";
    static const QString SENT_TO_ENTRY = "entry";

    QString sentTo;

    // If this is a first run we short-circuit the address passed in
    if (_firstRun.get()
#ifdef Q_OS_ANDROID
        || addressLookupString.isEmpty()
#endif
    ) {
        if (!BuildInfo::PRELOADED_STARTUP_LOCATION.isEmpty()) {
            DependencyManager::get<LocationBookmarks>()->setHomeLocationToAddress(NetworkingConstants::DEFAULT_OVERTE_ADDRESS);
            Menu::getInstance()->triggerOption(MenuOption::HomeLocation);
        }

        if (!_overrideEntry) {
#ifdef Q_OS_ANDROID
            // Mobile builds ship a self-contained tutorial and may have no
            // entry-point setting yet (or retain an empty one from an older
            // install). Always choose the packaged, known-good location.
#if defined(ANDROID_APP_PICO_INTERFACE)
            qCInfo(interfaceapp) << "Pico startup: loading optimized LAN world"
                << PICO_DEFAULT_STARTUP_ADDRESS;
            DependencyManager::get<AddressManager>()->handleLookupString(
                PICO_DEFAULT_STARTUP_ADDRESS);
#else
            DependencyManager::get<AddressManager>()->handleLookupString(
                NetworkingConstants::DEFAULT_OVERTE_ADDRESS);
#endif
#else
            DependencyManager::get<AddressManager>()->goToEntry();
#endif
            sentTo = SENT_TO_ENTRY;
        } else {
            DependencyManager::get<AddressManager>()->loadSettings(addressLookupString);
            sentTo = SENT_TO_PREVIOUS_LOCATION;
        }
       _firstRun.set(false);
    } else {
        QString goingTo = "";
        if (addressLookupString.isEmpty()) {
            if (Menu::getInstance()->isOptionChecked(MenuOption::HomeLocation)) {
                auto locationBookmarks = DependencyManager::get<LocationBookmarks>();
                addressLookupString = locationBookmarks->addressForBookmark(LocationBookmarks::HOME_BOOKMARK);
                goingTo = "home location";
            } else {
                goingTo = "previous location";
            }
        }
        qCDebug(interfaceapp) << "Not first run... going to" << qPrintable(!goingTo.isEmpty() ? goingTo : addressLookupString);
        DependencyManager::get<AddressManager>()->loadSettings(addressLookupString);
        sentTo = SENT_TO_PREVIOUS_LOCATION;
    }

    UserActivityLogger::getInstance().logAction("startup_sent_to", {
        { "sent_to", sentTo },
        { "sandbox_is_running", sandboxIsRunning },
        { "has_hmd", hasHMD },
        { "has_hand_controllers", hasHandControllers },
        { "is_using_hmd", isUsingHMD },
        { "is_using_hmd_and_hand_controllers", isUsingHMDAndHandControllers },
        { "content_version", contentVersion }
    });

    _connectionMonitor.init();
}

void Application::cleanupBeforeQuit() {
    // add a logline indicating if QTWEBENGINE_REMOTE_DEBUGGING is set or not
    QString webengineRemoteDebugging = QProcessEnvironment::systemEnvironment().value("QTWEBENGINE_REMOTE_DEBUGGING", "false");
    qCDebug(interfaceapp) << "QTWEBENGINE_REMOTE_DEBUGGING =" << webengineRemoteDebugging;

    DependencyManager::prepareToExit();

    if (tracing::enabled()) {
        auto tracer = DependencyManager::get<tracing::Tracer>();
        tracer->stopTracing();
        auto outputFile = property(hifi::properties::TRACING).toString();
        tracer->serialize(outputFile);
    }

    // Stop third party processes so that they're not left running in the event of a subsequent shutdown crash.
    AnimDebugDraw::getInstance().shutdown();

    // FIXME: once we move to shared pointer for the INputDevice we shoud remove this naked delete:
    _applicationStateDevice.reset();

    {
        if (_keyboardFocusHighlightID != UNKNOWN_ENTITY_ID) {
            DependencyManager::get<EntityScriptingInterface>()->deleteEntity(_keyboardFocusHighlightID);
            _keyboardFocusHighlightID = UNKNOWN_ENTITY_ID;
        }
    }

    {
        auto nodeList = DependencyManager::get<NodeList>();

        // send the domain a disconnect packet, force stoppage of domain-server check-ins
        nodeList->getDomainHandler().disconnect("Quitting");
        nodeList->setIsShuttingDown(true);

        // tell the packet receiver we're shutting down, so it can drop packets
        nodeList->getPacketReceiver().setShouldDropPackets(true);
    }

    getEntities()->shutdown(); // tell the entities system we're shutting down, so it will stop running scripts

    // Clear any queued processing (I/O, FBX/OBJ/Texture parsing)
    QThreadPool::globalInstance()->clear();
    QThreadPool::globalInstance()->waitForDone();

    DependencyManager::destroy<RecordingScriptingInterface>();

    // FIXME: Something is still holding on to the ScriptEnginePointers contained in ScriptEngines, and they hold backpointers to ScriptEngines,
    // so this doesn't shut down properly
    DependencyManager::get<ScriptEngines>()->shutdownScripting(); // stop all currently running global scripts
    // These classes hold ScriptEnginePointers, so they must be destroyed before ScriptEngines
    // Must be done after shutdownScripting in case any scripts try to access these things
    {
        DependencyManager::destroy<StandAloneJSConsole>();
        EntityTreePointer tree = getEntities()->getTree();
        tree->setSimulation(nullptr);
        DependencyManager::destroy<EntityTreeRenderer>();
    }
    DependencyManager::destroy<ScriptEngines>();

    bool keepMeLoggedIn = Setting::Handle<bool>(KEEP_ME_LOGGED_IN_SETTING_NAME, false).get();
    if (!keepMeLoggedIn) {
        DependencyManager::get<AccountManager>()->removeAccountFromFile();
    }
    // ####### TODO

    _displayPlugin.reset();
    PluginManager::getInstance()->shutdown();

    // Cleanup all overlays after the scripts, as scripts might add more
    _overlays.cleanupAllOverlays();

    // first stop all timers directly or by invokeMethod
    // depending on what thread they run in
    _locationUpdateTimer.stop();
    _window->saveGeometry();

    // stop QML
    DependencyManager::destroy<TabletScriptingInterface>();
    DependencyManager::destroy<ToolbarScriptingInterface>();
    DependencyManager::destroy<OffscreenUi>();

    DependencyManager::destroy<OffscreenQmlSurfaceCache>();

    // destroy Audio so it and its threads have a chance to go down safely
    // this must happen after QML, as there are unexplained audio crashes originating in qtwebengine
    AudioInjector::setLocalAudioInterface(nullptr);
    DependencyManager::destroy<AudioClient>();
    DependencyManager::destroy<AudioScriptingInterface>();

    // The PointerManager must be destroyed before the PickManager because when a Pointer is deleted,
    // it accesses the PickManager to delete its associated Pick
    DependencyManager::destroy<PointerManager>();
    DependencyManager::destroy<PickManager>();
    DependencyManager::destroy<KeyboardScriptingInterface>();
    DependencyManager::destroy<Keyboard>();
    DependencyManager::destroy<AvatarPackager>();

    qCDebug(interfaceapp) << "Application::cleanupBeforeQuit() complete";
}


static const float FOCUS_HIGHLIGHT_EXPANSION_FACTOR = 1.05f;
void Application::idle() {
    PerformanceTimer perfTimer("idle");

#if !defined(DISABLE_QML)
    auto offscreenUi = getOffscreenUI();

    // These tasks need to be done on our first idle, because we don't want the showing of
    // overlay subwindows to do a showDesktop() until after the first time through
    static bool firstIdle = true;
    if (firstIdle) {
        firstIdle = false;
        connect(offscreenUi.data(), &OffscreenUi::showDesktop, this, &Application::showDesktop);
    }
#endif

#ifdef Q_OS_WIN
    {
        // If tracing is enabled then monitor the CPU in a separate thread
        static std::once_flag once;
        std::call_once(once, [&] {
            if (trace_app().isDebugEnabled()) {
                QThread* cpuMonitorThread = new QThread(qApp);
                cpuMonitorThread->setObjectName("cpuMonitorThread");
                QObject::connect(cpuMonitorThread, &QThread::started, [this] { setupCpuMonitorThread(); });
                QObject::connect(qApp, &QCoreApplication::aboutToQuit, cpuMonitorThread, &QThread::quit);
                cpuMonitorThread->start();
            }
        });
    }
#endif

    auto displayPlugin = getActiveDisplayPlugin();
#if !defined(DISABLE_QML)
    if (displayPlugin) {
        auto uiSize = displayPlugin->getRecommendedUiSize();
        // Bit of a hack since there's no device pixel ratio change event I can find.
        if (offscreenUi->size() != fromGlm(uiSize)) {
            qCDebug(interfaceapp) << "Device pixel ratio changed, triggering resize to " << uiSize;
            offscreenUi->resize(fromGlm(uiSize));
        }
    }
#endif

    if (displayPlugin) {
        PROFILE_COUNTER_IF_CHANGED(app, "present", float, displayPlugin->presentRate());
    }
    PROFILE_COUNTER_IF_CHANGED(app, "renderLoopRate", float, getRenderLoopRate());
    PROFILE_COUNTER_IF_CHANGED(app, "currentDownloads", uint32_t, ResourceCache::getLoadingRequests().length());
    PROFILE_COUNTER_IF_CHANGED(app, "pendingDownloads", uint32_t, ResourceCache::getPendingRequestCount());
    PROFILE_COUNTER_IF_CHANGED(app, "currentProcessing", int, DependencyManager::get<StatTracker>()->getStat("Processing").toInt());
    PROFILE_COUNTER_IF_CHANGED(app, "pendingProcessing", int, DependencyManager::get<StatTracker>()->getStat("PendingProcessing").toInt());
    auto renderConfig = _graphicsEngine->getRenderEngine()->getConfiguration();
    PROFILE_COUNTER_IF_CHANGED(render, "gpuTime", float, (float)_graphicsEngine->getGPUContext()->getFrameTimerGPUAverage());

    PROFILE_RANGE(app, __FUNCTION__);

    if (auto steamClient = PluginManager::getInstance()->getSteamClientPlugin()) {
        steamClient->runCallbacks();
    }

    if (auto oculusPlugin = PluginManager::getInstance()->getOculusPlatformPlugin()) {
        oculusPlugin->handleOVREvents();
    }

    float secondsSinceLastUpdate = (float)_lastTimeUpdated.nsecsElapsed() / NSECS_PER_MSEC / MSECS_PER_SECOND;
    _lastTimeUpdated.start();

#if !defined(DISABLE_QML)
    // If the offscreen Ui has something active that is NOT the root, then assume it has keyboard focus.
    if (offscreenUi && offscreenUi->getWindow()) {
        auto activeFocusItem = offscreenUi->getWindow()->activeFocusItem();
        if (_keyboardDeviceHasFocus && (activeFocusItem != NULL && activeFocusItem != offscreenUi->getRootItem())) {
            _keyboardMouseDevice->pluginFocusOutEvent();
            _keyboardDeviceHasFocus = false;
            synthesizeKeyReleasEvents();
        } else if (activeFocusItem == offscreenUi->getRootItem()) {
            _keyboardDeviceHasFocus = true;
        }
    }
#endif

    checkChangeCursor();

#if !defined(DISABLE_QML)
    auto stats = Stats::getInstance();
    if (stats) {
        stats->updateStats();
    }
    auto animStats = AnimStats::getInstance();
    if (animStats) {
        animStats->updateStats();
    }
#endif

    // Normally we check PipelineWarnings, but since idle will often take more than 10ms we only show these idle timing
    // details if we're in ExtraDebugging mode. However, the ::update() and its subcomponents will show their timing
    // details normally.
#ifdef Q_OS_ANDROID
    bool showWarnings = false;
#else
    bool showWarnings = getLogger()->extraDebugging();
#endif
    PerformanceWarning warn(showWarnings, "idle()");

    {
        _gameWorkload.updateViews(_viewFrustum, getMyAvatar()->getHeadPosition());
        _gameWorkload._engine->run();
    }
    {
        PerformanceTimer perfTimer("update");
        PerformanceWarning warn(showWarnings, "Application::idle()... update()");
        static const float BIGGEST_DELTA_TIME_SECS = 0.25f;
        update(glm::clamp(secondsSinceLastUpdate, 0.0f, BIGGEST_DELTA_TIME_SECS));
    }

    { // Update keyboard focus highlight
        if (!_keyboardFocusedEntity.get().isInvalidID()) {
            const quint64 LOSE_FOCUS_AFTER_ELAPSED_TIME = 30 * USECS_PER_SECOND; // if idle for 30 seconds, drop focus
            quint64 elapsedSinceAcceptedKeyPress = usecTimestampNow() - _lastAcceptedKeyPress;
            if (elapsedSinceAcceptedKeyPress > LOSE_FOCUS_AFTER_ELAPSED_TIME) {
                setKeyboardFocusEntity(UNKNOWN_ENTITY_ID);
            } else {
                if (auto entity = getEntities()->getTree()->findEntityByID(_keyboardFocusedEntity.get())) {
                    EntityItemProperties properties;
                    properties.setPosition(entity->getWorldPosition());
                    properties.setRotation(entity->getWorldOrientation());
                    properties.setDimensions(entity->getScaledDimensions() * FOCUS_HIGHLIGHT_EXPANSION_FACTOR);
                    DependencyManager::get<EntityScriptingInterface>()->editEntity(_keyboardFocusHighlightID, properties);
                }
            }
        }
    }

    {
        if (_keyboardFocusWaitingOnRenderable && getEntities()->renderableForEntityId(_keyboardFocusedEntity.get())) {
            QUuid entityId = _keyboardFocusedEntity.get();
            setKeyboardFocusEntity(UNKNOWN_ENTITY_ID);
            _keyboardFocusWaitingOnRenderable = false;
            setKeyboardFocusEntity(entityId);
        }
    }

    {
        PerformanceTimer perfTimer("pluginIdle");
        PerformanceWarning warn(showWarnings, "Application::idle()... pluginIdle()");
        getActiveDisplayPlugin()->idle();
        const auto& inputPlugins = PluginManager::getInstance()->getInputPlugins();
        for(const auto& inputPlugin : inputPlugins) {
            if (inputPlugin->isActive()) {
                inputPlugin->idle();
            }
        }
    }

    _overlayConductor.update(secondsSinceLastUpdate);

    _gameLoopCounter.increment();

    // Perform one-time startup checks in case we need to show warnings
    {
        static std::once_flag once;
        std::call_once(once, [this] {
            const QString& bookmarksError = DependencyManager::get<AvatarBookmarks>()->getBookmarkError();
            if (!bookmarksError.isEmpty()) {
#if defined(ANDROID_APP_PHONE_INTERFACE)
                // Parser diagnostics can contain file paths or fragments of
                // personal bookmark data. Android logs are routinely captured
                // by automated tooling, so report only the aggregate failure.
                qWarning() << "Avatar bookmarks JSON could not be loaded";
#else
                OffscreenUi::asyncWarning("Avatar Bookmarks Error", "JSON parse error: " + bookmarksError, QMessageBox::Ok, QMessageBox::Ok);
#endif
            }

#if !defined(ANDROID_APP_PHONE_INTERFACE)
            // Desktop GPU drivers can be replaced or rolled back by the user,
            // so the blocklist warning is actionable there. Android GPU
            // drivers are delivered with the OS and the desktop warning is
            // misleading (and poorly sized) in the phone activity.
            QString os = platform::getComputer()[platform::keys::computer::OS].dump().c_str();
            os = os.replace("\"", "");
            GPUIdent* gpuIdent = GPUIdent::getInstance();
            QString vendor = platform::Instance::findGPUVendorInDescription(gpuIdent->getName().toStdString());
            QString renderer = gl::ContextInfo::get().renderer.c_str();
            QString api = _graphicsEngine->getGPUContext()->getBackendVersion().c_str();
            QString driver = gpuIdent->getDriver();
            QString fullDriverToTest = os + " " + vendor + " " + renderer + " " + api + " " + driver;
            if (fullDriverToTest != _prevCheckedDriver.get()) {
                QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();
                QNetworkRequest request(QUrl("https://mv.overte.org/gpu_driver_blocklist.json"));
                request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
                request.setHeader(QNetworkRequest::UserAgentHeader, NetworkingConstants::OVERTE_USER_AGENT);
                QNetworkReply* reply = networkAccessManager.get(request);
                auto onFinished = std::bind(&Application::processDriverBlocklistReply, this, fullDriverToTest, os, vendor, renderer, api, driver.replace(" ", "."));
                connect(reply, &QNetworkReply::finished, this, onFinished);
            }
#endif
        });
    }
}

void Application::update(float deltaTime) {
    PROFILE_RANGE_EX(app, __FUNCTION__, 0xffff0000, (uint64_t)_graphicsEngine->_renderFrameCount + 1);

    if (_aboutToQuit) {
        return;
    }
#if defined(Q_OS_ANDROID)
    const quint64 picoUpdateStart = usecTimestampNow();
    static bool picoTestMode { false };
    static double picoAvatarSimulationMsSum { 0.0 };
    static double picoAvatarProcessingMsSum { 0.0 };
    static double picoAvatarPriorityBuildMsSum { 0.0 };
    static double picoAvatarSortMsSum { 0.0 };
    static double picoAvatarPreUpdateMsSum { 0.0 };
    static double picoAvatarStatePollMsSum { 0.0 };
    static double picoAvatarEnsureSceneMsSum { 0.0 };
    static double picoAvatarScaleAnimationMsSum { 0.0 };
    static double picoAvatarSimulateMsSum { 0.0 };
    static quint64 picoAvatarSimulationSamples { 0 };
    static quint64 picoLocalAvatarTemplateRefreshes { 0 };
    static quint64 lastTestModePropertyCheck { 0 };
    if (picoUpdateStart - lastTestModePropertyCheck >= USECS_PER_SECOND) {
        lastTestModePropertyCheck = picoUpdateStart;
        char testModeValue[PROP_VALUE_MAX] {};
        const QString requestedTestMode = __system_property_get("debug.overte.test_mode", testModeValue) > 0
            ? QString::fromLatin1(testModeValue).trimmed().toLower()
            : QString();
        picoTestMode = requestedTestMode == "1" || requestedTestMode == "on" ||
            requestedTestMode == "true" || requestedTestMode == "enabled";
        if (!picoTestMode) {
            picoAvatarSimulationMsSum = 0.0;
            picoAvatarProcessingMsSum = 0.0;
            picoAvatarPriorityBuildMsSum = 0.0;
            picoAvatarSortMsSum = 0.0;
            picoAvatarPreUpdateMsSum = 0.0;
            picoAvatarStatePollMsSum = 0.0;
            picoAvatarEnsureSceneMsSum = 0.0;
            picoAvatarScaleAnimationMsSum = 0.0;
            picoAvatarSimulateMsSum = 0.0;
            picoAvatarSimulationSamples = 0;
            picoLocalAvatarTemplateRefreshes = 0;
        }
    }
    // ADB-controlled navigation for unattended Pico performance tests. The
    // nonce prefix lets the same destination be requested more than once.
    static quint64 lastNavigationPropertyCheck { 0 };
    static QString lastNavigationCommand;
    static QString lastExportCommand;
    if (picoUpdateStart - lastNavigationPropertyCheck >= 250 * USECS_PER_MSEC) {
        lastNavigationPropertyCheck = picoUpdateStart;
        auto addressManager = DependencyManager::get<AddressManager>();
#if defined(ANDROID_APP_PICO_INTERFACE)
        // Test-only export of the currently received domain scene. This is
        // intentionally ADB/property controlled and never active in normal
        // sessions; it lets the Pico loading harness create a reproducible
        // serverless copy for before/after comparisons.
        char exportValue[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.export", exportValue) > 0) {
            const QString command = QString::fromUtf8(exportValue).trimmed();
            if (!command.isEmpty() && command != lastExportCommand) {
                    lastExportCommand = command;
                    const QStringList fields = command.split('|');
                    bool xOk { false };
                    bool yOk { false };
                    bool zOk { false };
                    bool scaleOk { false };
                    const QString filename = fields.value(1);
                    const float x = fields.value(2).toFloat(&xOk);
                    const float y = fields.value(3).toFloat(&yOk);
                    const float z = fields.value(4).toFloat(&zOk);
                    const float scale = fields.value(5).toFloat(&scaleOk);
                    if (fields.size() == 6 && !filename.isEmpty() && xOk && yOk && zOk && scaleOk && scale > 0.0f) {
                        QVariantMap options;
                        options.insert("globalPositions", true);
                        const bool exported = exportEntities(filename, x, y, z, scale, options);
                        qCInfo(interfaceapp) << "PICO_SERVERLESS_EXPORT"
                            << "success" << exported << "filename" << filename
                            << "center" << x << y << z << "scale" << scale;
                    } else {
                        qCWarning(interfaceapp) << "PICO_SERVERLESS_EXPORT invalid command" << command;
                    }
            }
        }
#endif
        // Publish the authoritative connected world and avatar position only
        // for explicitly enabled unattended tests. Normal Pico sessions avoid
        // this once-per-second cache-file write.
        static quint64 lastWorldStatusWrite { 0 };
        if (picoTestMode && picoUpdateStart - lastWorldStatusWrite >= USECS_PER_SECOND) {
            lastWorldStatusWrite = picoUpdateStart;
            const glm::vec3 worldPosition = getMyAvatar()->getWorldPosition();
            const QString worldStatus = QStringLiteral("%1|%2|%3|%4|%5|%6|%7")
                .arg(QDateTime::currentSecsSinceEpoch())
                .arg(addressManager->isConnected() ? 1 : 0)
                .arg(addressManager->getPlaceName().replace('|', '_'))
                .arg(addressManager->getDomainID().replace('|', '_'))
                .arg(worldPosition.x, 0, 'f', 3)
                .arg(worldPosition.y, 0, 'f', 3)
                .arg(worldPosition.z, 0, 'f', 3);
            QSaveFile worldStatusFile("/data/user/0/org.overte.pico/cache/world-status");
            if (worldStatusFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
                worldStatusFile.write(worldStatus.toUtf8());
                worldStatusFile.commit();
            }

#if defined(ANDROID_APP_PICO_INTERFACE)
            if (_picoLoadingMeasurementStartedAt > 0) {
                const auto loadingRequests = ResourceCache::getLoadingRequests();
                const auto statTracker = DependencyManager::get<StatTracker>();
                const auto scriptEngines = DependencyManager::get<ScriptEngines>();
                const auto safeLandingStatus = _octreeProcessor->safeLandingLoadingStatus();
                const auto loadingElapsedMs = [this](quint64 milestone) -> qint64 {
                    return milestone > 0 && _picoLoadingMeasurementStartedAt > 0
                        ? static_cast<qint64>((milestone - _picoLoadingMeasurementStartedAt) / USECS_PER_MSEC)
                        : -1;
                };
                int activeScripts { 0 };
                int activeModels { 0 };
                int activeTextures { 0 };
                int activeAudio { 0 };
                int activeOther { 0 };
                QString activeResourceManifest;
                for (const auto& request : loadingRequests) {
                    const QString path = request.first->getURL().path().toLower();
                    QString category { QStringLiteral("other") };
                    if (path.endsWith(".js") || path.endsWith(".json")) {
                        ++activeScripts;
                        category = QStringLiteral("script");
                    } else if (path.endsWith(".fbx") || path.endsWith(".gltf") || path.endsWith(".glb") ||
                            path.endsWith(".obj")) {
                        ++activeModels;
                        category = QStringLiteral("model");
                    } else if (path.endsWith(".png") || path.endsWith(".jpg") || path.endsWith(".jpeg") ||
                            path.endsWith(".ktx") || path.endsWith(".ktx2")) {
                        ++activeTextures;
                        category = QStringLiteral("texture");
                    } else if (path.endsWith(".wav") || path.endsWith(".mp3") || path.endsWith(".ogg")) {
                        ++activeAudio;
                        category = QStringLiteral("audio");
                    } else {
                        ++activeOther;
                    }
                    const auto resource = request.first;
                    const auto encodedURL = QUrl::toPercentEncoding(
                        resource->getURL().toString(), "", "|,\n\r\"");
                    activeResourceManifest += QStringLiteral("%1|%2|%3|%4|%5|%6|%7\n")
                        .arg(QDateTime::currentMSecsSinceEpoch())
                        .arg((picoUpdateStart - _picoLoadingMeasurementStartedAt) / USECS_PER_MSEC)
                        .arg(category)
                        .arg(resource->getProgress(), 0, 'f', 3)
                        .arg(resource->getBytesReceived())
                        .arg(resource->getBytesTotal())
                        .arg(QString::fromLatin1(encodedURL));
                }
                const QString loadingSample = QStringLiteral(
                    "%1|%2|%3|%4|%5|%6|%7|%8|%9|%10|%11|%12|%13|%14|%15|%16|%17|%18|%19|%20|%21|%22|%23|%24|%25|%26|%27|%28|%29|%30|%31|%32|%33|%34|%35|%36|%37|%38|%39|%40|%41")
                    .arg(QDateTime::currentMSecsSinceEpoch())
                    .arg((picoUpdateStart - _picoLoadingMeasurementStartedAt) / USECS_PER_MSEC)
                    .arg(isInterstitialMode() ? 1 : 0)
                    .arg(loadingRequests.size())
                    .arg(ResourceCache::getPendingRequestCount())
                    .arg(statTracker->getStat("Processing").toInt())
                    .arg(statTracker->getStat("PendingProcessing").toInt())
                    .arg(statTracker->getStat(STAT_ATP_REQUEST_STARTED).toLongLong())
                    .arg(statTracker->getStat(STAT_HTTP_REQUEST_STARTED).toLongLong())
                    .arg(statTracker->getStat(STAT_ATP_REQUEST_SUCCESS).toLongLong())
                    .arg(statTracker->getStat(STAT_HTTP_REQUEST_SUCCESS).toLongLong())
                    .arg(statTracker->getStat(STAT_ATP_REQUEST_FAILED).toLongLong())
                    .arg(statTracker->getStat(STAT_HTTP_REQUEST_FAILED).toLongLong())
                    .arg(statTracker->getStat(STAT_ATP_RESOURCE_TOTAL_BYTES).toLongLong())
                    .arg(statTracker->getStat(STAT_HTTP_RESOURCE_TOTAL_BYTES).toLongLong())
                    .arg(_octreeProcessor->getEntityPacketCount())
                    .arg(_octreeProcessor->getEntityPacketBytes())
                    .arg(scriptEngines ? scriptEngines->getRunningScripts().size() : 0)
                    .arg(gpu::Context::getUsedGPUMemSize())
                    .arg(safeLandingStatus.trackedEntityCount)
                    .arg(safeLandingStatus.maximumTrackedEntityCount)
                    .arg(safeLandingStatus.physicsBlockedEntityCount)
                    .arg(safeLandingStatus.visuallyBlockedEntityCount)
                    .arg(safeLandingStatus.receivedSequenceCount)
                    .arg(safeLandingStatus.expectedSequenceCount)
                    .arg(safeLandingStatus.completionReceived ? 1 : 0)
                    .arg(_octreeProcessor->getFullSceneReceivedCounter().load())
                    .arg(getEntities()->getEntityScriptLoadCount())
                    .arg(getEntities()->getEntityScriptPreloadFinishedCount())
                    .arg(activeScripts)
                    .arg(activeModels)
                    .arg(activeTextures)
                    .arg(activeAudio)
                    .arg(activeOther)
                    .arg(_physicsEnabled ? 1 : 0)
                    .arg(loadingElapsedMs(_picoLoadingSafeLandingCompleteAt))
                    .arg(loadingElapsedMs(_picoLoadingGpuReadyAt))
                    .arg(loadingElapsedMs(_picoLoadingPhysicsEnabledAt))
                    .arg(loadingElapsedMs(_picoLoadingReadyAt))
                    .arg(_picoLoadingMeasurementEpochMs)
                    .arg(_picoLoadingDomainReconnects);
                QSaveFile loadingSampleFile("/data/user/0/org.overte.pico/cache/world-loading-sample");
                if (loadingSampleFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
                    loadingSampleFile.write(loadingSample.toUtf8());
                    loadingSampleFile.commit();
                }
                QSaveFile activeResourceFile("/data/user/0/org.overte.pico/cache/world-loading-active-resources");
                if (activeResourceFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
                    activeResourceFile.write(activeResourceManifest.toUtf8());
                    activeResourceFile.commit();
                }
            }
#endif
        }

        // Locally replicate received other avatars for repeatable Pico crowd
        // load tests. The timestamped command is accepted only while fresh so
        // a debug property left behind by an interrupted test cannot replay on
        // a later Interface launch. Format: epochSeconds|replicasPerAvatar.
        static QString lastAvatarReplicaCommand;
        if (picoTestMode) {
            static QString lastLocalAvatarTemplateCommand;
            char localAvatarTemplateValue[PROP_VALUE_MAX] {};
            if (__system_property_get("debug.overte.avatar_local_template", localAvatarTemplateValue) > 0) {
                const QString command = QString::fromUtf8(localAvatarTemplateValue).trimmed();
                if (!command.isEmpty() && command != lastLocalAvatarTemplateCommand) {
                    lastLocalAvatarTemplateCommand = command;
                    const QStringList fields = command.split('|');
                    bool timestampOk { false };
                    bool enabledOk { false };
                    const qint64 timestamp = fields.value(0).toLongLong(&timestampOk);
                    const int enabled = fields.value(1).toInt(&enabledOk);
                    const qint64 commandAge = QDateTime::currentSecsSinceEpoch() - timestamp;
                    if (fields.size() == 2 && timestampOk && enabledOk &&
                            commandAge >= -5 && commandAge <= 10 && (enabled == 0 || enabled == 1)) {
                        DependencyManager::get<AvatarManager>()->setLocalTestAvatarTemplateEnabled(enabled == 1);
                        qCInfo(interfaceapp) << "PICO_LOCAL_AVATAR_TEMPLATE" << enabled;
                    } else {
                        qCWarning(interfaceapp) << "PICO_LOCAL_AVATAR_TEMPLATE invalid or stale command" << command;
                    }
                }
            }

            char avatarReplicaValue[PROP_VALUE_MAX] {};
            if (__system_property_get("debug.overte.avatar_replicas", avatarReplicaValue) > 0) {
                const QString command = QString::fromUtf8(avatarReplicaValue).trimmed();
                if (!command.isEmpty() && command != lastAvatarReplicaCommand) {
                    lastAvatarReplicaCommand = command;
                    const QStringList fields = command.split('|');
                    bool timestampOk { false };
                    bool countOk { false };
                    const qint64 timestamp = fields.value(0).toLongLong(&timestampOk);
                    const int count = fields.value(1).toInt(&countOk);
                    const qint64 commandAge = QDateTime::currentSecsSinceEpoch() - timestamp;
                    if (fields.size() == 2 && timestampOk && countOk &&
                            commandAge >= -5 && commandAge <= 10 && count >= 0 && count <= 50) {
                        DependencyManager::get<AvatarManager>()->setReplicaCount(count);
                        qCInfo(interfaceapp) << "PICO_AVATAR_REPLICAS" << count;
                    } else {
                        qCWarning(interfaceapp) << "PICO_AVATAR_REPLICAS invalid or stale command" << command;
                    }
                }
            }

            static quint64 lastAvatarStatusWrite { 0 };
            if (picoUpdateStart - lastAvatarStatusWrite >= USECS_PER_SECOND) {
                lastAvatarStatusWrite = picoUpdateStart;
                auto avatarManager = DependencyManager::get<AvatarManager>();
                const auto avatarHash = avatarManager->getHashCopy();
                int replicatedAvatars { 0 };
                int loadedOtherAvatars { 0 };
                int loadedReplicatedAvatars { 0 };
                for (const auto& avatar : avatarHash) {
                    const bool replicated = avatar->getReplicaIndex() > 0;
                    if (replicated) {
                        ++replicatedAvatars;
                    }
                    const auto renderedAvatar = std::dynamic_pointer_cast<Avatar>(avatar);
                    const auto skeletonModel = renderedAvatar ? renderedAvatar->getSkeletonModel() : nullptr;
                    if (avatar.get() != avatarManager->getMyAvatar().get() &&
                            skeletonModel && skeletonModel->isLoaded()) {
                        ++loadedOtherAvatars;
                        if (replicated) {
                            ++loadedReplicatedAvatars;
                        }
                    }
                }
                const double averageAvatarSimulationMs = picoAvatarSimulationSamples > 0
                    ? picoAvatarSimulationMsSum / double(picoAvatarSimulationSamples)
                    : 0.0;
                const double timingDivisor = double(std::max<quint64>(1, picoAvatarSimulationSamples));
                const QString avatarStatus = QStringLiteral("%1|%2|%3|%4|%5|%6|%7|%8|%9|%10|%11|%12|%13|%14|%15|%16|%17|%18|%19|%20")
                    .arg(QDateTime::currentSecsSinceEpoch())
                    .arg(avatarHash.size())
                    .arg(replicatedAvatars)
                    .arg(avatarManager->getReplicaCount())
                    .arg(avatarManager->getNumAvatarsUpdated())
                    .arg(avatarManager->getNumAvatarsNotUpdated())
                    .arg(avatarManager->getNumHeroAvatars())
                    .arg(averageAvatarSimulationMs, 0, 'f', 3)
                    .arg(picoAvatarProcessingMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarPriorityBuildMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarSortMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarPreUpdateMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarStatePollMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarEnsureSceneMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarScaleAnimationMsSum / timingDivisor, 0, 'f', 3)
                    .arg(picoAvatarSimulateMsSum / timingDivisor, 0, 'f', 3)
                    .arg(loadedOtherAvatars)
                    .arg(loadedReplicatedAvatars)
                    .arg(avatarManager->isLocalTestAvatarTemplateEnabled() ? 1 : 0)
                    .arg(picoLocalAvatarTemplateRefreshes);
                QSaveFile avatarStatusFile("/data/user/0/org.overte.pico/cache/avatar-status");
                if (avatarStatusFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
                    avatarStatusFile.write(avatarStatus.toUtf8());
                    avatarStatusFile.commit();
                }
                picoAvatarSimulationMsSum = 0.0;
                picoAvatarProcessingMsSum = 0.0;
                picoAvatarPriorityBuildMsSum = 0.0;
                picoAvatarSortMsSum = 0.0;
                picoAvatarPreUpdateMsSum = 0.0;
                picoAvatarStatePollMsSum = 0.0;
                picoAvatarEnsureSceneMsSum = 0.0;
                picoAvatarScaleAnimationMsSum = 0.0;
                picoAvatarSimulateMsSum = 0.0;
                picoAvatarSimulationSamples = 0;
                picoLocalAvatarTemplateRefreshes = 0;
            }
        } else {
            auto avatarManager = DependencyManager::get<AvatarManager>();
            avatarManager->setReplicaCount(0);
            avatarManager->setLocalTestAvatarTemplateEnabled(false);
        }

        char navigationValue[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.navigate", navigationValue) > 0) {
            const QString command = QString::fromUtf8(navigationValue).trimmed();
            if (!command.isEmpty() && command != lastNavigationCommand) {
                lastNavigationCommand = command;
                const qsizetype separator = command.indexOf('|');
                const QString address = separator >= 0 ? command.mid(separator + 1) : command;
#if defined(ANDROID_APP_PICO_INTERFACE)
                _picoLoadingMeasurementStartedAt = usecTimestampNow();
                _picoLoadingMeasurementEpochMs = QDateTime::currentMSecsSinceEpoch();
                _picoLoadingDomainReconnects = 0;
                _picoLoadingAwaitingInitialDomainClear = true;
#endif
                if (address.startsWith("EXPORT|")) {
                    const QStringList fields = address.split('|');
                    bool xOk { false };
                    bool yOk { false };
                    bool zOk { false };
                    bool scaleOk { false };
                    const QString filename = fields.value(1);
                    const float x = fields.value(2).toFloat(&xOk);
                    const float y = fields.value(3).toFloat(&yOk);
                    const float z = fields.value(4).toFloat(&zOk);
                    const float scale = fields.value(5).toFloat(&scaleOk);
                    if (fields.size() == 6 && !filename.isEmpty() && xOk && yOk && zOk && scaleOk && scale > 0.0f) {
                        QVariantMap options;
                        options.insert("globalPositions", true);
                        const bool exported = exportEntities(filename, x, y, z, scale, options);
                        qCInfo(interfaceapp) << "PICO_SERVERLESS_EXPORT"
                            << "success" << exported << "filename" << filename
                            << "center" << x << y << z << "scale" << scale;
                    } else {
                        qCWarning(interfaceapp) << "PICO_SERVERLESS_EXPORT invalid navigate command" << address;
                    }
                } else {
                    qCInfo(interfaceapp) << "PICO_ADB_NAVIGATE" << address;
                    addressManager->handleLookupString(address);
                }
            }
        }
    }
    // Direct, verifiable return to a known-safe world position. Re-entering a
    // domain does not guarantee that its spawn is applied when already there.
    // Format: nonce|x|y|z.
    static QString lastTeleportCommand;
    char teleportValue[PROP_VALUE_MAX] {};
    if (__system_property_get("debug.overte.teleport", teleportValue) > 0) {
        const QString command = QString::fromUtf8(teleportValue).trimmed();
        if (!command.isEmpty() && command != lastTeleportCommand) {
            lastTeleportCommand = command;
            const QStringList fields = command.split('|');
            bool xOk { false }, yOk { false }, zOk { false };
            const float x = fields.value(1).toFloat(&xOk);
            const float y = fields.value(2).toFloat(&yOk);
            const float z = fields.value(3).toFloat(&zOk);
            if (fields.size() == 4 && xOk && yOk && zOk) {
                getMyAvatar()->goToLocation(glm::vec3(x, y, z), false, glm::quat(), false, true);
                qCInfo(interfaceapp) << "PICO_ADB_TELEPORT" << glm::vec3(x, y, z);
            } else {
                qCWarning(interfaceapp) << "PICO_ADB_TELEPORT invalid command" << command;
            }
        }
    }
    // ADB-controlled locomotion for repeatable unattended performance tests.
    // Format: nonce|forward|strafe|turn|durationMs. A new nonce starts a new
    // segment; duration 0 stops playback. Values use the same -1..1 range as
    // controller axes.
    static quint64 lastAutowalkPropertyCheck { 0 };
    static QString lastAutowalkCommand;
    static quint64 autowalkUntil { 0 };
    static float autowalkForward { 0.0f };
    static float autowalkStrafe { 0.0f };
    static float autowalkTurn { 0.0f };
    if (picoUpdateStart - lastAutowalkPropertyCheck >= 250 * USECS_PER_MSEC) {
        lastAutowalkPropertyCheck = picoUpdateStart;
        char autowalkValue[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.autowalk", autowalkValue) > 0) {
            const QString command = QString::fromUtf8(autowalkValue).trimmed();
            if (!command.isEmpty() && command != lastAutowalkCommand) {
                lastAutowalkCommand = command;
                const QStringList fields = command.split('|');
                bool forwardOk { false };
                bool strafeOk { false };
                bool turnOk { false };
                bool durationOk { false };
                const float forward = fields.value(1).toFloat(&forwardOk);
                const float strafe = fields.value(2).toFloat(&strafeOk);
                const float turn = fields.value(3).toFloat(&turnOk);
                const int durationMs = fields.value(4).toInt(&durationOk);
                if (fields.size() == 5 && forwardOk && strafeOk && turnOk && durationOk) {
                    // Locomotion measurements model normal walking, not
                    // walking while operating the tablet. Closing it also
                    // lets the controller dispatcher disable both expensive
                    // hand rays until the next real UI interaction.
                    DependencyManager::get<HMDScriptingInterface>()->closeTablet();
                    autowalkForward = glm::clamp(forward, -1.0f, 1.0f);
                    autowalkStrafe = glm::clamp(strafe, -1.0f, 1.0f);
                    autowalkTurn = glm::clamp(turn, -1.0f, 1.0f);
                    autowalkUntil = durationMs > 0
                        ? picoUpdateStart + static_cast<quint64>(durationMs) * USECS_PER_MSEC
                        : 0;
                    qCInfo(interfaceapp) << "PICO_ADB_AUTOWALK"
                                         << "forward" << autowalkForward
                                         << "strafe" << autowalkStrafe
                                         << "turn" << autowalkTurn
                                         << "durationMs" << durationMs;
                } else {
                    qCWarning(interfaceapp) << "PICO_ADB_AUTOWALK invalid command" << command;
                }
            }
        }
    }
    quint64 picoAfterDevices = picoUpdateStart;
    quint64 picoAfterTestProperties = usecTimestampNow();
    quint64 picoAfterWorldLoading = picoUpdateStart;
    quint64 picoAfterLoadingHandoff = picoUpdateStart;
    quint64 picoAfterMouseCapture = picoUpdateStart;
    quint64 picoBeforeInputPlugins = picoUpdateStart;
    quint64 picoAfterInputPlugins = picoUpdateStart;
    quint64 picoAfterInputMapper = picoUpdateStart;
    quint64 picoAfterDriveKeys = picoUpdateStart;
    quint64 picoBeforePick = picoUpdateStart;
    quint64 picoAfterPick = picoUpdateStart;
    quint64 picoAfterPointer = picoUpdateStart;
    quint64 picoAfterSimulationSetup = picoUpdateStart;
    quint64 picoAfterPrePhysics = picoUpdateStart;
    quint64 picoBeforeEntityUpdate = picoUpdateStart;
    quint64 picoAfterEntityUpdate = picoUpdateStart;
    quint64 picoBeforeSimulationCleanup = picoUpdateStart;
    quint64 picoAfterSimulation = picoUpdateStart;
    quint64 picoAfterAvatars = picoUpdateStart;
    quint64 picoAfterOverlays = picoUpdateStart;
    quint64 picoBeforePostUpdate = picoUpdateStart;
    quint64 picoAfterPostLambdas = picoUpdateStart;
    quint64 picoAfterRenderArgs = picoUpdateStart;
#endif

    if (!_physicsEnabled) {
        if (!_domainLoadingInProgress) {
            PROFILE_ASYNC_BEGIN(app, "Scene Loading", "");
            _domainLoadingInProgress = true;
        }

        // we haven't yet enabled physics.  we wait until we think we have all the collision information
        // for nearby entities before starting bullet up.
        if (isServerlessMode() && !_waitForServerlessToBeSet) {
            tryToEnablePhysics();
        } else if (_failedToConnectToEntityServer) {
            if (_octreeProcessor->safeLandingIsActive()) {
                _octreeProcessor->stopSafeLanding();
            }
        } else {
            _octreeProcessor->updateSafeLanding();
            if (_octreeProcessor->safeLandingIsComplete()) {
#if defined(ANDROID_APP_PICO_INTERFACE)
                // Ignore a safe-landing completion inherited from the local
                // startup scene. The world-loading milestone starts only once
                // the new domain is connected; the authoritative physics
                // handoff below records the final collision-ready timestamp.
                if (_picoLoadingConnectedAt > 0 && _picoLoadingSafeLandingCompleteAt == 0) {
                    _picoLoadingSafeLandingCompleteAt = usecTimestampNow();
                    _picoLoadingFinalStatus = _octreeProcessor->safeLandingLoadingStatus();
                }
#endif
                tryToEnablePhysics();
            }
        }

#if defined(ANDROID_APP_PICO_INTERFACE)
        if (_graphicsEngine && isInterstitialMode()) {
            auto nodeList = DependencyManager::get<NodeList>();
            const auto& domainHandler = nodeList->getDomainHandler();
            GraphicsEngine::LoadingPhase phase = GraphicsEngine::LoadingPhase::CONNECTING;
            float progress = 0.05f;
            const quint64 loadingNow = usecTimestampNow();

            if (!domainHandler.isConnected()) {
                if (_picoLoadingConnectedAt > 0) {
                    phase = _picoLoadingLastRecovery > 0
                        ? GraphicsEngine::LoadingPhase::RECOVERING_WORLD
                        : GraphicsEngine::LoadingPhase::WAITING_FOR_WORLD;
                    progress = _picoLoadingLastRecovery > 0
                        ? _picoLoadingSequenceProgress
                        : _picoLoadingWorldProgress;
                } else {
                    _picoLoadingWorldProgress = 0.0f;
                    _picoLoadingResourceProgress = 0.0f;
                    _picoLoadingSequenceProgress = 0.0f;
                    _picoLoadingLastAdvance = loadingNow;
                    _picoLoadingWasConnected = false;
                    const auto connectionTimes = nodeList->getLastConnectionTimes();
                    if (!connectionTimes.isEmpty()) {
                        const int latestStep = static_cast<int>(connectionTimes.last());
                        const int firstStep = static_cast<int>(LimitedNodeList::ConnectionStep::LookupAddress);
                        const int connectedStep = static_cast<int>(LimitedNodeList::ConnectionStep::ReceiveDSList);
                        const float connectionProgress = glm::clamp(
                            static_cast<float>(latestStep - firstStep) / (connectedStep - firstStep), 0.0f, 1.0f);
                        progress = 0.05f + 0.13f * connectionProgress;
                    }
                }
            } else if (_failedToConnectToEntityServer) {
                phase = GraphicsEngine::LoadingPhase::WORLD_SERVER_UNAVAILABLE;
                progress = 0.0f;
            } else {
                if (_picoLoadingDomainConnectedAt == 0) {
                    _picoLoadingDomainConnectedAt = loadingNow;
                }
                const float worldProgress = glm::clamp(
                    _octreeProcessor->domainLoadingProgress(), 0.0f, 1.0f);

                const auto loadingRequests = ResourceCache::getLoadingRequests();
                const uint32_t pendingDownloads = ResourceCache::getPendingRequestCount();
                float resourceProgress = 0.0f;
                for (const auto& request : loadingRequests) {
                    resourceProgress += glm::clamp(request.first->getProgress(), 0.0f, 1.0f);
                }
                const size_t resourceCount = loadingRequests.size() + pendingDownloads;
                if (resourceCount > 0) {
                    resourceProgress /= static_cast<float>(resourceCount);
                }
                const auto statTracker = DependencyManager::get<StatTracker>();
                const int processingResources = statTracker->getStat("Processing").toInt();
                const int pendingProcessingResources = statTracker->getStat("PendingProcessing").toInt();
                const bool isDownloading = resourceCount > 0;
                const bool isProcessing = processingResources > 0 || pendingProcessingResources > 0;
                const auto safeLandingStatus = _octreeProcessor->safeLandingLoadingStatus();
                const bool isRecoveringWorldPackets = safeLandingStatus.completionReceived &&
                    safeLandingStatus.receivedSequenceCount < safeLandingStatus.expectedSequenceCount;
                const float sequenceProgress = safeLandingStatus.completionReceived
                    ? (safeLandingStatus.expectedSequenceCount > 0
                        ? static_cast<float>(safeLandingStatus.receivedSequenceCount) /
                            static_cast<float>(safeLandingStatus.expectedSequenceCount)
                        : 1.0f)
                    : 0.0f;
                if (safeLandingStatus.completionReceived && _picoLoadingSequenceCompleteAt == 0) {
                    _picoLoadingSequenceCompleteAt = loadingNow;
                }

                const bool connectionJustEstablished = !_picoLoadingWasConnected;
                const bool worldAdvanced = worldProgress > _picoLoadingWorldProgress + 0.005f;
                const bool sequenceAdvanced = sequenceProgress > _picoLoadingSequenceProgress + 0.005f;
                if (connectionJustEstablished || worldAdvanced || sequenceAdvanced) {
                    _picoLoadingLastAdvance = loadingNow;
                }
                _picoLoadingWorldProgress = glm::max(_picoLoadingWorldProgress, worldProgress);
                _picoLoadingResourceProgress = glm::max(_picoLoadingResourceProgress, resourceProgress);
                _picoLoadingSequenceProgress = glm::max(_picoLoadingSequenceProgress, sequenceProgress);
                _picoLoadingWasConnected = true;
                const bool sceneReceived =
                    _octreeProcessor->getFullSceneReceivedCounter().load() > 0;
                const bool initialWorldDataReceived = sceneReceived ||
                    safeLandingStatus.receivedSequenceCount > 0 ||
                    safeLandingStatus.maximumTrackedEntityCount > 0;
                if (initialWorldDataReceived && _picoLoadingConnectedAt == 0) {
                    _picoLoadingConnectedAt = loadingNow;
                }
                constexpr quint64 STATUS_CONFIRMATION_TIME = 1000 * USECS_PER_MSEC;
                const bool showConnectedConfirmation = initialWorldDataReceived && _picoLoadingConnectedAt > 0 &&
                    loadingNow - _picoLoadingConnectedAt < STATUS_CONFIRMATION_TIME;
                const bool showRecoveryConfirmation = _picoLoadingRecoveryAttempts == 1 &&
                    _picoLoadingLastRecovery > 0 &&
                    loadingNow - _picoLoadingLastRecovery < STATUS_CONFIRMATION_TIME;
                if (showRecoveryConfirmation) {
                    phase = GraphicsEngine::LoadingPhase::RECONNECTING_WORLD;
                    progress = 0.28f;
                } else if (showConnectedConfirmation) {
                    phase = GraphicsEngine::LoadingPhase::CONNECTED;
                    progress = 0.20f;
                } else if (!initialWorldDataReceived) {
                    phase = _picoLoadingLastRecovery > 0
                        ? GraphicsEngine::LoadingPhase::RECOVERING_WORLD
                        : GraphicsEngine::LoadingPhase::WAITING_FOR_WORLD;
                    progress = _picoLoadingLastRecovery > 0
                        ? 0.28f + 0.27f * _picoLoadingSequenceProgress
                        : 0.22f;
                } else if (isRecoveringWorldPackets) {
                    phase = GraphicsEngine::LoadingPhase::RECOVERING_WORLD;
                    progress = 0.28f + 0.27f * _picoLoadingSequenceProgress;
                } else if (!safeLandingStatus.completionReceived) {
                    phase = GraphicsEngine::LoadingPhase::RECEIVING_WORLD;
                    progress = 0.25f + 0.30f * glm::max(
                        _picoLoadingWorldProgress, _picoLoadingSequenceProgress);
                } else {
                    // Once the complete entity packet sequence is present, all remaining safe-landing work is
                    // local: models, textures, and collision shapes. Keep this umbrella phase stable instead of
                    // flickering between download and processing queues as individual requests finish and spawn.
                    phase = GraphicsEngine::LoadingPhase::PREPARING_WORLD;
                    progress = 0.55f + 0.30f * glm::max(
                        _picoLoadingWorldProgress, _picoLoadingResourceProgress);
                }

                if (_octreeProcessor->safeLandingIsComplete()) {
                    if (_picoLoadingSafeLandingCompleteAt == 0) {
                        _picoLoadingSafeLandingCompleteAt = loadingNow;
                        _picoLoadingFinalStatus = safeLandingStatus;
                    }
                    if (_picoLoadingFinalizingAt == 0) {
                        _picoLoadingFinalizingAt = loadingNow;
                    }
                    if (_picoLoadingTextureMemoryReady || _picoLoadingGpuFallbackUsed) {
                        phase = GraphicsEngine::LoadingPhase::STARTING_PHYSICS;
                        progress = 0.97f;
                    } else {
                        phase = GraphicsEngine::LoadingPhase::UPLOADING_RESOURCES;
                        const float gpuStabilityProgress = glm::clamp(
                            static_cast<float>(_gpuTextureMemSizeStabilityCount) /
                                static_cast<float>(_minimumGPUTextureMemSizeStabilityCount),
                            0.0f, 1.0f);
                        progress = 0.88f + 0.07f * gpuStabilityProgress;
                    }
                } else {
                    constexpr quint64 WORLD_PROGRESS_STALL_TIME = 5 * USECS_PER_SECOND;
                    constexpr quint64 WORLD_PROGRESS_RECOVERY_TIME = 10 * USECS_PER_SECOND;
                    const quint64 timeWithoutProgress = _picoLoadingLastAdvance > 0
                        ? loadingNow - _picoLoadingLastAdvance : 0;
                    const bool emptySceneComplete = sceneReceived &&
                        safeLandingStatus.trackedEntityCount == 0 &&
                        safeLandingStatus.maximumTrackedEntityCount == 0 &&
                        safeLandingStatus.receivedSequenceCount == 0 &&
                        !safeLandingStatus.completionReceived &&
                        !isDownloading;
                    const bool packetSequenceComplete = safeLandingStatus.completionReceived &&
                        safeLandingStatus.receivedSequenceCount == safeLandingStatus.expectedSequenceCount;
                    const bool visualAssetsBlocked = packetSequenceComplete &&
                        safeLandingStatus.trackedEntityCount > 0 &&
                        safeLandingStatus.physicsBlockedEntityCount == 0 &&
                        safeLandingStatus.visuallyBlockedEntityCount == safeLandingStatus.trackedEntityCount &&
                        !isDownloading && !isProcessing;
                    if (emptySceneComplete &&
                            timeWithoutProgress >= WORLD_PROGRESS_RECOVERY_TIME) {
                        qCWarning(interfaceapp) << "Pico world loading completed an empty scene"
                            << "after the completion packet did not arrive";
                        _octreeProcessor->finishEmptySafeLandingSequence();
                        phase = GraphicsEngine::LoadingPhase::PREPARING_WORLD;
                        progress = 0.85f;
                    } else {
                        // Only retry when the initial scene has not started at all or its completion marker proves
                        // that packet numbers are missing. Never restart for slow model, texture, or collision work.
                        // Further packet retries stay under the stable RECOVERING status and back off to 30 seconds.
                        const quint64 retryDelay = glm::min(
                            WORLD_PROGRESS_RECOVERY_TIME +
                                static_cast<quint64>(_picoLoadingRecoveryAttempts) * 10 * USECS_PER_SECOND,
                            30 * USECS_PER_SECOND);
                        const bool recoverySceneHasNoCompletion =
                            _picoLoadingRecoveryAttempts > 0 && !safeLandingStatus.completionReceived;
                        const bool shouldRetryWorldPackets =
                            (!initialWorldDataReceived || isRecoveringWorldPackets ||
                                recoverySceneHasNoCompletion ||
                                (visualAssetsBlocked && _picoLoadingRecoveryAttempts == 0)) &&
                            timeWithoutProgress >= retryDelay;
                        if (shouldRetryWorldPackets) {
                            const bool firstRecoveryAttempt = _picoLoadingRecoveryAttempts == 0;
                            phase = firstRecoveryAttempt
                                ? GraphicsEngine::LoadingPhase::RECONNECTING_WORLD
                                : GraphicsEngine::LoadingPhase::RECOVERING_WORLD;
                            progress = 0.28f + 0.27f * _picoLoadingSequenceProgress;
                            ++_picoLoadingRecoveryAttempts;
                            _picoLoadingLastRecovery = loadingNow;
                            _picoLoadingLastAdvance = loadingNow;
                            // Do not discard a partially received initial scene.  A missing completion
                            // marker is recoverable by requesting another view while retaining the
                            // packets already processed; resetting the sequence here made the UI fall
                            // back to 25% repeatedly and could release a visibly incomplete scene.
                            const bool restartIncompleteSequence = safeLandingStatus.completionReceived;
                            if (restartIncompleteSequence) {
                                _picoLoadingSequenceProgress = 0.0f;
                            }
                            qCWarning(interfaceapp) << "Pico world loading missing entity packets; requesting a fresh scene"
                                << "attempt" << _picoLoadingRecoveryAttempts
                                << "tracked" << safeLandingStatus.trackedEntityCount
                                << "maximum" << safeLandingStatus.maximumTrackedEntityCount
                                << "physics" << safeLandingStatus.physicsBlockedEntityCount
                                << "visual" << safeLandingStatus.visuallyBlockedEntityCount
                                << "sequence" << safeLandingStatus.receivedSequenceCount
                                << "/" << safeLandingStatus.expectedSequenceCount
                                << "completion" << safeLandingStatus.completionReceived;
                            if (restartIncompleteSequence) {
                                _octreeProcessor->restartSafeLandingSequence();
                            }
                            _octreeQuery.incrementConnectionID();
                            _lastQueriedViews.clear();
                            _queryExpiry = SteadyClock::now();
                        } else if (!isDownloading && !isProcessing &&
                                timeWithoutProgress >= WORLD_PROGRESS_STALL_TIME) {
                            phase = initialWorldDataReceived
                                ? GraphicsEngine::LoadingPhase::RECOVERING_WORLD
                                : GraphicsEngine::LoadingPhase::WAITING_FOR_WORLD;
                        }
                    }
                }
            }

            const int desiredPhase = static_cast<int>(phase);
            const int connectingPhase = static_cast<int>(GraphicsEngine::LoadingPhase::CONNECTING);
            const int connectedPhase = static_cast<int>(GraphicsEngine::LoadingPhase::CONNECTED);
            const int preparingPhase = static_cast<int>(GraphicsEngine::LoadingPhase::PREPARING_WORLD);
            const int uploadingPhase = static_cast<int>(GraphicsEngine::LoadingPhase::UPLOADING_RESOURCES);
            const int physicsPhase = static_cast<int>(GraphicsEngine::LoadingPhase::STARTING_PHYSICS);
            const int readyPhase = static_cast<int>(GraphicsEngine::LoadingPhase::READY);
            const int unavailablePhase = static_cast<int>(GraphicsEngine::LoadingPhase::WORLD_SERVER_UNAVAILABLE);
            const int retryingPhase = static_cast<int>(GraphicsEngine::LoadingPhase::RECONNECTING_WORLD);
            const int recoveringPhase = static_cast<int>(GraphicsEngine::LoadingPhase::RECOVERING_WORLD);
            constexpr quint64 PHASE_DEBOUNCE_TIME = 1500 * USECS_PER_MSEC;
            const bool waitingForConnection = _picoLoadingDisplayedPhase < 0 ||
                _picoLoadingDisplayedPhase == static_cast<int>(GraphicsEngine::LoadingPhase::STARTING) ||
                _picoLoadingDisplayedPhase == connectingPhase;
            const bool leavingConfirmation =
                _picoLoadingDisplayedPhase == connectedPhase || _picoLoadingDisplayedPhase == retryingPhase;
            const bool immediatePhase = (desiredPhase == connectingPhase && waitingForConnection) ||
                desiredPhase == connectedPhase || desiredPhase == preparingPhase ||
                desiredPhase == uploadingPhase || desiredPhase == physicsPhase || desiredPhase == readyPhase ||
                desiredPhase == unavailablePhase || desiredPhase == retryingPhase ||
                leavingConfirmation;
            // A transient domain connection flap must not replace a more advanced status with an
            // earlier one (for example Connected -> Connecting). Recovery and server-unavailable
            // states remain explicit exceptions so genuine failures are still visible immediately.
            const bool regressiveConnectionPhase = _picoLoadingDisplayedPhase >= 0 &&
                progress + 0.005f < _picoLoadingDisplayedProgress &&
                desiredPhase != recoveringPhase && desiredPhase != retryingPhase &&
                desiredPhase != unavailablePhase;

            if (_picoLoadingDisplayedPhase < 0 || immediatePhase) {
                if (regressiveConnectionPhase) {
                    _picoLoadingCandidatePhase = -1;
                    _picoLoadingCandidatePhaseSince = 0;
                } else {
                _picoLoadingDisplayedPhase = desiredPhase;
                _picoLoadingDisplayedProgress = glm::max(_picoLoadingDisplayedProgress, progress);
                _picoLoadingCandidatePhase = -1;
                _picoLoadingCandidatePhaseSince = 0;
                }
            } else if (desiredPhase == _picoLoadingDisplayedPhase) {
                _picoLoadingDisplayedProgress = glm::max(_picoLoadingDisplayedProgress, progress);
                _picoLoadingCandidatePhase = -1;
                _picoLoadingCandidatePhaseSince = 0;
            } else if (_picoLoadingCandidatePhase != desiredPhase) {
                _picoLoadingCandidatePhase = desiredPhase;
                _picoLoadingCandidatePhaseSince = loadingNow;
            } else if (loadingNow - _picoLoadingCandidatePhaseSince >= PHASE_DEBOUNCE_TIME) {
                _picoLoadingDisplayedPhase = desiredPhase;
                _picoLoadingDisplayedProgress = glm::max(_picoLoadingDisplayedProgress, progress);
                _picoLoadingCandidatePhase = -1;
                _picoLoadingCandidatePhaseSince = 0;
            }

            phase = static_cast<GraphicsEngine::LoadingPhase>(_picoLoadingDisplayedPhase);
            progress = _picoLoadingDisplayedProgress;
            _graphicsEngine->setLoadingState(true, phase, progress);
        }
#endif
    } else if (_domainLoadingInProgress) {
        _domainLoadingInProgress = false;
        PROFILE_ASYNC_END(app, "Scene Loading", "");
    }
#if defined(Q_OS_ANDROID)
    picoAfterWorldLoading = usecTimestampNow();
#endif

#if defined(ANDROID_APP_PICO_INTERFACE)
    // Physics activation makes the scene playable, but render-scene transactions still need a short time to
    // produce the first complete frame. Keep input locked and the opaque overlay visible while those frames are
    // presented, then show READY briefly. Hard time limits guarantee that stale counters cannot trap the user.
    if (_physicsEnabled && isInterstitialMode() && _graphicsEngine) {
        const quint64 handoffNow = usecTimestampNow();
        const auto displayPlugin = getActiveDisplayPlugin();
        const uint32_t presentFrame = displayPlugin ? displayPlugin->presentCount() : 0;
        if (_picoLoadingPhysicsEnabledAt == 0) {
            // Safe Landing is reset as part of enabling physics. Preserve a
            // deterministic handoff even if a domain transition reset the
            // Pico-only timestamp during that same update.
            _picoLoadingPhysicsEnabledAt = handoffNow;
            _picoLoadingPhysicsPresentFrame = presentFrame;
        }
        if (_picoLoadingReadyAt == 0) {
            _graphicsEngine->setLoadingState(true, GraphicsEngine::LoadingPhase::FINALIZING_SCENE, 0.98f);
            // Keep the final handoff short on Pico 4. Physics is already
            // enabled here and the presented-frame gate below still prevents
            // exposing an incomplete render scene.
            constexpr quint64 SCENE_SETTLE_TIME = 1000 * USECS_PER_MSEC;
            constexpr quint64 SCENE_SETTLE_TIMEOUT = 2 * USECS_PER_SECOND;
            constexpr uint32_t SCENE_SETTLE_PRESENT_FRAMES = 30;
            const quint64 sceneSettleElapsed = handoffNow - _picoLoadingPhysicsEnabledAt;
            const bool sceneFramesPresented = displayPlugin &&
                presentFrame >= _picoLoadingPhysicsPresentFrame + SCENE_SETTLE_PRESENT_FRAMES;
            if ((sceneSettleElapsed >= SCENE_SETTLE_TIME && sceneFramesPresented) ||
                    sceneSettleElapsed >= SCENE_SETTLE_TIMEOUT) {
                _picoLoadingReadyAt = handoffNow;
                _picoLoadingReadyPresentFrame = presentFrame;
                _graphicsEngine->setLoadingState(true, GraphicsEngine::LoadingPhase::READY, 1.0f);
            }
        } else {
            _graphicsEngine->setLoadingState(true, GraphicsEngine::LoadingPhase::READY, 1.0f);
            constexpr quint64 READY_DISPLAY_TIME = 100 * USECS_PER_MSEC;
            constexpr quint64 READY_DISPLAY_TIMEOUT = 500 * USECS_PER_MSEC;
            constexpr uint32_t READY_PRESENT_FRAMES = 3;
            const quint64 readyElapsed = handoffNow - _picoLoadingReadyAt;
            const bool readyFramesPresented = displayPlugin &&
                presentFrame >= _picoLoadingReadyPresentFrame + READY_PRESENT_FRAMES;
            if ((readyElapsed >= READY_DISPLAY_TIME && readyFramesPresented) ||
                    readyElapsed >= READY_DISPLAY_TIMEOUT) {
                const quint64 releasedAt = usecTimestampNow();
                const auto elapsedMs = [this](quint64 milestone) -> qint64 {
                    return milestone > 0 && _picoLoadingMeasurementStartedAt > 0
                        ? static_cast<qint64>((milestone - _picoLoadingMeasurementStartedAt) / USECS_PER_MSEC)
                        : -1;
                };
                const QString loadingStatus = QStringLiteral(
                    "%1|%2|%3|%4|%5|%6|%7|%8|%9|%10|%11|%12|%13|%14|%15|%16|%17")
                    .arg(_picoLoadingMeasurementEpochMs)
                    .arg(elapsedMs(_picoLoadingDomainConnectedAt))
                    .arg(elapsedMs(_picoLoadingConnectedAt))
                    .arg(elapsedMs(_picoLoadingSequenceCompleteAt))
                    .arg(elapsedMs(_picoLoadingSafeLandingCompleteAt))
                    .arg(elapsedMs(_picoLoadingGpuReadyAt))
                    .arg(elapsedMs(_picoLoadingPhysicsEnabledAt))
                    .arg(elapsedMs(_picoLoadingReadyAt))
                    .arg(elapsedMs(releasedAt))
                    .arg(_picoLoadingFinalStatus.maximumTrackedEntityCount)
                    .arg(_picoLoadingFinalStatus.receivedSequenceCount)
                    .arg(_picoLoadingFinalStatus.expectedSequenceCount)
                    .arg(_picoLoadingRecoveryAttempts)
                    .arg(_picoLoadingGpuFallbackUsed ? 1 : 0)
                    .arg(presentFrame - _picoLoadingPhysicsPresentFrame)
                    .arg(_picoLoadingDismissedByUser ? 1 : 0)
                    .arg(_picoLoadingDomainReconnects);
                QSaveFile loadingStatusFile("/data/user/0/org.overte.pico/cache/world-loading-status");
                if (loadingStatusFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
                    loadingStatusFile.write(loadingStatus.toUtf8());
                    loadingStatusFile.commit();
                }
                qCInfo(interfaceapp) << "Pico world ready; releasing loading screen"
                    << "presentedFrames"
                    << (presentFrame - _picoLoadingPhysicsPresentFrame);
                setIsInterstitialMode(false);
            }
        }
    }
#endif
#if defined(Q_OS_ANDROID)
    picoAfterLoadingHandoff = usecTimestampNow();
#endif

     if (shouldCaptureMouse()) {
        QPoint point = _primaryWidget->mapToGlobal(_primaryWidget->geometry().center());
        if (QCursor::pos() != point) {
            _mouseCaptureTarget = point;
            _ignoreMouseMove = true;
            if (_captureMouse) {
                _keyboardMouseDevice->updateMousePositionForCapture(QCursor::pos(), _mouseCaptureTarget);
            }
            QCursor::setPos(point);
        }
    }

    auto myAvatar = getMyAvatar();
#if defined(Q_OS_ANDROID)
    picoAfterMouseCapture = usecTimestampNow();
    picoBeforeInputPlugins = usecTimestampNow();
#endif
    {
        PerformanceTimer perfTimer("devices");
        auto userInputMapper = DependencyManager::get<UserInputMapper>();

        controller::HmdAvatarAlignmentType hmdAvatarAlignmentType;
        if (myAvatar->getHmdAvatarAlignmentType() == "eyes") {
            hmdAvatarAlignmentType = controller::HmdAvatarAlignmentType::Eyes;
        } else {
            hmdAvatarAlignmentType = controller::HmdAvatarAlignmentType::Head;
        }

        controller::InputCalibrationData calibrationData = {
            myAvatar->getSensorToWorldMatrix(),
            createMatFromQuatAndPos(myAvatar->getWorldOrientation(), myAvatar->getWorldPosition()),
            myAvatar->getHMDSensorMatrix(),
            myAvatar->getCenterEyeCalibrationMat(),
            myAvatar->getHeadCalibrationMat(),
            myAvatar->getSpine2CalibrationMat(),
            myAvatar->getHipsCalibrationMat(),
            myAvatar->getLeftFootCalibrationMat(),
            myAvatar->getRightFootCalibrationMat(),
            myAvatar->getRightArmCalibrationMat(),
            myAvatar->getLeftArmCalibrationMat(),
            myAvatar->getRightHandCalibrationMat(),
            myAvatar->getLeftHandCalibrationMat(),
            hmdAvatarAlignmentType
        };

        InputPluginPointer keyboardMousePlugin;
        for(const auto& inputPlugin : PluginManager::getInstance()->getInputPlugins()) {
            if (inputPlugin->getName() == KeyboardMouseDevice::NAME) {
                keyboardMousePlugin = inputPlugin;
            } else if (inputPlugin->isActive()) {
                inputPlugin->pluginUpdate(deltaTime, calibrationData);
            }
        }
#if defined(Q_OS_ANDROID)
        picoAfterInputPlugins = usecTimestampNow();
#endif

        userInputMapper->setInputCalibrationData(calibrationData);
        userInputMapper->update(deltaTime);
#if defined(ANDROID_APP_PICO_INTERFACE)
        // Keep an emergency escape hatch available while the loading interstitial captures normal input.
        // OpenXR exposes the controller face buttons through the public standard X channel.
        const auto standardDevice = userInputMapper->getStandardDevice();
        const bool dismissLoadingPressed = standardDevice &&
            standardDevice->getButton(controller::X) > 0.5f;
        if (dismissLoadingPressed && !_picoLoadingDismissButtonWasPressed && isInterstitialMode()) {
            _picoLoadingDismissedByUser = true;
            qCInfo(interfaceapp) << "Pico loading screen dismissed by controller X button";
            setIsInterstitialMode(false);
        }
        _picoLoadingDismissButtonWasPressed = dismissLoadingPressed;
#endif
#if defined(Q_OS_ANDROID)
        picoAfterInputMapper = usecTimestampNow();
#endif

#if defined(ANDROID_APP_PICO_INTERFACE) && !defined(NDEBUG)
        {
            static quint64 nextPicoLocomotionLog { 0 };
            const quint64 now = usecTimestampNow();
            if (now >= nextPicoLocomotionLog) {
                nextPicoLocomotionLog = now + USECS_PER_SECOND;
                qInfo() << "PICO_LOCOMOTION"
                        << "translateX" << userInputMapper->getActionState(controller::Action::TRANSLATE_X)
                        << "translateY" << userInputMapper->getActionState(controller::Action::TRANSLATE_Y)
                        << "translateZ" << userInputMapper->getActionState(controller::Action::TRANSLATE_Z)
                        << "yaw" << userInputMapper->getActionState(controller::Action::YAW)
                        << "actionsCaptured" << _controllerScriptingInterface->areActionsCaptured()
                        << "interstitial" << isInterstitialMode()
                        << "cameraMode" << static_cast<int>(_myCamera.getMode());
            }
        }
#endif

        if (keyboardMousePlugin && keyboardMousePlugin->isActive()) {
            keyboardMousePlugin->pluginUpdate(deltaTime, calibrationData);
        }
        // Transfer the user inputs to the driveKeys
        // FIXME can we drop drive keys and just have the avatar read the action states directly?
        myAvatar->clearDriveKeys();
        if (_myCamera.getMode() != CAMERA_MODE_INDEPENDENT && !isInterstitialMode()) {
            if (!_controllerScriptingInterface->areActionsCaptured() && _myCamera.getMode() != CAMERA_MODE_MIRROR) {
                myAvatar->setDriveKey(MyAvatar::TRANSLATE_Z, -1.0f * userInputMapper->getActionState(controller::Action::TRANSLATE_Z));
                myAvatar->setDriveKey(MyAvatar::TRANSLATE_Y, userInputMapper->getActionState(controller::Action::TRANSLATE_Y));
                myAvatar->setDriveKey(MyAvatar::TRANSLATE_X, userInputMapper->getActionState(controller::Action::TRANSLATE_X));
                if (deltaTime > FLT_EPSILON && userInputMapper->getActionState(controller::Action::TRANSLATE_CAMERA_Z)  == 0.0f) {
                    myAvatar->setDriveKey(MyAvatar::PITCH, -1.0f * userInputMapper->getActionState(controller::Action::PITCH));
                    myAvatar->setDriveKey(MyAvatar::YAW, -1.0f * userInputMapper->getActionState(controller::Action::YAW));
                    myAvatar->setDriveKey(MyAvatar::DELTA_PITCH, -_myCamera.getSensitivity() * userInputMapper->getActionState(controller::Action::DELTA_PITCH));
                    myAvatar->setDriveKey(MyAvatar::DELTA_YAW, -_myCamera.getSensitivity() * userInputMapper->getActionState(controller::Action::DELTA_YAW));
                    myAvatar->setDriveKey(MyAvatar::STEP_YAW, -1.0f * userInputMapper->getActionState(controller::Action::STEP_YAW));
                }
            }
            myAvatar->setDriveKey(MyAvatar::ZOOM, userInputMapper->getActionState(controller::Action::TRANSLATE_CAMERA_Z));
#if defined(Q_OS_ANDROID)
            if (picoUpdateStart < autowalkUntil) {
                myAvatar->setDriveKey(MyAvatar::TRANSLATE_Z, autowalkForward);
                myAvatar->setDriveKey(MyAvatar::TRANSLATE_X, autowalkStrafe);
                myAvatar->setDriveKey(MyAvatar::YAW, autowalkTurn);
#if !defined(NDEBUG)
                static quint64 nextAutowalkLog { 0 };
                if (picoUpdateStart >= nextAutowalkLog) {
                    nextAutowalkLog = picoUpdateStart + USECS_PER_SECOND;
                    qInfo() << "PICO_ADB_AUTOWALK_ACTIVE"
                            << "position" << myAvatar->getWorldPosition()
                            << "forward" << autowalkForward
                            << "strafe" << autowalkStrafe
                            << "turn" << autowalkTurn
                            << "remainingMs" << (autowalkUntil - picoUpdateStart) / USECS_PER_MSEC;
                }
#endif
            }
#endif
        }

        myAvatar->setSprintMode((bool)userInputMapper->getActionState(controller::Action::SPRINT));
#if defined(Q_OS_ANDROID)
        picoAfterDriveKeys = usecTimestampNow();
#endif
        static const std::vector<controller::Action> avatarControllerActions = {
            controller::Action::LEFT_HAND,
            controller::Action::RIGHT_HAND,
#if defined(ANDROID_APP_PICO_INTERFACE)
            // Pico OpenXR currently supplies head and controller poses here,
            // not desktop full-body, eye, or per-finger tracking. Avoid dozens
            // of mapper lookups and invalid pose writes on every world update.
            controller::Action::HEAD
#else
            controller::Action::LEFT_FOOT,
            controller::Action::RIGHT_FOOT,
            controller::Action::HIPS,
            controller::Action::SPINE2,
            controller::Action::HEAD,
            controller::Action::LEFT_HAND_THUMB1,
            controller::Action::LEFT_HAND_THUMB2,
            controller::Action::LEFT_HAND_THUMB3,
            controller::Action::LEFT_HAND_THUMB4,
            controller::Action::LEFT_HAND_INDEX1,
            controller::Action::LEFT_HAND_INDEX2,
            controller::Action::LEFT_HAND_INDEX3,
            controller::Action::LEFT_HAND_INDEX4,
            controller::Action::LEFT_HAND_MIDDLE1,
            controller::Action::LEFT_HAND_MIDDLE2,
            controller::Action::LEFT_HAND_MIDDLE3,
            controller::Action::LEFT_HAND_MIDDLE4,
            controller::Action::LEFT_HAND_RING1,
            controller::Action::LEFT_HAND_RING2,
            controller::Action::LEFT_HAND_RING3,
            controller::Action::LEFT_HAND_RING4,
            controller::Action::LEFT_HAND_PINKY1,
            controller::Action::LEFT_HAND_PINKY2,
            controller::Action::LEFT_HAND_PINKY3,
            controller::Action::LEFT_HAND_PINKY4,
            controller::Action::RIGHT_HAND_THUMB1,
            controller::Action::RIGHT_HAND_THUMB2,
            controller::Action::RIGHT_HAND_THUMB3,
            controller::Action::RIGHT_HAND_THUMB4,
            controller::Action::RIGHT_HAND_INDEX1,
            controller::Action::RIGHT_HAND_INDEX2,
            controller::Action::RIGHT_HAND_INDEX3,
            controller::Action::RIGHT_HAND_INDEX4,
            controller::Action::RIGHT_HAND_MIDDLE1,
            controller::Action::RIGHT_HAND_MIDDLE2,
            controller::Action::RIGHT_HAND_MIDDLE3,
            controller::Action::RIGHT_HAND_MIDDLE4,
            controller::Action::RIGHT_HAND_RING1,
            controller::Action::RIGHT_HAND_RING2,
            controller::Action::RIGHT_HAND_RING3,
            controller::Action::RIGHT_HAND_RING4,
            controller::Action::RIGHT_HAND_PINKY1,
            controller::Action::RIGHT_HAND_PINKY2,
            controller::Action::RIGHT_HAND_PINKY3,
            controller::Action::RIGHT_HAND_PINKY4,
            controller::Action::LEFT_ARM,
            controller::Action::RIGHT_ARM,
            controller::Action::LEFT_SHOULDER,
            controller::Action::RIGHT_SHOULDER,
            controller::Action::LEFT_FORE_ARM,
            controller::Action::RIGHT_FORE_ARM,
            controller::Action::LEFT_LEG,
            controller::Action::RIGHT_LEG,
            controller::Action::LEFT_UP_LEG,
            controller::Action::RIGHT_UP_LEG,
            controller::Action::LEFT_TOE_BASE,
            controller::Action::RIGHT_TOE_BASE,
            controller::Action::LEFT_EYE,
            controller::Action::RIGHT_EYE
#endif

        };

        // copy controller poses from userInputMapper to myAvatar.
        glm::mat4 myAvatarMatrix = createMatFromQuatAndPos(myAvatar->getWorldOrientation(), myAvatar->getWorldPosition());
        glm::mat4 worldToSensorMatrix = glm::inverse(myAvatar->getSensorToWorldMatrix());
        glm::mat4 avatarToSensorMatrix = worldToSensorMatrix * myAvatarMatrix;
        for (auto& action : avatarControllerActions) {
            controller::Pose pose = userInputMapper->getPoseState(action);
            myAvatar->setControllerPoseInSensorFrame(action, pose.transform(avatarToSensorMatrix));
        }

        static const std::vector<QString> trackedObjectStringLiterals = {
            QStringLiteral("_TrackedObject00"), QStringLiteral("_TrackedObject01"), QStringLiteral("_TrackedObject02"), QStringLiteral("_TrackedObject03"),
            QStringLiteral("_TrackedObject04"), QStringLiteral("_TrackedObject05"), QStringLiteral("_TrackedObject06"), QStringLiteral("_TrackedObject07"),
            QStringLiteral("_TrackedObject08"), QStringLiteral("_TrackedObject09"), QStringLiteral("_TrackedObject10"), QStringLiteral("_TrackedObject11"),
            QStringLiteral("_TrackedObject12"), QStringLiteral("_TrackedObject13"), QStringLiteral("_TrackedObject14"), QStringLiteral("_TrackedObject15")
        };

        // Controlled by the Developer > Avatar > Show Tracked Objects menu.
        if (_showTrackedObjects) {
            static const std::vector<controller::Action> trackedObjectActions = {
                controller::Action::TRACKED_OBJECT_00, controller::Action::TRACKED_OBJECT_01, controller::Action::TRACKED_OBJECT_02, controller::Action::TRACKED_OBJECT_03,
                controller::Action::TRACKED_OBJECT_04, controller::Action::TRACKED_OBJECT_05, controller::Action::TRACKED_OBJECT_06, controller::Action::TRACKED_OBJECT_07,
                controller::Action::TRACKED_OBJECT_08, controller::Action::TRACKED_OBJECT_09, controller::Action::TRACKED_OBJECT_10, controller::Action::TRACKED_OBJECT_11,
                controller::Action::TRACKED_OBJECT_12, controller::Action::TRACKED_OBJECT_13, controller::Action::TRACKED_OBJECT_14, controller::Action::TRACKED_OBJECT_15
            };

            int i = 0;
            glm::vec4 BLUE(0.0f, 0.0f, 1.0f, 1.0f);
            for (auto& action : trackedObjectActions) {
                controller::Pose pose = userInputMapper->getPoseState(action);
                if (pose.valid) {
                    glm::vec3 pos = transformPoint(myAvatarMatrix, pose.translation);
                    glm::quat rot = glmExtractRotation(myAvatarMatrix) * pose.rotation;
                    DebugDraw::getInstance().addMarker(trackedObjectStringLiterals[i], rot, pos, BLUE);
                } else {
                    DebugDraw::getInstance().removeMarker(trackedObjectStringLiterals[i]);
                }
                i++;
            }
        } else if (_prevShowTrackedObjects) {
            for (auto& key : trackedObjectStringLiterals) {
                DebugDraw::getInstance().removeMarker(key);
            }
        }
        _prevShowTrackedObjects = _showTrackedObjects;
    }
#if defined(Q_OS_ANDROID)
    picoAfterDevices = usecTimestampNow();
#endif

    updateThreads(deltaTime); // If running non-threaded, then give the threads some time to process...
    updateDialogs(deltaTime); // update various stats dialogs if present

    auto grabManager = DependencyManager::get<GrabManager>();
    grabManager->simulateGrabs();
#if defined(Q_OS_ANDROID)
    picoBeforePick = usecTimestampNow();
#endif

    // TODO: break these out into distinct perfTimers when they prove interesting
    {
        PROFILE_RANGE(app, "PickManager");
        PerformanceTimer perfTimer("pickManager");
        DependencyManager::get<PickManager>()->update();
    }
#if defined(Q_OS_ANDROID)
    picoAfterPick = usecTimestampNow();
#endif

    {
        PROFILE_RANGE(app, "PointerManager");
        PerformanceTimer perfTimer("pointerManager");
        DependencyManager::get<PointerManager>()->update();
    }
#if defined(Q_OS_ANDROID)
    picoAfterPointer = usecTimestampNow();
#endif

    QSharedPointer<AvatarManager> avatarManager = DependencyManager::get<AvatarManager>();

    {
        PROFILE_RANGE(simulation_physics, "Simulation");
        PerformanceTimer perfTimer("simulation");

        getEntities()->preUpdate();
        _entitySimulation->removeDeadEntities();
#if defined(Q_OS_ANDROID)
        picoAfterSimulationSetup = usecTimestampNow();
#endif

        auto t0 = std::chrono::high_resolution_clock::now();
        auto t1 = t0;
        {
            PROFILE_RANGE(simulation_physics, "PrePhysics");
            PerformanceTimer perfTimer("prePhysics)");
            {
                PROFILE_RANGE(simulation_physics, "Entities");
                PhysicsEngine::Transaction transaction;
                _entitySimulation->buildPhysicsTransaction(transaction);
                _physicsEngine->processTransaction(transaction);
                _entitySimulation->handleProcessedPhysicsTransaction(transaction);
            }

            t1 = std::chrono::high_resolution_clock::now();

            {
                PROFILE_RANGE(simulation_physics, "Avatars");
                PhysicsEngine::Transaction transaction;
                avatarManager->buildPhysicsTransaction(transaction);
                _physicsEngine->processTransaction(transaction);
                avatarManager->handleProcessedPhysicsTransaction(transaction);

                myAvatar->prepareForPhysicsSimulation();
                myAvatar->getCharacterController()->preSimulation();
            }
        }
#if defined(Q_OS_ANDROID)
        picoAfterPrePhysics = usecTimestampNow();
        picoBeforeEntityUpdate = picoAfterPrePhysics;
        picoAfterEntityUpdate = picoAfterPrePhysics;
#endif

        if (_physicsEnabled) {
            {
                PROFILE_RANGE(simulation_physics, "PrepareActions");
                _entitySimulation->applyDynamicChanges();
                _physicsEngine->forEachDynamic([&](EntityDynamicPointer dynamic) {
                    dynamic->prepareForPhysicsSimulation();
                });
            }
            auto t2 = std::chrono::high_resolution_clock::now();
            {
                PROFILE_RANGE(simulation_physics, "StepPhysics");
                PerformanceTimer perfTimer("stepPhysics");
                getEntities()->getTree()->withWriteLock([&] {
                    _physicsEngine->stepSimulation();
                });
            }
            auto t3 = std::chrono::high_resolution_clock::now();
            {
                if (_physicsEngine->hasOutgoingChanges()) {
                    {
                        PROFILE_RANGE(simulation_physics, "PostPhysics");
                        PerformanceTimer perfTimer("postPhysics");
                        // grab the collision events BEFORE handleChangedMotionStates() because at this point
                        // we have a better idea of which objects we own or should own.
                        auto& collisionEvents = _physicsEngine->getCollisionEvents();

                        getEntities()->getTree()->withWriteLock([&] {
                            PROFILE_RANGE(simulation_physics, "HandleChanges");
                            PerformanceTimer perfTimer("handleChanges");

                            const VectorOfMotionStates& outgoingChanges = _physicsEngine->getChangedMotionStates();
                            _entitySimulation->handleChangedMotionStates(outgoingChanges);
                            avatarManager->handleChangedMotionStates(outgoingChanges);

                            const VectorOfMotionStates& deactivations = _physicsEngine->getDeactivatedMotionStates();
                            _entitySimulation->handleDeactivatedMotionStates(deactivations);
                        });

                        // handleCollisionEvents() AFTER handleChangedMotionStates()
                        {
                            PROFILE_RANGE(simulation_physics, "CollisionEvents");
                            avatarManager->handleCollisionEvents(collisionEvents);
                            // Collision events (and their scripts) must not be handled when we're locked, above. (That would risk
                            // deadlock.)
                            _entitySimulation->handleCollisionEvents(collisionEvents);
                        }

                        {
                            PROFILE_RANGE(simulation_physics, "MyAvatar");
                            myAvatar->getCharacterController()->postSimulation();
                            myAvatar->harvestResultsFromPhysicsSimulation(deltaTime);
                        }

                        if (PerformanceTimer::isActive() &&
                                Menu::getInstance()->isOptionChecked(MenuOption::DisplayDebugTimingDetails) &&
                                Menu::getInstance()->isOptionChecked(MenuOption::ExpandPhysicsTiming)) {
                            _physicsEngine->harvestPerformanceStats();
                        }
                        // NOTE: the PhysicsEngine stats are written to stdout NOT to Qt log framework
                        _physicsEngine->dumpStatsIfNecessary();
                    }
                    auto t4 = std::chrono::high_resolution_clock::now();

                    // NOTE: the getEntities()->update() call below will wait for lock
                    // and will provide non-physical entity motion
#if defined(Q_OS_ANDROID)
                    picoBeforeEntityUpdate = usecTimestampNow();
#endif
                    getEntities()->update(true); // update the models...
#if defined(Q_OS_ANDROID)
                    picoAfterEntityUpdate = usecTimestampNow();
#endif

                    auto t5 = std::chrono::high_resolution_clock::now();

                    workload::Timings timings(6);
                    timings[0] = t1 - t0; // prePhysics entities
                    timings[1] = t2 - t1; // prePhysics avatars
                    timings[2] = t3 - t2; // stepPhysics
                    timings[3] = t4 - t3; // postPhysics
                    timings[4] = t5 - t4; // non-physical kinematics
                    timings[5] = workload::Timing_ns((int32_t)(NSECS_PER_SECOND * deltaTime)); // game loop duration
                    _gameWorkload.updateSimulationTimings(timings);
                }
            }
        } else {
            // update the rendering without any simulation
#if defined(Q_OS_ANDROID)
            picoBeforeEntityUpdate = usecTimestampNow();
#endif
            getEntities()->update(false);
#if defined(Q_OS_ANDROID)
            picoAfterEntityUpdate = usecTimestampNow();
#endif
        }
#if defined(Q_OS_ANDROID)
        picoBeforeSimulationCleanup = usecTimestampNow();
#endif
        // remove recently dead avatarEntities
        SetOfEntities deadAvatarEntities;
        _entitySimulation->takeDeadAvatarEntities(deadAvatarEntities);
        avatarManager->removeDeadAvatarEntities(deadAvatarEntities);
    }
#if defined(Q_OS_ANDROID)
    picoAfterSimulation = usecTimestampNow();
#endif

    // AvatarManager update
    {
        {
            PROFILE_RANGE(simulation, "OtherAvatars");
            PerformanceTimer perfTimer("otherAvatars");
#if defined(Q_OS_ANDROID)
            if (picoTestMode && avatarManager->refreshLocalTestAvatarTemplate()) {
                ++picoLocalAvatarTemplateRefreshes;
            }
            avatarManager->updateOtherAvatars(deltaTime, picoTestMode);
            if (picoTestMode) {
                picoAvatarSimulationMsSum += avatarManager->size() > 1
                    ? avatarManager->getAvatarSimulationTime()
                    : 0.0;
                picoAvatarProcessingMsSum += avatarManager->getAvatarProcessingTime();
                picoAvatarPriorityBuildMsSum += avatarManager->getAvatarPriorityBuildTime();
                picoAvatarSortMsSum += avatarManager->getAvatarSortTime();
                picoAvatarPreUpdateMsSum += avatarManager->getAvatarPreUpdateTime();
                picoAvatarStatePollMsSum += avatarManager->getAvatarStatePollTime();
                picoAvatarEnsureSceneMsSum += avatarManager->getAvatarEnsureSceneTime();
                picoAvatarScaleAnimationMsSum += avatarManager->getAvatarScaleAnimationTime();
                picoAvatarSimulateMsSum += avatarManager->getAvatarSimulateTime();
                ++picoAvatarSimulationSamples;
            }
#else
            avatarManager->updateOtherAvatars(deltaTime);
#endif
        }

        {
            PROFILE_RANGE(simulation, "MyAvatar");
            PerformanceTimer perfTimer("MyAvatar");
            qApp->updateMyAvatarLookAtPosition(deltaTime);
            avatarManager->updateMyAvatar(deltaTime);
        }
    }
#if defined(Q_OS_ANDROID)
    picoAfterAvatars = usecTimestampNow();
#endif

    bool showWarnings = Menu::getInstance()->isOptionChecked(MenuOption::PipelineWarnings);
    PerformanceWarning warn(showWarnings, "Application::update()");

    updateLOD(deltaTime);

    if (!_loginDialogID.isNull()) {
        _loginStateManager.update(getMyAvatar()->getDominantHand(), _loginDialogID);
        updateLoginDialogPosition();
    }

    {
        PROFILE_RANGE_EX(app, "Overlays", 0xffff0000, (uint64_t)getActiveDisplayPlugin()->presentCount());
        PerformanceTimer perfTimer("overlays");
        _overlays.update(deltaTime);
    }
#if defined(Q_OS_ANDROID)
    picoAfterOverlays = usecTimestampNow();
#endif

    // Update _viewFrustum with latest camera and view frustum data...
    // NOTE: we get this from the view frustum, to make it simpler, since the
    // loadViewFrumstum() method will get the correct details from the camera
    // We could optimize this to not actually load the viewFrustum, since we don't
    // actually need to calculate the view frustum planes to send these details
    // to the server.
    {
        QMutexLocker viewLocker(&_viewMutex);
        _myCamera.loadViewFrustum(_viewFrustum);

        _conicalViews.clear();
        _conicalViews.push_back(_viewFrustum);
        // TODO: Fix this by modeling the way the secondary camera works on how the main camera works
        // ie. Use a camera object stored in the game logic and informs the Engine on where the secondary
        // camera should be.
        updateSecondaryCameraViewFrustum();
    }

    quint64 now = usecTimestampNow();

    // Update my voxel servers with my current voxel query...
    {
        PROFILE_RANGE_EX(app, "QueryOctree", 0xffff0000, (uint64_t)getActiveDisplayPlugin()->presentCount());
        PerformanceTimer perfTimer("queryOctree");
        QMutexLocker viewLocker(&_viewMutex);

        bool viewIsDifferentEnough = false;
        if (_conicalViews.size() == _lastQueriedViews.size()) {
            for (size_t i = 0; i < _conicalViews.size(); ++i) {
                if (!_conicalViews[i].isVerySimilar(_lastQueriedViews[i])) {
                    viewIsDifferentEnough = true;
                    break;
                }
            }
        } else {
            viewIsDifferentEnough = true;
        }


        // if it's been a while since our last query or the view has significantly changed then send a query, otherwise suppress it
        static const std::chrono::seconds MIN_PERIOD_BETWEEN_QUERIES { 3 };
        auto now = SteadyClock::now();
        if (now > _queryExpiry || viewIsDifferentEnough) {
            if (DependencyManager::get<SceneScriptingInterface>()->shouldRenderEntities()) {
                queryOctree(NodeType::EntityServer, PacketType::EntityQuery);
            }
            queryAvatars();

            _lastQueriedViews = _conicalViews;
            _queryExpiry = now + MIN_PERIOD_BETWEEN_QUERIES;
        }
    }

    // sent nack packets containing missing sequence numbers of received packets from nodes
    {
        quint64 sinceLastNack = now - _lastNackTime;
        const quint64 TOO_LONG_SINCE_LAST_NACK = 1 * USECS_PER_SECOND;
        if (sinceLastNack > TOO_LONG_SINCE_LAST_NACK) {
            _lastNackTime = now;
            sendNackPackets();
        }
    }

    // send packet containing downstream audio stats to the AudioMixer
    {
        quint64 sinceLastNack = now - _lastSendDownstreamAudioStats;
        if (sinceLastNack > TOO_LONG_SINCE_LAST_SEND_DOWNSTREAM_AUDIO_STATS && !isInterstitialMode()) {
            _lastSendDownstreamAudioStats = now;

            QMetaObject::invokeMethod(DependencyManager::get<AudioClient>().data(), "sendDownstreamAudioStatsPacket", Qt::QueuedConnection);
        }
    }
#if defined(Q_OS_ANDROID)
    picoBeforePostUpdate = usecTimestampNow();
#endif

    {
        PerformanceTimer perfTimer("avatarManager/postUpdate");
        avatarManager->postUpdate(deltaTime, getMain3DScene());
    }

    {
        PROFILE_RANGE_EX(app, "PostUpdateLambdas", 0xffff0000, (uint64_t)0);
        PerformanceTimer perfTimer("postUpdateLambdas");
        std::unique_lock<std::mutex> guard(_postUpdateLambdasLock);
        for (auto& iter : _postUpdateLambdas) {
            iter.second();
        }
        _postUpdateLambdas.clear();
    }
#if defined(Q_OS_ANDROID)
    picoAfterPostLambdas = usecTimestampNow();
#endif


    updateRenderArgs(deltaTime);
#if defined(Q_OS_ANDROID)
    picoAfterRenderArgs = usecTimestampNow();
#endif

    {
        PerformanceTimer perfTimer("AnimDebugDraw");
        AnimDebugDraw::getInstance().update();
    }

    { // Game loop is done, mark the end of the frame for the scene transactions and the render loop to take over
        PerformanceTimer perfTimer("enqueueFrame");
        getMain3DScene()->enqueueFrame();
    }

    // If the display plugin is inactive then the frames won't be processed so process them here.
    if (!getActiveDisplayPlugin()->isActive()) {
        getMain3DScene()->processTransactionQueue();
    }

    // decide if the sensorToWorldMatrix is changing in a way that warrents squeezing the edges of the view down
    if (getActiveDisplayPlugin()->isHmd()) {
        PerformanceTimer perfTimer("squeezeVision");
        _visionSqueeze.updateVisionSqueeze(myAvatar->getSensorToWorldMatrix(), deltaTime);
    }
#if defined(Q_OS_ANDROID)
    struct PicoUpdateStats {
        quint64 windowStart { 0 };
        quint64 calls { 0 };
        quint64 total { 0 };
        quint64 devices { 0 };
        quint64 testProperties { 0 };
        quint64 worldLoading { 0 };
        quint64 loadingHandoff { 0 };
        quint64 mouseCapture { 0 };
        quint64 devicesPrefix { 0 };
        quint64 inputPlugins { 0 };
        quint64 inputMapper { 0 };
        quint64 driveKeys { 0 };
        quint64 controllerPoses { 0 };
        quint64 prePick { 0 };
        quint64 pick { 0 };
        quint64 pointer { 0 };
        quint64 simulationSetup { 0 };
        quint64 prePhysics { 0 };
        quint64 physics { 0 };
        quint64 entityUpdate { 0 };
        quint64 afterEntityUpdate { 0 };
        quint64 simulationCleanup { 0 };
        quint64 avatars { 0 };
        quint64 overlaysAndView { 0 };
        quint64 postUpdate { 0 };
        quint64 postLambdas { 0 };
        quint64 renderArgs { 0 };
        quint64 frameEnd { 0 };
        quint64 maximum { 0 };
    };
    static PicoUpdateStats stats;
    const quint64 end = usecTimestampNow();
    if (stats.windowStart == 0) {
        stats.windowStart = picoUpdateStart;
    }
    const quint64 total = end - picoUpdateStart;
    stats.calls++;
    stats.total += total;
    stats.devices += picoAfterDevices - picoUpdateStart;
    stats.testProperties += picoAfterTestProperties - picoUpdateStart;
    stats.worldLoading += picoAfterWorldLoading - picoAfterTestProperties;
    stats.loadingHandoff += picoAfterLoadingHandoff - picoAfterWorldLoading;
    stats.mouseCapture += picoAfterMouseCapture - picoAfterLoadingHandoff;
    stats.devicesPrefix += picoBeforeInputPlugins - picoUpdateStart;
    stats.inputPlugins += picoAfterInputPlugins - picoBeforeInputPlugins;
    stats.inputMapper += picoAfterInputMapper - picoAfterInputPlugins;
    stats.driveKeys += picoAfterDriveKeys - picoAfterInputMapper;
    stats.controllerPoses += picoAfterDevices - picoAfterDriveKeys;
    stats.prePick += picoBeforePick - picoAfterDevices;
    stats.pick += picoAfterPick - picoBeforePick;
    stats.pointer += picoAfterPointer - picoAfterPick;
    stats.simulationSetup += picoAfterSimulationSetup - picoAfterPointer;
    stats.prePhysics += picoAfterPrePhysics - picoAfterSimulationSetup;
    stats.physics += picoBeforeEntityUpdate - picoAfterPrePhysics;
    stats.entityUpdate += picoAfterEntityUpdate - picoBeforeEntityUpdate;
    stats.afterEntityUpdate += picoBeforeSimulationCleanup - picoAfterEntityUpdate;
    stats.simulationCleanup += picoAfterSimulation - picoBeforeSimulationCleanup;
    stats.avatars += picoAfterAvatars - picoAfterSimulation;
    stats.overlaysAndView += picoAfterOverlays - picoAfterAvatars;
    stats.postUpdate += picoBeforePostUpdate - picoAfterOverlays;
    stats.postLambdas += picoAfterPostLambdas - picoBeforePostUpdate;
    stats.renderArgs += picoAfterRenderArgs - picoAfterPostLambdas;
    stats.frameEnd += end - picoAfterRenderArgs;
    stats.maximum = std::max(stats.maximum, total);
    if (end - stats.windowStart >= USECS_PER_SECOND) {
        const double divisor = std::max<quint64>(1, stats.calls);
        qInfo() << "PICO_UPDATE_STAGES"
                << "callsPerSec" << stats.calls
                << "avgTotalMs" << stats.total / divisor / 1000.0
                << "maxTotalMs" << stats.maximum / 1000.0
                << "devicesMs" << stats.devices / divisor / 1000.0
                << "testPropertiesMs" << stats.testProperties / divisor / 1000.0
                << "worldLoadingMs" << stats.worldLoading / divisor / 1000.0
                << "loadingHandoffMs" << stats.loadingHandoff / divisor / 1000.0
                << "mouseCaptureMs" << stats.mouseCapture / divisor / 1000.0
                << "devicesPrefixMs" << stats.devicesPrefix / divisor / 1000.0
                << "inputPluginsMs" << stats.inputPlugins / divisor / 1000.0
                << "inputMapperMs" << stats.inputMapper / divisor / 1000.0
                << "driveKeysMs" << stats.driveKeys / divisor / 1000.0
                << "controllerPosesMs" << stats.controllerPoses / divisor / 1000.0
                << "prePickMs" << stats.prePick / divisor / 1000.0
                << "pickMs" << stats.pick / divisor / 1000.0
                << "pointerMs" << stats.pointer / divisor / 1000.0
                << "simulationSetupMs" << stats.simulationSetup / divisor / 1000.0
                << "prePhysicsMs" << stats.prePhysics / divisor / 1000.0
                << "physicsMs" << stats.physics / divisor / 1000.0
                << "entityUpdateMs" << stats.entityUpdate / divisor / 1000.0
                << "afterEntityUpdateMs" << stats.afterEntityUpdate / divisor / 1000.0
                << "simulationCleanupMs" << stats.simulationCleanup / divisor / 1000.0
                << "avatarsMs" << stats.avatars / divisor / 1000.0
                << "overlaysViewMs" << stats.overlaysAndView / divisor / 1000.0
                << "postUpdateMs" << stats.postUpdate / divisor / 1000.0
                << "postLambdasMs" << stats.postLambdas / divisor / 1000.0
                << "renderArgsMs" << stats.renderArgs / divisor / 1000.0
                << "frameEndMs" << stats.frameEnd / divisor / 1000.0;
        stats = PicoUpdateStats{};
        stats.windowStart = end;
    }
#endif
}


void Application::updateLOD(float deltaTime) const {
    PerformanceTimer perfTimer("LOD");
    // adjust it unless we were asked to disable this feature, or if we're currently in throttleRendering mode
    if (!isThrottleRendering()) {
        float presentTime = getActiveDisplayPlugin()->getAveragePresentTime();
        float engineRunTime = (float)(_graphicsEngine->getRenderEngine()->getConfiguration().get()->getCPURunTime());
        float gpuTime = getGPUContext()->getFrameTimerGPUAverage();
        float batchTime = getGPUContext()->getFrameTimerBatchAverage();
        auto lodManager = DependencyManager::get<LODManager>();
        lodManager->setRenderTimes(presentTime, engineRunTime, batchTime, gpuTime);
        lodManager->autoAdjustLOD(deltaTime);
    } else {
        DependencyManager::get<LODManager>()->resetLODAdjust();
    }
}

void Application::updateThreads(float deltaTime) {
    PerformanceTimer perfTimer("updateThreads");
    bool showWarnings = Menu::getInstance()->isOptionChecked(MenuOption::PipelineWarnings);
    PerformanceWarning warn(showWarnings, "Application::updateThreads()");

    // parse voxel packets
    if (!_enableProcessOctreeThread) {
        _octreeProcessor->threadRoutine();
        _entityEditSender->threadRoutine();
    }
}

void Application::userKickConfirmation(const QUuid& nodeID, unsigned int banFlags) {
    auto avatarHashMap = DependencyManager::get<AvatarHashMap>();
    auto avatar = avatarHashMap->getAvatarBySessionID(nodeID);

    QString userName;

    if (avatar) {
        userName = avatar->getSessionDisplayName();
    } else {
        userName = nodeID.toString();
    }

    QString kickMessage = "Do you wish to kick " + userName + " from your domain";
    ModalDialogListener* dlg = OffscreenUi::asyncQuestion("Kick User", kickMessage,
                                                          QMessageBox::Yes | QMessageBox::No);

    if (dlg->getDialogItem()) {

        QObject::connect(dlg, &ModalDialogListener::response, this, [=, this] (QVariant answer) {
            QObject::disconnect(dlg, &ModalDialogListener::response, this, nullptr);

            bool yes = (static_cast<QMessageBox::StandardButton>(answer.toInt()) == QMessageBox::Yes);
            // ask the NodeList to kick the user with the given session ID

            if (yes) {
                DependencyManager::get<NodeList>()->kickNodeBySessionID(nodeID, banFlags);
            }

            DependencyManager::get<UsersScriptingInterface>()->setWaitForKickResponse(false);
        });
        DependencyManager::get<UsersScriptingInterface>()->setWaitForKickResponse(true);
    }
}

std::shared_ptr<MyAvatar> Application::getMyAvatar() const {
    return DependencyManager::get<AvatarManager>()->getMyAvatar();
}

void Application::checkSkeleton() const {
    if (getMyAvatar()->getSkeletonModel()->isLoaded() && !getMyAvatar()->getSkeletonModel()->hasSkeleton()) {
        qCDebug(interfaceapp) << "MyAvatar model has no skeleton";

        QString message = "Your selected avatar body has no skeleton.\n\nThe default body will be loaded...";
        OffscreenUi::asyncWarning("", message);

        getMyAvatar()->useFullAvatarURL(AvatarData::defaultFullAvatarModelUrl(), DEFAULT_FULL_AVATAR_MODEL_NAME);
    } else {
        _physicsEngine->setCharacterController(getMyAvatar()->getCharacterController());
    }
}

void Application::queryAvatars() {
    if (!isInterstitialMode()) {
        auto avatarPacket = NLPacket::create(PacketType::AvatarQuery);
        auto destinationBuffer = reinterpret_cast<unsigned char*>(avatarPacket->getPayload());
        unsigned char* bufferStart = destinationBuffer;

        uint8_t numFrustums = (uint8_t)_conicalViews.size();
        memcpy(destinationBuffer, &numFrustums, sizeof(numFrustums));
        destinationBuffer += sizeof(numFrustums);

        for (const auto& view : _conicalViews) {
            destinationBuffer += view.serialize(destinationBuffer);
        }

        avatarPacket->setPayloadSize(destinationBuffer - bufferStart);

        DependencyManager::get<NodeList>()->broadcastToNodes(std::move(avatarPacket), NodeSet() << NodeType::AvatarMixer);
    }
}

void Application::tryToEnablePhysics() {
    bool enableInterstitial = DependencyManager::get<NodeList>()->getDomainHandler().getInterstitialModeEnabled();
#if defined(ANDROID_APP_PICO_INTERFACE)
    // Domain settings may arrive or change while Pico's native interstitial is
    // already visible. Once shown, finish the same safe GPU/physics/present
    // handoff instead of bypassing it mid-load and dropping the final status.
    enableInterstitial = enableInterstitial || isInterstitialMode();
#endif
    bool textureMemoryReady = gpuTextureMemSizeStable();
#if defined(ANDROID_APP_PICO_INTERFACE)
    const quint64 physicsNow = usecTimestampNow();
    if (enableInterstitial && _picoLoadingFinalizingAt == 0) {
        _picoLoadingFinalizingAt = physicsNow;
    }
    _picoLoadingTextureMemoryReady = textureMemoryReady;
    if ((textureMemoryReady || _picoLoadingGpuFallbackUsed) && _picoLoadingGpuReadyAt == 0) {
        _picoLoadingGpuReadyAt = physicsNow;
    }

    // A stale driver transfer statistic must not leave the user trapped forever after every entity and
    // collision shape is ready. This fallback is deliberately bounded and only applies when CPU resource
    // queues are idle and GPU allocation has already been stable for the normal settling interval.
    constexpr quint64 GPU_FINALIZATION_TIMEOUT = 15 * USECS_PER_SECOND;
    if (!textureMemoryReady && enableInterstitial && !_picoLoadingGpuFallbackUsed &&
            _picoLoadingFinalizingAt > 0 && physicsNow - _picoLoadingFinalizingAt >= GPU_FINALIZATION_TIMEOUT) {
        const auto loadingRequests = ResourceCache::getLoadingRequests();
        const bool resourceQueuesIdle = loadingRequests.empty() && ResourceCache::getPendingRequestCount() == 0;
        const auto statTracker = DependencyManager::get<StatTracker>();
        const bool processingQueuesIdle = statTracker->getStat("Processing").toInt() == 0 &&
            statTracker->getStat("PendingProcessing").toInt() == 0;
        const bool gpuAllocationStable =
            _gpuTextureMemSizeStabilityCount >= _minimumGPUTextureMemSizeStabilityCount;
        if (resourceQueuesIdle && processingQueuesIdle && gpuAllocationStable) {
            _picoLoadingGpuFallbackUsed = true;
            textureMemoryReady = true;
            if (_picoLoadingGpuReadyAt == 0) {
                _picoLoadingGpuReadyAt = physicsNow;
            }
            qCWarning(interfaceapp) << "Pico world loading ignored a stale GPU transfer statistic"
                << "after resources and GPU allocation became stable";
        }
    }
#endif
    if (textureMemoryReady || !enableInterstitial) {
        _fullSceneCounterAtLastPhysicsCheck = _octreeProcessor->getFullSceneReceivedCounter();
        _lastQueriedViews.clear();  // Force new view.

        // process octree stats packets are sent in between full sends of a scene (this isn't currently true).
        // We keep physics disabled until we've received a full scene and everything near the avatar in that
        // scene is ready to compute its collision shape.
        auto myAvatar = getMyAvatar();
#if defined(ANDROID_APP_PICO_INTERFACE)
        constexpr quint64 DOMAIN_SETTINGS_TIMEOUT = 10 * USECS_PER_SECOND;
        const quint64 domainSettingsWaitStarted = _picoLoadingConnectedAt > 0
            ? _picoLoadingConnectedAt : _picoLoadingFinalizingAt;
        const bool domainSettingsTimedOut = enableInterstitial && domainSettingsWaitStarted > 0 &&
            physicsNow - domainSettingsWaitStarted >= DOMAIN_SETTINGS_TIMEOUT;
        if (domainSettingsTimedOut && !myAvatar->isReadyForPhysics()) {
            qCWarning(interfaceapp) << "Pico world loading using default avatar height limits"
                << "because domain settings did not arrive";
            myAvatar->restrictScaleFromDomainSettings(QJsonObject());
        }
#endif
        if (myAvatar->isReadyForPhysics()) {
            myAvatar->getCharacterController()->setPhysicsEngine(_physicsEngine);
#if defined(ANDROID_APP_PICO_INTERFACE)
            if (enableInterstitial && _picoLoadingSafeLandingCompleteAt == 0) {
                // This is the authoritative safe-landing commit point: physics
                // can only be enabled after the tracked collision set and its
                // initial entity packet sequence have completed.
                _picoLoadingSafeLandingCompleteAt = physicsNow;
                _picoLoadingFinalStatus = _octreeProcessor->safeLandingLoadingStatus();
            }
#endif
            _octreeProcessor->resetSafeLanding();
            _physicsEnabled = true;
#if defined(ANDROID_APP_PICO_INTERFACE)
            if (enableInterstitial && _graphicsEngine) {
                _picoLoadingPhysicsEnabledAt = physicsNow;
                const auto displayPlugin = getActiveDisplayPlugin();
                _picoLoadingPhysicsPresentFrame = displayPlugin ? displayPlugin->presentCount() : 0;
                _picoLoadingDisplayedPhase = static_cast<int>(GraphicsEngine::LoadingPhase::FINALIZING_SCENE);
                _picoLoadingDisplayedProgress = 0.98f;
                _graphicsEngine->setLoadingState(
                    true, GraphicsEngine::LoadingPhase::FINALIZING_SCENE, 0.98f);
            } else {
                setIsInterstitialMode(false);
            }
#else
            setIsInterstitialMode(false);
#endif
            myAvatar->updateMotionBehaviorFromMenu();
        }
    }
}
