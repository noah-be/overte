// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "services.h"
#include <RequestCancellation.h>
#include <QNetworkAccessManager>
#include <QJsonObject>
#include <QJsonDocument>
#include <QBuffer>
#include <QHttpMultiPart>
#include <QThread>
struct AddressManager { QUrl currentPublicAddress() { return QUrl("hifi://place/path"); } QString currentShareableAddress() { return "hifi://place/path"; } };
namespace AccountManagerAuth { enum Type {Required}; }
struct JSONCallbackParameters {
    JSONCallbackParameters(QObject*,const char*,const char*) {}
    overte::network::RequestTicket requestTicket;
};
class AccountManager : public QObject {
    Q_OBJECT
public:
    struct Info { QString getUsername() { return "Snapshot contract"; } };
    Info getAccountInfo() { return {}; }
    int calls {0};QByteArray lastBody;overte::network::RequestTicket lastTicket;
    void sendRequest(QString,AccountManagerAuth::Type,QNetworkAccessManager::Operation,
                     const JSONCallbackParameters& callbacks,QByteArray body,QHttpMultiPart* multipart=nullptr) {
        if (!callbacks.requestTicket.current()) { return; }
        ++calls;lastBody=body;lastTicket=callbacks.requestTicket;
        // The fixture transport owns and disposes the actual multipart.
        delete multipart;
    }
signals:
    void authEndpointChanged(); void logoutComplete(); void usernameChanged();
};
class FakeReply : public QNetworkReply {
public:
    FakeReply(QByteArray body) : payload(std::move(body)) { open(QIODevice::ReadOnly); }
    QByteArray payload;qint64 offset {0};bool aborted {false};QThread* abortThread {nullptr};
    void abort() override { aborted=true;abortThread=QThread::currentThread();emit finished(); }
    qint64 bytesAvailable() const override { return payload.size()-offset+QNetworkReply::bytesAvailable(); }
    qint64 readData(char* destination,qint64 maximum) override {
        const auto size=qMin(maximum,payload.size()-offset);
        if(size==0){return -1;}
        memcpy(destination,payload.constData()+offset,size);offset+=size;return size;
    }
};
