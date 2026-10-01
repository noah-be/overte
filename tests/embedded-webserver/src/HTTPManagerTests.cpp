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
#include <QPointer>
#include <QThread>
#include <QScopeGuard>
#include <functional>
#include <new>

#include <HTTPConnection.h>
#include <HTTPManager.h>

class HTTPManagerTests : public QObject {
    Q_OBJECT
private:
    struct RecordingHandler : HTTPRequestHandler {
        int requests { 0 };
        bool hold { false };
        bool requireAuthentication { false };
        QByteArray content;
        QList<FormData> form;
        QPointer<HTTPConnection> connection;
        bool handleHTTPRequest(HTTPConnection* c, const QUrl&, bool = false) override {
            ++requests;
            connection = c;
            // File-backed content is a borrowed mapped view, valid only during
            // the connection lifetime. Retained fixture evidence must own its bytes.
            content = QByteArray(c->requestContent().constData(), c->requestContent().size());
            form = c->parseFormData();
            if (!hold) {
                const bool authorized = !requireAuthentication || c->requestHeader("Authorization") == "Fixture permitted";
                c->respond(authorized ? HTTPConnection::StatusCode200 : HTTPConnection::StatusCode401, "handled");
            }
            return true;
        }
    };

    struct StorageManager : HTTPManager {
        enum Fault { None, MemoryThrow, MemoryShort, Open, Resize, Map, Write };
        StorageManager(HTTPRequestHandler* handler) : HTTPManager(QHostAddress::LocalHost, 0, QString(), handler) {}
        Fault fault { None };
        int allocations { 0 }, opens { 0 }, resizes { 0 }, maps { 0 };
        int maxParserChildren { 0 }, maxSocketChildren { 0 };
        QString filePath;
        QPointer<QTemporaryFile> file;
        QTemporaryDir fixture;
        void incomingConnection(qintptr descriptor) override {
            HTTPManager::incomingConnection(descriptor);
            // Observe immediately, before deleteLater/event-loop cleanup can hide an excess child.
            maxParserChildren = std::max(maxParserChildren, findChildren<HTTPConnection*>().size());
            maxSocketChildren = std::max(maxSocketChildren, findChildren<QTcpSocket*>().size());
        }
        QByteArray allocateRequestMemory(int size) override {
            ++allocations;
            if (fault == MemoryThrow) { throw std::bad_alloc(); }
            if (fault == MemoryShort) { return {}; }
            return HTTPManager::allocateRequestMemory(size);
        }
        bool openRequestFile(QTemporaryFile& f) override {
            ++opens;
            file = &f;
            // An actual failing open, not a replacement storage/parser.
            f.setFileTemplate(fixture.path() + (fault == Open ? "/missing/" : "/") + "request-XXXXXX");
            const bool result = HTTPManager::openRequestFile(f);
            filePath = f.fileName();
            return result;
        }
        bool resizeRequestFile(QTemporaryFile& f, qint64 size) override {
            ++resizes;
            const bool result = HTTPManager::resizeRequestFile(f, fault == Resize ? -1 : size);
            if (fault == Write) { f.close(); } // Exercise a real failing QFile::write.
            return result;
        }
        uchar* mapRequestFile(QTemporaryFile& f, qint64 size) override {
            ++maps;
            return HTTPManager::mapRequestFile(f, fault == Map ? 0 : size);
        }
    };

    static HTTPRequestLimits smallLimits() {
        HTTPRequestLimits limits;
        limits.maxHeaderBytes = 256;
        limits.maxBodyBytes = 128;
        limits.memoryBodyThreshold = 16;
        limits.maxReservedBytes = 4 * (limits.maxHeaderBytes + HTTPRequestLimits::SOCKET_BUFFER_BYTES + limits.maxBodyBytes);
        limits.maxConnections = 4;
        limits.headerDeadlineMs = 1000;
        limits.requestDeadlineMs = 2000;
        limits.idleDeadlineMs = 1000;
        return limits;
    }

    static bool until(const std::function<bool()>& predicate, int timeout = 3000) {
        QElapsedTimer elapsed;
        elapsed.start();
        while (!predicate() && elapsed.elapsed() < timeout) {
            QTest::qWait(1);
        }
        return predicate();
    }

