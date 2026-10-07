// SPDX-License-Identifier: Apache-2.0
// An isolated, always-muted guest observer. It never edits entities or uploads assets.
(function () {
    'use strict';
    Audio.muted = true;
    Render.viewportResolutionScale = 0.2;
    MyAvatar.displayName = 'Browser compatibility observer';
    MyAvatar.setGravity(0);
    MyAvatar.velocity = { x: 0, y: 0, z: 0 };
    MyAvatar.collisionsEnabled = false;
    var reportedWorld = false;
    function permission(name) { return typeof Entities[name] === 'function' ? !!Entities[name]() : null; }
    function observe() {
        Audio.muted = true;
        MyAvatar.velocity = { x: 0, y: 0, z: 0 };
        var permissions = {
            id_can_connect: !!location.isConnected,
            id_can_rez: permission('canRez'), id_can_rez_tmp: permission('canRezTmp'),
            id_can_rez_avatar_entities: permission('canRezAvatarEntities'),
            id_can_view_asset_urls: permission('canViewAssetURLs'),
            id_can_adjust_locks: permission('canAdjustLocks'), id_can_write_to_asset_server: permission('canWriteAssets'),
            id_can_replace_content: permission('canReplaceContent'),
            id_can_get_and_set_private_user_data: permission('canGetAndSetPrivateUserData'),
            id_can_kick: typeof Users.canKick === 'boolean' ? Users.canKick : null
        };
        var self = String(MyAvatar.sessionUUID).replace(/[{}]/g, '').toLowerCase();
        var peerCount = AvatarList.getAvatarIdentifiers().filter(function (id) {
            if (!id) { return false; }
            var key = String(id).replace(/[{}]/g, '').toLowerCase();
            return key !== self && key !== 'null' && key !== '00000000-0000-0000-0000-000000000000';
        }).length;
        print('HUB_OBSERVER ' + JSON.stringify({ at: Date.now(), connected: !!location.isConnected,
            domain: String(location.href), domainID: String(location.domainID), position: MyAvatar.position, orientation: MyAvatar.orientation,
            muted: Audio.muted, permissions: permissions, peerCount: peerCount }));
        if (location.isConnected && !reportedWorld) {
            var entities = Entities.findEntities(MyAvatar.position, 8192).map(function (id) { return Entities.getEntityProperties(id); });
            if (entities.length) {
                reportedWorld = true;
                // Local, ignored diagnostic only: do not publish identities or raw world scripts.
                print('HUB_ENTITY_SNAPSHOT ' + JSON.stringify({ at: Date.now(), entities: entities }));
            }
        }
    }
    Script.setInterval(observe, 2000);
    Script.setTimeout(function () { location = 'hifi://overte_hub'; }, 1000);
}());
