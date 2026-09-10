//
//  ScriptCache.cpp
//  libraries/script-engine/src
//
//  Created by Brad Hefta-Gaub on 2015-03-30
//  Copyright 2015 High Fidelity, Inc.
//  Copyright 2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#include "ScriptCache.h"

#include <QCoreApplication>
#include <QEventLoop>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QThread>
#include <QRegularExpression>
#include <QMetaEnum>

#include <assert.h>
#include <ResourceCache.h>
#include <SharedUtil.h>

#include "ScriptEngines.h"
#include "ScriptEngineLogging.h"
#include <QtCore/QTimer>

const QString ScriptCache::STATUS_INLINE { "Inline" };
const QString ScriptCache::STATUS_CACHED { "Cached" };

ScriptCache::ScriptCache(QObject* parent) {
    // nothing to do here...
}

void ScriptCache::clearCache() {
    Lock lock(_containerLock);
    _scriptCache.clear();
}

void ScriptCache::clearATPScriptsFromCache() {
    Lock lock(_containerLock);
    qCDebug(scriptengine) << "Clearing ATP scripts from ScriptCache";
    for (auto it = _scriptCache.begin(); it != _scriptCache.end();) {
        if (it.key().first.scheme() == "atp") {
            it = _scriptCache.erase(it);
        } else {
            ++it;
        }
    }
}

void ScriptCache::deleteScript(const QUrl& unnormalizedURL) {
    QUrl url = DependencyManager::get<ResourceManager>()->normalizeURL(unnormalizedURL);
    Lock lock(_containerLock);
    for (auto it = _scriptCache.begin(); it != _scriptCache.end();) {
        if (it.key().first == url) { it = _scriptCache.erase(it); } else { ++it; }
    }
}

void ScriptCache::getScriptContents(const QString& scriptOrURL, contentAvailableCallback contentAvailable, bool forceDownload, int maxRetries, bool failOnRedirect, std::shared_ptr<EntityScriptConsentScope> consentScope) {
    #ifdef THREAD_DEBUGGING
    qCDebug(scriptengine) << "ScriptCache::getScriptContents() on thread [" << QThread::currentThread() << "] expected thread [" << thread() << "]";
    #endif
    if (failOnRedirect && !observeConsentScope(consentScope)) {
        contentAvailable(scriptOrURL, QString(), true, false, QStringLiteral("Cancelled"));
        return;
    }
    if (!failOnRedirect) {
        consentScope.reset();
    } else {
        // Recheck at delivery too: normalization, cache diagnostics and another
        // callback can synchronously revoke the session after entry validation.
        contentAvailable = [scope = consentScope, callback = std::move(contentAvailable)](
            const QString& source, const QString& contents, bool isURL, bool success, const QString& status) {
            const bool active = scope->active();
            callback(source, active ? contents : QString(), isURL, success && active,
                     active ? status : QStringLiteral("Cancelled"));
        };
    }
    QUrl unnormalizedURL(scriptOrURL);
    QUrl url = DependencyManager::get<ResourceManager>()->normalizeURL(unnormalizedURL);

    if (consentScope && !consentScope->active()) {
        contentAvailable(scriptOrURL, QString(), true, false, QStringLiteral("Cancelled"));
        return;
    }

    // attempt to determine if this is a URL to a script, or if this is actually a script itself (which is valid in the
    // entityScript use case)
    if (unnormalizedURL.scheme().isEmpty() &&
            scriptOrURL.simplified().replace(" ", "").contains(QRegularExpression(R"(\(function\([a-z]?[\w,]*\){)"))) {
        contentAvailable(scriptOrURL, scriptOrURL, false, true, STATUS_INLINE);
        return;
    }

    // give a similar treatment to javacript: urls
    if (unnormalizedURL.scheme() == "javascript") {
        QString contents { scriptOrURL };
        contents.replace(QRegularExpression("^javascript:"), "");
        contentAvailable(scriptOrURL, contents, false, true, STATUS_INLINE);
        return;
    }

    // Approval names this source, not a hidden ResourceManager substitution.
    // Inline source handling above does not perform a resource request.
    if (failOnRedirect && url != unnormalizedURL) {
        contentAvailable(scriptOrURL, QString(), true, false, QStringLiteral("InvalidURL"));
        return;
    }
    const auto key = cacheKey(url, failOnRedirect, consentScope);
    Lock lock(_containerLock);
    if (_scriptCache.contains(key) && !forceDownload) {
        auto entry = _scriptCache[key];
        if (url.isLocalFile() || url.scheme().isEmpty()) {
            auto modifiedTime = QFileInfo(url.toLocalFile()).lastModified();
            QString localTime = ResourceRequest::toHttpDateString(modifiedTime.toMSecsSinceEpoch());
            QString cachedTime = entry["last-modified"].toString();
            if (cachedTime != localTime) {
                forceDownload = true;
                qCDebug(scriptengine) << "Found script in cache, but local file modified; reloading:" << url.fileName()
                                      << "(memory:" << cachedTime << "disk:" << localTime << ")";
            }
        }
        if (!forceDownload) {
            lock.unlock();
            qCDebug(scriptengine) << "Found script in cache:" << url.fileName();
            contentAvailable(url.toString(), entry["data"].toString(), true, true, STATUS_CACHED);
            return;
        }
    }
    {
        auto& scriptRequest = _activeScriptRequests[key];
        bool alreadyWaiting = scriptRequest.scriptUsers.size() > 0;
        scriptRequest.scriptUsers.push_back(contentAvailable);
        if (!alreadyWaiting) { scriptRequest.maxRetries = maxRetries; }
        const auto numRetries = scriptRequest.numRetries;
        const auto userCount = scriptRequest.scriptUsers.size();

        lock.unlock();

        if (alreadyWaiting) {
            qCDebug(scriptengine) << QString("Already downloading script at: %1 (retry: %2; scriptusers: %3)")
                .arg(url.toString()).arg(numRetries).arg(userCount);
        } else {
            #ifdef THREAD_DEBUGGING
            qCDebug(scriptengine) << "about to call: ResourceManager::createResourceRequest(this, url); on thread [" << QThread::currentThread() << "] expected thread [" << thread() << "]";
            #endif
            auto request = DependencyManager::get<ResourceManager>()->createResourceRequest(
                nullptr, url, true, -1, "ScriptCache::getScriptContents");
            if (!request || (failOnRedirect && request->getUrl() != url)) {
                if (request) { request->deleteLater(); }
                failScriptRequest(url, failOnRedirect, consentScope);
                return;
            }
            if (consentScope && !consentScope->active()) {
                request->deleteLater();
                failScriptRequest(url, failOnRedirect, consentScope, QStringLiteral("Cancelled"));
                return;
            }
            request->setCacheEnabled(!forceDownload);
            request->setFailOnRedirect(failOnRedirect);
            connect(request, &ResourceRequest::finished, this, [=, this]{ scriptContentAvailable(maxRetries, failOnRedirect, consentScope); });
            request->send();
        }
    }
}

