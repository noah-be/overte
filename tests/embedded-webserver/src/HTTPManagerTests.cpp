// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QFileInfo>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTimer>

#include <HTTPConnection.h>
#include <HTTPManager.h>

class HTTPManagerTests : public QObject {
    Q_OBJECT
private:
    static bool writeFile(const QString& path, const QByteArray& data) {
        if (!QDir().mkpath(QFileInfo(path).absolutePath())) {
            return false;
        }
        QFile file(path);
        return file.open(QIODevice::WriteOnly) && file.write(data) == data.size();
    }

    static QByteArray get(HTTPManager& manager, const QByteArray& path) {
        QTcpSocket socket;
        QEventLoop loop;
        QTimer deadline;
        deadline.setSingleShot(true);
        QByteArray response;
        QObject::connect(&deadline, &QTimer::timeout, &loop, &QEventLoop::quit);
        QObject::connect(&socket, &QTcpSocket::readyRead, [&] { response += socket.readAll(); });
        QObject::connect(&socket, &QTcpSocket::disconnected, &loop, &QEventLoop::quit);
        QObject::connect(&socket, &QTcpSocket::connected, [&] {
            socket.write("GET " + path + " HTTP/1.1\r\nHost: localhost\r\n\r\n");
        });
        deadline.start(3000);
        socket.connectToHost(QHostAddress::LocalHost, manager.serverPort());
        loop.exec();
        response += socket.readAll();
        if (!deadline.isActive()) {
            return {}; // A bounded local-server timeout must fail the assertion.
        }
        return response;
    }

