//
//  AssetMappingsScriptingInterface.cpp
//  libraries/script-engine/src
//
//  Created by Ryan Huffman on 2016-03-09.
//  Copyright 2016 High Fidelity, Inc.
//  Copyright 2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#include "AssetMappingsScriptingInterface.h"

#include <QtCore/QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QUuid>
#include <QTimer>
#include <FileDialogHelper.h>
#include <QDir>
#include <QtCore/QThread>

#include <AssetRequest.h>
#include <AssetUpload.h>
#include <MappingRequest.h>
#include <NetworkLogging.h>
#include <NodeList.h>
#include <OffscreenUi.h>
#include <UserActivityLogger.h>
#include "WarningsSuppression.h"

static const int AUTO_REFRESH_INTERVAL = 1000;

int assetMappingModelMetatypeId = qRegisterMetaType<AssetMappingModel*>("AssetMappingModel*");

AssetMappingsScriptingInterface::AssetMappingsScriptingInterface() {
    _proxyModel.setSourceModel(&_assetMappingModel);
    _proxyModel.setSortRole(Qt::DisplayRole);
    _proxyModel.setDynamicSortFilter(true);
    _proxyModel.setSortLocaleAware(true);
    _proxyModel.setFilterCaseSensitivity(Qt::CaseInsensitive);
    _proxyModel.sort(0);
}

void AssetMappingsScriptingInterface::setMapping(QString path, QString hash, QJSValue callback) {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createSetMappingRequest(path, hash);
    connect(request, &SetMappingRequest::finished, this, [callback](SetMappingRequest* request) mutable {
        if (callback.isCallable()) {
            QJSValueList args { request->getErrorString(), request->getPath() };
            callback.call(args);
        }

        request->deleteLater();
    });
    request->start();
}

void AssetMappingsScriptingInterface::getMapping(QString path, QJSValue callback) {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createGetMappingRequest(path);
    connect(request, &GetMappingRequest::finished, this, [callback](GetMappingRequest* request) mutable {
        auto hash = request->getHash();

        if (callback.isCallable()) {
            QJSValueList args { request->getErrorString(), hash };
            callback.call(args);
        }

        request->deleteLater();
    });

    request->start();
}

void AssetMappingsScriptingInterface::uploadFile(QString path, QString mapping, QJSValue startedCallback, QJSValue completedCallback, bool dropEvent) {
    static const QString helpText =
        "Upload your asset to a specific folder by entering the full path. Specifying "
        "a new folder name will automatically create that folder for you.";
    static const QString dropHelpText =
        "This file will be added to your Asset Server.\n"
        "Use the field below to place your file in a specific folder or to rename it. "
        "Specifying a new folder name will automatically create that folder for you.";

    auto offscreenUI = DependencyManager::get<OffscreenUi>();
    if (!offscreenUI) {
        completedCallback.call({ -1 });
        return;
    }

    auto result = offscreenUI->inputDialog(OffscreenUi::ICON_INFORMATION, "Specify Asset Path",
                                           dropEvent ? dropHelpText : helpText, mapping);

    if (!result.isValid() || result.toString() == "") {
        completedCallback.call({ -1 });
        return;
    }
    mapping = result.toString();
    mapping = mapping.trimmed();

    if (mapping[0] != '/') {
        mapping = "/" + mapping;
    }

    // Check for override
    if (isKnownMapping(mapping)) {
        auto message = mapping + "\n" + "This file already exists. Do you want to overwrite it?";
        auto button = offscreenUI->messageBox(OffscreenUi::ICON_QUESTION, "Overwrite File", message,
                                              QMessageBox::Yes | QMessageBox::No, QMessageBox::No);
        if (button == QMessageBox::No) {
            completedCallback.call({ -1 });
            return;
        }
    }

    startedCallback.call();

    QFileInfo fileInfo { path };
    int64_t size { fileInfo.size() };

    QString extension = "";
    auto idx = path.lastIndexOf(".");
    if (idx >= 0) {
        extension = path.mid(idx + 1);
    }

    UserActivityLogger::getInstance().logAction("uploading_asset", {
        { "size", (qint64)size },
        { "mapping", mapping },
        { "extension", extension}
    });

    auto upload = DependencyManager::get<AssetClient>()->createUpload(path);
    QObject::connect(upload, &AssetUpload::finished, this, [=, this](AssetUpload* upload, const QString& hash) mutable {
        if (upload->getError() != AssetUpload::NoError) {
            if (completedCallback.isCallable()) {
                QJSValueList args { upload->getErrorString() };
                completedCallback.call(args);
            }
        } else {
            setMapping(mapping, hash, completedCallback);
        }

        upload->deleteLater();
    });

    upload->start();
}

