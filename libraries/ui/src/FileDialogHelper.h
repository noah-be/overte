//
//  Created by Bradley Austin Davis on 2016-01-21
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#pragma once
#ifndef hifi_ui_FileDialogHelper_h
#define hifi_ui_FileDialogHelper_h

#include <QtCore/QFileSystemWatcher>
#include <QtCore/QObject>
#include <QtCore/QPointer>
#include <QtCore/QStandardPaths>
#include <QtCore/QString>
#include <QtCore/QStringList>
#include <QtCore/QUrl>

#include <functional>

class QFileDialog;

class FileDialogHelper : public QObject {
    Q_OBJECT
    Q_ENUMS(StandardLocation)

public:
    // Do not re-order, must match QDesktopServices
    enum StandardLocation {
        DesktopLocation,
        DocumentsLocation,
        FontsLocation,
        ApplicationsLocation,
        MusicLocation,
        MoviesLocation,
        PicturesLocation,
        TempLocation,
        HomeLocation,
        DataLocation,
        CacheLocation,
        GenericDataLocation,
        RuntimeLocation,
        ConfigLocation,
        DownloadLocation,
        GenericCacheLocation,
        GenericConfigLocation,
        AppDataLocation,
        AppConfigLocation,
        AppLocalDataLocation = DataLocation
    };

    ~FileDialogHelper() override;

    // Native provider adapters enforce these bounds while copying. Desktop
    // QFileDialog paths retain their existing behavior without copying limits.
    static constexpr int MAX_DOCUMENT_COUNT = 32;
    static constexpr qint64 MAX_DOCUMENT_BYTES = 256 * 1024 * 1024;
    static constexpr qint64 MAX_DOCUMENT_TOTAL_BYTES = 512 * 1024 * 1024;
    using DocumentSelection = std::function<void(const QList<QUrl>&, const QString&)>;
    using DocumentPickerOperator = std::function<bool(const QString&, const QString&, const QString&, bool, DocumentSelection)>;
    using DocumentPickerCancel = std::function<void(const QString&)>;
    // Platform adapters materialize provider bytes and retain the resulting
    // local files. No content/provider URL enters the script or asset engine.
    static void setDocumentPickerOperator(DocumentPickerOperator picker, DocumentPickerCancel cancel);

    // Empty return means busy/unavailable; otherwise signals carry this request ID.
    Q_INVOKABLE QString openDocuments(const QString& caption, const QString& filter, bool multiple = false);

    Q_INVOKABLE bool cancelDocuments(const QString& requestId);

    Q_INVOKABLE QUrl home();
    Q_INVOKABLE QStringList standardPath(StandardLocation location);
    Q_INVOKABLE QString writableLocation(StandardLocation location);
    Q_INVOKABLE QStringList drives();
    Q_INVOKABLE QString urlToPath(const QUrl& url);
    Q_INVOKABLE bool urlIsDir(const QUrl& url);
    Q_INVOKABLE bool urlIsFile(const QUrl& url);
    Q_INVOKABLE bool urlExists(const QUrl& url);
    Q_INVOKABLE bool urlIsWritable(const QUrl& url);
    Q_INVOKABLE bool fileExists(const QString& path);
    Q_INVOKABLE bool validPath(const QString& path);
    Q_INVOKABLE bool validFolder(const QString& path);
    Q_INVOKABLE QUrl pathToUrl(const QString& path);
    Q_INVOKABLE QUrl saveHelper(const QString& saveText, const QUrl& currentFolder, const QStringList& selectionFilters);
    Q_INVOKABLE QList<QUrl> urlToList(const QUrl& url);

    static void setOpenDirectoryOperator(std::function<void(const QString&)> openDirectoryOperator) { _openDirectoryOperator = openDirectoryOperator; }
    Q_INVOKABLE void openDirectory(const QString& path);

    Q_INVOKABLE void monitorDirectory(const QString& path);

signals:
    void contentsChanged();
    void documentsSelected(const QString& requestId, const QList<QUrl>& urls);
    void documentSelectionCanceled(const QString& requestId);
    void documentSelectionFailed(const QString& requestId, const QString& message);

private:
    QPointer<QFileDialog> _documentDialog;
    QString _documentRequestId;
    bool _nativeDocumentPending { false };
    bool _multipleDocuments { false };
    DocumentPickerCancel _documentCancel;
    void finishDocuments(const QString& requestId, const QList<QUrl>& urls, const QString& error);
    QFileSystemWatcher _fsWatcher;
    QString _fsWatcherPath;
    static std::function<void(const QString&)> _openDirectoryOperator;
};


#endif
