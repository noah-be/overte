//
//  HTTPConnection.cpp
//  libraries/embedded-webserver/src
//
//  Created by Stephen Birarda on 1/16/14.
//  Copyright 2014 High Fidelity, Inc.
//  Copyright 2022 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "HTTPConnection.h"

#include <algorithm>
#include <limits>
#include <new>

#include <QBuffer>
#include <QCryptographicHash>
#include <QTcpSocket>
#include <QUrlQuery>

#include "EmbeddedWebserverLogging.h"
#include "HTTPManager.h"

const char* HTTPConnection::StatusCode200 = "200 OK";
const char* HTTPConnection::StatusCode204 = "204 No Content";
const char* HTTPConnection::StatusCode301 = "301 Moved Permanently";
const char* HTTPConnection::StatusCode302 = "302 Found";
const char* HTTPConnection::StatusCode400 = "400 Bad Request";
const char* HTTPConnection::StatusCode401 = "401 Unauthorized";
const char* HTTPConnection::StatusCode403 = "403 Forbidden";
const char* HTTPConnection::StatusCode404 = "404 Not Found";
const char* HTTPConnection::StatusCode500 = "500 Internal server error";
const char* HTTPConnection::DefaultContentType = "text/plain; charset=ISO-8859-1";


class MemoryStorage : public HTTPConnection::Storage {
public:
    explicit MemoryStorage(QByteArray array) : _array(std::move(array)) {}
    virtual ~MemoryStorage() = default;

    const QByteArray& content() const override { return _array; }
    qint64 bytesLeftToWrite() const override { return _array.size() - _bytesWritten; }
    bool write(const QByteArray& data) override;

private:
    QByteArray _array;
    qint64 _bytesWritten { 0 };
};

bool MemoryStorage::write(const QByteArray& data) {
    if (data.size() > bytesLeftToWrite()) {
        return false;
    }
    memcpy(_array.data() + _bytesWritten, data.data(), data.size());
    _bytesWritten += data.size();
    return true;
}


class FileStorage : public HTTPConnection::Storage {
public:
    FileStorage(std::unique_ptr<QTemporaryFile> file, qint64 size, HTTPManager* manager);
    virtual ~FileStorage();

    const QByteArray& content() const override { return _wrapperArray; };
    qint64 bytesLeftToWrite() const override { return _mappedMemorySize - _bytesWritten; }
    bool write(const QByteArray& data) override;
    bool finish() override;

private:
    // Initialized once after the checked writes; only const access thereafter.
    QByteArray _wrapperArray;
    std::unique_ptr<QTemporaryFile> _file;

    uchar* _mappedMemoryAddress { nullptr };
    const qint64 _mappedMemorySize { 0 };
    qint64 _bytesWritten { 0 };
    HTTPManager* _manager;
};

// Use QByteArray::fromRawData to avoid a new allocation and access the already existing
// memory directly as long as all operations on the array are const.
FileStorage::FileStorage(std::unique_ptr<QTemporaryFile> file, qint64 size, HTTPManager* manager) :
    _file(std::move(file)),
    _mappedMemorySize(size),
    _manager(manager)
{
}

FileStorage::~FileStorage() {
    if (_mappedMemoryAddress) {
        _file->unmap(_mappedMemoryAddress);
    }
    _file->close();
}

bool FileStorage::write(const QByteArray& data) {
    if (data.size() > bytesLeftToWrite()) {
        return false;
    }
    // Checked file I/O avoids a SIGBUS from writing sparse mapped pages when
    // the temporary filesystem is full. Map only fully written content.
    if (_file->write(data) != data.size()) {
        return false;
    }
    _bytesWritten += data.size();
    return true;
}

bool FileStorage::finish() {
    if (bytesLeftToWrite() != 0 || !_file->flush()) {
        return false;
    }
    _mappedMemoryAddress = _manager->mapRequestFile(*_file, _mappedMemorySize);
    if (!_mappedMemoryAddress) {
        return false;
    }
    _wrapperArray = QByteArray::fromRawData(reinterpret_cast<char*>(_mappedMemoryAddress), static_cast<int>(_mappedMemorySize));
    return true;
}


