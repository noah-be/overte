#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QPointer>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include "security/redaction/SafeDiagnostics.h"
#include "libraries/networking/src/RequestCancellation.h"
#include "libraries/networking/src/AccountSettings.h"
#include <cassert>
#include <cstring>
#include <functional>

Q_LOGGING_CATEGORY(networking, "overte.test.settings-upload")
const QByteArray ACCESS_TOKEN_AUTHORIZATION_HEADER = "Authorization";
const int MAX_PULL_RETRIES = 3;
class Reply : public QNetworkReply {
    qint64 offset = 0;
public:
    QByteArray payload = "{\"status\":\"success\"}";
    std::function<void()> onRead;
    Reply(QObject* parent) : QNetworkReply(parent) {
        open(QIODevice::ReadOnly); setAttribute(QNetworkRequest::HttpStatusCodeAttribute, 200);
    }
    void status(int code) { setAttribute(QNetworkRequest::HttpStatusCodeAttribute, code); }
    void fail() { setError(QNetworkReply::ConnectionRefusedError, "fixture"); }
    void finish() { setFinished(true); emit finished(); }
    void abort() override { finish(); }
    qint64 bytesAvailable() const override { return payload.size() - offset + QNetworkReply::bytesAvailable(); }
    qint64 readData(char* dest, qint64 size) override {
        if (onRead) { auto action = std::move(onRead); onRead = {}; action(); }
        size = qMin(size, qint64(payload.size()) - offset);
        if (!size) return -1;
        std::memcpy(dest, payload.constData() + offset, size_t(size)); offset += size; return size;
    }
};
class NetworkAccessManager : public QNetworkAccessManager {
public:
    Reply* last = nullptr;
    QList<QByteArray> payloads;
    QList<QPointer<Reply>> created;
    std::function<void()> onPut;
    static NetworkAccessManager& getInstance() { static NetworkAccessManager instance; return instance; }
protected:
    QNetworkReply* createRequest(Operation operation, const QNetworkRequest&, QIODevice* body) override {
        assert(operation == PutOperation || operation == GetOperation);
        if (body) payloads.append(body->readAll());
        auto* reply = new Reply(this);
        last = reply; created.append(reply);
        if (operation == GetOperation) reply->payload = "{\"status\":\"success\",\"data\":{\"home_location\":\"server-home\"}}";
        if (onPut) { auto action = std::move(onPut); onPut = {}; action(); }
        return reply;
    }
};
// Settings storage is an explicit boundary. The original manager PUT and
// completion below must bind its acknowledgement to the value actually sent.
class AccountManager : public QObject {
    Q_OBJECT
public:
    bool _accountSettingsEnabled = true;
    bool _isPostingAccountSettings = false, _isWaitingForAccessToken = false;
    overte::network::RequestScope _credentialContext, _settingsPostContext, _settingsGetContext;
    overte::network::RequestTicket _settingsSyncCredentials, _settingsRetryCredentials, _settingsRetryRequest;
    QUrl _authURL { "https://settings.invalid" };
    quint64 _lastSuccessfulSyncTimestamp = 0;
    QTimer pullTimer;
    QTimer* _pullSettingsRetryTimer = &pullTimer;
    QTimer postTimer;
    QTimer* _postSettingsTimer = &postTimer;
    int _numPullRetries = 0;
    AccountManager() {
        pullTimer.setSingleShot(true); pullTimer.setInterval(10000);
        postTimer.setInterval(10000);
        connect(&pullTimer, &QTimer::timeout, this, &AccountManager::requestAccountSettings);
    }
    struct Settings {
        quint64 stamp = 10;
        AccountSettings::State state = AccountSettings::Loaded;
        AccountSettings::State homeLocationState() const { return state; }
        void loggedOut() { stamp = 0; state = AccountSettings::LoggedOut; }
        quint64 lastChangeTimestamp() const { return stamp; }
        QJsonObject pack() const { return {{ "home_location", QString::number(stamp) }}; }
        AccountSettings::Snapshot snapshot() const { return {pack(), stamp}; }
        void startedLoading() {}
        void unpack(QJsonObject) { stamp = 30; state = AccountSettings::Loaded; }
        bool unpackIfUnchanged(const QJsonObject& data, quint64 expected, quint64& applied) {
            if (stamp != expected) return false;
            unpack(data); applied = stamp; return true;
        }
    } _settings;
    struct AccountInfo {
        struct Token { QByteArray authorizationHeaderValue() const { return "Bearer fixture"; } } token;
        const Token& getAccessToken() const { return token; }
    } _accountInfo;
    bool isLoggedIn() const { return true; }
    std::function<void()> onUserAgent;
    QString _userAgentGetter() {
        if (onUserAgent) { auto action = std::move(onUserAgent); onUserAgent = {}; action(); }
        return "fixture";
    }
    QString getMetaverseServerURLPath() const { return "/api"; }
    void postAccountSettings();
    void resetAccountSettings();
    void requestAccountSettings();
public slots:
    void postAccountSettingsFinished();
    void postAccountSettingsError(QNetworkReply::NetworkError);
    void requestAccountSettingsFinished();
    void requestAccountSettingsError(QNetworkReply::NetworkError);
signals:
    void accountSettingsLoaded();
};
#include "settings.inc"
#include "settings.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    auto& network = NetworkAccessManager::getInstance();
    AccountManager manager;
    manager.postAccountSettings(); auto* first = network.last;
    manager._settings.stamp = 20;
    manager.postAccountSettings();
    assert(network.last == first && network.payloads.size() == 1);
    assert(manager._isPostingAccountSettings && network.payloads[0].contains("10"));
    first->finish();
    assert(manager._lastSuccessfulSyncTimestamp == 10);
    manager.postAccountSettings(); auto* second = network.last;
    assert(second != first && network.payloads[1].contains("20"));
    first->finish(); // Duplicate old completion cannot release the newer PUT.
    assert(manager._isPostingAccountSettings);
    second->finish();
    assert(manager._lastSuccessfulSyncTimestamp == 20);
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    for (int boundary = 0; boundary < 3; ++boundary) {
        for (bool destroy : {false, true}) {
            QPointer<AccountManager> target = new AccountManager;
            const auto before = network.created.size();
            auto change = [&] {
                if (destroy) delete target.data();
                else target->_credentialContext.next();
            };
            if (boundary == 0) target->onUserAgent = change;
            if (boundary == 1) network.onPut = change;
            target->postAccountSettings();
            if (boundary == 2) {
                network.last->onRead = change;
                network.last->finish();
            }
            if (target) assert(target->_lastSuccessfulSyncTimestamp == 0);
            QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
            if (boundary == 0) assert(network.created.size() == before);
            else assert(!network.created[before]);
            if (target) assert(!target->_isPostingAccountSettings);
            delete target.data();
        }
    }
    for (bool putBoundary : {false, true}) {
        AccountManager target;
        const auto before = network.created.size();
        auto recursive = [&] { target.postAccountSettings(); };
        if (putBoundary) network.onPut = recursive;
        else target.onUserAgent = recursive;
        target.postAccountSettings();
        assert(network.created.size() == before + 1);
        network.last->finish();
        assert(target._lastSuccessfulSyncTimestamp == 10);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    }
    for (int invalid = 0; invalid < 7; ++invalid) {
        AccountManager target;
        target.postAccountSettings(); QPointer<Reply> reply(network.last);
        if (invalid == 0) reply->status(302);
        if (invalid == 1) reply->fail();
        if (invalid == 2) reply->payload = "{";
        if (invalid == 3) reply->payload = "[]";
        if (invalid == 4) reply->payload.append(QByteArray(1024 * 1024, ' '));
        if (invalid == 5) reply->setProperty("_overte_account_auth_timed_out", true);
        if (invalid == 6) target._credentialContext.next();
        reply->finish();
        assert(target._lastSuccessfulSyncTimestamp == 0 && !target._isPostingAccountSettings);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!reply);
        target.postAccountSettings();
        assert(target._isPostingAccountSettings);
        delete network.last;
        assert(!target._isPostingAccountSettings);
    }
    // A GET started before a local edit must neither overwrite that edit nor
    // mark its new timestamp as synchronized. Actual GET/finished are compiled.
    AccountManager downloading;
    downloading.requestAccountSettings(); auto* downloaded = network.last;
    downloading._settings.stamp = 20;
    downloaded->finish();
    assert(downloading._settings.stamp == 20);
    assert(downloading._lastSuccessfulSyncTimestamp == 0);
    assert(downloading.postTimer.isActive());
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    AccountManager editedDuringUserAgent;
    editedDuringUserAgent.onUserAgent = [&] { editedDuringUserAgent._settings.stamp = 20; };
    editedDuringUserAgent.requestAccountSettings(); network.last->finish();
    assert(editedDuringUserAgent._settings.stamp == 20 && editedDuringUserAgent.postTimer.isActive());
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    AccountManager failedDownload;
    failedDownload.requestAccountSettings();
    failedDownload._settings.stamp = 20;
    network.last->fail(); network.last->finish();
    assert(failedDownload._settings.stamp == 20 && failedDownload.postTimer.isActive());
    assert(!failedDownload.pullTimer.isActive() && failedDownload._numPullRetries == 0);
    failedDownload.postAccountSettings(); network.last->finish();
    assert(failedDownload._lastSuccessfulSyncTimestamp == 20);
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    for (int invalid = 0; invalid < 8; ++invalid) {
        AccountManager target;
        int loaded = 0;
        QObject::connect(&target, &AccountManager::accountSettingsLoaded, [&] { ++loaded; });
        target.requestAccountSettings(); QPointer<Reply> reply(network.last);
        if (invalid == 0) reply->status(302);
        if (invalid == 1) reply->fail();
        if (invalid == 2) reply->payload = "{";
        if (invalid == 3) reply->payload = "[]";
        if (invalid == 4) reply->payload.append(QByteArray(1024 * 1024, ' '));
        if (invalid == 5) reply->setProperty("_overte_account_auth_timed_out", true);
        if (invalid == 6) target._credentialContext.next();
        if (invalid == 7) target.postAccountSettings(); // Older GET cannot undo upload.
        reply->finish(); reply->finish();
        assert(target._settings.stamp == 10 && target._lastSuccessfulSyncTimestamp == 0 && loaded == 0);
        assert(target._numPullRetries == (invalid < 6 ? 1 : 0));
        const auto beforeRetry = network.created.size();
        target._credentialContext.next();
        QMetaObject::invokeMethod(&target.pullTimer, "timeout", Qt::DirectConnection);
        assert(network.created.size() == beforeRetry);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!reply);
    }
    for (int boundary = 0; boundary < 3; ++boundary) {
        for (bool destroy : {false, true}) {
            QPointer<AccountManager> target = new AccountManager;
            const auto before = network.created.size();
            auto change = [&] {
                if (destroy) delete target.data();
                else target->_credentialContext.next();
            };
            if (boundary == 0) target->onUserAgent = change;
            if (boundary == 1) network.onPut = change; // Shared createRequest seam, also GET.
            target->requestAccountSettings();
            if (boundary == 2) {
                network.last->onRead = change;
                network.last->finish();
            }
            if (target) assert(target->_settings.stamp == 10 && target->_numPullRetries == 0);
            QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
            if (boundary == 0) assert(network.created.size() == before);
            else assert(!network.created[before]);
            delete target.data();
        }
    }
    AccountManager retrying;
    retrying.requestAccountSettings(); network.last->fail(); network.last->finish();
    assert(retrying._numPullRetries == 1 && retrying.pullTimer.isActive());
    const auto beforeValidRetry = network.created.size();
    QMetaObject::invokeMethod(&retrying.pullTimer, "timeout", Qt::DirectConnection);
    assert(network.created.size() == beforeValidRetry + 1);
    network.last->finish();
    assert(retrying._settings.stamp == 30 && retrying._numPullRetries == 0 && !retrying.pullTimer.isActive());
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    AccountManager current;
    current.requestAccountSettings(); auto* staleGet = network.last;
    current.requestAccountSettings(); auto* latestGet = network.last;
    staleGet->finish();
    assert(current._settings.stamp == 10 && current._numPullRetries == 0);
    latestGet->finish();
    assert(current._settings.stamp == 30 && current._lastSuccessfulSyncTimestamp == 30);
    const auto beforeUnchanged = network.created.size();
    current.postAccountSettings();
    assert(network.created.size() == beforeUnchanged);
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    current.pullTimer.start(); current.postTimer.start(10000);
    current.resetAccountSettings();
    assert(current._settings.state == AccountSettings::LoggedOut && current._settings.stamp == 0);
    assert(!current.pullTimer.isActive() && !current.postTimer.isActive());
    assert(current._lastSuccessfulSyncTimestamp == 0 && !current._settingsSyncCredentials.scoped());
    current.postAccountSettings();
    assert(network.created.size() == beforeUnchanged);
    current.requestAccountSettings(); network.last->finish();
    assert(current._settings.state == AccountSettings::Loaded && current._lastSuccessfulSyncTimestamp == 30);
}
