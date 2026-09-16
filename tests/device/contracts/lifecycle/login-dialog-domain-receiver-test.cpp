// Real QObject/moc, QML Connections and original constructor; manager and
// application dependencies are explicit test boundaries, not native providers.
#include <QtCore/QCoreApplication>
#include <QtCore/QSharedPointer>
#include <QtCore/QUrl>
#include <QtQml/QQmlComponent>
#include <QtQml/QQmlContext>
#include <QtQml/QQmlEngine>
#include <QtQml/QJSValue>
#include <cassert>
#include "interface/src/ui/PhoneLoginState.h"
#include "interface/src/ui/AccountLoginStateBinding.h"
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"

using QQuickItem = QObject;
using OffscreenQmlDialog = QObject;
class AccountManager : public QObject {
    Q_OBJECT
signals:
    void loginComplete(const QUrl& authURL);
    void loginFailed();
};
class DomainAccountManager : public QObject {
    Q_OBJECT
public:
    enum class LoginOutcome { Succeeded, Failed, Cancelled, TimedOut, ResponseRejected };
    overte::network::RequestScope scope;
    bool pending {};
    bool rejectStart {};
    overte::network::RequestTicket latest;
    bool isAccessTokenRequestPending() const { return pending; }
    overte::network::RequestTicket accessTokenRequestTicket() const { return pending ? latest : overte::network::RequestTicket(); }
    overte::network::RequestTicket requestAccessToken(const QString&, const QString&) {
        scope.setActive(!rejectStart);
        pending = !rejectStart; latest = scope.next(); return latest;
    }
    void finish(LoginOutcome outcome) {
        pending = false;
        if (outcome == LoginOutcome::Cancelled || outcome == LoginOutcome::TimedOut || outcome == LoginOutcome::ResponseRejected) {
            scope.next();
        }
        emit loginRequestFinished(latest, scope.snapshot(), static_cast<int>(outcome));
    }
signals:
    void loginComplete();
    void loginFailed();
    void loginRequestFinished(overte::network::RequestTicket ticket, overte::network::RequestTicket context, int outcome);
};
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() {
        static auto object = QSharedPointer<T>::create();
        return object;
    }
};
class Application : public QCoreApplication {
    Q_OBJECT
public:
    using QCoreApplication::QCoreApplication;
    int dismissals { 0 };
public slots:
    void onDismissedLoginDialog() { ++dismissals; }
signals:
    void loginDialogFocusEnabled();
    void loginDialogFocusDisabled();
};
class LoginDialog : public QObject {
    Q_OBJECT
public:
    LoginDialog(QQuickItem* parent = nullptr);
    void loginDomain(const QString&, const QString&) const;
    bool getDomainLoginRequested() const { return true; } // Actual DialogsManager selection boundary.
    mutable overte::network::RequestTicket _domainLoginRequest;
    int domainDismissals {};
    Q_INVOKABLE void dismissLoginDialog() { ++domainDismissals; }
signals:
    void handleLoginCompleted();
    void handleLoginFailed();
    void handleDomainLoginFailed(const QString& reason);
    void dismissedLoginDialog();
    void focusEnabled();
    void focusDisabled();
};
PhoneLoginState phoneLoginState;
QPointer<AccountLoginStateBinding<AccountManager>> phoneAccountLoginBinding;
#include "receiver.moc"
// Define production switches only after host Qt/moc headers are parsed.
#if TEST_ANDROID
#define Q_OS_ANDROID
#endif
#if TEST_PHONE
#define ANDROID_APP_PHONE_INTERFACE
#endif
#if TEST_IOS
#define Q_OS_IOS
#endif
#undef qApp
#define qApp static_cast<Application*>(QCoreApplication::instance())
#include "constructor.inc"

