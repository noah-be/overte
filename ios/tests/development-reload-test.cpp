// SPDX-License-Identifier: Apache-2.0
#include "../development/QmlOverrideInterceptor.h"
#include <QQmlComponent>
#include <QQmlFileSelector>
#include <QTemporaryDir>

using namespace overte::ios::development;

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    // The Python test supplies a published revision using the real transfer
    // protocol; execute its QML and imported JavaScript with the actual engine.
    const QString documents = QString::fromLocal8Bit(argv[1]);
    const auto scripts = initialize(documents, "host-test-installation");
    const auto state = QJsonDocument::fromJson(read(documents + "/OverteDevelopment/status.json")).object();
    const auto expected = QString::fromLocal8Bit(argv[2]);
    if (state["state"] != expected) { qFatal("unexpected selection state"); }
    if (expected != "selected") { return 0; }
    if (scripts.isEmpty() || !QFileInfo::exists(scripts + "/defaultScripts.js")) { qFatal("script root missing"); }
    QQmlEngine engine;
    const auto root = qApp->property(RESOURCE_PROPERTY).toString();
    auto interceptor = new QmlOverrideInterceptor(&engine, root);
    engine.addUrlInterceptor(interceptor);
    auto selector = new QQmlFileSelector(&engine);
    selector->setExtraSelectors({"ios"});
    // Qrc base, existing local component, imported .js, plus selector all run.
    QQmlComponent component(&engine, QUrl("qrc:/qml/Root.qml"));
    QScopedPointer<QObject> object(component.create());
    if (!object) { qCritical() << component.errors(); return 1; }
    if (object->property("answer").toInt() != 50) { qFatal("dependent QML/JS/selector/new module did not execute"); }
    if (interceptor->intercept(QUrl::fromLocalFile(root + "/images/bundled.png"),
            QQmlAbstractUrlInterceptor::UrlString) != QUrl("qrc:/images/bundled.png")) {
        qFatal("asset fallback from redirected qmldir failed");
    }
    for (const auto& url : {QUrl("https://example.invalid/Root.qml"), QUrl("qrc:/qml/Missing.qml"),
                            QUrl("qrc:/qml/../../outside.qml"), QUrl("file:///tmp/Root.qml")}) {
        if (interceptor->intercept(url, QQmlAbstractUrlInterceptor::QmlFile) != url) { qFatal("URL boundary changed"); }
    }
    // A new request cannot change objects or their dependencies mid-session.
    writeJson(documents + "/OverteDevelopment/active.json", {{"schema", 1}, {"disabled", true}});
    if (object->property("answer").toInt() != 50 || qApp->property(RESOURCE_PROPERTY).toString() != root) {
        qFatal("active process changed revision");
    }
    return 0;
}
