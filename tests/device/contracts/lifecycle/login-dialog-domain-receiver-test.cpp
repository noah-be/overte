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
signals:
    void loginComplete();
    void loginFailed();
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
signals:
    void handleLoginCompleted();
    void handleLoginFailed();
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
    auto account = DependencyManager::get<AccountManager>();
    auto domain = DependencyManager::get<DomainAccountManager>();
    int completed = 0, failed = 0, focused = 0, unfocused = 0;
    {
        LoginDialog dialog;
        QObject::connect(&dialog, &LoginDialog::handleLoginCompleted, &app, [&] { ++completed; });
        QObject::connect(&dialog, &LoginDialog::handleLoginFailed, &app, [&] { ++failed; });
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

        assert(phoneLoginState.beginRequest());
        emit domain->loginComplete();
        assert(completed == 1 && failed == 0);
        assert(view->property("successStarts").toInt() == 1);
        assert(avatar.property("displayName").toString() == "domain receiver fixture");
        assert(phoneLoginState.requestPending()); // Domain result cannot clear account ownership.
        phoneLoginState.finishRequest();
        assert(phoneLoginState.beginRequest());
        // Manager's failure signal is also its finite-deadline outcome.
        emit domain->loginFailed();
        assert(completed == 1 && failed == 1);
        assert(view->property("failureLoads").toInt() == 1);
        assert(view->property("lastSource").toString() == "LinkAccountBody.qml");
        auto properties = view->property("lastProperties").value<QJSValue>();
        assert(properties.property("errorString").toString() == "Username or password is incorrect.");
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
        assert(completed == 1 + accountExpected && failed == 1 + accountExpected);
        assert(focused == accountExpected && unfocused == accountExpected);
        assert(phoneLoginState.requestPending() == !TEST_EXPECT_PENDING);
        emit dialog.dismissedLoginDialog();
        assert(app.dismissals == 1);
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