int main(int argc, char** argv) {
    Application app(argc, argv);
    qRegisterMetaType<overte::network::RequestTicket>();
    auto account = DependencyManager::get<AccountManager>();
    auto domain = DependencyManager::get<DomainAccountManager>();
    int completed = 0, failed = 0, domainFailed = 0, focused = 0, unfocused = 0;
    {
        LoginDialog dialog;
        QObject::connect(&dialog, &LoginDialog::handleLoginCompleted, &app, [&] { ++completed; });
        QObject::connect(&dialog, &LoginDialog::handleLoginFailed, &app, [&] { ++failed; });
        QObject::connect(&dialog, &LoginDialog::handleDomainLoginFailed, &app, [&] { ++domainFailed; });
        QObject::connect(&dialog, &LoginDialog::focusEnabled, &app, [&] { ++focused; });
        QObject::connect(&dialog, &LoginDialog::focusDisabled, &app, [&] { ++unfocused; });
        QQmlEngine engine;
        engine.rootContext()->setContextProperty("loginDialog", &dialog);
        auto avatar = engine.newObject();
        engine.rootContext()->setContextProperty("MyAvatar", QVariant::fromValue(avatar));
        QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
        if (component.isError()) qFatal("%s", qPrintable(component.errorString()));
        QScopedPointer<QObject> view(component.create());
        assert(view);

        dialog.loginDomain("u", "p");
        assert(phoneLoginState.beginRequest());
        domain->finish(DomainAccountManager::LoginOutcome::Succeeded);
        QCoreApplication::processEvents();
        assert(completed == 1 && failed == 0);
        assert(view->property("successStarts").toInt() == 1);
        assert(avatar.property("displayName").toString() == "domain receiver fixture");
        assert(phoneLoginState.requestPending()); // Domain result cannot clear account ownership.
        phoneLoginState.finishRequest();
        dialog.loginDomain("u", "p");
        assert(phoneLoginState.beginRequest());
        // Manager's failure signal is also its finite-deadline outcome.
        domain->finish(DomainAccountManager::LoginOutcome::Failed);
        QCoreApplication::processEvents();
        assert(completed == 1 && failed == 0 && domainFailed == 1);
        assert(view->property("failureLoads").toInt() == 1);
        assert(view->property("lastSource").toString() == "LinkAccountBody.qml");
        auto properties = view->property("lastProperties").value<QJSValue>();
        assert(properties.property("errorString").toString() == "Domain sign-in failed. Check your connection and credentials, then try again.");
        assert(properties.property("loginDialog").toQObject() == &dialog);
        assert(!view->property("loggingInSpinner").value<QJSValue>().property("visible").toBool());
        assert(!view->property("loggingInGlyph").value<QJSValue>().property("visible").toBool());
        assert(phoneLoginState.requestPending());

        // Account and focus routing stay excluded on Pico, enabled elsewhere.
        const int accountExpected = !TEST_ANDROID || TEST_PHONE;
        emit account->loginComplete(QUrl("https://example.invalid"));
        emit account->loginFailed();
        emit app.loginDialogFocusEnabled();
        emit app.loginDialogFocusDisabled();
        assert(completed == 1 + accountExpected && failed == accountExpected);
        assert(focused == accountExpected && unfocused == accountExpected);
        assert(phoneLoginState.requestPending() == !TEST_EXPECT_PENDING);
        emit dialog.dismissedLoginDialog();
        assert(app.dismissals == 1);
        phoneLoginState.finishRequest();
        dialog.loginDomain("u", "p");
        domain->finish(DomainAccountManager::LoginOutcome::TimedOut);
        QCoreApplication::processEvents();
        assert(domainFailed == 2);
        properties = view->property("lastProperties").value<QJSValue>();
        assert(properties.property("errorString").toString() == "Domain sign-in timed out. Check your connection and try again.");
        // Old cancellation queued before a new login cannot close the newer view.
        dialog.loginDomain("u", "p");
        const auto oldTicket = domain->latest;
        domain->finish(DomainAccountManager::LoginOutcome::Cancelled);
        dialog.loginDomain("u", "p");
        QCoreApplication::processEvents();
        assert(domainFailed == 2 && view->property("destroys").toInt() == 0);
        emit domain->loginRequestFinished(oldTicket, oldTicket, static_cast<int>(DomainAccountManager::LoginOutcome::Succeeded));
        QCoreApplication::processEvents();
        assert(completed == 1 + accountExpected);
        domain->finish(DomainAccountManager::LoginOutcome::Cancelled);
        QCoreApplication::processEvents();
        assert(domainFailed == 3 && view->property("destroys").toInt() == 1 && dialog.domainDismissals == 1);
        // Duplicate terminal result remains consumed, including after invalidation.
        emit domain->loginRequestFinished(domain->latest, domain->scope.snapshot(), static_cast<int>(DomainAccountManager::LoginOutcome::Cancelled));
        QCoreApplication::processEvents();
        assert(domainFailed == 3);
        domain->rejectStart = true;
        dialog.loginDomain("u", "p");
        QCoreApplication::processEvents();
        assert(domainFailed == 4); // Inactive admission fails visibly without a live reply.
        domain->rejectStart = false;
        // Timeout's request is invalidated by its own abort, but a subsequent
        // context change must still prevent showing its recovery credentials.
        dialog.loginDomain("u", "p");
        domain->finish(DomainAccountManager::LoginOutcome::TimedOut);
        domain->scope.next();
        QCoreApplication::processEvents();
        assert(domainFailed == 4);
    }
    const int oldCompleted = completed, oldFailed = failed;
    emit domain->loginComplete();
    emit domain->loginFailed();
    assert(completed == oldCompleted && failed == oldFailed);
    // A closed dialog does not remove the application's account-state observer.
    phoneLoginState.finishRequest();
    assert(phoneLoginState.beginRequest());
    {
        LoginDialog reopened;
        assert(phoneLoginState.requestPending()); // Rebinding same manager cannot erase it.
    }
    emit account->loginComplete(QUrl());
    assert(phoneLoginState.requestPending() == !TEST_EXPECT_PENDING);
    phoneLoginState.finishRequest();
    assert(phoneLoginState.beginRequest());
    emit account->loginFailed();
    assert(phoneLoginState.requestPending() == !TEST_EXPECT_PENDING);

    // Real binding lifetime/replacement: a queued old-manager result cannot
    // clear a request admitted against the replacement manager.
    PhoneLoginState isolatedState;
    QPointer<AccountLoginStateBinding<AccountManager>> isolatedBinding;
    auto first = new AccountManager;
    auto second = new AccountManager;
    bindAccountLoginState(isolatedState, isolatedBinding, first, &app);
    auto* originalBinding = isolatedBinding.data();
    bindAccountLoginState(isolatedState, isolatedBinding, first, &app);
    assert(isolatedBinding.data() == originalBinding);
    assert(isolatedState.beginRequest());
    QMetaObject::invokeMethod(first, [first] { emit first->loginFailed(); }, Qt::QueuedConnection);
    bindAccountLoginState(isolatedState, isolatedBinding, second, &app);
    assert(!isolatedState.requestPending());
    assert(isolatedState.beginRequest());
    QCoreApplication::processEvents();
    assert(isolatedState.requestPending());
    delete first;
    assert(isolatedState.requestPending());
    delete second;
    assert(!isolatedState.requestPending());
    delete isolatedBinding.data(); // Destroy before referenced local state.
}