    static QByteArray body(const QByteArray& response) {
        const int split = response.indexOf("\r\n\r\n");
        return split < 0 ? QByteArray() : response.mid(split + 4);
    }

private slots:
    void staticFiles_data() {
        QTest::addColumn<QByteArray>("path");
        QTest::addColumn<int>("status");
        QTest::addColumn<QByteArray>("content");
        QTest::addColumn<QByteArray>("location");
        QTest::newRow("file") << QByteArray("/ok.txt") << 200 << QByteArray("inside") << QByteArray();
        QTest::newRow("subdirectory-file") << QByteArray("/sub/ok.txt") << 200 << QByteArray("nested") << QByteArray();
        QTest::newRow("empty-file") << QByteArray("/empty.txt") << 200 << QByteArray("") << QByteArray();
        QTest::newRow("encoded-file") << QByteArray("/a%20b.txt") << 200 << QByteArray("space") << QByteArray();
        QTest::newRow("large-file") << QByteArray("/large.txt") << 200 << QByteArray(25000, 'x') << QByteArray();
        QTest::newRow("html-mime") << QByteArray("/page.html") << 200 << QByteArray("html") << QByteArray();
        QTest::newRow("root-index-priority") << QByteArray("/") << 200 << QByteArray("root-index") << QByteArray();
        QTest::newRow("subdirectory-index") << QByteArray("/sub/") << 200 << QByteArray("sub-index") << QByteArray();
        QTest::newRow("shtml-index") << QByteArray("/ssi/") << 200 << QByteArray("ssi:inside") << QByteArray();
        QTest::newRow("redirect") << QByteArray("/sub") << 302 << QByteArray("") << QByteArray("/sub/");
        QTest::newRow("redirect-query") << QByteArray("/sub?x=1&y=2") << 302 << QByteArray("") << QByteArray("/sub/?x=1&y=2");
        QTest::newRow("missing-file") << QByteArray("/missing.txt") << 404 << QByteArray("Resource not found.") << QByteArray();
        QTest::newRow("missing-index") << QByteArray("/no-index/") << 404 << QByteArray("Resource not found.") << QByteArray();
        QTest::newRow("missing-directory") << QByteArray("/missing/") << 404 << QByteArray("Resource not found.") << QByteArray();
        QTest::newRow("file-with-slash") << QByteArray("/ok.txt/") << 404 << QByteArray("Resource not found.") << QByteArray();
        QTest::newRow("within-root-dotdot") << QByteArray("/sub/../ok.txt") << 200 << QByteArray("inside") << QByteArray();
        QTest::newRow("sibling-prefix") << QByteArray("/../www-neighbor/secret.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("encoded-traversal") << QByteArray("/%2e%2e/www-neighbor/secret.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("encoded-separators") << QByteArray("/..%2fwww-neighbor%2fsecret.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("outside-unrelated") << QByteArray("/../outside/secret.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("outside-missing") << QByteArray("/../www-neighbor/absent.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("index-directory-fallback") << QByteArray("/directory-index/") << 200 << QByteArray("fallback") << QByteArray();
        QTest::newRow("outside-index") << QByteArray("/../www-neighbor/") << 400 << QByteArray() << QByteArray();
        QTest::newRow("outside-redirect") << QByteArray("/../www-neighbor") << 400 << QByteArray() << QByteArray();
        QTest::newRow("embedded-nul") << QByteArray("/ok.txt%00ignored") << 400 << QByteArray() << QByteArray();
#ifndef Q_OS_WIN
        QTest::newRow("internal-file-symlink") << QByteArray("/internal.txt") << 200 << QByteArray("inside") << QByteArray();
        QTest::newRow("internal-directory-symlink") << QByteArray("/internal-dir/") << 200 << QByteArray("sub-index") << QByteArray();
        QTest::newRow("internal-symlink-redirect") << QByteArray("/internal-dir") << 302 << QByteArray("") << QByteArray("/internal-dir/");
        QTest::newRow("external-file-symlink") << QByteArray("/external.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("external-directory-symlink") << QByteArray("/external-dir/secret.txt") << 400 << QByteArray() << QByteArray();
        QTest::newRow("external-symlink-index") << QByteArray("/external-dir/") << 400 << QByteArray() << QByteArray();
        QTest::newRow("external-symlink-redirect") << QByteArray("/external-dir") << 400 << QByteArray() << QByteArray();
        QTest::newRow("external-index-html-symlink") << QByteArray("/bad-index/") << 400 << QByteArray() << QByteArray();
        QTest::newRow("external-index-shtml-symlink") << QByteArray("/bad-ssi-index/") << 400 << QByteArray() << QByteArray();
        QTest::newRow("internal-index-symlink") << QByteArray("/good-index/") << 200 << QByteArray("inside") << QByteArray();
        QTest::newRow("text-mime-symlink") << QByteArray("/text-alias.txt") << 200 << QByteArray("inside") << QByteArray();
        QTest::newRow("shtml-file-symlink") << QByteArray("/alias.shtml") << 200 << QByteArray("ssi:inside") << QByteArray();
        QTest::newRow("shtml-index-symlink") << QByteArray("/good-ssi-index/") << 200 << QByteArray("ssi:inside") << QByteArray();
        QTest::newRow("dangling-index-fallback") << QByteArray("/dangling-index/") << 200 << QByteArray("fallback") << QByteArray();
        QTest::newRow("dangling-symlink") << QByteArray("/dangling.txt") << 404 << QByteArray("Resource not found.") << QByteArray();
#endif
    }

    void staticFiles() {
        QFETCH(QByteArray, path);
        QFETCH(int, status);
        QFETCH(QByteArray, content);
        QFETCH(QByteArray, location);
        QTemporaryDir fixture;
        QVERIFY(fixture.isValid());
        const QString root = fixture.path() + "/www";
        QVERIFY(writeFile(root + "/ok.txt", "inside"));
        QVERIFY(writeFile(root + "/empty.txt", ""));
        QVERIFY(writeFile(root + "/a b.txt", "space"));
        QVERIFY(writeFile(root + "/page.html", "html"));
        QVERIFY(writeFile(root + "/large.txt", QByteArray(25000, 'x')));
        QVERIFY(writeFile(root + "/index.html", "root-index"));
        QVERIFY(writeFile(root + "/index.shtml", "lower-priority"));
        QVERIFY(writeFile(root + "/sub/ok.txt", "nested"));
        QVERIFY(writeFile(root + "/sub/index.html", "sub-index"));
        QVERIFY(writeFile(root + "/ssi/index.shtml", "ssi:<!--#include virtual=\"/ok.txt\" -->"));
        QVERIFY(QDir().mkpath(root + "/no-index"));
        QVERIFY(QDir().mkpath(root + "/directory-index/index.html"));
        QVERIFY(writeFile(root + "/directory-index/index.shtml", "fallback"));
        QVERIFY(writeFile(fixture.path() + "/www-neighbor/secret.txt", "OUTSIDE-MARKER"));
        QVERIFY(writeFile(fixture.path() + "/www-neighbor/index.html", "OUTSIDE-MARKER"));
        QVERIFY(writeFile(fixture.path() + "/outside/secret.txt", "OUTSIDE-MARKER"));
#ifndef Q_OS_WIN
        QVERIFY(QFile::link(root + "/ok.txt", root + "/internal.txt"));
        QVERIFY(writeFile(root + "/mime-target.png", "inside"));
        QVERIFY(QFile::link(root + "/mime-target.png", root + "/text-alias.txt"));
        QVERIFY(QFile::link(root + "/sub", root + "/internal-dir"));
        QVERIFY(QFile::link(fixture.path() + "/www-neighbor/secret.txt", root + "/external.txt"));
        QVERIFY(QFile::link(fixture.path() + "/www-neighbor", root + "/external-dir"));
        for (const QString& directory : { "bad-index", "bad-ssi-index", "good-index", "good-ssi-index", "dangling-index" }) {
            QVERIFY(QDir().mkpath(root + "/" + directory));
        }
        QVERIFY(QFile::link(fixture.path() + "/www-neighbor/secret.txt", root + "/bad-index/index.html"));
        QVERIFY(QFile::link(fixture.path() + "/www-neighbor/secret.txt", root + "/bad-ssi-index/index.shtml"));
        QVERIFY(QFile::link(root + "/ok.txt", root + "/good-index/index.html"));
        QVERIFY(writeFile(root + "/include-source.txt", "ssi:<!--#include virtual=\"/ok.txt\" -->"));
        QVERIFY(QFile::link(root + "/include-source.txt", root + "/alias.shtml"));
        QVERIFY(QFile::link(root + "/include-source.txt", root + "/good-ssi-index/index.shtml"));
        QVERIFY(QFile::link(fixture.path() + "/absent", root + "/dangling-index/index.html"));
        QVERIFY(writeFile(root + "/dangling-index/index.shtml", "fallback"));
        QVERIFY(QFile::link(fixture.path() + "/absent", root + "/dangling.txt"));
#endif
        // Exercise both configured spellings, including a relative root and a root symlink.
        QStringList roots { root + "/", root, QDir::current().relativeFilePath(root) };
#ifndef Q_OS_WIN
        QVERIFY(QFile::link(root, fixture.path() + "/root-alias"));
        roots << fixture.path() + "/root-alias/";
#endif
        for (const QString& configuredRoot : roots) {
            HTTPManager manager(QHostAddress::LocalHost, 0, configuredRoot);
            QVERIFY(manager.isListening());
            const auto response = get(manager, path);
            QVERIFY2(response.startsWith("HTTP/1.1 " + QByteArray::number(status) + ' '), response.constData());
            QVERIFY2(!response.contains("OUTSIDE-MARKER"), response.constData());
            if (status != 400) {
                QCOMPARE(body(response), content);
            }
            if (!location.isEmpty()) {
                QVERIFY(response.contains("Location: " + location + "\r\n"));
            }
            if (status == 200 && path.endsWith(".txt") && !content.isEmpty()) {
                QVERIFY(response.contains("Content-Type: text/plain\r\n"));
            }
            if (status == 200 && (path.endsWith("html") || path.endsWith('/'))) {
                QVERIFY(response.contains("Content-Type: text/html\r\n"));
            }
        }
    }

    void includes_data() {
        QTest::addColumn<QByteArray>("directive");
        QTest::addColumn<QByteArray>("expected");
        QTest::newRow("relative-file") << QByteArray("<!--#include file=\"local.txt\" -->") << QByteArray("local");
        QTest::newRow("file-leading-slash") << QByteArray("<!--#include file=\"/local.txt\" -->") << QByteArray("local");
        QTest::newRow("virtual-double-slash") << QByteArray("<!--#include virtual=\"//ok.txt\" -->") << QByteArray("inside");
        QTest::newRow("root-virtual") << QByteArray("<!--#include virtual=\"/ok.txt\" -->") << QByteArray("inside");
        QTest::newRow("relative-virtual") << QByteArray("<!--#include virtual=\"ok.txt\" -->") << QByteArray("inside");
        QTest::newRow("file-parent-within-root") << QByteArray("<!--#include file=\"../ok.txt\" -->") << QByteArray("inside");
        QTest::newRow("missing-file") << QByteArray("<!--#include file=\"missing.txt\" -->") << QByteArray("");
        QTest::newRow("file-traversal") << QByteArray("<!--#include file=\"../../www-neighbor/secret.txt\" -->") << QByteArray("");
        QTest::newRow("virtual-traversal") << QByteArray("<!--#include virtual=\"../www-neighbor/secret.txt\" -->") << QByteArray("");
        QTest::newRow("virtual-leading-slash-traversal") << QByteArray("<!--#include virtual=\"/../www-neighbor/secret.txt\" -->") << QByteArray("");
        QTest::newRow("encoded-name-is-literal") << QByteArray("<!--#include virtual=\"%2e%2e/www-neighbor/secret.txt\" -->") << QByteArray("");
        QTest::newRow("rejected-then-valid") << QByteArray("<!--#include virtual=\"../www-neighbor/secret.txt\" --><!--#include file=\"local.txt\" -->") << QByteArray("local");
        QTest::newRow("directory") << QByteArray("<!--#include virtual=\"sub\" -->") << QByteArray("");
        QTest::newRow("adjacent-includes") << QByteArray("<!--#include file=\"local.txt\" --><!--#include virtual=\"/ok.txt\" -->") << QByteArray("localinside");
        QTest::newRow("nonrecursive") << QByteArray("<!--#include file=\"nested.shtml\" -->") << QByteArray("<!--#include virtual=\"/ok.txt\" -->");
        QTest::newRow("nul") << (QByteArray("<!--#include file=\"local.txt") + '\0' + "ignored\" -->") << QByteArray("");
#ifndef Q_OS_WIN
        QTest::newRow("external-file-link") << QByteArray("<!--#include file=\"external.txt\" -->") << QByteArray("");
        QTest::newRow("dangling-file-link") << QByteArray("<!--#include file=\"dangling.txt\" -->") << QByteArray("");
        QTest::newRow("external-directory-link") << QByteArray("<!--#include virtual=\"external-dir/secret.txt\" -->") << QByteArray("");
        QTest::newRow("internal-file-link") << QByteArray("<!--#include file=\"internal.txt\" -->") << QByteArray("inside");
#endif
    }

    void includes() {
        QFETCH(QByteArray, directive);
        QFETCH(QByteArray, expected);
        QTemporaryDir fixture;
        QVERIFY(fixture.isValid());
        const QString root = fixture.path() + "/www";
        QVERIFY(writeFile(root + "/ok.txt", "inside"));
        QVERIFY(writeFile(root + "/sub/local.txt", "local"));
        QVERIFY(writeFile(root + "/sub/nested.shtml", "<!--#include virtual=\"/ok.txt\" -->"));
        QVERIFY(writeFile(root + "/sub/page.shtml", "before:" + directive + ":after"));
        QVERIFY(writeFile(fixture.path() + "/www-neighbor/secret.txt", "OUTSIDE-MARKER"));
#ifndef Q_OS_WIN
        QVERIFY(QFile::link(fixture.path() + "/www-neighbor/secret.txt", root + "/sub/external.txt"));
        QVERIFY(QFile::link(fixture.path() + "/www-neighbor", root + "/external-dir"));
        QVERIFY(QFile::link(root + "/ok.txt", root + "/sub/internal.txt"));
        QVERIFY(QFile::link(fixture.path() + "/missing", root + "/sub/dangling.txt"));
#endif
        for (const QString& configuredRoot : { root + "/", root }) {
            HTTPManager manager(QHostAddress::LocalHost, 0, configuredRoot);
            QVERIFY(manager.isListening());
            const auto response = get(manager, "/sub/page.shtml");
            QVERIFY2(response.startsWith("HTTP/1.1 200 "), response.constData());
            QVERIFY(!response.contains("OUTSIDE-MARKER"));
            QCOMPARE(body(response), "before:" + expected + ":after");
            QVERIFY(response.contains("Content-Type: text/html\r\n"));
        }
    }

    void subHandlerAndNulGuard() {
        struct Handler : HTTPRequestHandler {
            int requests { 0 };
            bool handleHTTPRequest(HTTPConnection* connection, const QUrl&, bool = false) override {
                ++requests;
                connection->respond(HTTPConnection::StatusCode200, "handled");
                return true;
            }
        } handler;
        HTTPManager manager(QHostAddress::LocalHost, 0, QString(), &handler);
        QVERIFY(manager.isListening());
        const auto response = get(manager, "/handler-route");
        QVERIFY(response.startsWith("HTTP/1.1 200 "));
        QCOMPARE(body(response), QByteArray("handled"));
        QCOMPARE(handler.requests, 1);
        QVERIFY(get(manager, "/handler-route%00ignored").startsWith("HTTP/1.1 400 "));
        QCOMPARE(handler.requests, 1);
    }

    void unavailableRoot() {
        QTemporaryDir fixture;
        QVERIFY(fixture.isValid());
        QVERIFY(writeFile(fixture.path() + "/file.txt", "OUTSIDE-MARKER"));
        for (const auto& root : { QString(), fixture.path() + "/missing/", fixture.path() + "/file.txt" }) {
            HTTPManager manager(QHostAddress::LocalHost, 0, root);
            QVERIFY(manager.isListening());
            const auto response = get(manager, "/");
            QVERIFY2(response.startsWith("HTTP/1.1 404 "), response.constData());
            QVERIFY(!response.contains("OUTSIDE-MARKER"));
        }
    }
};

QTEST_GUILESS_MAIN(HTTPManagerTests)
#include "HTTPManagerTests.moc"
