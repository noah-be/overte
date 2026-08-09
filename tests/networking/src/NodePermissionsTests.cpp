#include "NodePermissionsTests.h"

#include <QDataStream>
#include <QDebug>

#include <NodePermissions.h>

QTEST_MAIN(NodePermissionsTests)

void NodePermissionsTests::normalizesIdentityAndMapKeys() {
    const QUuid rank = QUuid::createUuid();
    NodePermissions permissions(NodePermissionsKey("MixedCase", rank));
    QCOMPARE(permissions.getID(), QString("mixedcase"));
    QCOMPARE(permissions.getRankID(), rank);

    permissions.setVerifiedUserName("Alice");
    permissions.setVerifiedDomainUserName("DomainUser");
    QCOMPARE(permissions.getVerifiedUserName(), QString("alice"));
    QCOMPARE(permissions.getVerifiedDomainUserName(), QString("domainuser"));

    NodePermissionsMap map;
    auto inserted = map[NodePermissionsKey("ALICE", rank)];
    QVERIFY(inserted);
    QVERIFY(map.contains("alice", rank));
    QCOMPARE(map[NodePermissionsKey("aLiCe", rank)], inserted);
    QCOMPARE(map.keys().size(), 1);
    map.remove(NodePermissionsKey("Alice", rank));
    QVERIFY(!map.contains("alice", rank));
    map.clear();
    QVERIFY(map.get().empty());
}

void NodePermissionsTests::convertsVariantsAndGroupRanks() {
    const QUuid group = QUuid::createUuid();
    const QUuid rank = QUuid::createUuid();
    QMap<QString, QVariant> values {
        { "permissions_id", "Builders" }, { "group_id", group },
        { "rank_id", rank.toString() }, { "id_can_connect", true },
        { "id_can_rez", true }, { "id_can_kick", false },
        { "id_can_view_asset_urls", true }
    };
    NodePermissions permissions(values);
    QVERIFY(permissions.isGroup());
    QCOMPARE(permissions.getGroupID(), group);
    QVERIFY(permissions.can(NodePermissions::Permission::canConnectToDomain));
    QVERIFY(permissions.can(NodePermissions::Permission::canRezPermanentEntities));
    QVERIFY(!permissions.can(NodePermissions::Permission::canKick));

    QHash<QUuid, GroupRank> ranks;
    ranks.insert(rank, GroupRank(rank, 7, "Maintainer", 3));
    const auto output = permissions.toVariant(ranks).toMap();
    QCOMPARE(output.value("permissions_id").toString(), QString("builders"));
    QCOMPARE(output.value("rank_name").toString(), QString("Maintainer"));
    QCOMPARE(output.value("rank_order").toInt(), 7);
    QVERIFY(output.value("id_can_view_asset_urls").toBool());
}

void NodePermissionsTests::combinesAndSerializesFlags() {
    NodePermissions left("left");
    left.set(NodePermissions::Permission::canConnectToDomain);
    left.set(NodePermissions::Permission::canKick);
    left.clear(NodePermissions::Permission::canKick);
    QVERIFY(!left.can(NodePermissions::Permission::canKick));

    NodePermissions right("right");
    right.set(NodePermissions::Permission::canWriteToAssetServer);
    left |= right;
    QVERIFY(left.can(NodePermissions::Permission::canWriteToAssetServer));
    left &= right;
    QVERIFY(!left.can(NodePermissions::Permission::canConnectToDomain));

    left.setAll(true);
    QVERIFY(left.can(NodePermissions::Permission::canViewAssetURLs));
    const NodePermissions inverted = ~left;
    QVERIFY(!inverted.can(NodePermissions::Permission::canViewAssetURLs));

    QByteArray bytes;
    QDataStream output(&bytes, QIODevice::WriteOnly);
    output << right;
    NodePermissions restored("restored");
    QDataStream input(&bytes, QIODevice::ReadOnly);
    input >> restored;
    QCOMPARE(restored.permissions, right.permissions);

    QString debugText;
    QDebug(&debugText) << restored;
    QVERIFY(debugText.contains("asset-server"));
    NodePermissionsPointer nullPermissions;
    debugText.clear();
    QDebug(&debugText) << nullPermissions;
    QVERIFY(debugText.contains("null"));
}