struct AssetMappingsScriptingInterface::BundleUpload {
    QString id, primary, destination;
    QStringList files, relative, hashes, published;
    QJSValue progress, completed;
    int index { 0 };
    bool publishing { false }, canceled { false };
};

QString AssetMappingsScriptingInterface::uploadBundle(QStringList paths, QStringList relativePaths, QString destination,
                                                     QString primaryPath, QJSValue progress, QJSValue completed) {
    if (!_bundleUploads.isEmpty()) return {};
    auto state = std::make_shared<BundleUpload>();
    state->id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    state->files = paths; state->relative = relativePaths; state->primary = primaryPath;
    state->progress = progress; state->completed = completed;
    destination = destination.trimmed();
    if (!destination.startsWith('/')) destination.prepend('/');
    if (!destination.endsWith('/')) destination.append('/');
    state->destination = destination;
    _bundleUploads.insert(state->id, state);
    QTimer::singleShot(0, this, [this, state] {
        QList<QUrl> files;
        for (const auto& path : state->files) files.append(QUrl::fromLocalFile(path));
        const auto safe = [](const QString& path) {
            if (path.isEmpty() || path.contains('\\') || path.contains(QChar(0))) return false;
            for (const auto& part : path.split('/')) if (part == "." || part == "..") return false;
            return true;
        };
        if (state->files.isEmpty() || state->files.size() != state->relative.size()
                || !safe(state->destination) || !state->relative.contains(state->primary)) {
            finishBundle(state, "Invalid bundle files, destination or main file."); return;
        }
        QSet<QString> mappings;
        for (const auto& relative : state->relative) {
            auto mapping = state->destination + relative;
            if (!safe(relative) || relative.startsWith('/') || QDir::isAbsolutePath(relative) || relative.contains(':')
                    || relative.endsWith('/') || relative.split('/').contains(QString())
                    || relative.split('/').size() > FileDialogHelper::MAX_DOCUMENT_DEPTH
                    || mappings.contains(mapping) || isKnownMapping(mapping) || isKnownFolder(mapping)) {
                finishBundle(state, "Choose a new destination: a bundle path is invalid, duplicated or already exists."); return;
            }
            mappings.insert(mapping);
        }
        // Derive the chosen root from a real file and its original relative name;
        // every other file must have the same root and unchanged hierarchy.
        auto firstPath = QFileInfo(state->files.first()).absoluteFilePath();
        const auto suffix = '/' + state->relative.first();
        if (!firstPath.endsWith(suffix)) { finishBundle(state, "Bundle names must match the selected files."); return; }
        FileDialogHelper helper;
        auto bundle = helper.documentBundle(files, QUrl::fromLocalFile(firstPath.left(firstPath.size() - suffix.size())));
        if (!bundle.value("error").toString().isEmpty() || bundle.value("relativePaths").toStringList() != state->relative) {
            finishBundle(state, "Bundle files must preserve their original relative names and folder."); return;
        }
        int main = state->relative.indexOf(state->primary);
        state->relative.append(state->relative.takeAt(main));
        state->files.append(state->files.takeAt(main));
        advanceBundle(state);
    });
    return state->id;
}

bool AssetMappingsScriptingInterface::cancelUploadBundle(const QString& requestId) {
    auto state = _bundleUploads.value(requestId);
    if (!state) return false;
    // An in-flight server operation settles before the terminal callback; no next operation starts.
    state->canceled = true;
    return true;
}

void AssetMappingsScriptingInterface::finishBundle(const std::shared_ptr<BundleUpload>& state, const QString& error) {
    if (!_bundleUploads.remove(state->id)) return;
    if (state->completed.isCallable()) {
        QJsonArray paths;
        for (const auto& path : state->published) paths.append(path);
        const auto summary = QString::fromUtf8(QJsonDocument(paths).toJson(QJsonDocument::Compact));
        state->completed.call({ error, summary, error.isEmpty() ? state->destination + state->primary : QString() });
    }
}