bool ScriptCache::observeConsentScope(const std::shared_ptr<EntityScriptConsentScope>& scope) {
    if (!scope || !scope->active()) { return false; }
    const auto identity = scope->identity();
    {
        Lock lock(_containerLock);
        if (_observedConsentScopes.contains(identity)) { return scope->active(); }
        _observedConsentScopes.insert(identity);
    }
    const auto weakCache = DependencyManager::get<ScriptCache>().toWeakRef();
    scope->onInvalidated([weakCache, identity] {
        if (const auto cache = weakCache.toStrongRef()) {
            QMetaObject::invokeMethod(cache.data(), [weakCache, identity] {
                if (const auto cache = weakCache.toStrongRef()) { cache->purgeConsentScope(identity); }
            }, Qt::QueuedConnection);
        }
    });
    return scope->active();
}

void ScriptCache::purgeConsentScope(const QUuid& identity) {
    std::vector<std::pair<QUrl, std::vector<contentAvailableCallback>>> pending;
    {
        Lock lock(_containerLock);
        _observedConsentScopes.remove(identity);
        for (auto it = _scriptCache.begin(); it != _scriptCache.end();) {
            if (it.key().second.second == identity) { it = _scriptCache.erase(it); } else { ++it; }
        }
        for (auto it = _activeScriptRequests.begin(); it != _activeScriptRequests.end();) {
            if (it.key().second.second == identity) {
                pending.push_back({ it.key().first, std::move(it->scriptUsers) });
                it = _activeScriptRequests.erase(it);
            } else { ++it; }
        }
    }
    for (const auto& entry : pending) {
        for (const auto& callback : entry.second) {
            callback(entry.first.toString(), QString(), true, false, QStringLiteral("Cancelled"));
        }
    }
}

void ScriptCache::failScriptRequest(const QUrl& url, bool failOnRedirect,
    const std::shared_ptr<EntityScriptConsentScope>& scope, const QString& status) {
    std::vector<contentAvailableCallback> callbacks;
    {
        Lock lock(_containerLock);
        callbacks = _activeScriptRequests.take(cacheKey(url, failOnRedirect, scope)).scriptUsers;
    }
    for (const auto& callback : callbacks) {
        callback(url.toString(), QString(), true, false, status);
    }
}

