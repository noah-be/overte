// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QMessageBox>
#include <QQuickItem>
#include <EntityScriptConsent.h>

// Drive the displayed production dialog. Never resolve a consent request here:
// its existing selected signal and Application listener own that decision.
inline bool pressEntityScriptConsentDialog(QQuickItem* dialog,
        const std::shared_ptr<EntityScriptConsentRequest>& request,
        const std::shared_ptr<EntityScriptConsentScope>& scope,
        const QString& source, const QString& origin) {
    if (!dialog || !dialog->isVisible() || dialog->width() <= 0 || dialog->height() <= 0 ||
            !request || !request->active() || !request->belongsTo(scope) ||
            request->source() != source || request->origin() != origin ||
            dialog->property("buttons").toInt() != int(QMessageBox::Yes | QMessageBox::No) ||
            dialog->property("defaultButton").toInt() != int(QMessageBox::No)) {
        return false;
    }
    return QMetaObject::invokeMethod(dialog, "click", Qt::DirectConnection,
        Q_ARG(QVariant, QVariant(int(QMessageBox::Yes))));
}
