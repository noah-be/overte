#include <QtCore/QCoreApplication>
#include <QtCore/QFile>
#include <QtQml/QJSEngine>
#include <cassert>

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    QJSEngine engine;
    engine.installExtensions(QJSEngine::ConsoleExtension | QJSEngine::TranslationExtension);
    QFile source(QString::fromLocal8Bit(argv[1]));
    assert(source.open(QIODevice::ReadOnly));
    const auto handlers = QString::fromUtf8(source.readAll());
    for (const QString& seed : {QString("https://private-canary.invalid/?token=canary-secret"),
                               QString("<img src='https://private-canary.invalid/pixel'>"),
                               QString("Oculus ID user-canary."), QString("%73%65%63%72%65%74")}) {
        engine.globalObject().setProperty("error", seed);
        const auto result = engine.evaluate(handlers);
        assert(!result.isError() && result.isBool() && result.toBool());
    }
    // Original zero-argument QML handlers also work with no ambient error binding.
    engine.globalObject().deleteProperty("error");
    const auto result = engine.evaluate(handlers);
    assert(!result.isError() && result.toBool());
}