    static bool openClient(HTTPManager& manager, QTcpSocket& socket) {
        bool connected = false;
        const auto notification = QObject::connect(&socket, &QTcpSocket::connected, [&] { connected = true; });
        socket.connectToHost(QHostAddress::LocalHost, manager.serverPort());
        const bool result = until([&] { return connected; });
        QObject::disconnect(notification);
        return result;
    }

    static QByteArray closedResponse(QTcpSocket& socket) {
        if (!until([&] { return socket.state() == QAbstractSocket::UnconnectedState; })) {
            return {};
        }
        return socket.readAll();
    }

    static QByteArray exchange(HTTPManager& manager, const QByteArray& request) {
        QTcpSocket socket;
        if (!openClient(manager, socket)) { return {}; }
        if (socket.state() == QAbstractSocket::ConnectedState) {
            socket.write(request);
        } // Admission may send its rejection and close before the client writes.
        return closedResponse(socket);
    }

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
    void framing_data() {
        QTest::addColumn<QByteArray>("headers");
        QTest::addColumn<int>("status");
        QTest::newRow("negative") << QByteArray("Content-Length: -1\r\n") << 400;
        QTest::newRow("plus") << QByteArray("Content-Length: +1\r\n") << 400;
        QTest::newRow("empty") << QByteArray("Content-Length:\r\n") << 400;
        QTest::newRow("fraction") << QByteArray("Content-Length: 1.0\r\n") << 400;
        QTest::newRow("hex") << QByteArray("Content-Length: 0x10\r\n") << 400;
        QTest::newRow("internal-space") << QByteArray("Content-Length: 1 2\r\n") << 400;
        QTest::newRow("signed-overflow") << QByteArray("Content-Length: 9223372036854775808\r\n") << 400;
        QTest::newRow("unsigned-overflow") << QByteArray("Content-Length: 18446744073709551616\r\n") << 400;
        QTest::newRow("very-long-number") << QByteArray("Content-Length: ") + QByteArray(100, '9') + "\r\n" << 400;
        QTest::newRow("qt-int-boundary") << QByteArray("Content-Length: 2147483647\r\n") << 413;
        QTest::newRow("qt-int-overflow") << QByteArray("Content-Length: 2147483648\r\n") << 413;
        QTest::newRow("qint64-max") << QByteArray("Content-Length: 9223372036854775807\r\n") << 413;
        QTest::newRow("oversized") << QByteArray("Content-Length: 129\r\n") << 413;
        QTest::newRow("equal-duplicates") << QByteArray("Content-Length: 0\r\nCONTENT-LENGTH: 0\r\n") << 400;
        QTest::newRow("conflicting-duplicates") << QByteArray("Content-Length: 0\r\nContent-Length: 1\r\n") << 400;
        QTest::newRow("empty-duplicate") << QByteArray("Content-Length:\r\nContent-Length: 0\r\n") << 400;
        QTest::newRow("length-list") << QByteArray("Content-Length: 0, 0\r\n") << 400;
        QTest::newRow("chunked") << QByteArray("Transfer-Encoding: chunked\r\n") << 400;
        QTest::newRow("chunked-and-length") << QByteArray("Content-Length: 0\r\nTransfer-Encoding: chunked\r\n") << 400;
        QTest::newRow("identity") << QByteArray("Transfer-Encoding: identity\r\n") << 400;
        QTest::newRow("empty-transfer-encoding") << QByteArray("Transfer-Encoding:\r\n") << 400;
        QTest::newRow("folded-length") << QByteArray("Content-Length: 0\r\n 0\r\n") << 400;
        QTest::newRow("key-whitespace") << QByteArray("Content-Length : 0\r\n") << 400;
        QTest::newRow("missing-colon") << QByteArray("Content-Length 0\r\n") << 400;
        QTest::newRow("control-in-value") << QByteArray("X: a\x01\r\n") << 400;
        QTest::newRow("lf-only") << QByteArray("X: a\n") << 400;
    }

