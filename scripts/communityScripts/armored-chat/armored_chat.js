//
//  armored_chat.js
//
//  Created by Armored Dragon, May 17th, 2024.
//  Copyright 2024 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html

(() => {
    ("use strict");

    var appIsVisible = false;
    var settings = {
        external_window: false,
        maximum_messages: 200,
        join_notification: true,
        use_chat_bubbles: true,
    };

    // Global vars
    var tablet;
    var chatOverlayWindow;
    var appButton;
    var quickMessage;
    var tabletMode = false;
    var chatSource = Script.resolvePath("./armored_chat.qml");
    const channels = ["domain", "local"];
    var messageHistory = Settings.getValue("ArmoredChat-Messages", []) || [];
    if (!Array.isArray(messageHistory)) { messageHistory = []; }
    var maxLocalDistance = 20; // Maximum range for the local chat
    var palData = AvatarManager.getPalData().data;
    var isTyping = false;

    Controller.keyPressEvent.connect(keyPressEvent);
    Messages.subscribe("Chat"); // Floofchat
    Messages.subscribe("chat");
    Messages.messageReceived.connect(receivedMessage);

    // We have Users.avatarDisconnected which only emits when
    // a client really leaves the server, but there's no signal
    // for when a client really joins the server. Keep track of
    // what avatar IDs we've seen so if one gets hidden and then
    // unhidden, we don't do the "user connected" notification again.
    let connectedAvatars = new Set();

    AvatarManager.avatarAddedEvent.connect((sessionId) => {
        if (!connectedAvatars.has(sessionId)) {
            connectedAvatars.add(sessionId);
            _avatarAction("connected", sessionId);
        }
    });
    Users.avatarDisconnected.connect((sessionId) => {
        _avatarAction("left", sessionId);
        connectedAvatars.delete(sessionId);
    });

    startup();

    function startup() {
        tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
        // Touch and headset clients use the normal system tablet. Script-engine
        // globals from defaultScripts are not available in this separate engine.
        tabletMode = HMD.active || tablet.toolbarMode === false;
        readSettings();

        appButton = tablet.addButton({
            icon: Script.resolvePath("./img/icon_white.png"),
            activeIcon: Script.resolvePath("./img/icon_black.png"),
            text: "CHAT",
            sortOrder: 8,
            isActive: appIsVisible,
        });

        // When script ends, remove itself from tablet
        Script.scriptEnding.connect(function () {
            console.log("Shutting Down");
            tablet.removeButton(appButton);
            appButton.clicked.disconnect(toggleMainChatWindow);
            Controller.keyPressEvent.disconnect(keyPressEvent);
            Messages.messageReceived.disconnect(receivedMessage);
            Messages.unsubscribe("Chat");
            Messages.unsubscribe("chat");
            if (isTyping) { endTyping(); }
            if (tabletMode) {
                tablet.fromQml.disconnect(fromTabletQML);
                tablet.screenChanged.disconnect(onScreenChanged);
                tablet.tabletShownChanged.disconnect(onTabletShownChanged);
                if (appIsVisible) { tablet.gotoHomeScreen(); }
            } else {
                chatOverlayWindow.close();
                quickMessage.close();
            }
        });

        // Overlay button toggle
        appButton.clicked.connect(toggleMainChatWindow);

        if (tabletMode) {
            tablet.fromQml.connect(fromTabletQML);
            tablet.screenChanged.connect(onScreenChanged);
            tablet.tabletShownChanged.connect(onTabletShownChanged);
        } else {
            quickMessage = new OverlayWindow({
                source: Script.resolvePath("./armored_chat_quick_message.qml"),
            });
            _openWindow();
        }
    }
    function toggleMainChatWindow() {
        if (tabletMode) {
            if (appIsVisible) { tablet.gotoHomeScreen(); }
            else { tablet.loadQMLSource(chatSource); }
            return;
        }
        appIsVisible = !appIsVisible;
        appButton.editProperties({ isActive: appIsVisible });
        chatOverlayWindow.visible = appIsVisible;

        // External window was closed; the window does not exist anymore
        if (chatOverlayWindow.title == "" && appIsVisible) {
            _openWindow();
        }
    }
    function onScreenChanged(type, source) {
        appIsVisible = type === "QML" && source === chatSource;
        appButton.editProperties({ isActive: appIsVisible });
        if (!appIsVisible && isTyping) { endTyping(); }
    }
    function fromTabletQML(event) {
        if (!appIsVisible || !event || typeof event !== "object") { return; }
        if (event.type === "chat.close") { tablet.gotoHomeScreen(); return; }
        fromQML(event);
    }
    function onTabletShownChanged() {
        if (!tablet.tabletShown && appIsVisible) {
            endTyping();
            tablet.sendToQml({ type: "chat.hidden" });
        }
    }
    function endTyping() {
        if (isTyping) {
            Messages.sendMessage("Chat-Typing", JSON.stringify({ action: "typing_stop" }));
        }
        isTyping = false;
    }
    function _openWindow() {
        chatOverlayWindow = new Desktop.createWindow(
            Script.resolvePath("./armored_chat.qml"),
            {
                title: "Chat",
                size: { x: 550, y: 400 },
                additionalFlags: Desktop.ALWAYS_ON_TOP,
                visible: appIsVisible,
                presentationMode: Desktop.PresentationMode.VIRTUAL,
            }
        );

        chatOverlayWindow.closed.connect(toggleMainChatWindow);
        chatOverlayWindow.fromQml.connect(fromQML);
        quickMessage.fromQml.connect(fromQML);
    }
    function receivedMessage(channel, message) {
        // Is the message a chat message?
        channel = channel.toLowerCase();
        if (channel !== "chat") return;
        try { message = JSON.parse(message); } catch (error) { return; }
        if (!message || typeof message !== "object" || message.forApp) return;
        // Accept the legacy packet before testing its newer action field.
        message = floofChatCompatibilityConversion(message);
        if (message.action !== "send_chat_message" || typeof message.message !== "string") return;

        // Get the message data
        const currentTimestamp = _getTimestamp();
        const timeArray = _formatTimestamp(currentTimestamp);

        if (!message.channel) message.channel = "domain"; // We don't know where to put this message. Assume it is a domain wide message.
        if (typeof message.channel !== "string") return;
        message.channel = message.channel.toLowerCase();
        message.displayName = typeof message.displayName === "string" ? message.displayName : "Unknown";

        // Check the channel. If the channel is not one we have, do nothing.
        if (!channels.includes(message.channel)) return;

        // If message is local, and if player is too far away from location, do nothing.
        if (message.channel == "local" && (!message.position
                || ![message.position.x, message.position.y, message.position.z].every(Number.isFinite)
                || isTooFar(message.position))) return;

        // Format the timestamp 
        message.timeString = timeArray[0];
        message.dateString = timeArray[1];

        // Update qml view of to new message
        _emitEvent({ type: "show_message", ...message });

        // Show new message on screen
        if (message.channel !== "local" || !settings.use_chat_bubbles) {
            Messages.sendLocalMessage(
                "Floof-Notif",
                JSON.stringify({
                    sender: message.displayName,
                    text: message.message,
                })
            );
        }

        // Save message to history
        let savedMessage = message;

        // Remove unnecessary data.
        delete savedMessage.position;
        delete savedMessage.timeString;
        delete savedMessage.dateString;
        delete savedMessage.action;

        savedMessage.timestamp = currentTimestamp;

        messageHistory.push(savedMessage);
        while (messageHistory.length > settings.maximum_messages) {
            messageHistory.shift();
        }
        Settings.setValue("ArmoredChat-Messages", messageHistory);

        // Check to see if the message is close enough to the user
        function isTooFar(messagePosition) {
            return Vec3.distance(MyAvatar.position, messagePosition) > maxLocalDistance;
        }
    }
    function fromQML(event) {
        if (!event || typeof event !== "object") { return; }
        switch (event.type) {
            case "send_message":
                _sendMessage(event.message, event.channel);
                break;
            case "setting_change":
                if (!["external_window", "maximum_messages", "join_notification", "use_chat_bubbles"].includes(event.setting)) return;
                if (event.setting === "maximum_messages") {
                    if (!Number.isFinite(event.value)) return;
                    event.value = Math.max(1, Math.min(1000, Math.floor(event.value)));
                } else if (typeof event.value !== "boolean") return;
                if (tabletMode && event.setting === "external_window") return;
                // Set the setting value, and save the config
                settings[event.setting] = event.value; // Update local settings
                _saveSettings(); // Save local settings

                // Extra actions to preform. 
                switch (event.setting) {
                    case "external_window":
                        chatOverlayWindow.presentationMode = event.value
                            ? Desktop.PresentationMode.NATIVE
                            : Desktop.PresentationMode.VIRTUAL;
                        break;
                    case "use_chat_bubbles":
                        Messages.sendLocalMessage(
                            "ChatBubbles-Config",
                            JSON.stringify({
                                enabled: event.value,
                            })
                        );
                        break;
                }

                break;
            case "action":
                switch (event.action) {
                    case "erase_history":
                        Settings.setValue("ArmoredChat-Messages", null);
                        messageHistory = [];
                        _emitEvent({
                            type: "clear_messages",
                        });
                        break;
                    case "start_typing":
                        if (!isTyping) {
                            Messages.sendMessage(
                                "Chat-Typing",
                                JSON.stringify({
                                    action: "typing_start",
                                    position: MyAvatar.position,
                                })
                            );
                        }
                        isTyping = true;
                        break;
                    case "end_typing":
                        endTyping();
                        break;
                }
                break;
            case "initialized":
                // https://github.com/overte-org/overte/issues/824
                if (!tabletMode) { chatOverlayWindow.visible = appIsVisible; }
                _loadSettings();
                break;
        }
    }
    function keyPressEvent(event) {
        if (tabletMode) return;
        switch (JSON.stringify(event.key)) {
            case "16777220": // Enter key
                if (HMD.active) return; // Don't allow in VR

                quickMessage.sendToQml({
                    type: "change_visibility",
                    value: true,
                });
        }
    }
    function _sendMessage(message, channel) {
        if (typeof message !== "string" || message.trim().length === 0 || !channels.includes(channel)) return;

        Messages.sendMessage(
            "chat",
            JSON.stringify({
                position: MyAvatar.position,
                message: message,
                displayName: MyAvatar.sessionDisplayName,
                channel: channel,
                action: "send_chat_message",
            })
        );

        floofChatCompatibilitySendMessage(message, channel);
    }
    function _avatarAction(type, sessionId) {
        Script.setTimeout(() => {
            if (type == "connected") {
                palData = AvatarManager.getPalData().data;
            }

            // Get the display name of the user
            let displayName = "";
            displayName = AvatarManager.getPalData([sessionId])?.data[0]?.sessionDisplayName || null;
            if (displayName == null) {
                for (let i = 0; i < palData.length; i++) {
                    if (palData[i].sessionUUID == sessionId) {
                        displayName = palData[i].sessionDisplayName;
                    }
                }
            }

            // Format the packet
            let message = {};
            const timeArray = _formatTimestamp(_getTimestamp());
            message.timeString = timeArray[0];
            message.dateString = timeArray[1];
            message.message = `${displayName} ${type}`;

            // Show new message on screen
            if (settings.join_notification) {
                Messages.sendLocalMessage(
                    "Floof-Notif",
                    JSON.stringify({
                        sender: displayName,
                        text: type,
                    })
                );
            }

            _emitEvent({ type: "notification", ...message });
        }, 1500);
    }
    function _loadSettings() {
        readSettings();
        if (!tabletMode) {
            chatOverlayWindow.presentationMode = settings.external_window
                ? Desktop.PresentationMode.NATIVE : Desktop.PresentationMode.VIRTUAL;
        }
        _emitEvent({ type: "initial_settings", settings: settings, tabletMode: tabletMode });
        _emitEvent({ type: "clear_messages" });
        Messages.sendLocalMessage("ChatBubbles-Config", JSON.stringify({ enabled: settings.use_chat_bubbles }));

        messageHistory.forEach((message) => {
            const timeArray = _formatTimestamp(message.timestamp);
            message.timeString = timeArray[0];
            message.dateString = timeArray[1];
            _emitEvent({ type: "show_message", ...message });
        });
    }
    function readSettings() {
        var stored = Settings.getValue("ArmoredChat-Config", {}) || {};
        Object.keys(settings).forEach(function(key) {
            if (key === "maximum_messages") {
                if (Number.isFinite(stored[key])) { settings[key] = Math.max(1, Math.min(1000, Math.floor(stored[key]))); }
            } else if (typeof stored[key] === "boolean") { settings[key] = stored[key]; }
        });
        messageHistory = messageHistory.slice(-settings.maximum_messages);
    }
    function _saveSettings() {
        console.log("Saving config");
        Settings.setValue("ArmoredChat-Config", settings);
    }
    function _getTimestamp() {
        return Date.now();
    }
    function _formatTimestamp(timestamp) {
        // We cannot use Date.toLocaleTimeString and Date.toLocaleDateString due to a bug,
        // see https://github.com/overte-org/overte/issues/2197
        const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        const timeArray = [];
        const date = new Date(timestamp);
        const day = date.getDate();
        const dayString = String(day).padStart(2, '0')
        // const suffix = (dayString[0] != '1' && dayString[1] === '1') ? 'st' : (dayString[0] != '1' && dayString[1] === '2') ? 'nd' : (dayString[0] != '1' && dayString[1]) === '3' ? 'rd' : 'th';

        timeArray.push(`${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`);
        timeArray.push(`${day} ${monthNames[date.getMonth()]} ${date.getFullYear()}`);

        return timeArray;
    }

    /**
     * Emit a packet to the HTML front end. Easy communication!
     * @param {Object} packet - The Object packet to emit to the HTML
     * @param {("show_message"|"clear_messages"|"notification"|"initial_settings")} packet.type - The type of packet it is
     */
    function _emitEvent(packet = { type: "" }) {
        if (tabletMode) {
            if (appIsVisible) { tablet.sendToQml(packet); }
        } else { chatOverlayWindow.sendToQml(packet); }
    }

    //
    // Floofchat compatibility functions
    // Added to ease the transition between Floofchat to ArmoredChat
    // These functions can be safely removed at a much later date.
    function floofChatCompatibilityConversion(message) {
        if (message.type === "TransmitChatMessage" && !message.forApp) {
            return {
                position: message.position,
                message: message.message,
                displayName: message.displayName,
                channel: typeof message.channel === "string" ? message.channel.toLowerCase() : "domain",
                action: "send_chat_message",
            };
        }
        return message;
    }

    function floofChatCompatibilitySendMessage(message, channel) {
        Messages.sendMessage(
            "Chat",
            JSON.stringify({
                position: MyAvatar.position,
                message: message,
                displayName: MyAvatar.sessionDisplayName,
                channel: channel.charAt(0).toUpperCase() + channel.slice(1),
                type: "TransmitChatMessage",
                forApp: "Floof",
            })
        );
    }
})();