HTTPConnection::HTTPConnection(QTcpSocket* socket, HTTPManager* parentManager) :
    QObject(parentManager),
    _parentManager(parentManager),
    _socket(socket),
    _address(socket->peerAddress()),
    _limits(parentManager->requestLimits()),
    _requestTimer(new QTimer(this)),
    _headerTimer(new QTimer(this)),
    _idleTimer(new QTimer(this))
{
    // take over ownership of the socket
    _socket->setParent(this);
    _socket->setReadBufferSize(HTTPRequestLimits::SOCKET_BUFFER_BYTES);

    // connect initial slots
    connect(socket, &QAbstractSocket::readyRead, this, &HTTPConnection::readRequest);
    auto cleanup = [this] {
        _finished = true;
        releaseResources();
        deleteLater();
    };
    connect(socket, &QAbstractSocket::errorOccurred, this, cleanup);
    connect(socket, &QAbstractSocket::disconnected, this, cleanup);

    _elapsed.start();
    for (auto timer : { _requestTimer, _headerTimer, _idleTimer }) {
        timer->setSingleShot(true);
        timer->setTimerType(Qt::PreciseTimer);
        connect(timer, &QTimer::timeout, this, [this] { failRequest("408 Request Timeout"); });
    }
    _admitted = _parentManager->acquireRequest();
    if (!_admitted) {
        failRequest("503 Service Unavailable");
        return;
    }
    _requestTimer->start(_limits.requestDeadlineMs);
    _headerTimer->start(_limits.headerDeadlineMs);
    _idleTimer->start(_limits.idleDeadlineMs);
}

HTTPConnection::~HTTPConnection() {
    releaseResources();
    // log the destruction
    if (_socket->error() != QAbstractSocket::UnknownSocketError
        && _socket->error() != QAbstractSocket::RemoteHostClosedError) {
        qCDebug(embeddedwebserver) << _socket->errorString() << "-" << _socket->error();
    }
}

void HTTPConnection::releaseStorage() {
    _requestContent.reset(); // Unmap/remove the temporary file before returning its budget.
    _parentManager->releaseRequestBody(_reservedBodyBytes);
    _reservedBodyBytes = 0;
}

void HTTPConnection::releaseResources() {
    _requestTimer->stop();
    _headerTimer->stop();
    _idleTimer->stop();
    releaseStorage();
    if (_admitted) {
        _parentManager->releaseRequest();
        _admitted = false;
    }
}

void HTTPConnection::failRequest(const char* status) {
    if (_finished) {
        return;
    }
    _finished = true;
    _requestTimer->stop();
    _headerTimer->stop();
    _idleTimer->stop();
    disconnect(_socket, &QTcpSocket::readyRead, this, nullptr);
    releaseStorage();
    _requestHeaders.clear();
    if (_responseStarted || _socket->state() != QAbstractSocket::ConnectedState) {
        // A dispatch failure after response headers must not append a second
        // response or keep a streaming response alive with its request budget.
        disconnect(_socket, &QTcpSocket::bytesWritten, this, nullptr);
        _socket->abort();
        releaseResources();
        deleteLater();
        return;
    }
    try {
        respond(status);
    } catch (const std::bad_alloc&) {
        _socket->abort();
        deleteLater();
    }
    // Do not retain a rejected socket if the peer never drains its response.
    QTimer::singleShot(1000, this, [this] { _socket->abort(); deleteLater(); });
}

bool HTTPConnection::withinDeadline() {
    if (_finished) {
        return false;
    }
    const auto elapsed = _elapsed.elapsed();
    if (elapsed >= _limits.requestDeadlineMs ||
        (!_headersComplete && elapsed >= _limits.headerDeadlineMs) ||
        elapsed - _lastProgressMs >= _limits.idleDeadlineMs) {
        failRequest("408 Request Timeout");
        return false;
    }
    return true;
}

