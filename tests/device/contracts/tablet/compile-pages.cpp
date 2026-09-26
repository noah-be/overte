#include <QGuiApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlFileSelector>
#include <iostream>

// Native registrations are boundaries, not simulated device implementations.
// Compile the real, transitive QML graph. Runtime behavior is covered separately
// by Quick Test and, ultimately, the product's physical-device acceptance.
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    if (argc != 3) { return 2; }
    const QString root = QString::fromUtf8(argv[1]);
    const QString fixture = root + "/tests/device/contracts/tablet/fixtures/";
    qmlRegisterModule("Hifi", 1, 0);
    qmlRegisterModule("TabletScriptingInterface", 1, 0);
    qmlRegisterModule("PerformanceEnums", 1, 0);
    qmlRegisterModule("OverteIOS", 1, 0);
    qmlRegisterType(QUrl::fromLocalFile(fixture + "TabletButtonsProxyModel.qml"),
                    "TabletScriptingInterface", 1, 0, "TabletButtonsProxyModel");
    qmlRegisterType(QUrl::fromLocalFile(fixture + "SoundEffect.qml"), "Hifi", 1, 0, "SoundEffect");
    qmlRegisterType(QUrl::fromLocalFile(fixture + "AddressBarDialog.qml"), "Hifi", 1, 0, "AddressBarDialog");
    QQmlEngine engine;
    engine.addImportPath(root + "/interface/resources/qml");
    QQmlFileSelector selector(&engine);
    if (QString::fromUtf8(argv[2]) == "ios") {
        selector.setExtraSelectors({"ios", "mobile", "touch", "android_phoneInterface", "android_interface", "webview"});
    }
    QFile manifest(root + "/tests/device/contracts/tablet/pages.json");
    if (!manifest.open(QIODevice::ReadOnly)) { return 2; }
    const auto pages = QJsonDocument::fromJson(manifest.readAll()).object();
    if (pages.isEmpty()) { return 2; }
    bool failed = false;
    for (auto page = pages.begin(); page != pages.end(); ++page) {
        QQmlComponent component(&engine, QUrl::fromLocalFile(root + "/" + page.value().toString()),
                                QQmlComponent::PreferSynchronous);
        const bool ready = component.status() == QQmlComponent::Ready;
        std::cout << (ready ? "PASS " : "FAIL ") << page.key().toStdString() << '\n';
        for (const auto& error : component.errors()) {
            std::cerr << error.toString().toStdString() << '\n';
        }
        failed |= !ready;
    }
    return failed ? 1 : 0;
}
