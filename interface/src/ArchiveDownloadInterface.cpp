//
//  ArchiveDownloadInterface.cpp
//  libraries/script-engine/src
//
//  Created by Elisa Lupin-Jimenez on 6/28/16.
//  Copyright 2016 High Fidelity, Inc.
//  Copyright 2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "ArchiveDownloadInterface.h"

#include <QtCore/QTemporaryDir>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QDebug>
#include <QtCore/QBuffer>
#include <QtCore/QIODevice>
#include <QtCore/QUrl>
#include <QtCore/QByteArray>
#include <QtCore/QString>
#include <QtCore/QFileInfo>
#include <QtCore/QSet>

#if !defined(Q_OS_IOS)
#include <quazip/quazip.h>
#include <quazip/JlCompress.h>
#endif

#include "ResourceManager.h"
#include "ScriptEngineLogging.h"

namespace {

#if !defined(Q_OS_IOS)

constexpr int MAX_ARCHIVE_ENTRIES = 4096;
constexpr qint64 MAX_ARCHIVE_FILE_BYTES = 256LL * 1024 * 1024;
constexpr qint64 MAX_ARCHIVE_TOTAL_BYTES = 512LL * 1024 * 1024;
constexpr int MAX_ARCHIVE_PATH_BYTES = 1024;

bool validateArchive(QuaZip& archive) {
    if (!archive.open(QuaZip::mdUnzip)) {
        return false;
    }

    QSet<QString> paths;
    qint64 totalBytes { 0 };
    int entryCount { 0 };
    bool valid { true };
    if (archive.goToFirstFile()) {
        do {
            QuaZipFileInfo64 info;
            if (!archive.getCurrentFileInfo(&info)) {
                valid = false;
                break;
            }
            QString path = archive.getCurrentFileName();
            const bool directory = path.endsWith('/');
            if (directory) {
                path.chop(1);
            }
            const QString cleanPath = QDir::cleanPath(path);
            if (path.isEmpty() || path.contains('\\') || QDir::isAbsolutePath(path) ||
                    cleanPath != path || cleanPath == ".." || cleanPath.startsWith("../") ||
                    path.toUtf8().size() > MAX_ARCHIVE_PATH_BYTES ||
                    info.isSymbolicLink() || paths.contains(cleanPath) ||
                    ++entryCount > MAX_ARCHIVE_ENTRIES ||
                    info.uncompressedSize > static_cast<quint64>(MAX_ARCHIVE_FILE_BYTES) ||
                    info.uncompressedSize > static_cast<quint64>(MAX_ARCHIVE_TOTAL_BYTES - totalBytes)) {
                valid = false;
                break;
            }
            paths.insert(cleanPath);
            totalBytes += static_cast<qint64>(info.uncompressedSize);
        } while (archive.goToNextFile());
    }

    archive.close();
    return valid && archive.getZipError() == UNZ_OK;
}

QStringList extractArchiveSafely(const QString& archivePath, const QString& target) {
    QFile archiveFile(archivePath);
    if (!archiveFile.open(QIODevice::ReadOnly)) {
        return {};
    }

    QuaZip archive(&archiveFile);
    if (!validateArchive(archive)) {
        return {};
    }

    QStringList extracted = JlCompress::extractDir(archive, target);
    if (extracted.isEmpty()) {
        QDir(target).removeRecursively();
    }
    return extracted;
}
#endif

} // namespace


ArchiveDownloadInterface::ArchiveDownloadInterface(QObject* parent) : QObject(parent) {
    // nothing for now
}

void ArchiveDownloadInterface::runUnzip(QString path, QUrl url, bool autoAdd, bool isZip) {
    QString fileName = "/" + path.section("/", -1);
    QString tempDir = path;
    if (!isZip) {
        tempDir.remove(fileName);
    } else {
        QTemporaryDir zipTemp;
        tempDir = zipTemp.path();
        path.remove("file:///");
    }
    
    qCDebug(scriptengine) << "Temporary directory at: " + tempDir;
    if (!isTempDir(tempDir)) {
        qCDebug(scriptengine) << "Temporary directory mismatch; risk of losing files";
        return;
    }

    QStringList fileList = unzipFile(path, tempDir);
    
    if(fileList.isEmpty()) {
        qCDebug(scriptengine) << "Unzip failed";
    }

    if (path.contains("vr.google.com/downloads")) {
        isZip = true;
    }
    if (!hasModel(fileList)) {
        isZip = false;
    }

    emit unzipResult(path, fileList, autoAdd, isZip);

}

QStringList ArchiveDownloadInterface::unzipFile(QString path, QString tempDir) {
#if defined(Q_OS_IOS)
    Q_UNUSED(path)
    Q_UNUSED(tempDir)
    qCWarning(scriptengine) << "Archive extraction is unavailable on iOS until a Qt 6 QuaZIP package is integrated";
    return {};
#else
    QDir dir(path);
    QString dirName = dir.path();
    qCDebug(scriptengine) << "Directory to unzip: " << dirName;
    QString target = tempDir + "/model_repo";
    QStringList list = extractArchiveSafely(dirName, target);

    qCDebug(scriptengine) << list;

    if (!list.isEmpty()) {
        return list;
    } else {
        qCDebug(scriptengine) << "Extraction failed";
        return list;
    }
#endif
}

// fix to check that we are only referring to a temporary directory
bool ArchiveDownloadInterface::isTempDir(QString tempDir) {
    QString folderName = "/" + tempDir.section("/", -1);
    QString tempContainer = tempDir;
    tempContainer.remove(folderName);
    QTemporaryDir test;
    QString testDir = test.path();
    folderName = "/" + testDir.section("/", -1);
    QString testContainer = testDir;
    testContainer.remove(folderName);
    return (testContainer == tempContainer);
}

bool ArchiveDownloadInterface::hasModel(QStringList fileList) {
    for (int i = 0; i < fileList.size(); i++) {
        if (fileList.at(i).toLower().contains(".fbx") || fileList.at(i).toLower().contains(".obj")) {
            return true;
        }
    }
    return false;
}

QString ArchiveDownloadInterface::getTempDir() {
    QTemporaryDir dir;
    dir.setAutoRemove(false);
    return dir.path();
    // do something to delete this temp dir later
}

QString ArchiveDownloadInterface::convertUrlToPath(QUrl url) {
    QString newUrl;
    QString oldUrl = url.toString();
    newUrl = oldUrl.section("filename=", 1, 1);
    return newUrl;
}

// this function is not in use
void ArchiveDownloadInterface::downloadZip(QString path, const QString link) {
    QUrl url = QUrl(link);
    auto request = DependencyManager::get<ResourceManager>()->createResourceRequest(
        nullptr, url, true, -1, "ArchiveDownloadInterface::downloadZip");
    connect(request, &ResourceRequest::finished, this, [this, path]{
        unzipFile(path, ""); // so intellisense isn't mad
    });
    request->send();
}

// this function is not in use
void ArchiveDownloadInterface::recursiveFileScan(QFileInfo file, QString* dirName) {
    /*if (!file.isDir()) {
        return;
    }*/
    QFileInfoList files;
    if (file.fileName().contains(".zip")) {
#if !defined(Q_OS_IOS)
        extractArchiveSafely(file.fileName(), file.dir().path());
#endif
    }
    files = file.dir().entryInfoList();

    /*if (files.empty()) {
        files = JlCompress::getFileList(file.fileName());
    }*/

    foreach (QFileInfo file, files) {
        recursiveFileScan(file, dirName);
    }
    return;
}
