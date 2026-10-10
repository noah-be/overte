// Real Qt dispatch exercises the production wrapper method bodies.
#include <QCoreApplication>
#include <QMetaProperty>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QThread>
#include <QVariant>
#include <atomic>
#include <cassert>

class QmlWrapper : public QObject {
    Q_OBJECT
public:
    explicit QmlWrapper(QObject* item) : _qmlObject(item) {}
    Q_INVOKABLE void writeProperty(QString propertyName, QVariant propertyValue);
    Q_INVOKABLE void writeProperties(QVariant propertyMap);
private:
    QObject* _qmlObject;
};

#include "wrapper-methods.inc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData("import QtQml\nQtObject { property int counter: 0; property url image: \"old.png\" }", QUrl());
    auto object = component.create();
    assert(object);
    QmlWrapper wrapper(object);

    // Keep GUI dispatch paused until the script worker has returned. A queued
    // write must leave the real QML property untouched until that dispatch.
    auto worker = QThread::create([&] {
        wrapper.writeProperty("counter", 7);
        wrapper.writeProperties(QVariantMap{{"image", QUrl("new.png")}});
    });
    worker->start();
    assert(worker->wait(3000));
    assert(object->property("counter").toInt() == 0);
    assert(object->property("image").toUrl() == QUrl("old.png"));
    QCoreApplication::sendPostedEvents(&wrapper, QEvent::MetaCall);
    assert(object->property("counter").toInt() == 7);
    assert(object->property("image").toUrl() == QUrl("new.png"));

    // GUI callers retain synchronous writes.
    wrapper.writeProperty("counter", 9);
    wrapper.writeProperties(QVariantMap{{"image", QUrl("gui.png")}});
    assert(object->property("counter").toInt() == 9);
    assert(object->property("image").toUrl() == QUrl("gui.png"));
    delete worker;
    delete object;
}

#include "wrapper.moc"
