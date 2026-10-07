// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QClipboard>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QTimer>
#include <QVariant>
#include <cstdio>

int main(int argc, char** argv) {
    QGuiApplication application(argc, argv);
    if (argc != 3) return 2;
    QQmlApplicationEngine engine;
    engine.addImportPath(QString::fromLocal8Bit(argv[1]));
    engine.load(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));
    if (engine.rootObjects().size() != 1) return 3;
    auto* window = qobject_cast<QQuickWindow*>(engine.rootObjects().first());
    if (!window) return 4;
    window->requestActivate();
    QGuiApplication::clipboard()->setText(QStringLiteral("private clipboard sentinel"));
    QTimer::singleShot(100, [&] {
        QVariant passed;
        const bool invoked = QMetaObject::invokeMethod(window, "runTests", Q_RETURN_ARG(QVariant, passed));
        const bool clipboardPreserved = QGuiApplication::clipboard()->text() == QStringLiteral("private clipboard sentinel");
        if (!invoked || !passed.toBool() || !clipboardPreserved) {
            std::fputs("Native Qt input assertions failed\n", stderr);
            application.exit(1);
        } else {
            std::puts("Native Qt input: Unicode, atomic undo/redo, selection, rich literal text, readonly, disabled, native validator, mask, length, byte cap, focus and private clipboard passed");
            application.exit(0);
        }
    });
    QTimer::singleShot(10000, [&] { application.exit(5); });
    return application.exec();
}
