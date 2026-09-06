#include <QGuiApplication>
#include <QQuickItem>
#include <QPointer>
#include <QVariant>
#include <QTimer>
#include <QMessageBox>
#include <QSharedPointer>
#include <QUrl>
#include <cassert>

// ACTUAL_BASE
class OffscreenUi : public QObject {
    Q_OBJECT
public:
    enum Icon { ICON_NONE };
    QVariant inputResult;
    QVariantMap lastItemConfig;
    QString lastItemTitle;
    QQuickItem* nextItemDialog { nullptr };
    QList<QObject*> _modalDialogListeners;
    QVariant inputDialog(Icon, const QString&, const QString&, const QVariant&) { return inputResult; }
    ModalDialogListener* customInputDialogAsync(Icon, const QString& title, const QVariantMap& config) {
        lastItemConfig = config; lastItemTitle = title;
        return make(1, nextItemDialog);
    }
    static QString getText(Icon, const QString&, const QString&, const QString&, bool*);
    static ModalDialogListener* getItemAsync(Icon, const QString&, const QString&, const QStringList&, int, bool);
    void removeModalDialog(QObject*);
    void registerModalDialog(ModalDialogListener*);
    ModalDialogListener* make(int kind, QQuickItem* dialog, bool owned = true);
    static QVariant wait(ModalDialogListener* listener) { return listener->waitForResult(); }
    static int syncMessage(QQuickItem* dialog);
};
static QSharedPointer<OffscreenUi> owner;
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() { return owner; }
};
// ACTUAL_CLASSES
// ACTUAL_FUNCTIONS
ModalDialogListener* OffscreenUi::make(int kind, QQuickItem* dialog, bool owned) {
    ModalDialogListener* listener = nullptr;
    switch (kind) {
        case 0: listener = new MessageBoxListener(dialog); break;
        case 1: listener = new InputDialogListener(dialog); break;
        case 2: listener = new FileDialogListener(dialog); break;
        case 3: listener = new AssetDialogListener(dialog); break;
    }
    if (owned) { registerModalDialog(listener); }
    return listener;
}
int OffscreenUi::syncMessage(QQuickItem* dialog) {
    MessageBoxListener listener(dialog);
    return listener.waitForButtonResult();
}
class Dialog : public QQuickItem {
    Q_OBJECT
public:
    void choose(int kind) {
        switch (kind) {
            case 0: emit selected(int(QMessageBox::Yes)); break;
            case 1: emit selected(QVariant("typed input")); break;
            case 2: emit selectedFile(QUrl::fromLocalFile("/fixture/file")); break;
            case 3: emit selectedAsset(QVariant("atp:/fixture")); break;
        }
    }
signals:
    void selected(int);
    void selected(QVariant);
    void selectedFile(QVariant);
    void selectedAsset(QVariant);
    void canceled();
};
static void flush() { QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); }
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    owner.reset(new OffscreenUi);
    for (int kind = 0; kind != 4; ++kind) {
        auto* dialog = new Dialog;
        QPointer<ModalDialogListener> listener = owner->make(kind, dialog);
        int count = 0;
        QVariant result;
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant& value) {
            ++count; result = value;
            assert(owner->_modalDialogListeners.isEmpty());
            if (count == 1) { dialog->choose(kind); emit dialog->canceled(); }
        });
        dialog->choose(kind);
        assert(count == 1);
        if (kind == 0) { assert(result.toInt() == int(QMessageBox::Yes)); }
        if (kind == 1) { assert(result.toString() == "typed input"); }
        if (kind == 2) { assert(result.toString() == "/fixture/file"); }
        if (kind == 3) { assert(result.toString() == "atp:/fixture"); }
        delete dialog;
        assert(count == 1);
        flush(); assert(!listener);

        dialog = new Dialog;
        listener = owner->make(kind, dialog);
        count = 0;
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant& value) {
            ++count; assert(kind == 0 ? value.toInt() == int(QMessageBox::NoButton) : !value.isValid());
        });
        delete dialog; assert(count == 1);
        flush(); assert(!listener); assert(owner->_modalDialogListeners.isEmpty());

        listener = owner->make(kind, nullptr);
        count = 0;
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant& value) {
            ++count; assert(kind == 0 ? value.toInt() == int(QMessageBox::NoButton) : !value.isValid());
        });
        QCoreApplication::processEvents(); assert(count == 1);
        flush(); assert(!listener);

        dialog = new Dialog;
        listener = owner->make(kind, dialog);
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant&) {
            delete static_cast<QObject*>(listener.data());
            delete dialog;
        });
        dialog->choose(kind); assert(!listener); assert(owner->_modalDialogListeners.isEmpty());

        dialog = new Dialog;
        listener = owner->make(kind, dialog);
        delete static_cast<QObject*>(listener.data());
        assert(owner->_modalDialogListeners.isEmpty());
        delete dialog;

        // No owner remains during delivery; response must still terminate.
        dialog = new Dialog;
        listener = owner->make(kind, dialog, false);
        auto retainedOwner = owner; owner.clear();
        count = 0;
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant&) { ++count; });
        dialog->choose(kind); assert(count == 1);
        delete static_cast<QObject*>(listener.data()); delete dialog;
        owner = retainedOwner;
    }
    // Actual input listener distinguishes cancel from an accepted empty value.
    for (bool canceled : { true, false }) {
        Dialog input;
        auto* listener = owner->make(1, &input, false);
        QVariant received("unset");
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant& value) { received = value; });
        if (canceled) { emit input.canceled(); } else { emit input.selected(QVariant(QString())); }
        assert(received.isValid() != canceled);
        owner->inputResult = received;
        bool ok = !canceled;
        assert(OffscreenUi::getText(OffscreenUi::ICON_NONE, "Title", "Label", "old", &ok).isEmpty());
        assert(ok != canceled);
        delete static_cast<QObject*>(listener);
    }
    {
        Dialog item;
        owner->nextItemDialog = &item;
        QPointer<ModalDialogListener> listener = OffscreenUi::getItemAsync(OffscreenUi::ICON_NONE, "Item", "Choose", { "first", "second" }, 1, false);
        assert(listener && listener->parent() == owner.data());
        assert(owner->lastItemTitle == "Item");
        assert(owner->lastItemConfig.value("items").toStringList() == QStringList({ "first", "second" }));
        assert(owner->lastItemConfig.value("label").toString() == "Choose");
        assert(owner->lastItemConfig.value("current").toInt() == 1);
        assert(!owner->lastItemConfig.value("editable").toBool());
        emit item.canceled(); flush(); assert(!listener);
        owner->nextItemDialog = nullptr;
        listener = OffscreenUi::getItemAsync(OffscreenUi::ICON_NONE, "Item", "Choose", {}, 0, true);
        assert(listener);
        int canceled = 0;
        QObject::connect(listener, &ModalDialogListener::response, &app, [&](const QVariant& value) { assert(!value.isValid()); ++canceled; });
        QCoreApplication::processEvents(); assert(canceled == 1);
        flush(); assert(!listener);
    }
    {
        Dialog pendingDialog;
        QPointer<ModalDialogListener> pending = owner->make(0, &pendingDialog);
        assert(pending->parent() == owner.data());
        owner.clear();
        assert(!pending);
        owner.reset(new OffscreenUi);
    }
    Dialog dialog;
    QTimer::singleShot(0, &dialog, [&] { dialog.choose(0); });
    assert(OffscreenUi::syncMessage(&dialog) == int(QMessageBox::Yes));
    flush(); // The stack listener must not have a queued deletion.
    assert(OffscreenUi::syncMessage(nullptr) == int(QMessageBox::NoButton));
    flush();
    auto* input = new Dialog;
    auto* listener = owner->make(1, input, false);
    QTimer::singleShot(0, &app, [listener] { delete static_cast<QObject*>(listener); });
    assert(!OffscreenUi::wait(listener).isValid());
    delete input;
    assert(owner->_modalDialogListeners.isEmpty());
    qInfo("Four actual modal listener types: single terminal response, destruction, null creation, reentrancy, ownership and waits PASS");
}
#include "test.moc"
