//
//  OffscreenUi.cpp
//  interface/src/render-utils
//
//  Created by Bradley Austin Davis on 2015-04-04
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "FileDialogHelper.h"
#include "ui/Logging.h"
#include <QFileDialog>
#include <QMutex>
#include <QMutexLocker>
#include <QThread>
#include <QUuid>


#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QDebug>
#include <QtCore/QRegularExpression>
#include <QDesktopServices>

std::function<void(const QString&)> FileDialogHelper::_openDirectoryOperator = nullptr;

QUrl FileDialogHelper::home() {
    return pathToUrl(QStandardPaths::standardLocations(QStandardPaths::HomeLocation)[0]);
}

QStringList FileDialogHelper::standardPath(StandardLocation location) {
    return QStandardPaths::standardLocations(static_cast<QStandardPaths::StandardLocation>(location)); 
}

QString FileDialogHelper::writableLocation(StandardLocation location) {
    return QStandardPaths::writableLocation(static_cast<QStandardPaths::StandardLocation>(location));
}

QString FileDialogHelper::urlToPath(const QUrl& url) { 
    return url.toLocalFile(); 
}

bool FileDialogHelper::fileExists(const QString& path) {
    return QFile(path).exists();
}

bool FileDialogHelper::validPath(const QString& path) {
    return QFile(path).exists(); 
}

bool FileDialogHelper::validFolder(const QString& path) { 
    return QDir(path).exists(); 
}

QUrl FileDialogHelper::pathToUrl(const QString& path) { 
    return QUrl::fromLocalFile(path); 
}


QUrl FileDialogHelper::saveHelper(const QString& saveText, const QUrl& currentFolder, const QStringList& selectionFilters) {
    qDebug(uiLogging) << "Calling save helper with " << saveText << " " << currentFolder << " " << selectionFilters;

    QFileInfo fileInfo(saveText);

    // Check if it's a relative path and if it is resolve to the absolute path
    {
        if (fileInfo.isRelative()) {
            fileInfo = QFileInfo(currentFolder.toLocalFile() + "/" + fileInfo.filePath());
        }
    }

    // Check if we need to append an extension, but only if the current resolved path isn't a directory
    if (!fileInfo.isDir()) {
        QString fileName = fileInfo.fileName();
        if (!fileName.contains(".") && selectionFilters.size() == 1) {
            const QRegularExpression extensionRe{ ".*(\\.[a-zA-Z0-9]+)$" };
            QString filter = selectionFilters[0];
            auto match = extensionRe.match(filter);
            if (match.hasMatch()) {
                fileInfo = QFileInfo(fileInfo.filePath() + match.captured(1));
            }
        }
    }

    return QUrl::fromLocalFile(fileInfo.absoluteFilePath());
}

bool FileDialogHelper::urlIsDir(const QUrl& url) {
    return QFileInfo(url.toLocalFile()).isDir();
}

bool FileDialogHelper::urlIsFile(const QUrl& url) {
    return QFileInfo(url.toLocalFile()).isFile();
}

bool FileDialogHelper::urlExists(const QUrl& url) {
    return QFileInfo(url.toLocalFile()).exists();
}

bool FileDialogHelper::urlIsWritable(const QUrl& url) {
    QFileInfo fileInfo(url.toLocalFile());
    // Is the file writable?
    if (fileInfo.exists()) {
        return fileInfo.isWritable();
    } 

    // No file, get the parent directory and check if writable
    return QFileInfo(fileInfo.absoluteDir().absolutePath()).isWritable();
}

QStringList FileDialogHelper::drives() {
    QStringList result;
    for (const auto& drive : QDir::drives()) {
        result << drive.absolutePath();
    }
    return result;
}

void FileDialogHelper::openDirectory(const QString& path) {
    if (_openDirectoryOperator) {
        _openDirectoryOperator(path);
    }
}

QList<QUrl> FileDialogHelper::urlToList(const QUrl& url) {
    QList<QUrl> results;
    results.push_back(url);
    return results;
}

void FileDialogHelper::monitorDirectory(const QString& path) {
    if (!_fsWatcherPath.isEmpty()) {
        _fsWatcher.removePath(_fsWatcherPath);
        _fsWatcherPath = "";
    }

    if (!path.isEmpty()) {
        _fsWatcher.addPath(path);
        _fsWatcherPath = path;
        connect(&_fsWatcher, &QFileSystemWatcher::directoryChanged, this, &FileDialogHelper::contentsChanged);
    }
}


namespace {
QMutex documentPickerMutex;
FileDialogHelper::DocumentPickerOperator documentPicker;
FileDialogHelper::DocumentPickerCancel documentPickerCancel;
}

