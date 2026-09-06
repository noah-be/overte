#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QUrlQuery>
#include <QtCore/QTimer>
#include <QtCore/QEventLoop>
#include <QtCore/QElapsedTimer>
#include <QtCore/QPointer>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include "security/redaction/SafeDiagnostics.h"
#include "libraries/networking/src/RequestCancellation.h"
#include <cassert>

Q_LOGGING_CATEGORY(networking, "overte.test.account-request")
const QString ACCOUNT_MANAGER_REQUESTED_SCOPE = "owner";
class Reply : public QNetworkReply {
public:
    inline static int aborted = 0;
    inline static QEventLoop* deadlineLoop = nullptr;
    explicit Reply(QObject* parent) : QNetworkReply(parent) { open(QIODevice::ReadOnly); }
    void abort() override {
        assert(property("_overte_account_auth_timed_out").toBool());
        ++aborted;
        finish(); // Deliberately NoError: terminal callback must use the timeout fence.
        if (aborted == 5 && deadlineLoop) deadlineLoop->quit();
        if (property("delete_on_abort").toBool()) delete this;
    }
    void finish() { setFinished(true); emit finished(); }
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
    overte::network::RequestScope _credentialContext;
    QUrl _authURL { "https://auth-private.invalid" };
    bool _isWaitingForTokenRefresh = false;
    bool _isWaitingForAccessToken = false;
    int loginFinished = 0, refreshFinished = 0;
    QString _userAgentGetter() { return "overte-request-test"; }
    QString getMetaverseServerURLPath() { return "/api"; }
    void requestAccessToken(const QString&, const QString&);
    void requestAccessTokenWithAuthCode(const QString&, const QString&, const QString&, const QString&);
    void requestAccessTokenWithSteam(QByteArray);
    void requestAccessTokenWithOculus(const QString&, const QString&);
    void refreshAccessToken();
public slots:
    void requestAccessTokenError(QNetworkReply::NetworkError) {}
    // Receiver state boundary; complete production receivers run separately.
    // Count stale delivery here as well to exercise every original timer.
    void requestAccessTokenFinished() {
        ++loginFinished;
        if (overte::network::replyCurrent(qobject_cast<QNetworkReply*>(sender()))) _isWaitingForAccessToken = false;
    }
    void refreshAccessTokenFinished() {
        ++refreshFinished;
        if (overte::network::replyCurrent(qobject_cast<QNetworkReply*>(sender()))) _isWaitingForTokenRefresh = false;
    }
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
        const auto ticket = network.reply->property("_overte_request_ticket");
        assert(ticket.canConvert<overte::network::RequestTicket>());
        assert(ticket.value<overte::network::RequestTicket>().sameRequest(manager._credentialContext.snapshot()));
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
    assert(network.posts == 5 && !manager._isWaitingForTokenRefresh);
    QEventLoop loop;
    Reply::deadlineLoop = &loop;
    QElapsedTimer elapsed;
    elapsed.start();
    // Independent owners keep all five requests current for the original15s
    // deadline check. Superseded same-owner requests now abort via RequestScope
    // first; that behavior is exercised by the full context fixture instead.
    AccountManager deadlines[5];
    deadlines[4]._accountInfo.token.refreshToken = seed;
    deadlines[4].refreshAccessToken();
    QPointer<Reply> hungRefresh(network.reply);
    network.reply->setProperty("delete_on_abort", true);
    deadlines[0].requestAccessToken(seed, seed);
    QPointer<Reply> hungPassword(network.reply);
    deadlines[1].requestAccessTokenWithAuthCode(seed, seed, seed, seed);
    QPointer<Reply> hungCode(network.reply);
    deadlines[2].requestAccessTokenWithSteam(steam);
    QPointer<Reply> hungSteam(network.reply);
    deadlines[3].requestAccessTokenWithOculus(seed, seed);
    QPointer<Reply> hungOculus(network.reply);
    const int beforeBlockedRefresh = network.posts;
    deadlines[3].refreshAccessToken();
    assert(network.posts == beforeBlockedRefresh);
    manager.requestAccessToken(seed, seed);
    delete network.reply; // Reply-context destruction cancels its timer.
    QTimer::singleShot(16500, &loop, &QEventLoop::quit);
    loop.exec();
    assert(Reply::aborted == 5 && elapsed.elapsed() >= 15000);
    assert(manager.loginFinished == 4 && manager.refreshFinished == 1);
    for (int i = 0; i < 4; ++i) assert(deadlines[i].loginFinished == 1 && deadlines[i].refreshFinished == 0);
    assert(deadlines[4].loginFinished == 0 && deadlines[4].refreshFinished == 1);
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    assert(!hungPassword && !hungCode && !hungSteam && !hungOculus && !hungRefresh);
    Reply::deadlineLoop = nullptr;
}