    void framing() {
        QFETCH(QByteArray, headers);
        QFETCH(int, status);
        RecordingHandler handler;
        StorageManager manager(&handler);
        QVERIFY(manager.setRequestLimits(smallLimits()));
        const auto response = exchange(manager, "POST / HTTP/1.1\r\n" + headers + "\r\n");
        QVERIFY2(response.startsWith("HTTP/1.1 " + QByteArray::number(status) + " "), response.constData());
        QCOMPARE(handler.requests, 0);
        QCOMPARE(manager.allocations + manager.opens, 0);
        QVERIFY(until([&] { return manager.liveRequestCount() == 0; }));
        QCOMPARE(manager.reservedRequestBytes(), qint64(0));
    }

    void boundedHeaders() {
        RecordingHandler handler;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        limits.maxHeaderBytes = 128;
        QVERIFY(manager.setRequestLimits(limits));
        const QByteArray prefix = "GET / HTTP/1.1\r\nX: ";
        const auto exact = prefix + QByteArray(limits.maxHeaderBytes - prefix.size() - 4, 'a') + "\r\n\r\n";
        QCOMPARE(exact.size(), int(limits.maxHeaderBytes));
        QVERIFY(exchange(manager, exact).startsWith("HTTP/1.1 200 "));
        const auto oversized = prefix + QByteArray(129, 'a') + "\r\n\r\n";
        QVERIFY(exchange(manager, oversized).startsWith("HTTP/1.1 431 "));
        QVERIFY(exchange(manager, QByteArray(128, 'a')).startsWith("HTTP/1.1 431 "));
        QTcpSocket split;
        QVERIFY(openClient(manager, split));
        split.write("GET / HTTP/1.1\r\nX: ");
        QTest::qWait(5);
        split.write(QByteArray(128, 'a'));
        QVERIFY(closedResponse(split).startsWith("HTTP/1.1 431 "));
        // Request line + many individually small headers also consume the total budget.
        QVERIFY(exchange(manager, "GET / HTTP/1.1\r\n" + QByteArray("X: a\r\n").repeated(30) + "\r\n").startsWith("HTTP/1.1 431 "));
        QCOMPARE(handler.requests, 1);
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
        // A policy larger than the socket buffer still cannot stall on an oversized line.
        limits.maxHeaderBytes = 128 * 1024;
        limits.maxReservedBytes = 1024 * 1024;
        QVERIFY(manager.setRequestLimits(limits));
        QVERIFY(exchange(manager, QByteArray(64 * 1024, 'a')).startsWith("HTTP/1.1 431 "));
    }

    void validBodies_data() {
        QTest::addColumn<int>("size");
        QTest::newRow("zero") << 0;
        QTest::newRow("one") << 1;
        QTest::newRow("below-spool") << 15;
        QTest::newRow("at-spool") << 16;
        QTest::newRow("above-spool") << 17;
        QTest::newRow("exact-body-limit") << 128;
    }

    void validBodies() {
        QFETCH(int, size);
        RecordingHandler handler;
        handler.requireAuthentication = true;
        StorageManager manager(&handler);
        QVERIFY(manager.setRequestLimits(smallLimits()));
        QTcpSocket socket;
        QVERIFY(openClient(manager, socket));
        socket.write("POST / HTTP/1.1\r\nContent-Len");
        QTest::qWait(5);
        socket.write("gth:\t00" + QByteArray::number(size) + " \r\nAuthorization: Fixture permitted\r\n\r\n");
        if (size) {
            QTest::qWait(5);
            QCOMPARE(handler.requests, 0);
            socket.write(QByteArray(size / 2, 'a'));
            QTest::qWait(5);
            QCOMPARE(handler.requests, 0);
            socket.write(QByteArray(size - size / 2, 'a'));
        }
        QVERIFY(closedResponse(socket).startsWith("HTTP/1.1 200 "));
        QCOMPARE(handler.content, QByteArray(size, 'a'));
        QCOMPARE(handler.requests, 1);
        QCOMPARE(manager.opens, size >= 16 ? 1 : 0);
        QCOMPARE(manager.maps, manager.opens);
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
        QVERIFY(manager.file.isNull());
        QVERIFY(manager.filePath.isEmpty() || !QFileInfo::exists(manager.filePath));
        QVERIFY(exchange(manager, "GET / HTTP/1.1\r\n\r\n").startsWith("HTTP/1.1 401 "));
        QCOMPARE(handler.requests, 2); // Authentication remains in the application handler.
    }

