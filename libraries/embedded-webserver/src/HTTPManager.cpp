//
//  HTTPManager.cpp
//  libraries/embedded-webserver/src
//
//  Created by Stephen Birarda on 1/16/14.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "HTTPManager.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QDebug>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QMimeDatabase>
#include <QtNetwork/QTcpSocket>

#include "HTTPConnection.h"
#include "EmbeddedWebserverLogging.h"

const int SOCKET_ERROR_EXIT_CODE = 2;
const int SOCKET_CHECK_INTERVAL_IN_MS = 30000;

namespace {

bool isWithinDocumentRoot(const QString& root, const QString& path) {
    // Include the separator: a similarly named sibling is not a descendant.
    const QString prefix = root.endsWith('/') ? root : root + '/';
    return path == root || path.startsWith(prefix);
}

bool resolveDocumentPath(const QString& root, const QString& path, QString& canonicalPath) {
    canonicalPath.clear();
    if (path.contains(QChar(0x00)) ||
        !isWithinDocumentRoot(root, QDir::cleanPath(QFileInfo(path).absoluteFilePath()))) {
        return false;
    }
    canonicalPath = QFileInfo(path).canonicalFilePath();
    // Missing targets stay unresolved (404/empty SSI). Symlinks are allowed only
    // when their resolved target remains within the canonical document root.
    return canonicalPath.isEmpty() || isWithinDocumentRoot(root, canonicalPath);
}

} // namespace

HTTPManager::HTTPManager(const QHostAddress& listenAddress, quint16 port, const QString& documentRoot, HTTPRequestHandler* requestHandler) :
    _listenAddress(listenAddress),
    _documentRoot(documentRoot),
    _requestHandler(requestHandler),
    _port(port)
{
    bindSocket();

    _isListeningTimer = new QTimer(this);
    connect(_isListeningTimer, &QTimer::timeout, this, &HTTPManager::isTcpServerListening);
    _isListeningTimer->start(SOCKET_CHECK_INTERVAL_IN_MS);
}

void HTTPManager::incomingConnection(qintptr socketDescriptor) {
    QTcpSocket* socket = new QTcpSocket(this);

    if (socket->setSocketDescriptor(socketDescriptor)) {
        new HTTPConnection(socket, this);
    } else {
        delete socket;
    }
}