void FileDialogHelper::setDocumentPickerOperator(DocumentPickerOperator picker, DocumentPickerCancel cancel) {
    QMutexLocker guard(&documentPickerMutex);
    documentPicker = std::move(picker);
    documentPickerCancel = std::move(cancel);
}

FileDialogHelper::~FileDialogHelper() {
    if (!_documentRequestId.isEmpty()) cancelDocuments(_documentRequestId);
    delete _documentDialog.data();
}

void FileDialogHelper::finishDocuments(const QString& requestId, const QList<QUrl>& urls, const QString& failure) {
    if (requestId.isEmpty() || requestId != _documentRequestId) return;
    const bool providerSelection = _nativeDocumentPending;
    _documentCancel = {};
    _documentRequestId.clear();
    _nativeDocumentPending = false;
    QString error = failure;
    if (!_multipleDocuments && urls.size() > 1) error = tr("The document picker returned more than one file for a single-file request.");
    if (providerSelection && urls.size() > MAX_DOCUMENT_COUNT) error = tr("The document selection exceeds the 32-file limit.");
    qint64 total = 0;
    if (error.isEmpty()) {
        for (const auto& url : urls) {
            const qint64 size = QFileInfo(url.toLocalFile()).size();
            if (providerSelection && (size > MAX_DOCUMENT_BYTES || size > MAX_DOCUMENT_TOTAL_BYTES - total)) {
                error = tr("The document selection exceeds the import size limits.");
                break;
            }
            total += size;
            if (!url.isLocalFile() || !QFileInfo(url.toLocalFile()).isFile() || !QFileInfo(url.toLocalFile()).isReadable()) {
                error = tr("The document picker did not provide a readable local file.");
                break;
            }
        }
    }
    if (!error.isEmpty()) emit documentSelectionFailed(requestId, error);
    else if (urls.isEmpty()) emit documentSelectionCanceled(requestId);
    else emit documentsSelected(requestId, urls);
}

QString FileDialogHelper::openDocuments(const QString& caption, const QString& filter, bool multiple) {
    if (!_documentRequestId.isEmpty()) return {};
    const QString requestId = QUuid::createUuid().toString(QUuid::WithoutBraces);
    _documentRequestId = requestId;
    _multipleDocuments = multiple;
    DocumentPickerOperator picker;
    { QMutexLocker guard(&documentPickerMutex); picker = documentPicker; _documentCancel = documentPickerCancel; }
    if (picker) {
        _nativeDocumentPending = true;
        QPointer<FileDialogHelper> owner(this);
        DocumentSelection completed = [owner, requestId](const QList<QUrl>& urls, const QString& error) {
            if (!owner) return;
            QMetaObject::invokeMethod(owner, [owner, requestId, urls, error] {
                if (owner) owner->finishDocuments(requestId, urls, error);
            }, Qt::QueuedConnection);
        };
        if (picker(requestId, caption, filter, multiple, completed)) return requestId;
        _documentCancel = {};
        _documentRequestId.clear();
        _nativeDocumentPending = false;
        return {};
    }
#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS)
    // A widgets overlay or guessed QPA content provider is not a mobile picker.
    _documentRequestId.clear();
    return {};
#else
    auto* dialog = new QFileDialog(nullptr, caption);
    _documentDialog = dialog;
    dialog->setObjectName("overteDocumentPicker");
    dialog->setFileMode(multiple ? QFileDialog::ExistingFiles : QFileDialog::ExistingFile);
    dialog->setAcceptMode(QFileDialog::AcceptOpen);
    dialog->setNameFilter(filter.isEmpty() ? QStringLiteral("All files (*)") : filter);
    dialog->setSupportedSchemes({ QStringLiteral("file") });
    connect(dialog, &QDialog::finished, this, [this, dialog, requestId](int result) {
        if (_documentDialog != dialog || _documentRequestId != requestId) return;
        auto selected = result == QDialog::Accepted ? dialog->selectedUrls() : QList<QUrl>();
        _documentDialog.clear();
        dialog->deleteLater();
        finishDocuments(requestId, selected, {});
    });
    dialog->open();
    return requestId;
#endif
}

bool FileDialogHelper::cancelDocuments(const QString& requestId) {
    if (requestId.isEmpty() || requestId != _documentRequestId) return false;
    if (_nativeDocumentPending) {
        DocumentPickerCancel cancel = std::move(_documentCancel);
        _documentRequestId.clear();
        _nativeDocumentPending = false;
        if (cancel) cancel(requestId);
        emit documentSelectionCanceled(requestId);
    } else if (_documentDialog) {
        _documentDialog->reject();
    }
    return true;
}
