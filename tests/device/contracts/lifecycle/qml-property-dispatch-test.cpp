// Exercise the production property gate with real QML storage and Qt queues.
#include <QCoreApplication>
#include <QEvent>
#include <QElapsedTimer>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QThread>
#include <cassert>
#include "QmlPropertyThreadGate.h"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData("import QtQml\nQtObject { property int counter: 0; property url icon: \"initial.svg\" }", QUrl());
    auto item = component.create();
    assert(item);
    const auto count = item->metaObject()->property(item->metaObject()->indexOfProperty("counter"));
    const auto icon = item->metaObject()->property(item->metaObject()->indexOfProperty("icon"));
    auto writer = QThread::create([&] {
        assert(overte::qmlPropertyNeedsDispatch(item));
        overte::writeQmlProperty(item, count, 7);
        overte::writeQmlProperty(item, icon, QUrl("updated.svg"));
    });
    writer->start();
    assert(writer->wait(3000));
    // QML storage must not be accessed by the worker while GUI is paused.
    assert(item->property("counter").toInt() == 0);
    assert(item->property("icon").toUrl() == QUrl("initial.svg"));
    QCoreApplication::sendPostedEvents(item, QEvent::MetaCall);
    assert(item->property("counter").toInt() == 7);
    assert(item->property("icon").toUrl() == QUrl("updated.svg"));

    QVariant observed;
    auto reader = QThread::create([&] {
        // The synchronous read must preserve ordering after the queued write.
        overte::writeQmlProperty(item, icon, QUrl("ordered.svg"));
        observed = overte::readQmlProperty(item, icon);
    });
    reader->start();
    QElapsedTimer deadline;
    deadline.start();
    while (!reader->isFinished() && deadline.elapsed() < 3000) {
        QCoreApplication::processEvents();
        QThread::msleep(1);
    }
    assert(reader->wait(100));
    assert(observed.toUrl() == QUrl("ordered.svg"));
    assert(!overte::qmlPropertyNeedsDispatch(item));
    overte::writeQmlProperty(item, count, 11);
    assert(overte::readQmlProperty(item, count).toInt() == 11);

    auto pending = QThread::create([&] { overte::writeQmlProperty(item, count, 99); });
    pending->start();
    assert(pending->wait(3000));
    delete item; // QObject context cancellation prevents a pending dangling write.
    QCoreApplication::processEvents();
    QObject native;
    assert(!overte::qmlPropertyNeedsDispatch(&native));
    delete pending;
    delete reader;
    delete writer;
}
