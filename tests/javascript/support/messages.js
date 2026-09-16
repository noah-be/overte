"use strict";

const { FakeSignal } = require("./signal");

function createMessagesApi({ senderId = "test-sender" } = {}) {
    const subscriptions = new Set();
    const sent = [];
    const messageReceived = new FakeSignal();

    return {
        messageReceived,
        subscribe(channel) {
            subscriptions.add(channel);
        },
        unsubscribe(channel) {
            subscriptions.delete(channel);
        },
        sendMessage(channel, message, localOnly = false) {
            sent.push({ channel, message, localOnly });
            if (subscriptions.has(channel)) {
                messageReceived.emit(channel, message, senderId, localOnly);
            }
        },
        injectMessage(channel, message, injectedSenderId = senderId, localOnly = false) {
            if (subscriptions.has(channel)) {
                messageReceived.emit(channel, message, injectedSenderId, localOnly);
                return true;
            }
            return false;
        },
        subscriptions,
        sent
    };
}

module.exports = { createMessagesApi };
