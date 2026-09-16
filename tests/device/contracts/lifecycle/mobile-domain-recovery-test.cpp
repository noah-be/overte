#include <QtCore/QCoreApplication>
#include <QtCore/QScopedPointer>
#include <QtQml/QQmlEngine>
#include <QtQml/QQmlComponent>
#include <cassert>

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QQmlEngine engine;
    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    if (component.isError()) qFatal("%s", qPrintable(component.errorString()));
    auto deliver = [](QObject* view, const QString& reason) {
        assert(QMetaObject::invokeMethod(view, "deliver", Q_ARG(QVariant, QVariant(reason))));
    };
    auto message = [](QObject* view) {
        QVariant result;
        assert(QMetaObject::invokeMethod(view, "message", Q_RETURN_ARG(QVariant, result)));
        return result.toString();
    };
    for (bool submitted : { false, true }) {
        QScopedPointer<QObject> view(component.create()); assert(view);
        view->setProperty("requestSubmitted", submitted);
        deliver(view.data(), "timeout");
        assert(!view->property("waiting").toBool() && !view->property("requestSubmitted").toBool());
        assert(message(view.data()) == "Domain sign-in timed out. Check your connection and try again.");
        assert(view->property("selections").toInt() == 1 && view->property("focuses").toInt() == 1);
        deliver(view.data(), "private-server-payload-canary");
        assert(message(view.data()) == "Domain sign-in failed. Check your connection and credentials, then try again.");
        deliver(view.data(), "cancelled");
        assert(view->property("dismissals").toInt() == 1 && view->property("closing").toBool());
        deliver(view.data(), "cancelled");
        deliver(view.data(), "timeout");
        assert(view->property("dismissals").toInt() == 1 && view->property("selections").toInt() == 2);
    }
    QScopedPointer<QObject> account(component.create()); assert(account);
    account->setProperty("domainLogin", false);
    deliver(account.data(), "timeout");
    assert(account->property("waiting").toBool() && account->property("requestSubmitted").toBool());
    assert(account->property("dismissals").toInt() == 0 && message(account.data()).isEmpty());
}