bool HTTPConnection::readHeaderLine(QByteArray& line) {
    if (!withinDeadline()) {
        return false;
    }
    const auto remaining = _limits.maxHeaderBytes - _headerBytes;
    if (_socket->bytesAvailable() > 0) {
        _lastProgressMs = _elapsed.elapsed();
        _idleTimer->start(_limits.idleDeadlineMs);
    }
    if (!_socket->canReadLine()) {
        // A full socket buffer with no newline must be rejected too, rather than
        // waiting forever for a newline that cannot enter the bounded buffer.
        if (_socket->bytesAvailable() >= remaining ||
            _socket->bytesAvailable() >= HTTPRequestLimits::SOCKET_BUFFER_BYTES) {
            failRequest("431 Request Header Fields Too Large");
        }
        return false;
    }
    line = _socket->readLine(remaining + 2); // At most remaining + 1 payload bytes.
    if (line.size() > remaining) {
        failRequest("431 Request Header Fields Too Large");
        return false;
    }
    _headerBytes += line.size();
    if (!line.endsWith("\r\n")) {
        failRequest(StatusCode400);
        return false;
    }
    line.chop(2);
    return true;
}

bool HTTPConnection::prepareStorage(qint64 size) {
    if (!_parentManager->reserveRequestBody(size)) {
        failRequest("503 Service Unavailable");
        return false;
    }
    _reservedBodyBytes = size;
    if (size == 0 || size < _limits.memoryBodyThreshold) {
        auto array = _parentManager->allocateRequestMemory(static_cast<int>(size));
        if (array.size() != size) {
            failRequest(StatusCode500);
            return false;
        }
        _requestContent = std::make_unique<MemoryStorage>(std::move(array));
    } else {
        auto file = std::make_unique<QTemporaryFile>();
        if (!_parentManager->openRequestFile(*file) || !file->isOpen() ||
            !_parentManager->resizeRequestFile(*file, size)) {
            file.reset();
            failRequest(StatusCode500);
            return false;
        }
        _requestContent = std::make_unique<FileStorage>(std::move(file), size, _parentManager);
    }
    return true;
}

void HTTPConnection::finishRequest() {
    if (!withinDeadline()) {
        return;
    }
    _finished = true;
    _requestTimer->stop();
    _headerTimer->stop();
    _idleTimer->stop();
    disconnect(_socket, &QTcpSocket::readyRead, this, nullptr);
    try {
        _parentManager->handleHTTPRequest(this, _requestUrl);
    } catch (const std::bad_alloc&) {
        // Parsing has finished, but failed synchronous dispatch still needs
        // terminal cleanup. Successful asynchronous handlers keep the normal
        // finished state, stopped parsing timers, and live body reservation.
        _finished = false;
        failRequest(StatusCode500);
    }
}

QHash<QString, QString> HTTPConnection::parseUrlEncodedForm() {
    // make sure we have the correct MIME type
    QList<QByteArray> elements = requestHeader("Content-Type").split(';');

    QString contentType = elements.at(0).trimmed();
    if (contentType != "application/x-www-form-urlencoded") {
        return QHash<QString, QString>();
    }

    QUrlQuery form { requestContent() };
    QHash<QString, QString> pairs;
    for (auto pair : form.queryItems()) {
        auto key = QUrl::fromPercentEncoding(pair.first.toLatin1().replace('+', ' '));
        auto value = QUrl::fromPercentEncoding(pair.second.toLatin1().replace('+', ' '));
        pairs[key] = value;
    }

    return pairs;
}

QList<FormData> HTTPConnection::parseFormData() const {
    // make sure we have the correct MIME type
    QList<QByteArray> elements = requestHeader("Content-Type").split(';');

    QString contentType = elements.at(0).trimmed();

    if (contentType != "multipart/form-data") {
        return QList<FormData>();
    }

    // retrieve the boundary marker
    QByteArray boundary;
    for (int ii = 1, nn = elements.size(); ii < nn; ii++) {
        QByteArray element = elements.at(ii).trimmed();
        if (element.startsWith("boundary")) {
            boundary = element.mid(element.indexOf('=') + 1).trimmed();
            break;
        }
    }

    QByteArray start = "--" + boundary;
    QByteArray end = "\r\n--" + boundary + "--\r\n";

    QList<FormData> data;
    QBuffer buffer(const_cast<QByteArray*>(&requestContent()));
    buffer.open(QIODevice::ReadOnly);
    while (buffer.canReadLine()) {
        QByteArray line = buffer.readLine().trimmed();
        if (line == start) {
            FormData datum;
            while (buffer.canReadLine()) {
                QByteArray line = buffer.readLine().trimmed();
                if (line.isEmpty()) {
                    // content starts after this line
                    int idx = requestContent().indexOf(end, buffer.pos());
                    if (idx == -1) {
                        qWarning() << "Missing end boundary." << _address;
                        return data;
                    }
                    datum.second = QByteArray(requestContent().data() + buffer.pos(),
                                                           idx - buffer.pos());
                    data.append(datum);
                    buffer.seek(idx + end.length());

                } else {
                    // it's a header element
                    int idx = line.indexOf(':');
                    if (idx == -1) {
                        qWarning() << "Invalid form header line." << _address;
                        continue;
                    }
                    datum.first.insert(line.left(idx).trimmed(), line.mid(idx + 1).trimmed());
                }
            }
        }
    }

    return data;
}