void AssetMappingsScriptingInterface::advanceBundle(const std::shared_ptr<BundleUpload>& state) {
    if (!_bundleUploads.contains(state->id)) return;
    if (state->canceled) { finishBundle(state, "Upload canceled."); return; }
    if (!DependencyManager::get<NodeList>()->getThisNodeCanWriteAssets()) { finishBundle(state, "Asset write permission was revoked."); return; }
    if (state->index == state->files.size()) {
        if (state->publishing) { finishBundle(state, {}); return; }
        state->publishing = true; state->index = 0;
    }
    if (state->progress.isCallable()) state->progress.call({ state->index, state->publishing ? "Publishing mappings" : "Uploading files" });
    // Progress handlers can close the UI, cancel or change permissions before the next operation.
    if (state->canceled) { finishBundle(state, "Upload canceled."); return; }
    if (!DependencyManager::get<NodeList>()->getThisNodeCanWriteAssets()) { finishBundle(state, "Asset write permission was revoked."); return; }
    if (!state->publishing) {
        auto* upload = DependencyManager::get<AssetClient>()->createUpload(state->files[state->index]);
        connect(upload, &AssetUpload::finished, upload, &QObject::deleteLater);
        connect(upload, &AssetUpload::finished, this, [this, state](AssetUpload* upload, const QString& hash) {
            const auto error = upload->getErrorString();
            if (!error.isEmpty() || !QRegularExpression("^[a-fA-F0-9]{64}$").match(hash).hasMatch()) {
                finishBundle(state, error.isEmpty() ? "Invalid uploaded asset hash." : error); return;
            }
            state->hashes.append(hash); ++state->index; advanceBundle(state);
        });
        upload->start();
    } else {
        const auto mapping = state->destination + state->relative[state->index];
        // Recheck local mapping knowledge immediately before publishing. Remote races remain server-authoritative.
        if (isKnownMapping(mapping)) { finishBundle(state, "An asset mapping appeared while uploading; it was not overwritten."); return; }
        auto* request = DependencyManager::get<AssetClient>()->createSetMappingRequest(mapping, state->hashes[state->index]);
        connect(request, &SetMappingRequest::finished, request, &QObject::deleteLater);
        connect(request, &SetMappingRequest::finished, this, [this, state](SetMappingRequest* request) {
            const auto error = request->getErrorString();
            if (error.isEmpty()) state->published.append(request->getPath());
            if (!error.isEmpty()) { finishBundle(state, error); return; }
            ++state->index; advanceBundle(state);
        });
        request->start();
    }
}

void AssetMappingsScriptingInterface::deleteMappings(QStringList paths, QJSValue callback) {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createDeleteMappingsRequest(paths);

    connect(request, &DeleteMappingsRequest::finished, this, [callback](DeleteMappingsRequest* request) mutable {
        if (callback.isCallable()) {
            QJSValueList args { request->getErrorString() };
            callback.call(args);
        }

        request->deleteLater();
    });

    request->start();
}

void AssetMappingsScriptingInterface::sortProxyModel(int column, Qt::SortOrder order) {
    _proxyModel.sort(column, order);
}

void AssetMappingsScriptingInterface::getAllMappings(QJSValue callback) {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createGetAllMappingsRequest();

    connect(request, &GetAllMappingsRequest::finished, this, [callback](GetAllMappingsRequest* request) mutable {
        auto mappings = request->getMappings();

        OVERTE_IGNORE_DEPRECATED_BEGIN
        // Still using QScriptEngine
        auto map = callback.engine()->newObject();
        OVERTE_IGNORE_WARNING_END

        for (auto& kv : mappings ) {
            map.setProperty(kv.first, kv.second.hash);
        }

        if (callback.isCallable()) {
            QJSValueList args { request->getErrorString(), map };
            callback.call(args);
        }

        request->deleteLater();
    });

    request->start();
}

void AssetMappingsScriptingInterface::renameMapping(QString oldPath, QString newPath, QJSValue callback) {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createRenameMappingRequest(oldPath, newPath);

    connect(request, &RenameMappingRequest::finished, this, [callback](RenameMappingRequest* request) mutable {
        if (callback.isCallable()) {
            QJSValueList args{ request->getErrorString() };
            callback.call(args);
        }

        request->deleteLater();
    });

    request->start();
}

void AssetMappingsScriptingInterface::setBakingEnabled(QStringList paths, bool enabled, QJSValue callback) {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createSetBakingEnabledRequest(paths, enabled);

    connect(request, &SetBakingEnabledRequest::finished, this, [callback](SetBakingEnabledRequest* request) mutable {
        if (callback.isCallable()) {
            QJSValueList args{ request->getErrorString() };
            callback.call(args);
        }

        request->deleteLater();
    });

    request->start();
}

AssetMappingModel::AssetMappingModel() {
    setupRoles();

    connect(&_autoRefreshTimer, &QTimer::timeout, this, [this] {
        auto nodeList = DependencyManager::get<NodeList>();
        auto assetServer = nodeList->soloNodeOfType(NodeType::AssetServer);
        if (assetServer) {
            refresh();
        }
    });
    _autoRefreshTimer.setInterval(AUTO_REFRESH_INTERVAL);
}

bool AssetMappingModel::isAutoRefreshEnabled() {
    return _autoRefreshTimer.isActive();
}

void AssetMappingModel::setAutoRefreshEnabled(bool enabled) {
    if (enabled != _autoRefreshTimer.isActive()) {
        if (enabled) {
            _autoRefreshTimer.start();
        } else {
            _autoRefreshTimer.stop();
        }
    }
}

