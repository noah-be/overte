// SPDX-License-Identifier: Apache-2.0
#include <QMetaObject>
#include "PhoneApplicationOwner.h"

int main(int argc, char** argv) {
    int lost = 0;
    {
        QCoreApplication parser(argc, argv);
        if (phoneApplication() != nullptr) { return 1; }
        // A successful queue receipt is insufficient: parser teardown discards it.
        if (!QMetaObject::invokeMethod(&parser, [&] { ++lost; }, Qt::QueuedConnection)) { return 2; }
    }
    QGuiApplication client(argc, argv);
    if (lost != 0 || phoneApplication() != &client) { return 3; }
    int delivered = 0;
    if (!QMetaObject::invokeMethod(phoneApplication(), [&] { ++delivered; }, Qt::QueuedConnection)) { return 4; }
    QCoreApplication::processEvents();
    return delivered == 1 ? 0 : 5;
}
