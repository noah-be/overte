// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QFileSelector>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlFileSelector>
#include <CapabilityProfile.h>
#include <cassert>
#include <iostream>

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    assert(argc == 2);
    const QString root = QString::fromLocal8Bit(argv[1]);
    const auto fixture = root + "/tests/device/contracts/tablet/fixtures/";
    qmlRegisterModule("Hifi", 1, 0);
    qmlRegisterModule("TabletScriptingInterface", 1, 0);
    qmlRegisterModule("PerformanceEnums", 1, 0);
    qmlRegisterModule("OverteIOS", 1, 0);
    qmlRegisterType(QUrl::fromLocalFile(fixture + "SoundEffect.qml"), "Hifi", 1, 0, "SoundEffect");
    qmlRegisterType(QUrl::fromLocalFile(fixture + "TabletButtonsProxyModel.qml"), "TabletScriptingInterface", 1, 0, "TabletButtonsProxyModel");
    // Substitute only the native UIKit boundary. Compile production QML files,
    // selectors, imports and their transitive graph, without a copied directory.
    qmlRegisterType(QUrl::fromLocalFile(root + "/tests/device/contracts/web/qml/FakeEmbeddedWebBackend.qml"),
                    "Overte.iOS", 1, 0, "IOSWebView");
    qmlRegisterType(QUrl::fromLocalFile(root + "/tests/device/contracts/snapshot/qml/NativeExportBoundary.qml"),
                    "Overte.iOS", 1, 0, "IOSSnapshotAdapter");
    QQmlEngine engine;
    engine.addImportPath(root + "/interface/resources/qml");
    QQmlFileSelector selector(&engine);
    QStringList profile;
    for (const auto& item : overte::ui::profileSelectors(overte::ui::Product::IOS, true)) {
        profile.append(QString::fromStdString(item));
    }
    selector.setExtraSelectors(profile);
    const QStringList selectedFiles {
        "interface/resources/qml/controls/FlickableWebViewCore.qml",
        "interface/resources/qml/controls/EmbeddedWebBackend.qml",
        "interface/resources/qml/controls/SnapshotPlatformBackend.qml",
        "scripts/system/settings/qml/pages/GraphicsSettings.qml"
    };
    for (const auto& file : selectedFiles) {
        assert(selector.selector()->select(root + '/' + file).contains("/+ios/"));
    }
    const QStringList entries {
        "interface/resources/qml/controls/EmbeddedWebBackend.qml",
        "interface/resources/qml/controls/EmbeddedWebView.qml",
        "interface/resources/qml/controls/FlickableWebViewCore.qml",
        "interface/resources/qml/controls/NativeFlickableWebViewCore.qml",
        "interface/resources/qml/controls/TabletWebScreen.qml",
        "interface/resources/qml/controls/TabletWebView.qml",
        "interface/resources/qml/Web3DSurface.qml",
        "interface/resources/qml/Web3DSurfaceAndroid.qml",
        "scripts/system/settings/Settings.qml",
        "scripts/system/settings/qml/pages/GraphicsSettings.qml",
        "scripts/system/settings/qml/pages/GraphicsSettingsBase.qml",
        "scripts/system/create/qml/NativeCreate.qml",
        "interface/resources/qml/hifi/audio/LoopbackAudio.qml",
        "interface/resources/qml/hifi/audio/Audio.qml",
        "scripts/communityScripts/armored-chat/armored_chat.qml",
        "scripts/communityScripts/armored-chat/armored_chat_quick_message.qml",
        "interface/resources/qml/controls/SnapshotPlatformBackend.qml",
        "scripts/system/snapshot/SnapshotPlatform.qml",
        "scripts/system/snapshot/NativeSnapshotReview.qml",
        "interface/resources/qml/dialogs/NativeFileBrowser.qml",
        "interface/resources/qml/dialogs/FileDialog.qml",
        "interface/resources/qml/dialogs/TabletFileDialog.qml",
        "interface/resources/qml/hifi/dialogs/NativeModelTree.qml",
        "interface/resources/qml/hifi/dialogs/NativeKeyboardHost.qml",
        "interface/resources/qml/hifi/dialogs/RunningScripts.qml",
        "interface/resources/qml/hifi/dialogs/TabletRunningScripts.qml",
        "interface/resources/qml/hifi/AssetServer.qml",
        "interface/resources/qml/hifi/dialogs/TabletAssetServer.qml"
    };
    bool failed = false;
    for (const auto& entry : entries) {
        QQmlComponent component(&engine, QUrl::fromLocalFile(root + '/' + entry), QQmlComponent::PreferSynchronous);
        const bool ready = component.status() == QQmlComponent::Ready;
        std::cout << (ready ? "PASS " : "FAIL ") << entry.toStdString() << '\n';
        for (const auto& error : component.errors()) { std::cerr << error.toString().toStdString() << '\n'; }
        failed |= !ready;
    }
    return failed ? 1 : 0;
}
