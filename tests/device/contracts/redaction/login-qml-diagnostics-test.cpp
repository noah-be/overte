#include <QtCore/QCoreApplication>
#include <QtCore/QFile>
#include <QtCore/QLoggingCategory>
#include <QtCore/QStringList>
#include <QtQml/QJSEngine>
#include <cassert>

static QStringList messages;
static void collect(QtMsgType, const QMessageLogContext&, const QString& message) {
    messages.append(message);
}

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    QJSEngine engine;
    engine.installExtensions(QJSEngine::ConsoleExtension);
    QFile source(QString::fromLocal8Bit(argv[1]));
    assert(source.open(QIODevice::ReadOnly));
    const QString sites = QString::fromUtf8(source.readAll());
    QLoggingCategory::setFilterRules("*.debug=true");
    auto previous = qInstallMessageHandler(collect);
    const QStringList seeds {
        "https://private-canary.invalid/path?token=secret-canary",
        "user-canary:password-canary@domain-canary",
        "encoded%2Fsecret%3Dcanary", QString::fromUtf8("unicode-\xc3\xbc-canary")
    };
    for (const QString& seed : seeds) {
        for (const char* field : { "metaverseServer", "url", "error" }) {
            engine.globalObject().setProperty(QString::fromLatin1(field), seed);
        }
        // Positive control: prove that the actual console extension reaches this sink.
        messages.clear();
        assert(!engine.evaluate("console.log(error)").isError());
        assert(messages.size() == 1 && messages.first().contains(seed));
        messages.clear();
        assert(!engine.evaluate(sites).isError());
        assert(messages.size() == 24);
        for (const auto& message : messages) {
            assert(!message.contains(seed) && !message.contains("canary"));
        }
    }
    qInstallMessageHandler(previous);
}