    void multipartAndOneRequestPerConnection() {
        RecordingHandler handler;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        limits.maxBodyBytes = 256;
        QVERIFY(manager.setRequestLimits(limits));
        const QByteArray upload = "--fixture\r\nContent-Disposition: form-data; name=\"restore-file\"; filename=\"a.json\"\r\n\r\n{}\r\n--fixture--\r\n";
        QVERIFY(exchange(manager, "POST / HTTP/1.1\r\nContent-Type: multipart/form-data; boundary=fixture\r\nContent-Length: " +
            QByteArray::number(upload.size()) + "\r\n\r\n" + upload).startsWith("HTTP/1.1 200 "));
        QCOMPARE(handler.form.size(), 1);
        QCOMPARE(handler.form[0].second, QByteArray("{}"));
        QCOMPARE(manager.maps, 1);
        const auto response = exchange(manager, "POST / HTTP/1.1\r\nConnection: keep-alive\r\nContent-Length: 1\r\n\r\naGET /second HTTP/1.1\r\n\r\n");
        QVERIFY(response.startsWith("HTTP/1.1 200 "));
        QVERIFY(response.contains("Connection: close\r\n"));
        QCOMPARE(response.count("HTTP/1.1"), 1);
        QCOMPARE(handler.requests, 2);
        QCOMPARE(handler.content, QByteArray("a"));
    }

    void storageFailures_data() {
        QTest::addColumn<int>("fault");
        QTest::newRow("allocation-throws") << int(StorageManager::MemoryThrow);
        QTest::newRow("allocation-short") << int(StorageManager::MemoryShort);
        QTest::newRow("file-open") << int(StorageManager::Open);
        QTest::newRow("file-resize") << int(StorageManager::Resize);
        QTest::newRow("file-map") << int(StorageManager::Map);
        QTest::newRow("file-write") << int(StorageManager::Write);
    }

    void storageFailures() {
        QFETCH(int, fault);
        RecordingHandler handler;
        StorageManager manager(&handler);
        QVERIFY(manager.fixture.isValid());
        manager.fault = StorageManager::Fault(fault);
        QVERIFY(manager.setRequestLimits(smallLimits()));
        const int size = fault <= StorageManager::MemoryShort ? 1 : 16;
        const auto response = exchange(manager, "POST / HTTP/1.1\r\nContent-Length: " + QByteArray::number(size) + "\r\n\r\n" + QByteArray(size, 'a'));
        QVERIFY2(response.startsWith("HTTP/1.1 500 "), response.constData());
        QCOMPARE(handler.requests, 0);
        QVERIFY(until([&] { return manager.liveRequestCount() == 0; }));
        QCOMPARE(manager.reservedRequestBytes(), qint64(0));
        QVERIFY(manager.file.isNull());
        QCOMPARE(QDir(manager.fixture.path()).entryList(QDir::Files).size(), 0);
        if (fault == StorageManager::Resize) { QCOMPARE(manager.resizes, 1); QCOMPARE(manager.maps, 0); }
        if (fault == StorageManager::Map) { QCOMPARE(manager.resizes, 1); QCOMPARE(manager.maps, 1); }
        manager.fault = StorageManager::None;
        QVERIFY(exchange(manager, "POST / HTTP/1.1\r\nContent-Length: 16\r\n\r\n" + QByteArray(16, 'b')).startsWith("HTTP/1.1 200 "));
        QCOMPARE(handler.content, QByteArray(16, 'b'));
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
    }

