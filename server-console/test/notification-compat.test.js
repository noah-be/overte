'use strict';

const assert = require('node:assert/strict');
const EventEmitter = require('node:events');
const Module = require('node:module');
const test = require('node:test');

test('native Electron notifications preserve click behavior', function() {
    var lastNotification;
    var launchedURL;
    var clearedType;
    class FakeNotification extends EventEmitter {
        constructor(options) {
            super();
            this.options = options;
            lastNotification = this;
        }
        static isSupported() {
            return true;
        }
        show() {
            this.wasShown = true;
        }
    }

    var originalLoad = Module._load;
    Module._load = function(request, parent, isMain) {
        if (request === 'electron') {
            return {
                Notification: FakeNotification,
                shell: { openExternal: async function() {} }
            };
        }
        if (request === '@cypress/request') {
            return {};
        }
        if (request === './hf-app') {
            return {
                startInterface: function(url) { launchedURL = url; },
                isInterfaceRunning: function(callback) { callback(false); }
            };
        }
        if (request === './hf-acctinfo') {
            return { AccountInfo: function() {} };
        }
        return originalLoad(request, parent, isMain);
    };

    var notifications;
    try {
        delete require.cache[require.resolve('../src/modules/hf-notifications')];
        notifications = require('../src/modules/hf-notifications');
    } finally {
        Module._load = originalLoad;
    }

    var notification = new notifications.HifiNotification(
        notifications.NotificationType.GOTO,
        1,
        function(type, pending) {
            assert.equal(pending, false);
            clearedType = type;
        }
    );
    notification.show();
    lastNotification.emit('click');

    assert.equal(lastNotification.wasShown, true);
    assert.equal(lastNotification.options.title, 'You have 1 event invitation pending.');
    assert.equal(launchedURL, 'hifiapp:GOTO');
    assert.equal(clearedType, notifications.NotificationType.GOTO);
});
