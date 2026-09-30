// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Loaded only in a dedicated gateway Interface process, with configuration prepended.
(function () {
    'use strict';
    var socket = new WebSocket(BROWSER_GATEWAY.url);
    print('Browser gateway bridge starting.');
    var active = false;
    var lastConnected = false;
    var lastEntities = '';
    var permissionsApproved = false;
    var lastPermissions = '';
    var approvedAuthority = '';
    var permissionRevision = 0;
    var interval;
    var poseInterval;
    function send(value) { if (socket.readyState === 1) { socket.send(JSON.stringify(value)); } }
    function avatarData(id, avatar) {
        return { id: String(id), displayName: avatar.displayName || 'Visitor', position: avatar.position,
            orientation: avatar.orientation, scale: avatar.scale || 1, skeletonModelURL: avatar.skeletonModelURL };
    }
    function state() {
        var connected = !!location.isConnected;
        if (!connected) {
            permissionsApproved = false;
            Audio.muted = true;
            lastPermissions = '';
            lastEntities = '';
            if (lastConnected) { lastConnected = false; send({ type: 'state', state: 'connecting' }); }
            return;
        }
        function permission(name) { return typeof Entities[name] === 'function' ? !!Entities[name]() : null; }
        var permissions = {
            id_can_connect: true,
            id_can_rez: permission('canRez'), id_can_rez_tmp: permission('canRezTmp'),
            id_can_rez_avatar_entities: permission('canRezAvatarEntities'),
            id_can_view_asset_urls: permission('canViewAssetURLs'),
            id_can_adjust_locks: permission('canAdjustLocks'),
            id_can_write_to_asset_server: permission('canWriteAssets'),
            id_can_replace_content: permission('canReplaceContent'),
            id_can_get_and_set_private_user_data: permission('canGetAndSetPrivateUserData'),
            id_can_kick: typeof Users !== 'undefined' && typeof Users.canKick === 'boolean' ? Users.canKick : null,
        };
        var match = String(location.href).match(/^(?:overte|hifi):\/\/([^/]+)/i);
        var authority = match ? match[1].toLowerCase() : '';
        var serialized = JSON.stringify({ authority: authority, permissions: permissions });
        if (serialized !== lastPermissions) {
            lastPermissions = serialized; permissionsApproved = false;
            Audio.muted = true;
            lastEntities = '';
            approvedAuthority = authority;
            if (lastConnected) { lastConnected = false; send({ type: 'state', state: 'connecting' }); }
            permissionRevision++;
            send({ type: 'permissions', permissionRevision: permissionRevision, permissions: permissions, domain: String(location.href) });
        }
        if (permissionsApproved && !lastConnected) {
            lastConnected = true;
            send({ type: 'state', state: 'connected', domain: String(location.href),
                selfId: String(MyAvatar.sessionUUID) });
            send({ type: 'pose', position: MyAvatar.position, orientation: MyAvatar.orientation });
        }
    }
    function world() {
        state();
        if (!active || !location.isConnected || !permissionsApproved) { return; }
        var entities = Entities.findEntities(MyAvatar.position, BROWSER_GATEWAY.radius || 512).map(function (id) {
            return Entities.getEntityProperties(id);
        });
        var serialized = JSON.stringify(entities);
        if (serialized !== lastEntities) { lastEntities = serialized; send({ type: 'entities', entities: entities }); }
    }
    socket.onopen = function () {
        print('Browser gateway local transport connected.');
        send({ type: 'nativeHello', token: BROWSER_GATEWAY.token });
        active = true;
        // Browser collision/gravity integration owns the pose; the native bridge only replicates it.
        if (typeof MyAvatar.setGravity !== 'function') {
            send({ type: 'state', state: 'error', message: 'The native client lacks the browser pose gravity control API.' }); return;
        }
        MyAvatar.setGravity(0);
        MyAvatar.velocity = { x: 0, y: 0, z: 0 };
        MyAvatar.collisionsEnabled = false;
        location = BROWSER_GATEWAY.domain;
        MyAvatar.motorVelocity = { x: 0, y: 0, z: 0 };
        Audio.muted = true;
        Audio.noiseReduction = false;
        interval = Script.setInterval(function () { send({ type: 'heartbeat' }); state(); world(); }, 500);
        poseInterval = Script.setInterval(function () {
            state();
            if (!location.isConnected || !permissionsApproved) { return; }
            var selfId = String(MyAvatar.sessionUUID).replace(/[{}]/g, '').toLowerCase();
            var avatars = AvatarList.getAvatarIdentifiers().filter(function (id) {
                // Native AvatarManager stores MyAvatar under a null UUID key.
                if (!id) { return false; }
                var canonical = String(id).replace(/[{}]/g, '').toLowerCase();
                return canonical !== 'null' && canonical !== 'undefined' && canonical !== '00000000-0000-0000-0000-000000000000' && canonical !== selfId;
            }).map(function (id) {
                return avatarData(id, AvatarList.getAvatar(id));
            });
            avatars.push(avatarData(MyAvatar.sessionUUID, MyAvatar));
            send({ type: 'avatars', avatars: avatars, selfId: String(MyAvatar.sessionUUID) });
        }, 50);
    };
    socket.onmessage = function (event) {
        try {
            var message = JSON.parse(event.data);
            if (message.type === 'shutdown') {
                active = false; permissionsApproved = false; Audio.muted = true;
                // The normal File > Quit action runs native avatar/domain disconnect cleanup.
                Menu.triggerOption('Quit');
                return;
            }
            if (message.type === 'permissionsAccepted') {
                state();
                if (message.permissionRevision === permissionRevision && location.isConnected && lastPermissions) {
                    permissionsApproved = true; state();
                }
                Audio.muted = permissionsApproved ? message.muted !== false : true;
                return;
            }
            state();
            if (!permissionsApproved && message.type !== 'mute') { return; }
            if (message.type === 'pose') {
                MyAvatar.position = message.position;
                MyAvatar.orientation = message.orientation;
                MyAvatar.velocity = { x: 0, y: 0, z: 0 };
            } else if (message.type === 'mute') {
                Audio.muted = permissionsApproved ? message.muted : true;
            } else if (message.type === 'asset') {
                var requestAuthority = approvedAuthority;
                var requestPermissionRevision = permissionRevision;
                Assets.getAsset({ url: message.url, responseType: 'arraybuffer' }, function (error, result) {
                    state();
                    if (!permissionsApproved || approvedAuthority !== requestAuthority || permissionRevision !== requestPermissionRevision) {
                        send({ type: 'asset', requestId: message.requestId, error: 'The domain changed during the asset request.' }); return;
                    }
                    send({ type: 'asset', requestId: message.requestId, error: error || null,
                        data: error ? null : Script.btoa(result.response) });
                });
            } else if (message.type === 'interact') {
                var props = Entities.getEntityProperties(message.entityId, ['id', 'position', 'userData', 'locked']);
                if (!props.id || String(props.id).replace(/[{}]/g, '') === '00000000-0000-0000-0000-000000000000') {
                    send({ type: 'warning', message: 'That object is no longer available.' }); return;
                }
                if (Vec3.distance(MyAvatar.position, props.position) > 5) {
                    send({ type: 'warning', message: 'Move closer to interact with that object.' }); return;
                }
                var pointer = { type: 'Press', id: 0, pos2D: { x: 0, y: 0 }, pos3D: props.position,
                    normal: { x: 0, y: 1, z: 0 }, direction: Quat.getForward(MyAvatar.orientation),
                    button: 'Primary', buttons: 1, isPrimaryButton: true };
                Entities.sendClickDownOnEntity(message.entityId, pointer);
                pointer.type = 'Release';
                Entities.sendClickReleaseOnEntity(message.entityId, pointer);
                // Optional world-authored basic interaction, using the visitor's normal edit permissions.
                var userData;
                try { userData = JSON.parse(props.userData || '{}'); } catch (ignore) { userData = {}; }
                if (userData.browserInteraction === 'toggleColor' || (userData.browserClient && userData.browserClient.interaction === 'toggleColor')) {
                    if (props.locked) {
                        send({ type: 'warning', message: 'The object is locked. Its click event was sent, but its color cannot be changed.' }); return;
                    }
                    var color = Entities.getEntityProperties(message.entityId, ['color']).color;
                    Entities.editEntity(message.entityId, { color: color.red > 128
                        ? { red: 40, green: 190, blue: 90 } : { red: 230, green: 90, blue: 40 } });
                }
                send({ type: 'interaction', entityId: message.entityId, message: 'Object interaction sent through your native session.' });
            }
        } catch (error) { send({ type: 'warning', message: 'Native bridge rejected an invalid command.' }); }
    };
    socket.onerror = function () { print('Browser gateway local transport error.'); };
    if (location.hostChanged && typeof location.hostChanged.connect === 'function') {
        location.hostChanged.connect(function () { permissionsApproved = false; lastPermissions = ''; lastConnected = false;
            Audio.muted = true;
            send({ type: 'state', state: 'connecting' }); });
    }
    Window.domainConnectionRefused.connect(function (reason) { send({ type: 'state', state: 'error', message: String(reason) }); });
    Script.scriptEnding.connect(function () {
        if (interval) { Script.clearInterval(interval); }
        if (poseInterval) { Script.clearInterval(poseInterval); }
        socket.close();
    });
}());
