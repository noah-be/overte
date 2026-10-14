//
//  NetworkAccessManager.cpp
//  libraries/networking/src
//
//  Created by Clement on 7/1/14.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "NetworkAccessManager.h"
#include "CredentialTransportPolicy.h"

#include <QThreadStorage>

#include "AtpReply.h"
#include <QtNetwork/QNetworkProxy>

QThreadStorage<QNetworkAccessManager*> networkAccessManagers;

QNetworkAccessManager& NetworkAccessManager::getInstance() {
    if (!networkAccessManagers.hasLocalData()) {
        networkAccessManagers.setLocalData(new overte::network::CredentialNetworkAccessManager());
    }
    
    return *networkAccessManagers.localData();
}

QNetworkReply* NetworkAccessManager::createRequest(Operation operation, const QNetworkRequest& request, QIODevice* device) {
    if (overte::network::requestCarriesCredentials(request)) {
        if (!overte::network::credentialRequestTransportAllowed(request)) {
            return new overte::network::RejectedCredentialReply(*this, operation);
        }
        auto secured = request;
        secured.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
        return QNetworkAccessManager::createRequest(operation, secured, device);
    }
    if (request.url().scheme() == "atp" && operation == GetOperation) {
        return new AtpReply(request.url());
        //auto url = request.url().toString();
        //return QNetworkAccessManager::createRequest(operation, request, device);
    } else {
        return QNetworkAccessManager::createRequest(operation, request, device);
    }
}