    void aggregateBudgetAndDisconnect() {
        RecordingHandler handler;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        const auto fixed = limits.maxHeaderBytes + HTTPRequestLimits::SOCKET_BUFFER_BYTES;
        limits.maxReservedBytes = 2 * fixed + 50;
        QVERIFY(manager.setRequestLimits(limits));
        QTcpSocket first;
        QVERIFY(openClient(manager, first));
        first.write("POST / HTTP/1.1\r\nContent-Length: 32\r\n\r\na");
        QVERIFY(until([&] { return manager.resizes == 1; }));
        QCOMPARE(manager.reservedRequestBytes(), fixed + 32);
        const auto path = manager.filePath;
        QVERIFY(QFileInfo::exists(path));
        const auto response = exchange(manager, "POST / HTTP/1.1\r\nContent-Length: 32\r\n\r\n");
        QVERIFY(response.startsWith("HTTP/1.1 503 "));
        QCOMPARE(manager.opens, 1); // Refused before creating the second file.
        QCOMPARE(manager.maps, 0); // Incomplete files are never mapped.
        QVERIFY(until([&] { return manager.liveRequestCount() == 1; }));
        QCOMPARE(manager.reservedRequestBytes(), fixed + 32);
        first.abort();
        QVERIFY(until([&] { return manager.liveRequestCount() == 0; }));
        QCOMPARE(manager.reservedRequestBytes(), qint64(0));
        QVERIFY(!QFileInfo::exists(path));
        QCOMPARE(handler.requests, 0);

        // Exactly filling the aggregate budget is allowed; completed bodies stay
        // reserved while an asynchronous application handler owns the connection.
        limits.maxReservedBytes = fixed + 128;
        QVERIFY(manager.setRequestLimits(limits));
        handler.hold = true;
        QTcpSocket complete;
        QVERIFY(openClient(manager, complete));
        complete.write("POST / HTTP/1.1\r\nContent-Length: 128\r\n\r\n" + QByteArray(128, 'a'));
        QVERIFY(until([&] { return handler.requests == 1; }));
        QCOMPARE(manager.reservedRequestBytes(), limits.maxReservedBytes);
        QTcpSocket refused;
        QVERIFY(openClient(manager, refused));
        QVERIFY(until([&] { return refused.state() == QAbstractSocket::UnconnectedState; }));
        QCOMPARE(manager.findChildren<HTTPConnection*>().size(), 1);
        QCOMPARE(handler.requests, 1);
        handler.connection->respond(HTTPConnection::StatusCode200);
        QVERIFY(closedResponse(complete).startsWith("HTTP/1.1 200 "));
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
    }

    void connectionLimitAndManagerLifetime() {
        RecordingHandler handler;
        auto manager = std::make_unique<StorageManager>(&handler);
        auto limits = smallLimits();
        limits.maxConnections = 1;
        QVERIFY(manager->setRequestLimits(limits));
        QTcpSocket first;
        QVERIFY(openClient(*manager, first));
        QVERIFY(until([&] { return manager->liveRequestCount() == 1; }));
        QVERIFY(!manager->setRequestLimits(limits));
        // The callback observations must never see excess parser/socket children,
        // even transiently before the event loop processes deferred deletions.
        for (int i = 0; i < 8; ++i) {
            QTcpSocket refused;
            QVERIFY(openClient(*manager, refused));
            QVERIFY(until([&] { return refused.state() == QAbstractSocket::UnconnectedState; }));
            QCOMPARE(manager->findChildren<HTTPConnection*>().size(), 1);
            QCOMPARE(manager->findChildren<QTcpSocket*>().size(), 1);
            QCOMPARE(manager->liveRequestCount(), 1);
            QCOMPARE(manager->maxParserChildren, 1);
            QCOMPARE(manager->maxSocketChildren, 1);
        }
        first.write("POST / HTTP/1.1\r\nContent-Length: 32\r\n\r\na");
        QVERIFY(until([&] { return manager->resizes == 1; }));
        const auto path = manager->filePath;
        const auto file = manager->file;
        QVERIFY(QFileInfo::exists(path));
        manager.reset(); // Must delete connections while budget members are alive.
        QVERIFY(file.isNull());
        QVERIFY(!QFileInfo::exists(path));
        QVERIFY(until([&] { return first.state() == QAbstractSocket::UnconnectedState; }));
        QCOMPARE(handler.requests, 0);
    }

    void deferredConnectionAfterDisconnect() {
        RecordingHandler handler;
        handler.hold = true;
        StorageManager manager(&handler);
        QVERIFY(manager.setRequestLimits(smallLimits()));
        QTcpSocket socket;
        QVERIFY(openClient(manager, socket));
        const QByteArray data = "x=" + QByteArray(30, 'a');
        socket.write("POST / HTTP/1.1\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 32\r\n\r\n" + data);
        QVERIFY(until([&] { return handler.requests == 1; }));
        QCOMPARE(handler.connection->parseUrlEncodedForm().value("x"), QString(30, 'a'));
        handler.connection->socket()->abort(); // Real disconnected signal; deleteLater has not run yet.
        QVERIFY(handler.connection);
        QCOMPARE(handler.connection->requestContent(), QByteArray());
        QVERIFY(handler.connection->parseUrlEncodedForm().isEmpty());
        QCOMPARE(manager.liveRequestCount(), 0);
        QCOMPARE(manager.reservedRequestBytes(), qint64(0));
        QVERIFY(manager.file.isNull());
        QVERIFY(!QFileInfo::exists(manager.filePath));
        QCOMPARE(handler.content, data); // Only the explicit owning fixture copy survives.
    }