void HTTPConnection::respond(const char* code, const QByteArray& content, const char* contentType, const Headers& headers) {
    respondWithStatusAndHeaders(code, contentType, headers, content.size());

    _socket->write(content);

    _socket->disconnectFromHost();

    // make sure we receive no further read notifications
    disconnect(_socket, &QTcpSocket::readyRead, this, nullptr);
}

void HTTPConnection::respond(const char* code, std::unique_ptr<QIODevice> device, const char* contentType, const Headers& headers) {
    _responseDevice = std::move(device);

    if (_responseDevice->isSequential()) {
        qWarning() << "Error responding to HTTPConnection: sequential IO devices not supported";
        respondWithStatusAndHeaders(StatusCode500, contentType, headers, 0);
        _socket->disconnect(SIGNAL(readyRead()), this);
        _socket->disconnectFromHost();
        return;
    }

    int totalToBeWritten = _responseDevice->size();
    respondWithStatusAndHeaders(code, contentType, headers, totalToBeWritten);

    if (_responseDevice->atEnd()) {
        _socket->disconnectFromHost();
    } else {
        connect(_socket, &QTcpSocket::bytesWritten, this, [this, totalToBeWritten](size_t bytes) mutable {
            constexpr size_t HTTP_RESPONSE_CHUNK_SIZE = 1024 * 10;
            if (!_responseDevice->atEnd()) {
                totalToBeWritten -= _socket->write(_responseDevice->read(HTTP_RESPONSE_CHUNK_SIZE));
                if (_responseDevice->atEnd()) {
                    _socket->disconnectFromHost();
                    disconnect(_socket, &QTcpSocket::bytesWritten, this, nullptr);
                }
            }
        });

    }

    // make sure we receive no further read notifications
    disconnect(_socket, &QTcpSocket::readyRead, this, nullptr);
}

void HTTPConnection::respondWithStatusAndHeaders(const char* code, const char* contentType, const Headers& headers, qint64 contentLength) {
    _responseStarted = true; // Even a partial/throwing first write forbids another response.
    _socket->write("HTTP/1.1 ");

    _socket->write(code);
    _socket->write("\r\n");

    for (Headers::const_iterator it = headers.constBegin(), end = headers.constEnd();
            it != end; it++) {
        _socket->write(it.key());
        _socket->write(": ");
        _socket->write(it.value());
        _socket->write("\r\n");
    }

    if (contentLength > 0) {
        _socket->write("Content-Length: ");
        _socket->write(QByteArray::number(contentLength));
        _socket->write("\r\n");

        _socket->write("Content-Type: ");
        _socket->write(contentType);
        _socket->write("\r\n");
    }
    _socket->write("Connection: close\r\n\r\n");
}

namespace {
bool isHeaderToken(const QByteArray& token) {
    if (token.isEmpty()) {
        return false;
    }
    for (char c : token) {
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || QByteArray("!#$%&'*+-.^_`|~").contains(c))) {
            return false;
        }
    }
    return true;
}

bool parseLength(const QByteArray& value, qint64& length) {
    length = 0;
    if (value.isEmpty()) {
        return false;
    }
    for (char c : value) {
        if (c < '0' || c > '9' || length > (std::numeric_limits<qint64>::max() - (c - '0')) / 10) {
            return false;
        }
        length = length * 10 + (c - '0');
    }
    return true;
}
} // namespace

