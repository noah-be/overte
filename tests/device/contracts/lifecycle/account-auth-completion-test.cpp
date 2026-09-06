#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QPointer>
#include <QtCore/QLoggingCategory>
#include <QtNetwork/QNetworkReply>
#include "security/redaction/SafeDiagnostics.h"
#include "libraries/networking/src/RequestCancellation.h"
#include <cassert>
#include <cstring>

Q_LOGGING_CATEGORY(networking, "overte.test.account-completion")
// Explicit storage/profile boundaries: this fixture does not fake their evidence.
struct DataServerAccountInfo {
    QJsonObject tokens;
    void setAccessTokenFromJSON(const QJsonObject& object) { tokens = object; }
};
class AccountManager : public QObject {
    Q_OBJECT
public:
    DataServerAccountInfo _accountInfo;
    int persisted = 0, profiles = 0;
    bool _isWaitingForTokenRefresh = true;
    QString getMetaverseServerURLPath() { return "/api"; }
    void persistAccountToFile() { ++persisted; }
    void requestProfile() { ++profiles; }
    void requestAccessTokenFinished();
    void refreshAccessTokenFinished();
signals:
    void loginComplete(QUrl);
    void loginFailed();
};
struct Reply : QNetworkReply {
    QByteArray payload; qint64 offset = 0;
    explicit Reply(QByteArray bytes, int status, bool error) : payload(std::move(bytes)) {
        setUrl(QUrl("https://auth-private.invalid/api/oauth/token"));
        setAttribute(QNetworkRequest::HttpStatusCodeAttribute, status);
        if (error) setError(QNetworkReply::RemoteHostClosedError, "error-private-canary");
        open(QIODevice::ReadOnly | QIODevice::Unbuffered);
    }
    void finish() { setFinished(true); emit finished(); }
    void abort() override {}
    qint64 bytesAvailable() const override { return payload.size() - offset + QNetworkReply::bytesAvailable(); }
    qint64 readData(char* output, qint64 maximum) override {
        const auto size = qMin(maximum, qint64(payload.size()) - offset);
        if (size == 0) return -1;
        std::memcpy(output, payload.constData() + offset, size_t(size)); offset += size;
        return size;
    }
};
#include "completion.inc"
#include "completion.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const QByteArray good("{\"access_token\":\"token-canary\",\"expires_in\":3600,\"token_type\":\"Bearer\"}");
    for (bool refreshing : {false, true}) {
    auto check = [&](QByteArray payload, int status, bool error, bool accepted, bool timedOut = false) {
        AccountManager manager;
        manager._accountInfo.tokens.insert("prior", true);
        int success = 0, failure = 0;
        QObject::connect(&manager, &AccountManager::loginComplete, [&](const QUrl& root) {
            ++success; assert(root.path() == "/api");
        });
        QObject::connect(&manager, &AccountManager::loginFailed, [&] { ++failure; });
        QPointer<Reply> reply = new Reply(std::move(payload), status, error);
        reply->setProperty("_overte_account_auth_timed_out", timedOut);
        QObject::connect(reply.data(), &QNetworkReply::finished, &manager,
                         refreshing ? &AccountManager::refreshAccessTokenFinished : &AccountManager::requestAccessTokenFinished);
        reply->finish();
        assert(success == int(accepted && !refreshing) && failure == int(!accepted && !refreshing));
        assert(manager.persisted == int(accepted) && manager.profiles == int(accepted && !refreshing));
        if (refreshing) assert(!manager._isWaitingForTokenRefresh);
        if (accepted) assert(manager._accountInfo.tokens.value("access_token") == "token-canary");
        else assert(manager._accountInfo.tokens.value("prior").toBool());
        reply->finish();
        assert(success == int(accepted && !refreshing) && failure == int(!accepted && !refreshing));
        assert(manager.persisted == int(accepted));
        if (refreshing) manager.refreshAccessTokenFinished();
        else manager.requestAccessTokenFinished(); // No sender must not dereference null.
        assert(success == int(accepted && !refreshing) && failure == int(!accepted && !refreshing));
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!reply);
    };
    check("{}", 200, false, false); // Old source silently leaves the UI pending.
    for (const QByteArray& invalid : {QByteArray("{"), QByteArray("[]"), QByteArray("null"),
                                    QByteArray("{\"error\":\"private-provider-canary\"}"),
                                    QByteArray("{\"access_token\":\"t\",\"expires_in\":1}")}) {
        check(invalid, 200, false, false);
    }
    check(good, 200, false, true);
    check(good, 200, false, false, true); // Abort with NoError cannot revive a timeout.
    const auto goodObject = QJsonDocument::fromJson(good).object();
    for (const auto& key : {QString("access_token"), QString("token_type")}) {
        for (const QJsonValue& invalid : {QJsonValue(), QJsonValue(false), QJsonValue(12),
                                       QJsonValue(QJsonObject()), QJsonValue("")}) {
            auto object = goodObject; object.insert(key, invalid);
            check(QJsonDocument(object).toJson(), 200, false, false);
        }
    }
    for (const QJsonValue& invalid : {QJsonValue(), QJsonValue(true), QJsonValue("3600"),
                                   QJsonValue(-1), QJsonValue(0), QJsonValue(0.5),
                                   QJsonValue(2147483648.0), QJsonValue(1e100)}) {
        auto object = goodObject; object.insert("expires_in", invalid);
        check(QJsonDocument(object).toJson(), 200, false, false);
    }
    for (const QJsonValue& invalid : {QJsonValue(), QJsonValue(false), QJsonValue(12),
                                   QJsonValue(QJsonObject())}) {
        auto object = goodObject; object.insert("refresh_token", invalid);
        check(QJsonDocument(object).toJson(), 200, false, false);
    }
    for (int lifetime : {1, 2147483647}) {
        auto object = goodObject; object.insert("expires_in", lifetime);
        object.insert("refresh_token", ""); // Empty optional refresh token means no refresh.
        check(QJsonDocument(object).toJson(), 200, false, true);
        object.insert("refresh_token", "refresh-canary");
        check(QJsonDocument(object).toJson(), 200, false, true);
    }
    check(good, 302, false, false);
    check(good, 401, false, false);
    check(good, 500, false, false);
    check(good, 200, true, false);
    QByteArray exact = good.left(good.size() - 1) + ",\"padding\":\"";
    exact += QByteArray(1024 * 1024 - exact.size() - 2, 'x'); exact += "\"}";
    assert(exact.size() == 1024 * 1024);
    check(exact, 200, false, true);
    check(exact + ' ', 200, false, false);
    }
}