    void incompleteDeadlines_data() {
        QTest::addColumn<QByteArray>("initial");
        QTest::addColumn<bool>("idle");
        QTest::addColumn<bool>("trickle");
        QTest::newRow("no-bytes-header") << QByteArray() << false << false;
        QTest::newRow("partial-request-line") << QByteArray("GET / HTTP/") << false << true;
        QTest::newRow("partial-header") << QByteArray("GET / HTTP/1.1\r\nX: ") << false << true;
        QTest::newRow("idle-header") << QByteArray("GET / HTTP/1.1\r\nX: ") << true << false;
        QTest::newRow("incomplete-body") << QByteArray("POST / HTTP/1.1\r\nContent-Length: 128\r\n\r\na") << false << false;
        QTest::newRow("trickle-body") << QByteArray("POST / HTTP/1.1\r\nContent-Length: 128\r\n\r\na") << false << true;
        QTest::newRow("idle-body") << QByteArray("POST / HTTP/1.1\r\nContent-Length: 128\r\n\r\na") << true << false;
    }

    void incompleteDeadlines() {
        QFETCH(QByteArray, initial);
        QFETCH(bool, idle);
        QFETCH(bool, trickle);
        RecordingHandler handler;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        limits.headerDeadlineMs = 160;
        limits.requestDeadlineMs = 260;
        limits.idleDeadlineMs = idle ? 70 : 1000;
        QVERIFY(manager.setRequestLimits(limits));
        QTcpSocket socket;
        QVERIFY(openClient(manager, socket));
        socket.write(initial);
        QTimer sender;
        if (trickle) {
            connect(&sender, &QTimer::timeout, &socket, [&] { socket.write("a"); });
            sender.start(20);
        }
        QElapsedTimer elapsed;
        elapsed.start();
        const auto response = closedResponse(socket);
        sender.stop();
        QVERIFY2(response.startsWith("HTTP/1.1 408 "), response.constData());
        const int expected = idle ? 70 : initial.contains("Content-Length") ? 260 : 160;
        QVERIFY(elapsed.elapsed() >= expected - 30);
        QVERIFY(elapsed.elapsed() < expected + 600);
        QCOMPARE(handler.requests, 0);
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
        QVERIFY(manager.file.isNull());
        QVERIFY(manager.filePath.isEmpty() || !QFileInfo::exists(manager.filePath));
    }

    void totalDeadlineSpansHeadersAndBody() {
        RecordingHandler handler;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        limits.headerDeadlineMs = 240;
        limits.requestDeadlineMs = 300;
        limits.idleDeadlineMs = 1000;
        QVERIFY(manager.setRequestLimits(limits));
        QTcpSocket socket;
        QVERIFY(openClient(manager, socket));
        QElapsedTimer elapsed;
        elapsed.start();
        socket.write("POST / HTTP/1.1\r\n");
        QTest::qWait(180);
        socket.write("Content-Length: 128\r\n\r\na");
        QTimer sender;
        connect(&sender, &QTimer::timeout, &socket, [&] { socket.write("a"); });
        sender.start(20);
        QVERIFY(closedResponse(socket).startsWith("HTTP/1.1 408 "));
        sender.stop();
        QVERIFY(elapsed.elapsed() >= 270);
        QVERIFY(elapsed.elapsed() < 430); // A fresh 300 ms body timer would expire after 480 ms.
        QCOMPARE(handler.requests, 0);
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
    }

