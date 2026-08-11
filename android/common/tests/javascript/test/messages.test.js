"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { createMessagesApi } = require("../support");

test("messages are delivered only while subscribed", () => {
    const Messages = createMessagesApi({ senderId: "local-avatar" });
    const received = [];
    Messages.messageReceived.connect((...args) => received.push(args));

    Messages.sendMessage("channel", "before");
    Messages.subscribe("channel");
    Messages.sendMessage("channel", "during", true);
    Messages.unsubscribe("channel");
    Messages.sendMessage("channel", "after");

    assert.deepEqual(received, [["channel", "during", "local-avatar", true]]);
    assert.equal(Messages.sent.length, 3);
    assert.equal(Messages.subscriptions.size, 0);
});

test("external message injection reports whether it was delivered", () => {
    const Messages = createMessagesApi();
    const received = [];
    Messages.messageReceived.connect((channel, payload, sender) => {
        received.push({ channel, payload, sender });
    });
    Messages.subscribe("events");

    assert.equal(Messages.injectMessage("ignored", "{}"), false);
    assert.equal(Messages.injectMessage("events", "{\"type\":\"ready\"}", "peer"), true);
    assert.deepEqual(received, [
        { channel: "events", payload: "{\"type\":\"ready\"}", sender: "peer" }
    ]);
});
