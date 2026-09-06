#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QUrlQuery>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>

Q_LOGGING_CATEGORY(networking, "overte.test.account-request")
const QString ACCOUNT_MANAGER_REQUESTED_SCOPE = "owner";
class Reply : public QNetworkReply {
public:
    explicit Reply(QObject* parent) : QNetworkReply(parent) { open(QIODevice::ReadOnly); }
    void abort() override {}
    void finish() { emit finished(); }
    qint64 readData(char*, qint64) override { return -1; }
};
class NetworkAccessManager : public QNetworkAccessManager {
public:
    QNetworkRequest observed;
    QByteArray body;
    int posts = 0;
    Reply* reply = nullptr;
    static NetworkAccessManager& getInstance() { static NetworkAccessManager manager; return manager; }
protected:
    QNetworkReply* createRequest(Operation operation, const QNetworkRequest& request, QIODevice* data) override {
        assert(operation == PostOperation && data);
        ++posts; observed = request; body = data->readAll();
        reply = new Reply(this);
        return reply; // Actual Qt POST boundary: no socket/TLS/provider is simulated.
    }
};
struct Token { QString refreshToken; };
struct AccountInfo {
    Token token;
    const Token& getAccessToken() const { return token; }
};
class AccountManager : public QObject {
    Q_OBJECT
public:
    AccountInfo _accountInfo;
    QUrl _authURL { "https://auth-private.invalid" };
    bool _isWaitingForTokenRefresh = false;
    int loginFinished = 0, refreshFinished = 0;
    QString _userAgentGetter() { return "overte-request-test"; }
    QString getMetaverseServerURLPath() { return "/api"; }
    void requestAccessToken(const QString&, const QString&);
    void requestAccessTokenWithAuthCode(const QString&, const QString&, const QString&, const QString&);
    void requestAccessTokenWithSteam(QByteArray);
    void requestAccessTokenWithOculus(const QString&, const QString&);
    void refreshAccessToken();
public slots:
    void requestAccessTokenFinished() { ++loginFinished; }
    void refreshAccessTokenFinished() { ++refreshFinished; }
    void requestAccessTokenError(QNetworkReply::NetworkError) {}
    void refreshAccessTokenError(QNetworkReply::NetworkError) {}
};
#include "requests.inc"
#include "requests.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    auto& network = NetworkAccessManager::getInstance();
    AccountManager manager;
    const QString seed = QString::fromUtf8("secret&scope=foreign+%#= \r\nümlaut");
    auto check = [&](const QMap<QString, QString>& expected, bool refresh = false) {
        assert(network.observed.url() == QUrl("https://auth-private.invalid/api/oauth/token"));
        assert(network.observed.header(QNetworkRequest::ContentTypeHeader) == "application/x-www-form-urlencoded");
        const auto pairs = QUrlQuery(QString::fromUtf8(network.body)).queryItems(QUrl::FullyDecoded);
        assert(pairs.size() == expected.size()); // No injected grant/scope/extra field.
        for (const auto& pair : pairs) assert(expected.contains(pair.first) && expected.value(pair.first) == pair.second);
        assert(!network.body.contains('+') && !network.body.contains('\r') && !network.body.contains('\n'));
        assert(network.observed.attribute(QNetworkRequest::RedirectPolicyAttribute).isValid());
        assert(network.observed.attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() ==
               QNetworkRequest::ManualRedirectPolicy);
        const int beforeLogin = manager.loginFinished, beforeRefresh = manager.refreshFinished;
        network.reply->finish();
        assert(manager.loginFinished == beforeLogin + int(!refresh));
        assert(manager.refreshFinished == beforeRefresh + int(refresh));
    };
    manager.requestAccessTokenWithAuthCode(seed, seed, seed, seed);
    check({{"grant_type", "authorization_code"}, {"client_id", seed}, {"client_secret", seed},
           {"code", seed}, {"redirect_uri", seed}});
    manager.requestAccessToken(seed, seed);
    check({{"grant_type", "password"}, {"username", seed}, {"password", seed}, {"scope", "owner"}});
    manager.requestAccessTokenWithOculus(seed, seed);
    check({{"grant_type", "password"}, {"oculus_nonce", seed}, {"oculus_id", seed}, {"scope", "owner"}});
    const QByteArray steam("steam&scope=foreign+%#= \r\n");
    manager.requestAccessTokenWithSteam(steam);
    check({{"grant_type", "password"}, {"steam_auth_ticket", QString::fromUtf8(steam)}, {"scope", "owner"}});
    manager.refreshAccessToken();
    assert(network.posts == 4 && !manager._isWaitingForTokenRefresh);
    manager._accountInfo.token.refreshToken = seed;
    manager.refreshAccessToken();
    check({{"grant_type", "refresh_token"}, {"refresh_token", seed}, {"scope", "owner"}}, true);
    assert(network.posts == 5 && manager._isWaitingForTokenRefresh);
}