void HTTPConnection::readRequest() try {
    QByteArray line;
    if (!readHeaderLine(line)) {
        return;
    }
    const auto parts = line.split(' ');
    if (parts.size() != 3 || parts[1].isEmpty() ||
        (parts[2] != "HTTP/1.1" && parts[2] != "HTTP/1.0")) {
        failRequest(StatusCode400);
        return;
    }
    const auto& method = parts[0];
    if (method == "HEAD") {
        _requestOperation = QNetworkAccessManager::HeadOperation;
    } else if (method == "GET") {
        _requestOperation = QNetworkAccessManager::GetOperation;
    } else if (method == "PUT") {
        _requestOperation = QNetworkAccessManager::PutOperation;
    } else if (method == "POST") {
        _requestOperation = QNetworkAccessManager::PostOperation;
    } else if (method == "DELETE") {
        _requestOperation = QNetworkAccessManager::DeleteOperation;
    } else {
        failRequest(StatusCode400);
        return;
    }
    for (char c : parts[1]) {
        if (static_cast<uchar>(c) <= 32 || c == 127) {
            failRequest(StatusCode400);
            return;
        }
    }
    _requestUrl.setUrl(QString::fromUtf8(parts[1]));
    if (!_requestUrl.isValid()) {
        failRequest(StatusCode400);
        return;
    }
    disconnect(_socket, &QTcpSocket::readyRead, this, nullptr);
    connect(_socket, &QTcpSocket::readyRead, this, &HTTPConnection::readHeaders);
    readHeaders();
} catch (const std::bad_alloc&) {
    failRequest(StatusCode500);
}

void HTTPConnection::readHeaders() try {
    QByteArray line;
    while (readHeaderLine(line)) {
        if (line.isEmpty()) {
            _headersComplete = true;
            _headerTimer->stop();
            disconnect(_socket, &QTcpSocket::readyRead, this, nullptr);
            qint64 length = 0;
            if (_requestHeaders.contains("content-length") &&
                !parseLength(_requestHeaders.value("content-length"), length)) {
                failRequest(StatusCode400);
                return;
            }
            if (length > _limits.maxBodyBytes || length > std::numeric_limits<int>::max() - qint64(1)) {
                failRequest("413 Payload Too Large");
                return;
            }
            if (!prepareStorage(length)) {
                return;
            }
            connect(_socket, &QTcpSocket::readyRead, this, &HTTPConnection::readContent);
            readContent();
            return;
        }
        const int colon = line.indexOf(':');
        const auto key = line.left(colon).toLower();
        if (colon < 1 || !isHeaderToken(key)) { // Includes obsolete folded headers.
            failRequest(StatusCode400);
            return;
        }
        auto value = line.mid(colon + 1);
        for (char c : value) {
            if ((static_cast<uchar>(c) < 32 && c != '\t') || c == 127) {
                failRequest(StatusCode400);
                return;
            }
        }
        value = value.trimmed(); // Only SP/HTAB can remain as whitespace here.
        // This server never supported chunked bodies. Reject all transfer codings
        // and repeated lengths (even identical) rather than accepting ambiguity.
        if (key == "transfer-encoding" || (key == "content-length" && _requestHeaders.contains(key))) {
            failRequest(StatusCode400);
            return;
        }
        if (_requestHeaders.contains(key)) {
            _requestHeaders[key].append(", ");
            _requestHeaders[key].append(value);
        } else {
            _requestHeaders.insert(key, value);
        }
    }
} catch (const std::bad_alloc&) {
    failRequest(StatusCode500);
}

void HTTPConnection::readContent() try {
    if (!withinDeadline()) {
        return;
    }
    // Bound the transient read allocation independently of the declared body size.
    const auto size = std::min({ _socket->bytesAvailable(), _requestContent->bytesLeftToWrite(),
                                HTTPRequestLimits::SOCKET_BUFFER_BYTES });
    if (size > 0) {
        const auto data = _socket->read(size);
        if (data.size() != size || !_requestContent->write(data)) {
            failRequest(StatusCode500);
            return;
        }
        _lastProgressMs = _elapsed.elapsed();
        _idleTimer->start(_limits.idleDeadlineMs);
    }
    if (_requestContent->bytesLeftToWrite() == 0) {
        if (!_requestContent->finish()) {
            failRequest(StatusCode500);
            return;
        }
        finishRequest();
    } else if (_socket->bytesAvailable() > 0) {
        // Yield to the event loop so large bodies cannot starve deadline timers.
        QMetaObject::invokeMethod(this, "readContent", Qt::QueuedConnection);
    }
} catch (const std::bad_alloc&) {
    failRequest(StatusCode500);
}
