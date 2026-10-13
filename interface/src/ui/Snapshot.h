//
//  Snapshot.h
//  interface/src/ui
//
//  Created by Stojce Slavkovski on 1/26/14.
//  Copyright 2014 High Fidelity, Inc.
//  Copyright 2022 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_Snapshot_h
#define hifi_Snapshot_h

#include <glm/glm.hpp>

#include <QString>
#include <QStandardPaths>
#include <QUrl>
#include <QTimer>
#include <QtGui/QImage>
#include <QHash>
#include <QMutex>
#include <QPointer>
#include <array>
#include "SnapshotCapture.h"

#include <SettingHandle.h>
#include <DependencyManager.h>

class QFile;
class QTemporaryFile;
class SnapshotUploader;

class SnapshotMetaData {
public:

    QUrl getURL() { return _URL; }
    void setURL(QUrl URL) { _URL = URL; }

private:
    QUrl _URL;
};


/*@jsdoc
 * The <code>Snapshot</code> API provides access to the path that snapshots are saved to. This path is that provided in 
 * Settings &gt; General &gt; Snapshots. Snapshots may be taken using <code>Window</code> API functions such as 
 * {@link Window.takeSnapshot}. Mobile clients save captures in the application-owned Snapshot directory.
 * The native review previews only files validated against that directory; it does not grant a web page filesystem access.
 *
 * @namespace Snapshot
 * 
 * @hifi-interface
 * @hifi-client-entity
 * @hifi-avatar
 */

class Snapshot : public QObject, public Dependency {
    Q_OBJECT
    SINGLETON_DEPENDENCY
public:
    Snapshot();
    ~Snapshot() override;
    QString saveSnapshot(QImage image, const QString& filename, const QString& pathname = QString());
    void save360Snapshot(const glm::vec3& cameraPosition,
                         const bool& cubemapOutputFormat,
                         const bool& notify,
                         const QString& filename, const SnapshotCapture& capture = {});
    QTemporaryFile* saveTempSnapshot(QImage image);
    SnapshotMetaData* parseSnapshotData(QString snapshotPath);

    Setting::Handle<QString> _snapshotsLocation{ "snapshotsLocation" };
    Setting::Handle<bool> _snapshotNotifications{ "snapshotNotifications", true };
    Setting::Handle<QString> _snapshotFormat{ "snapshotFormat" };
    Setting::Handle<QString> _animatedSnapshotFormat{ "animatedSnapshotFormat" };
    void uploadSnapshot(const QString& filename, const QUrl& href = QUrl(""));
    SnapshotCapture beginCapture(const QString& requestId);
    void captureStatus(const SnapshotCapture&, const QString& phase, const QString& path = {}, const QString& error = {});

signals:
    /*@jsdoc
     * Reports a ticketed capture phase: processing, complete, cancelled, or error.
     * Cancellation invalidates queued render and encode callbacks; a completed app-owned file is retained.
     * @function Snapshot.captureStatusChanged
     * @param {string} requestId - The capture request identifier supplied to Window.
     * @param {string} phase - The current phase.
     * @param {string} path - The saved or processing file, if available.
     * @param {string} error - A failure code, or an empty string.
     * @returns {Signal}
     */
    void captureStatusChanged(const QString& requestId, const QString& phase, const QString& path, const QString& error);
    /*@jsdoc
     * Reports success, cancelled, or error for a native upload. Cancellation suppresses
     * further callbacks and follow-up story requests; already received server data cannot be withdrawn.
     * @function Snapshot.uploadStatusChanged
     * @param {string} path - The original snapshot path.
     * @param {string} status - The terminal status.
     * @param {string} error - A failure code, or an empty string.
     * @returns {Signal}
     */
    void uploadStatusChanged(const QString& path, const QString& status, const QString& error);

    /*@jsdoc
     * Triggered when the path that snapshots are saved to is changed.
     * @function Snapshot.snapshotLocationSet
     * @param {string} location - The new snapshots location.
     * @returns {Signal}
     * @example <caption>Report when the snapshots location is changed.</caption>
     * // Run this script then change the snapshots location in Settings > General > Snapshots.
     * Snapshot.snapshotLocationSet.connect(function (path) {
     *     print("New snapshot location: " + path);
     * });
     */
    void snapshotLocationSet(const QString& value);

public slots:
    /*@jsdoc
     * Whether this client uses the native mobile Snapshot review.
     * @function Snapshot.nativeReviewEnabled
     * @returns {boolean} Whether the native review is selected.
     */
    Q_INVOKABLE bool nativeReviewEnabled() const;
    /*@jsdoc
     * Cancels an active ticketed capture without deleting completed snapshot files.
     * @function Snapshot.cancelCapture
     * @param {string} requestId - The active capture request identifier.
     */
    Q_INVOKABLE void cancelCapture(const QString& requestId);
    /*@jsdoc
     * Returns a native image preview URL only for an existing app-owned snapshot.
     * This does not grant browser document or script authority.
     * @function Snapshot.snapshotFileUrl
     * @param {string} path - The app-owned capture path.
     * @returns {string} The validated local URL, or an empty URL.
     */
    Q_INVOKABLE QUrl snapshotFileUrl(const QString& path) const;
    /*@jsdoc
     * Requests cancellation of the active image/story upload for a snapshot.
     * @function Snapshot.cancelUpload
     * @param {string} path - The original snapshot path.
     */
    Q_INVOKABLE void cancelUpload(const QString& path);