bool HTTPManager::handleHTTPRequest(HTTPConnection* connection, const QUrl& url, bool skipSubHandler) {
    // Reject paths with embedded NULs
    if (url.path().contains(QChar(0x00))) {
        connection->respond(HTTPConnection::StatusCode400, "Embedded NULs not allowed in requests");
        qCWarning(embeddedwebserver) << "Received a request with embedded NULs";
        return true;
    }

    if (!skipSubHandler && requestHandledByRequestHandler(connection, url)) {
        // this request was handled by our request handler object
        // so we don't need to attempt to do so in the document root
        return true;
    }

    const QFileInfo documentRootInfo(_documentRoot);
    const QString documentRoot = documentRootInfo.canonicalFilePath();
    if (!_documentRoot.isEmpty() && documentRootInfo.isDir() && !documentRoot.isEmpty()) {
        // check to see if there is a file to serve from the document root for this path
        QString subPath = url.path();

        // remove any slash at the beginning of the path
        if (subPath.startsWith('/')) {
            subPath.remove(0, 1);
        }

        const QString requestedFilePath = QDir(documentRoot).filePath(subPath);
        QString absoluteFilePath;
        if (!resolveDocumentPath(documentRoot, requestedFilePath, absoluteFilePath)) {
            connection->respond(HTTPConnection::StatusCode400, "Requested path outside document root");
            return true;
        }
        QString filePath;
        QString servedFilename = requestedFilePath;
        QFileInfo pathFileInfo(absoluteFilePath);

        if (!absoluteFilePath.isEmpty() && pathFileInfo.isFile() && !subPath.endsWith('/')) {
            filePath = absoluteFilePath;
        } else if (!absoluteFilePath.isEmpty() && subPath.size() > 0 && !subPath.endsWith('/') && pathFileInfo.isDir()) {
            // this could be a directory with a trailing slash
            // send a redirect to the path with a slash so we can
            QString redirectLocation = '/' + subPath + '/';

            if (!url.query().isEmpty()) {
                redirectLocation += "?" + url.query();
            }

            QHash<QByteArray, QByteArray> redirectHeader;
            redirectHeader.insert(QByteArray("Location"), redirectLocation.toUtf8());

            connection->respond(HTTPConnection::StatusCode302, "", HTTPConnection::DefaultContentType, redirectHeader);
            return true;
        }

        // if the last thing is a trailing slash then we want to look for index file
        if (!absoluteFilePath.isEmpty() && pathFileInfo.isDir() && (subPath.endsWith('/') || subPath.size() == 0)) {
            QStringList possibleIndexFiles = QStringList() << "index.html" << "index.shtml";

            foreach (const QString& possibleIndexFilename, possibleIndexFiles) {
                QString indexPath;
                if (!resolveDocumentPath(documentRoot, QDir(absoluteFilePath).filePath(possibleIndexFilename), indexPath)) {
                    connection->respond(HTTPConnection::StatusCode400, "Requested path outside document root");
                    return true;
                }
                if (!indexPath.isEmpty() && QFileInfo(indexPath).isFile()) {
                    filePath = indexPath;
                    servedFilename = possibleIndexFilename;
                    break;
                }
            }
        }

        if (!filePath.isEmpty()) {
            // file exists, serve it
            static QMimeDatabase mimeDatabase;

            auto localFile = std::unique_ptr<QFile>(new QFile(filePath));
            if (!localFile->open(QIODevice::ReadOnly)) {
                connection->respond(HTTPConnection::StatusCode404, "Resource not found.");
                return true;
            }
            QByteArray localFileData;

            // Preserve the requested/index filename's MIME and SSI semantics
            // even when the file is a symlink with a differently named target.
            QFileInfo localFileInfo(servedFilename);

            if (localFileInfo.completeSuffix() == "shtml") {
                localFileData = localFile->readAll();
                // this is a file that may have some SSI statements
                // the only thing we support is the include directive, but check the contents for that

                // setup our static QRegExp that will catch <!--#include virtual ... --> and <!--#include file .. --> directives
                const QString includeRegExpString = "<!--\\s*#include\\s+(virtual|file)\\s?=\\s?\"(\\S+)\"\\s*-->";
                QRegExp includeRegExp(includeRegExpString);

                int matchPosition = 0;

                QString localFileString = QString::fromUtf8(localFileData.constData(), localFileData.size());

                while ((matchPosition = includeRegExp.indexIn(localFileString, matchPosition)) != -1) {
                    // check if this is a file or virtual include
                    bool isFileInclude = includeRegExp.cap(1) == "file";

                    // File includes are relative to the resolved served file;
                    // virtual includes are relative to the document root.
                    // Keep a leading slash root-relative as in the previous
                    // concatenation-based include handling, not OS-absolute.
                    const QString includeCandidate = (isFileInclude ? QFileInfo(filePath).path() : documentRoot)
                        + "/" + includeRegExp.cap(2);
                    QString includeFilePath;
                    QString replacementString;
                    if (resolveDocumentPath(documentRoot, includeCandidate, includeFilePath) &&
                        !includeFilePath.isEmpty() && QFileInfo(includeFilePath).isFile()) {
                        QFile includedFile(includeFilePath);
                        if (includedFile.open(QIODevice::ReadOnly)) {
                            replacementString = QString(includedFile.readAll());
                        }
                    } else {
                        qCDebug(embeddedwebserver) << "SSI include directive referenced an unavailable file";
                    }

                    // replace the match with the contents of the file, or an empty string if the file was not found
                    localFileString.replace(matchPosition, includeRegExp.matchedLength(), replacementString);

                    // Do not recursively expand included content, and do not skip
                    // adjacent directives after a shorter/empty replacement.
                    matchPosition += replacementString.size();
                }

                localFileData = localFileString.toLocal8Bit();
            }

            // if this is an shtml, html or htm file just make the MIME type match HTML so browsers aren't confused
            // otherwise use the mimeDatabase to look it up
            auto suffix = localFileInfo.suffix();
            auto mimeType = (suffix == "shtml" || suffix == "html" || suffix == "htm")
                ? QString { "text/html" }
                // Inspect the already opened, boundary-checked file rather
                // than letting MIME detection open the requested path again.
                : mimeDatabase.mimeTypeForFileNameAndData(servedFilename, localFile.get()).name();

            if (localFileData.isNull()) {
                connection->respond(HTTPConnection::StatusCode200, std::move(localFile), qPrintable(mimeType));
            } else {
                connection->respond(HTTPConnection::StatusCode200, localFileData, qPrintable(mimeType));
            }

            return true;
        }
    }

    // respond with a 404
    connection->respond(HTTPConnection::StatusCode404, "Resource not found.");

    return true;
}

bool HTTPManager::requestHandledByRequestHandler(HTTPConnection* connection, const QUrl& url) {
    return _requestHandler && _requestHandler->handleHTTPRequest(connection, url);
}

void HTTPManager::isTcpServerListening() {
    if (!isListening()) {
        qCWarning(embeddedwebserver) << "Socket on port " << QString::number(_port) << " is no longer listening";
        bindSocket();
    }
}

bool HTTPManager::bindSocket() {
    qCDebug(embeddedwebserver) << "Attempting to bind TCP socket on port " << QString::number(_port);

    if (listen(_listenAddress, _port)) {
        qCDebug(embeddedwebserver) << "TCP socket is listening on" << serverAddress() << "and port" << serverPort();

        return true;
    } else {
        QString errorMessage = "Failed to open HTTP server socket: " + errorString() + ", can't continue";
        QMetaObject::invokeMethod(this, "queuedExit", Qt::QueuedConnection, Q_ARG(QString, errorMessage));
        return false;
    }
}

void HTTPManager::queuedExit(QString errorMessage) {
    if (!errorMessage.isEmpty()) {
        qCCritical(embeddedwebserver) << qPrintable(errorMessage);
    }
    QCoreApplication::exit(SOCKET_ERROR_EXIT_CODE);
}