bool AssetMappingModel::isKnownFolder(QString path) const {
    if (!path.endsWith("/")) {
        return false;
    }

    auto existingPaths = _pathToItemMap.keys();
    for (auto& entry : existingPaths) {
        if (entry.startsWith(path)) {
            return true;
        }
    }
    return false;
}

void AssetMappingModel::refresh() {
    auto assetClient = DependencyManager::get<AssetClient>();
    auto request = assetClient->createGetAllMappingsRequest();

    connect(request, &GetAllMappingsRequest::finished, this, [this](GetAllMappingsRequest* request) mutable {
        if (request->getError() == MappingRequest::NoError) {
            int numPendingBakes = 0;
            auto mappings = request->getMappings();
            auto existingPaths = _pathToItemMap.keys();
            for (auto& mapping : mappings) {
                auto& path = mapping.first;

                if (path.startsWith(AssetUtils::HIDDEN_BAKED_CONTENT_FOLDER)) {
                    // Hide baked mappings
                    continue;
                }

                auto parts = path.split("/");
                auto length = parts.length();

                existingPaths.removeOne(mapping.first);

                QString fullPath = "/";

                QStandardItem* lastItem = nullptr;

                // start index at 1 to avoid empty string from leading slash
                for (int i = 1; i < length; ++i) {
                    fullPath += (i == 1 ? "" : "/") + parts[i];
                    bool isFolder = i < length - 1;

                    auto it = _pathToItemMap.find(fullPath);
                    if (it == _pathToItemMap.end()) {
                        auto item = new QStandardItem(parts[i]);
                        item->setData(isFolder ? fullPath + "/" : fullPath, Qt::UserRole);
                        item->setData(isFolder, Qt::UserRole + 1);
                        item->setData(parts[i], Qt::UserRole + 2);
                        item->setData("atp:" + fullPath, Qt::UserRole + 3);
                        item->setData(fullPath, Qt::UserRole + 4);

                        if (lastItem) {
                            lastItem->appendRow(item);
                        } else {
                            appendRow(item);
                        }
                        lastItem = item;
                        _pathToItemMap[fullPath] = lastItem;
                    } else {
                        lastItem = it.value();
                    }

                    // update status
                    auto statusString = isFolder ? "--" : bakingStatusToString(mapping.second.status);
                    lastItem->setData(statusString, Qt::UserRole + 5);
                    lastItem->setData(mapping.second.bakingErrors, Qt::UserRole + 6);
                    if (mapping.second.status == AssetUtils::Pending) {
                        ++numPendingBakes;
                    }
                }

                Q_ASSERT(fullPath == path);
            }

            // Remove folders from list
            auto it = existingPaths.begin();
            while (it != existingPaths.end()) {
                Q_ASSERT(_pathToItemMap.contains(*it));
                auto item = _pathToItemMap[*it];
                if (item && item->data(Qt::UserRole + 1).toBool()) {
                    it = existingPaths.erase(it);
                } else {
                    ++it;
                }
            }

            for (auto& path : existingPaths) {
                Q_ASSERT(_pathToItemMap.contains(path));

                auto item = _pathToItemMap[path];

                while (item) {
                    // During each iteration, delete item
                    QStandardItem* nextItem = nullptr;

                    auto fullPath = item->data(Qt::UserRole + 4).toString();
                    auto parent = item->parent();
                    if (parent) {
                        parent->removeRow(item->row());
                        if (parent->rowCount() > 0) {
                            // The parent still contains children, set the nextItem to null so we stop processing
                            nextItem = nullptr;
                        } else {
                            nextItem = parent;
                        }
                    } else {
                        auto removed = removeRow(item->row());
                        Q_ASSERT(removed);
                    }

                    Q_ASSERT(_pathToItemMap.contains(fullPath));
                    _pathToItemMap.remove(fullPath);

                    item = nextItem;
                }
            }

            if (numPendingBakes != _numPendingBakes) {
                _numPendingBakes = numPendingBakes;
                emit numPendingBakesChanged(_numPendingBakes);
            }
        } else {
            emit errorGettingMappings(request->getErrorString());
        }

        emit updated();

        request->deleteLater();
    });

    request->start();
}

void AssetMappingModel::clear() {
    // make sure we are on the same thread before we touch the hash
    if (thread() != QThread::currentThread()) {
        QMetaObject::invokeMethod(this, "clear");
        return;
    }

    qDebug() << "Clearing loaded asset mappings for Asset Browser";

    _pathToItemMap.clear();
    QStandardItemModel::clear();
}

void AssetMappingModel::setupRoles() {
    QHash<int, QByteArray> roleNames;
    roleNames[Qt::DisplayRole] = "name";
    roleNames[Qt::UserRole + 5] = "baked";
    setItemRoleNames(roleNames);
}