    /*@jsdoc
     * Gets the path that snapshots are saved to.
     * @function Snapshot.getSnapshotsLocation
     * @returns {string} The path to save snapshots to.
     */
    Q_INVOKABLE QString getSnapshotsLocation();

    /*@jsdoc
     * Sets the path that snapshots are saved to.
     * @function Snapshot.setSnapshotsLocation
     * @param {String} location - The path to save snapshots to.
     */
    Q_INVOKABLE void setSnapshotsLocation(const QString& location);
    
    /*@jsdoc
     * Gets the currently selected snapshot format.
     * @function Snapshot.getSnapshotFormat
     * @returns {string} Currently selected snapshot format.
     */
    Q_INVOKABLE QString getSnapshotFormat();

    /*@jsdoc
     * Sets the snapshot format.
     * @function Snapshot.setSnapshotFormat
     * @param {String} format - one of the format names returned by Snapshot.getAvailableSnapshotFormats().
     */
    Q_INVOKABLE void setSnapshotFormat(const QString& format);

    /*@jsdoc
     * Gets the currently selected animated snapshot format.
     * @function Snapshot.getAnimatedSnapshotFormat
     * @returns {Array.<string>} Currently selected snapshot format.
     */
    Q_INVOKABLE QString getAnimatedSnapshotFormat();

    /*@jsdoc
     * Sets the snapshot format.
     * @function Snapshot.setAnimatedSnapshotFormat
     * @param {String} format - one of the format names returned by Snapshot.getAvailableSnapshotFormats().
     */
    Q_INVOKABLE void setAnimatedSnapshotFormat(const QString& format);

    /*@jsdoc
     * Returns a list of supported snapshot formats.
     * @function Snapshot.getAvailableSnapshotFormats
     * @returns {Array.<string>} List of supported snapshot formats.
     */
    Q_INVOKABLE QStringList getAvailableSnapshotFormats();

    /*@jsdoc
     * Returns a list of supported snapshot formats with short descriptions.
     * @function Snapshot.getAvailableSnapshotFormatsWithDescriptions
     * @returns {Array.<string>} List of supported snapshot formats with short descriptions.
     */
    Q_INVOKABLE QStringList getAvailableSnapshotFormatsWithDescriptions();

    /*@jsdoc
     * Returns a list of supported animated snapshot formats.
     * @function Snapshot.getAvailableAnimatedSnapshotFormats
     * @returns {Array.<string>} List of supported animated snapshot formats.
     */
    Q_INVOKABLE QStringList getAvailableAnimatedSnapshotFormats();

    /*@jsdoc
     * Returns a list of supported animated snapshot formats with short descriptions.
     * @function Snapshot.getAvailableAnimatedSnapshotFormatsWithDescriptions
     * @returns {Array.<string>} List of supported animated snapshot formats with short descriptions.
     */
    Q_INVOKABLE QStringList getAvailableAnimatedSnapshotFormatsWithDescriptions();
    
    

private slots:
    void takeNextSnapshot();

private:
    QFile* savedFileForSnapshot(QImage& image,
                                       bool isTemporary,
                                       const QString& userSelectedFilename = QString(),
                                       const QString& userSelectedPathname = QString());
    QString _snapshotFilename;
    bool _notify360;
    bool _cubemapOutputFormat;
    QTimer _snapshotTimer;
    qint16 _snapshotIndex;
    bool _waitingOnSnapshot { false };
    bool _taking360Snapshot { false };
    bool _oldEnabled;
    QVariant _oldAttachedEntityId;
    QVariant _oldOrientation;
    QVariant _oldPosition;
    QVariant _oldMirrorProjection;
    QVariant _oldPortalProjection;
    int _oldTextureWidth { 0 };
    int _oldTextureHeight { 0 };
    QVariant _oldvFoV;
    QVariant _oldNearClipPlaneDistance;
    QVariant _oldFarClipPlaneDistance;
    QImage _imageArray[6];
    void restoreSecondaryCamera();
    static QImage convertToCubemap(std::array<QImage, 6> images, SnapshotCapture capture);
    static QImage convertToEquirectangular(std::array<QImage, 6> images, SnapshotCapture capture);
    void complete360(const QImage&, const QString&, bool, const SnapshotCapture&);
    SnapshotCapture _capture360;
    QMutex _captureMutex;
    QHash<QString, SnapshotCapture> _captures;
    QHash<QString, QPointer<SnapshotUploader>> _uploads;
    bool _uploadContextConnected { false };
    void cancelUploads();
};

#endif // hifi_Snapshot_h