    void largeValidBodyAndDeferredHandler() {
        RecordingHandler handler;
        handler.hold = true;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        limits.maxBodyBytes = 200000;
        limits.maxReservedBytes = 400000;
        limits.requestDeadlineMs = 500;
        QVERIFY(manager.setRequestLimits(limits));
        QTcpSocket socket;
        QVERIFY(openClient(manager, socket));
        const QByteArray data(200000, 'a');
        socket.write("POST / HTTP/1.1\r\nContent-Length: 200000\r\n\r\n" + data);
        QVERIFY(until([&] { return handler.requests == 1; }));
        QCOMPARE(handler.content, data); // More than three bounded socket/read chunks.
        QTest::qWait(550); // Parse deadlines must not expire an asynchronous handler.
        QCOMPARE(socket.state(), QAbstractSocket::ConnectedState);
        QVERIFY(handler.connection);
        QCOMPARE(handler.connection->requestContent(), data);
        handler.connection->respond(HTTPConnection::StatusCode200);
        QVERIFY(closedResponse(socket).startsWith("HTTP/1.1 200 "));
        QVERIFY(until([&] { return manager.reservedRequestBytes() == 0; }));
    }

    void timersAndCleanupInOwningThread() {
        QThread worker;
        auto context = new QObject;
        context->moveToThread(&worker);
        connect(&worker, &QThread::finished, context, &QObject::deleteLater);
        worker.start();
        const auto cleanup = qScopeGuard([&] { worker.quit(); worker.wait(); });
        StorageManager* manager = nullptr;
        quint16 port = 0;
        QMetaObject::invokeMethod(context, [&] {
            manager = new StorageManager(nullptr);
            manager->setParent(context);
            auto limits = smallLimits();
            limits.headerDeadlineMs = 100;
            limits.requestDeadlineMs = 220;
            limits.idleDeadlineMs = 100;
            if (manager->setRequestLimits(limits)) { port = manager->serverPort(); }
        }, Qt::BlockingQueuedConnection);
        QVERIFY(port != 0);
        QTcpSocket socket;
        socket.connectToHost(QHostAddress::LocalHost, port);
        QVERIFY(until([&] { return socket.state() == QAbstractSocket::ConnectedState; }));
        socket.write("POST / HTTP/1.1\r\nContent-Length: 128\r\n\r\na");
        socket.flush();
        bool initialized = false;
        QString path;
        QVERIFY(until([&] {
            QMetaObject::invokeMethod(context, [&] {
                if (manager->resizes != 1) { return; }
                const auto connections = manager->findChildren<HTTPConnection*>();
                if (connections.size() != 1) { return; }
                const auto timers = connections[0]->findChildren<QTimer*>();
                initialized = timers.size() == 3 && connections[0]->thread() == &worker;
                for (auto timer : timers) {
                    initialized = initialized && timer->parent() == connections[0] && timer->thread() == &worker;
                }
                path = manager->filePath;
            }, Qt::BlockingQueuedConnection);
            return initialized;
        }));
        QVERIFY(QFileInfo::exists(path));
        QTimer sender;
        connect(&sender, &QTimer::timeout, &socket, [&] { socket.write("a"); });
        sender.start(20);
        QVERIFY(closedResponse(socket).startsWith("HTTP/1.1 408 "));
        sender.stop();
        qint64 reserved = -1;
        QMetaObject::invokeMethod(context, [&] { reserved = manager->reservedRequestBytes(); }, Qt::BlockingQueuedConnection);
        QCOMPARE(reserved, qint64(0));
        QVERIFY(!QFileInfo::exists(path));
        // Context destruction on worker shutdown also destroys the manager there.
    }

    void invalidPolicy() {
        RecordingHandler handler;
        StorageManager manager(&handler);
        auto limits = smallLimits();
        limits.maxBodyBytes = std::numeric_limits<int>::max();
        QVERIFY(!manager.setRequestLimits(limits));
        limits = smallLimits(); limits.maxHeaderBytes = -1;
        QVERIFY(!manager.setRequestLimits(limits));
        limits = smallLimits(); limits.maxReservedBytes = 1;
        QVERIFY(!manager.setRequestLimits(limits));
        limits = smallLimits(); limits.idleDeadlineMs = 0;
        QVERIFY(!manager.setRequestLimits(limits));
        limits = smallLimits(); limits.maxConnections = 0;
        QVERIFY(!manager.setRequestLimits(limits));
        limits = smallLimits(); limits.maxReservedBytes = std::numeric_limits<qint64>::max();
        QVERIFY(manager.setRequestLimits(limits));
        QVERIFY(exchange(manager, "GET / HTTP/1.1\r\n\r\n").startsWith("HTTP/1.1 200 "));
    }

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
