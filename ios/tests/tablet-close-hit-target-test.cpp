// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QPointer>
#include <QtTest/QTest>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <memory>

using CGFloat = qreal;
using CGRect = QRectF;
static const CGRect CGRectZero;
CGRect CGRectMake(qreal x, qreal y, qreal w, qreal h) { return {x, y, w, h}; }
qreal CGRectGetMinX(CGRect r) { return r.x(); }
qreal CGRectGetMinY(CGRect r) { return r.y(); }
qreal CGRectGetMidX(CGRect r) { return r.center().x(); }
qreal CGRectGetMaxY(CGRect r) { return r.bottom(); }
CGRect CGRectIntersection(CGRect a, CGRect b) { return a.intersected(b); }
// The old UIKit expression used CGRect.size.width; the extraction adapts only
// that field syntax to QRectF.width(), leaving all selection/math unchanged.
#include "production.inc"

void require(bool condition, const char* message) {
    if (!condition) { std::fprintf(stderr, "%s\n", message); std::exit(1); }
}

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    require(argc == 3, "Expected repository and QML fixture");
    QQmlEngine engine;
    const QString repo = QString::fromLocal8Bit(argv[1]);
    engine.addImportPath(repo + "/interface/resources/qml");
    engine.addImportPath(repo + "/tests/device/qml/imports");
    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));
    std::unique_ptr<QObject> object(component.create());
    require(object != nullptr, qPrintable(component.errorString()));
    auto* root = qobject_cast<QQuickItem*>(object.get());
    require(root != nullptr, "Missing shared footer fixture");
    QQuickWindow window;
    window.resize(1400, 1400);
    root->setParentItem(window.contentItem());
    window.show();
    QQuickItem* home = nullptr;
    QQuickItem* close = nullptr;
    for (auto* item : tabletVisualItems(root)) {
        if (item->objectName() == "nav.home") { home = item; }
        if (item->objectName() == "nav.close") { close = item; }
    }
    require(home && close, "Missing real QML navigation controls");
    for (const QSize size : {QSize(768, 900), QSize(1024, 700), QSize(360, 640)}) {
        for (qreal scale : {1.0, 1.25}) {
            for (qreal ime : {0.0, 240.0}) {
                root->setSize(size);
                root->setProperty("footerScale", scale);
                root->setProperty("bottomInset", ime);
                QTest::qWait(50); // Polish the real QML Row and scaled delegates.
                const CGRect safeBounds(12, 24, size.width(), size.height());
                const auto nativeFrame = nativeCloseFrame(root, safeBounds);
                const auto homeFrame = tabletItemFrame(home, safeBounds);
                const auto closeFrame = tabletItemFrame(close, safeBounds);
                require(!nativeFrame.contains(homeFrame.center()),
                        "Native Close intercepts the visible Home button");
                require(nativeFrame == closeFrame,
                        "Native Close must use the visible Close geometry");
                const int homes = root->property("homes").toInt();
                QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier,
                    home->mapToScene(home->boundingRect().center()).toPoint());
                require(root->property("homes").toInt() == homes + 1 && root->property("closes").toInt() == 0,
                        "The visible Home action must not close the tablet");
                close->setVisible(false);
                require(nativeCloseFrame(root, safeBounds).isEmpty(),
                        "Hidden Close must not leave a fallback hit target");
                close->setVisible(true);
            }
        }
    }
    // The tablet home page names its Close control differently from the footer.
    close->setObjectName("OverteTabletClose");
    const CGRect safeBounds(0, 0, root->width(), root->height());
    require(nativeCloseFrame(root, safeBounds) == tabletItemFrame(close, safeBounds),
            "Tablet Home Close must retain its own visible target");
    close->setEnabled(false);
    require(nativeCloseFrame(root, safeBounds).isEmpty(), "Disabled Close must not intercept input");
    close->setEnabled(true);
    QQuickItem duplicate(root);
    duplicate.setObjectName("nav.close");
    duplicate.setSize(QSizeF(48, 48));
    require(nativeCloseFrame(root, safeBounds).isEmpty(), "Ambiguous Close targets must not intercept input");
    duplicate.setParentItem(nullptr);
    duplicate.setParent(nullptr);
    object.reset();
    std::puts("PASS native Close follows shared QML geometry and never covers Home");
}
