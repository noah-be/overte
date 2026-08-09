#pragma once

#include <QtTest/QtTest>

class NodePermissionsTests : public QObject {
    Q_OBJECT
private slots:
    void normalizesIdentityAndMapKeys();
    void convertsVariantsAndGroupRanks();
    void combinesAndSerializesFlags();
};
