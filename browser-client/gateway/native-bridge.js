// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Loaded only in a dedicated gateway Interface process, with configuration prepended.
(function () {
    'use strict';
    var socket = new WebSocket(BROWSER_GATEWAY.url);
    print('Browser gateway bridge starting.');
    var active = false;
    var lastConnected = false;
    var permissionsApproved = false;
    var lastPermissions = '';
    var approvedAuthority = '';
    var permissionRevision = 0;
    var tablet = null;
    var interval;
    var poseInterval;
    var appliedPose = null;
    var pendingPose = null;
    var outbound = [], outboundBytes = 0, outputFailed = false;
    function currentPose() {
        var p = MyAvatar.position, q = MyAvatar.orientation;
        return { position: { x: p.x, y: p.y, z: p.z }, orientation: { x: q.x, y: q.y, z: q.z, w: q.w } };
    }
    function poseChanged(first, second) {
        var p = first.position, r = second.position, q = first.orientation, s = second.orientation;
        var distance = Math.pow(p.x-r.x, 2) + Math.pow(p.y-r.y, 2) + Math.pow(p.z-r.z, 2);
        var direct = Math.pow(q.x-s.x, 2) + Math.pow(q.y-s.y, 2) + Math.pow(q.z-s.z, 2) + Math.pow(q.w-s.w, 2);
        var inverse = Math.pow(q.x+s.x, 2) + Math.pow(q.y+s.y, 2) + Math.pow(q.z+s.z, 2) + Math.pow(q.w+s.w, 2);
        return distance > 0.000625 || Math.min(direct, inverse) > 0.0001;
    }
    function externalPose() {
        if (!permissionsApproved || !location.isConnected || !appliedPose) { return false; }
        var current = currentPose();
        if (poseChanged(current, pendingPose || appliedPose)) {
            pendingPose = { position: current.position, orientation: current.orientation,
                nonce: String(Uuid.generate()).replace(/[{}]/g, '').toLowerCase(), permissionRevision: permissionRevision };
            send({ type: 'poseRequest', nonce: pendingPose.nonce, permissionRevision: permissionRevision,
                position: pendingPose.position, orientation: pendingPose.orientation });
        }
        return !!pendingPose;
    }
    function outputAuthority() {
        var match = String(location.href).match(/^(?:overte|hifi):\/\/([^/]+)/i);
        return (match ? match[1].toLowerCase() : '') + '|' + String(location.domainID || '');
    }
    function utf8Size(text) {
        if (/^[\x00-\x7f]*$/.test(text)) { return text.length; }
        var bytes = 0;
        for (var index = 0; index < text.length; index++) {
            var code = text.charCodeAt(index);
            if (code < 128) { bytes++; }
            else if (code < 2048) { bytes += 2; }
            else if (code >= 55296 && code <= 56319 && index + 1 < text.length
                && text.charCodeAt(index + 1) >= 56320 && text.charCodeAt(index + 1) <= 57343) { bytes += 4; index++; }
            else { bytes += 3; }
        }
        return bytes;
    }
    function send(value) {
        if (socket.readyState !== 1 || outputFailed) { return; }
        var text = JSON.stringify(value), size = utf8Size(text);
        // Qt socket/UI callbacks cannot write the engine-owned QWebSocket safely.
        // The existing Script timers drain all post-handshake output instead.
        if (value.type === 'avatars' || value.type === 'heartbeat') {
            outbound = outbound.filter(function (item) {
                if (item.type !== value.type) { return true; }
                outboundBytes -= item.size; return false;
            });
        }
        if (outbound.length >= 128 || outboundBytes + size > 64 * 1024 * 1024) {
            outbound = []; outboundBytes = 0; outputFailed = true; return;
        }
        var item = { type: value.type, text: text, size: size, revision: permissionRevision, authority: outputAuthority(),
            restricted: ['entities', 'entityUpdates', 'avatars', 'asset', 'pose', 'poseRequest', 'tablet', 'interaction', 'navigationRequest', 'navigationHistoryRequest', 'visitorPreferences', 'visitorPersona'].indexOf(value.type) !== -1
                || (value.type === 'state' && value.state === 'connected'),
            deadline: value.type === 'nativePong' ? value.deadline : 0 };
        if (value.type === 'nativePong') { outbound.unshift(item); } else { outbound.push(item); }
        outboundBytes += size;
    }
    function flush() {
        if (socket.readyState !== 1) { outbound = []; outboundBytes = 0; return; }
        if (outputFailed) {
            socket.send(JSON.stringify({ type: 'state', state: 'error', message: 'Native gateway output exceeded its bounded queue. Leave and reconnect.' }));
            outputFailed = false; active = false; permissionsApproved = false; Audio.muted = true;
            worldStream.stop(); return;
        }
        var ready = outbound; outbound = []; outboundBytes = 0;
        ready.forEach(function (item) {
            if (item.type === 'nativePong') { if (Date.now() < item.deadline) { socket.send(item.text); } return; }
            if (item.type !== 'heartbeat' && (item.revision !== permissionRevision || item.authority !== outputAuthority())) { return; }
            if (item.restricted && (!active || !permissionsApproved || !location.isConnected || !lastConnected)) { return; }
            socket.send(item.text);
        });
    }
    function clearOutput() {
        // A liveness nonce has no domain data or permission. Preserve its response
        // while discarding obsolete world/UI output during authority changes.
        outbound = outbound.filter(function (item) { return item.type === 'nativePong'; });
        outboundBytes = outbound.reduce(function (total, item) { return total + item.size; }, 0);
    }

    var visitorPreferences = null;
    if (BROWSER_GATEWAY.visitorPreferences && typeof LocationBookmarks !== 'undefined') {
        visitorPreferences = createBrowserVisitorPreferences({ initial: BROWSER_GATEWAY.visitorPreferences,
            api: LocationBookmarks, send: send, revision: function () { return permissionRevision; },
            authority: function () { return active && permissionsApproved && location.isConnected ? permissionRevision + '|' + outputAuthority() : null; } });
    }
    var visitorPersona = null;
    if (BROWSER_GATEWAY.visitorPersona && typeof AvatarBookmarks !== 'undefined') {
        visitorPersona = createBrowserVisitorPersona({initial:BROWSER_GATEWAY.visitorPersona,displayName:BROWSER_GATEWAY.visitorDisplayName,preserveFields:BROWSER_GATEWAY.personaPreserveFields,avatar:MyAvatar,bookmarks:AvatarBookmarks,
            wearableFields:BROWSER_GATEWAY.wearableFields,runtimeFields:BROWSER_GATEWAY.personaRuntimeFields,inertFields:BROWSER_GATEWAY.personaInertFields,
            send:send,revision:function(){return permissionRevision;},
            authority:function(){return active && permissionsApproved && location.isConnected ? permissionRevision+'|'+outputAuthority():null;}});
    }
    var rigCache = {};
    var navigationHistory = { canGoBack: false, canGoForward: false };
    function navigationMessage(channel, text, sender, localOnly) {
        if (!BROWSER_GATEWAY.navigation || channel !== BROWSER_GATEWAY.navigation.channel || !localOnly) { return; }
        var request; try { request = JSON.parse(text); } catch (error) { return; }
        if (request.kind === 'historyRequest') { publishNavigationHistory(); return; }
        if (request.kind === 'preferencesChanged') { if (visitorPreferences) { visitorPreferences.poll(true); } return; }
        state();
        if (!active || !permissionsApproved || !lastConnected || !location.isConnected) { return; }
        // Save a just-created bookmark before revoking this worker for navigation.
        if (visitorPreferences) { visitorPreferences.poll(true); }
        if (visitorPersona) { visitorPersona.poll(true); }
        var nonce = String(Uuid.generate()).replace(/[{}]/g, '').toLowerCase();
        if (request.kind === 'target' && typeof request.address === 'string' && request.address.length <= 1024) {
            send({ type: 'navigationRequest', nonce: nonce, permissionRevision: permissionRevision, address: request.address });
        } else if (request.kind === 'history' && (request.direction === 'back' || request.direction === 'forward')) {
            send({ type: 'navigationHistoryRequest', nonce: nonce, permissionRevision: permissionRevision, direction: request.direction });
        }
    }
    function publishNavigationHistory() {
        if (BROWSER_GATEWAY.navigation) {
            Messages.sendLocalMessage(BROWSER_GATEWAY.navigation.channel, JSON.stringify({ kind: 'historyState',
                canGoBack: navigationHistory.canGoBack, canGoForward: navigationHistory.canGoForward }));
        }
    }
    function closeNavigation() {
        if (BROWSER_GATEWAY.navigation) {
            Messages.messageReceived.disconnect(navigationMessage);
            Messages.unsubscribe(BROWSER_GATEWAY.navigation.channel);
        }
    }
    function avatarData(id, avatar) {
        var key = String(id), model = String(avatar.skeletonModelURL || ''), cached = rigCache[key], now = Date.now();
        var position = avatar.position, orientation = avatar.orientation;
        var result = { id: key, displayName: String(avatar.displayName || 'Visitor').slice(0, 256), position: {x:position.x,y:position.y,z:position.z},
            orientation: {x:orientation.x,y:orientation.y,z:orientation.z,w:orientation.w}, scale: avatar.scale || 1, skeletonModelURL: model };
        var offset = avatar.skeletonOffset;
        if (offset && [offset.x, offset.y, offset.z].every(function (v) { return typeof v === 'number' && isFinite(v) && Math.abs(v) <= 100; })) {
            result.skeletonOffset = { x: offset.x, y: offset.y, z: offset.z };
        }
        if (typeof avatar.getJointNames !== 'function' || typeof avatar.getJointRotations !== 'function'
            || typeof avatar.getJointTranslations !== 'function') { return result; }
        if (!cached || cached.model !== model || now - cached.time >= 100) {
            // The new URL can arrive before its asynchronously loaded rig. Sample names
            // with every bulk update so equal-size replacement rigs never retain old mappings.
            var names = avatar.getJointNames();
            var rotations = avatar.getJointRotations(), translations = avatar.getJointTranslations();
            var valid = names && rotations && translations && names.length > 0 && names.length <= 1000
                && rotations.length === names.length && translations.length === names.length;
            var copiedNames = [], copiedRotations = [], copiedTranslations = [];
            for (var index = 0; valid && index < names.length; index++) {
                var q = rotations[index], t = translations[index], name = String(names[index]);
                var norm = q && q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w;
                valid = name.length > 0 && name.length <= 128 && q && t && [q.x,q.y,q.z,q.w,t.x,t.y,t.z].every(function (v) {
                    return typeof v === 'number' && isFinite(v) && Math.abs(v) < 1000000;
                }) && norm >= 0.99 && norm <= 1.01;
                if (valid) { copiedNames.push(name); copiedRotations.push({x:q.x,y:q.y,z:q.z,w:q.w}); copiedTranslations.push({x:t.x,y:t.y,z:t.z}); }
            }
            cached = { model: model, time: now, names: valid ? copiedNames : [], rotations: valid ? copiedRotations : [], translations: valid ? copiedTranslations : [] };
            rigCache[key] = cached;
        }
        result.jointNames = cached.names; result.jointRotations = cached.rotations; result.jointTranslations = cached.translations;
        return result;
    }
    function state() {
        var connected = !!location.isConnected;
        if (!connected) {
            appliedPose = null; pendingPose = null;
            permissionsApproved = false; clearOutput();
            if (tablet) { tablet.setAuthority(permissionRevision, false); }
            Audio.muted = true;
            lastPermissions = '';
            worldStream.reset();
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
        var domainId = String(location.domainID || '').replace(/[{}]/g, '').toLowerCase();
        var serialized = JSON.stringify({ authority: authority, domainId: domainId, permissions: permissions });
        if (serialized !== lastPermissions) {
            appliedPose = null; pendingPose = null;
            lastPermissions = serialized; permissionsApproved = false; clearOutput();
            Audio.muted = true;
            worldStream.reset();
            approvedAuthority = authority;
            if (lastConnected) { lastConnected = false; send({ type: 'state', state: 'connecting' }); }
            permissionRevision++;
            if (tablet) { tablet.setAuthority(permissionRevision, false); }
            send({ type: 'permissions', permissionRevision: permissionRevision, permissions: permissions, domain: String(location.href), domainId: domainId });
        }
        if (permissionsApproved && !lastConnected) {
            lastConnected = true;
            send({ type: 'state', state: 'connected', domain: String(location.href),
                selfId: String(MyAvatar.sessionUUID), permissionRevision: permissionRevision });
            if (tablet) { tablet.setAuthority(permissionRevision, true); }
            appliedPose = currentPose(); pendingPose = null;
            send({ type: 'pose', position: MyAvatar.position, orientation: MyAvatar.orientation });
        }
    }
    var worldStream = createBrowserWorldStream({
        readIDs: function () { return Entities.findEntities(MyAvatar.position, BROWSER_GATEWAY.radius || 512); },
        readEntity: function (id) { return Entities.getEntityProperties(id); },
        authority: function () {
            var match = String(location.href).match(/^(?:overte|hifi):\/\/([^/]+)/i);
            return active && location.isConnected && permissionsApproved && match && match[1].toLowerCase() === approvedAuthority
                ? permissionRevision + '|' + approvedAuthority + '|' + String(location.domainID || '') : null;
        },
        send: send,
        schedule: function (callback, delay) { return Script.setTimeout(callback, delay); },
        cancel: function (timer) { Script.clearTimeout(timer); },
        onError: function (message) { send({ type: 'state', state: 'error', message: message }); },
        budgetMs: 8
    });
    function world() { state(); worldStream.poll(); }
    socket.onopen = function () {
        print('Browser gateway local transport connected.');
        socket.send(JSON.stringify({ type: 'nativeHello', token: BROWSER_GATEWAY.token }));
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
        if (BROWSER_GATEWAY.navigation) {
            Messages.subscribe(BROWSER_GATEWAY.navigation.channel);
            Messages.messageReceived.connect(navigationMessage);
        }
        if (BROWSER_GATEWAY.tablet) {
            try {
                Script.include(BROWSER_GATEWAY.tablet.scriptURL);
                tablet = createBrowserTablet({ qmlURL: BROWSER_GATEWAY.tablet.qmlURL,
                    framePath: BROWSER_GATEWAY.tablet.framePath,
                    filesDirectory: BROWSER_GATEWAY.tablet.filesDirectory,
                    snapshotChannel: BROWSER_GATEWAY.tablet.snapshotChannel,
                    chatURL: BROWSER_GATEWAY.tablet.chatURL,
                    defaultScriptsURL: BROWSER_GATEWAY.tablet.defaultScriptsURL, send: send });
                tablet.setAuthority(permissionRevision, false);
            } catch (error) { send({ type: 'warning', message: 'The installed native tablet helper could not start.' }); }
        }
        interval = Script.setInterval(function () { send({ type: 'heartbeat' }); state(); world(); if (visitorPreferences) { visitorPreferences.poll(); } if (visitorPersona) { visitorPersona.poll(); } flush(); }, 500);
        poseInterval = Script.setInterval(function () {
            state(); flush();
            if (!location.isConnected || !permissionsApproved) { return; }
            externalPose();
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
            var currentIds = {}; avatars.forEach(function (avatar) { currentIds[avatar.id] = true; });
            Object.keys(rigCache).forEach(function (id) { if (!currentIds[id]) { delete rigCache[id]; } });
            send({ type: 'avatars', avatars: avatars, selfId: String(MyAvatar.sessionUUID) }); flush();
        }, 50);
    };
    socket.onmessage = function (event) {
        try {
            var message = JSON.parse(event.data);
            if (message.type === 'shutdown') {
                closeNavigation(); if (visitorPreferences) { visitorPreferences.stop(); } if (visitorPersona) { visitorPersona.stop(); }
                active = false; permissionsApproved = false; Audio.muted = true; worldStream.stop();
                if (tablet) { tablet.close(); }
                // The normal File > Quit action runs native avatar/domain disconnect cleanup.
                Menu.triggerOption('Quit');
                return;
            }
            if (message.type === 'nativePing') {
                if (typeof message.nonce === 'string' && /^[a-f0-9]{32}$/.test(message.nonce)
                    && typeof message.deadline === 'number' && isFinite(message.deadline)
                    && message.deadline > Date.now() && message.deadline <= Date.now() + 30000) {
                    send({ type: 'nativePong', nonce: message.nonce, deadline: message.deadline });
                }
                return;
            }
            if (message.type === 'permissionsAccepted') {
                state();
                if (message.permissionRevision === permissionRevision && location.isConnected && lastPermissions) {
                    permissionsApproved = true;
                    if (visitorPreferences) { visitorPreferences.restore(); }
                    if (visitorPersona) { visitorPersona.restore(); }
                    state();
                    if (visitorPreferences) { visitorPreferences.poll(true); }
                    if (visitorPersona) { visitorPersona.poll(true); }
                }
                Audio.muted = permissionsApproved ? message.muted !== false : true;
                return;
            }
            state();
            if (!permissionsApproved && message.type !== 'mute') { return; }
            if (message.type === 'navigationHistoryState') {
                if (message.permissionRevision === permissionRevision && typeof message.canGoBack === 'boolean' && typeof message.canGoForward === 'boolean') {
                    navigationHistory = {canGoBack:message.canGoBack,canGoForward:message.canGoForward}; publishNavigationHistory();
                }
            } else if (message.type === 'tablet') {
                if (tablet) { tablet.setAuthority(permissionRevision, true); tablet.receive(message); }
            } else if (message.type === 'pose') {
                if (externalPose()) { return; }
                MyAvatar.position = message.position;
                MyAvatar.orientation = message.orientation;
                MyAvatar.velocity = { x: 0, y: 0, z: 0 };
                appliedPose = currentPose();
            } else if (message.type === 'poseAccepted') {
                externalPose();
                if (pendingPose && message.nonce === pendingPose.nonce && message.permissionRevision === permissionRevision) {
                    appliedPose = { position: pendingPose.position, orientation: pendingPose.orientation }; pendingPose = null;
                }
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
            appliedPose = null; pendingPose = null; worldStream.reset(); clearOutput();
            if (tablet) { tablet.setAuthority(permissionRevision, false); }
            Audio.muted = true;
            send({ type: 'state', state: 'connecting' }); });
    }
    Window.domainConnectionRefused.connect(function (reason) { send({ type: 'state', state: 'error', message: String(reason) }); });
    Script.scriptEnding.connect(function () {
        worldStream.stop(); clearOutput(); closeNavigation(); if (visitorPreferences) { visitorPreferences.stop(); } if (visitorPersona) { visitorPersona.stop(); }
        if (tablet) { tablet.close(); }
        if (interval) { Script.clearInterval(interval); }
        if (poseInterval) { Script.clearInterval(poseInterval); }
        socket.close();
    });
}());