void ScriptCache::scriptContentAvailable(int maxRetries, bool failOnRedirect, std::shared_ptr<EntityScriptConsentScope> consentScope) {
    #ifdef THREAD_DEBUGGING
    qCDebug(scriptengine) << "ScriptCache::scriptContentAvailable() on thread [" << QThread::currentThread() << "] expected thread [" << thread() << "]";
    #endif
    ResourceRequest* req = qobject_cast<ResourceRequest*>(sender());
    Q_ASSERT(req != nullptr);
    QUrl url = req->getUrl();
    const auto key = cacheKey(url, failOnRedirect, consentScope);

    if (consentScope && !consentScope->active()) {
        failScriptRequest(url, failOnRedirect, consentScope, QStringLiteral("Cancelled"));
        req->deleteLater();
        return;
    }
    QString scriptContent;
    std::vector<contentAvailableCallback> allCallbacks;
    QString status = QMetaEnum::fromType<ResourceRequest::Result>().valueToKey(req->getResult());
    bool success { false };

    {
        Q_ASSERT(req->getState() == ResourceRequest::Finished);
        success = req->getResult() == ResourceRequest::Success;

        Lock lock(_containerLock);

        if (_activeScriptRequests.contains(key)) {
            auto& scriptRequest = _activeScriptRequests[key];

            if (success) {
                allCallbacks = scriptRequest.scriptUsers;

                _activeScriptRequests.remove(key);

                _scriptCache[key] = {
                    { "data", scriptContent = req->getData() },
                    { "last-modified", req->property("last-modified") },
                };
            } else {
                auto result = req->getResult();
                bool irrecoverable =
                    result == ResourceRequest::AccessDenied ||
                    result == ResourceRequest::RedirectFail ||
                    result == ResourceRequest::InvalidURL ||
                    result == ResourceRequest::NotFound ||
                    scriptRequest.numRetries >= maxRetries;

                if (!irrecoverable) {
                    ++scriptRequest.numRetries;

                    int timeout = exp(scriptRequest.numRetries) * ScriptRequest::START_DELAY_BETWEEN_RETRIES;
                    int attempt = scriptRequest.numRetries;
                    qCDebug(scriptengine) << QString("Script request failed [%1]: (will retry %2 more times; attempt #%3 in %4ms...)")
                        .arg(status).arg(maxRetries - attempt + 1).arg(attempt).arg(timeout);

                    QTimer::singleShot(timeout, this, [this, url, attempt, maxRetries, failOnRedirect, consentScope]() {
                        qCDebug(scriptengine) << QString("Retrying script request [%1 / %2]")
                            .arg(attempt).arg(maxRetries);

                        if (consentScope && !consentScope->active()) {
                            failScriptRequest(url, failOnRedirect, consentScope, QStringLiteral("Cancelled"));
                            return;
                        }
                        auto request = DependencyManager::get<ResourceManager>()->createResourceRequest(
                            nullptr, url, true, -1, "ScriptCache::scriptContentAvailable");
                        if (!request || (failOnRedirect && request->getUrl() != url)) {
                            if (request) { request->deleteLater(); }
                            failScriptRequest(url, failOnRedirect, consentScope);
                            return;
                        }

                        // We've already made a request, so the cache must be disabled or it wasn't there, so enabling
                        // it will do nothing.
                        request->setCacheEnabled(false);
                        request->setFailOnRedirect(failOnRedirect);
                        connect(request, &ResourceRequest::finished, this, [=, this]{ scriptContentAvailable(maxRetries, failOnRedirect, consentScope); });
                        request->send();
                    });
                } else {
                    // Dubious, but retained here because it matches the behavior before fixing the threading

                    allCallbacks = scriptRequest.scriptUsers;

                    if (_scriptCache.contains(key)) {
                        scriptContent = _scriptCache[key]["data"].toString();
                    }
                    _activeScriptRequests.remove(key);
                    qCWarning(scriptengine) << "Error loading script from URL (" << status <<")";

                }
            }
        }
    }

    req->deleteLater();

    if (allCallbacks.size() > 0 && !DependencyManager::get<ScriptEngines>()->isStopped()) {
        foreach(contentAvailableCallback thisCallback, allCallbacks) {
            const bool active = !consentScope || consentScope->active();
            thisCallback(url.toString(), active ? scriptContent : QString(), true, success && active,
                         active ? status : QStringLiteral("Cancelled"));
        }
    }
}
