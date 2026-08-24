//
//  iosAutonomousTestRunner.js
//
//  SPDX-License-Identifier: Apache-2.0
//

(function () {
    "use strict";

    var SYSTEM_TABLET_ID = "com.highfidelity.interface.tablet.system";
    var POLL_INTERVAL_MS = 250;
    var DEFAULT_ACTION_TIMEOUT_MS = 30000;
    var plan = Test.getIOSAutomationPlan();
    var testId = String(plan.test_id || "invalid");
    var actions = plan.actions || [];
    var heartbeatMs = Number(plan.heartbeat_seconds || 5) * 1000;
    var globalTimeoutMs = Number(plan.timeout_seconds || 600) * 1000;
    var initialDelayMs = Number(plan.initial_delay_ms || 3000);
    var startMs = Date.now();
    var actionIndex = -1;
    var currentCommand = "startup";
    var actionGeneration = 0;
    var finished = false;
    var heartbeatTimer = null;
    var globalTimeoutTimer = null;
    var tablet = Tablet.getTablet(SYSTEM_TABLET_ID);
    var tabletScreen = { type: "Unknown", url: "" };

    function elapsedMs() {
        return Date.now() - startMs;
    }

    function copyFields(fields) {
        var result = {};
        var key;
        fields = fields || {};
        for (key in fields) {
            if (fields.hasOwnProperty(key)) {
                result[key] = fields[key];
            }
        }
        result.test_id = testId;
        result.elapsed_ms = elapsedMs();
        result.action_index = actionIndex;
        result.command = currentCommand;
        return result;
    }

    function event(stage, fields) {
        Test.logIOSAutomationEvent(stage, copyFields(fields));
    }

    function snapshot() {
        var value = Test.getIOSAutomationSnapshot();
        value.tablet_screen_type = tabletScreen.type;
        value.tablet_screen_url = tabletScreen.url;
        return value;
    }

    function valueAtPath(object, path) {
        var parts = String(path || "").split(".");
        var value = object;
        var index;
        for (index = 0; index < parts.length; ++index) {
            if (!parts[index] || value === null || typeof value === "undefined") {
                return undefined;
            }
            value = value[parts[index]];
        }
        return value;
    }

    function compare(actual, operator, expected) {
        switch (operator) {
        case "eq": return actual === expected;
        case "ne": return actual !== expected;
        case "gt": return Number(actual) > Number(expected);
        case "gte": return Number(actual) >= Number(expected);
        case "lt": return Number(actual) < Number(expected);
        case "lte": return Number(actual) <= Number(expected);
        case "truthy": return !!actual;
        case "falsy": return !actual;
        case "contains": return String(actual).indexOf(String(expected)) !== -1;
        default: return false;
        }
    }

    function evaluateAssertion(action) {
        var state = snapshot();
        var actual = valueAtPath(state, action.path);
        var operator = String(action.operator || "eq");
        return {
            passed: compare(actual, operator, action.value),
            actual: actual,
            expected: action.value,
            operator: operator,
            path: String(action.path || ""),
            state: state
        };
    }

    function finishRunner(status, reason) {
        if (finished) {
            return;
        }
        finished = true;
        if (heartbeatTimer !== null) {
            Script.clearInterval(heartbeatTimer);
        }
        if (globalTimeoutTimer !== null) {
            Script.clearTimeout(globalTimeoutTimer);
        }
        event("result", {
            status: status,
            reason: String(reason || ""),
            completed_actions: Math.max(0, actionIndex + (status === "passed" ? 1 : 0)),
            total_actions: actions.length,
            snapshot: snapshot()
        });
        Script.setTimeout(function () {
            if (plan.quit_on_finish === true) {
                Test.quit();
            } else {
                Script.stop();
            }
        }, 100);
    }

    function fail(reason, details) {
        details = details || {};
        details.status = "failed";
        details.reason = String(reason);
        event("action_finished", details);
        finishRunner("failed", reason);
    }

    function actionTimeout(action, fallbackMs) {
        var value = Number(action.timeout_ms || fallbackMs || DEFAULT_ACTION_TIMEOUT_MS);
        return Math.max(250, Math.min(value, globalTimeoutMs));
    }

    function pollUntil(action, predicate, success, timeoutReason) {
        var generation = actionGeneration;
        var started = Date.now();
        var timeoutMs = actionTimeout(action);

        function poll() {
            var result;
            if (finished || generation !== actionGeneration) {
                return;
            }
            try {
                result = predicate();
            } catch (error) {
                fail("poll-exception", { error: String(error) });
                return;
            }
            if (result) {
                success(result);
                return;
            }
            if (Date.now() - started >= timeoutMs) {
                fail(timeoutReason || "action-timeout", { timeout_ms: timeoutMs, snapshot: snapshot() });
                return;
            }
            Script.setTimeout(poll, POLL_INTERVAL_MS);
        }
        poll();
    }

    function nextAction(fields) {
        event("action_finished", fields || { status: "passed" });
        Script.setTimeout(runNextAction, 0);
    }

    function runAction(action) {
        var command = String(action.command || "");
        var settleMs = Math.max(0, Number(action.settle_ms || 500));
        var result;
        var assertion;

        switch (command) {
        case "wait":
            Script.setTimeout(function () {
                nextAction({ status: "passed", waited_ms: Math.max(0, Number(action.duration_ms || 0)) });
            }, Math.max(0, Number(action.duration_ms || 0)));
            return;

        case "wait_until":
            pollUntil(action, function () {
                assertion = evaluateAssertion(action);
                return assertion.passed;
            }, function () {
                nextAction({ status: "passed", assertion: assertion });
            }, "wait-until-timeout");
            return;

        case "navigate":
            if (!action.url) {
                fail("navigate-url-missing");
                return;
            }
            AddressManager.handleLookupString(String(action.url), false);
            if (action.wait_for_connection === true) {
                pollUntil(action, function () {
                    return snapshot().connected === true;
                }, function () {
                    Script.setTimeout(function () {
                        nextAction({ status: "passed", address: snapshot().address });
                    }, settleMs);
                }, "navigation-connection-timeout");
            } else {
                Script.setTimeout(function () {
                    nextAction({ status: "passed", address: snapshot().address });
                }, settleMs);
            }
            return;

        case "wait_connection":
            pollUntil(action, function () {
                return snapshot().connected === true;
            }, function () {
                nextAction({ status: "passed", address: snapshot().address });
            }, "connection-timeout");
            return;

        case "open_tablet":
            if (action.home !== false) {
                tablet.gotoHomeScreen();
            }
            HMD.openTablet(false);
            pollUntil(action, function () {
                return snapshot().tablet_shown === true;
            }, function () {
                Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            }, "tablet-open-timeout");
            return;

        case "close_tablet":
            HMD.closeTablet();
            pollUntil(action, function () {
                return snapshot().tablet_shown === false;
            }, function () {
                Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            }, "tablet-close-timeout");
            return;

        case "tablet_home":
            tablet.gotoHomeScreen();
            HMD.openTablet(false);
            pollUntil(action, function () {
                var state = snapshot();
                return state.tablet_shown === true && state.tablet_home === true;
            }, function () {
                Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            }, "tablet-home-timeout");
            return;

        case "tablet_qml":
            if (!action.path) {
                fail("tablet-qml-path-missing");
                return;
            }
            tablet.loadQMLSource(String(action.path));
            HMD.openTablet(false);
            pollUntil(action, function () {
                return tablet.isPathLoaded(String(action.path));
            }, function () {
                Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            }, "tablet-qml-timeout");
            return;

        case "tablet_web":
            if (!action.url) {
                fail("tablet-web-url-missing");
                return;
            }
            tablet.gotoWebScreen(String(action.url));
            HMD.openTablet(false);
            Script.setTimeout(function () {
                nextAction({ status: "passed", snapshot: snapshot() });
            }, settleMs);
            return;

        case "camera_mode":
            result = Test.executeIOSAutomationCommand("set_camera_mode", { mode: String(action.mode || "") });
            if (!result) {
                fail("camera-mode-rejected", { mode: action.mode });
                return;
            }
            pollUntil(action, function () {
                return snapshot().camera_mode === String(action.mode);
            }, function () {
                nextAction({ status: "passed", mode: snapshot().camera_mode });
            }, "camera-mode-timeout");
            return;

        case "turn":
            try {
                MyAvatar.orientation = Quat.multiply(
                    Quat.fromPitchYawRollDegrees(
                        Number(action.pitch_degrees || 0),
                        Number(action.yaw_degrees || 0),
                        Number(action.roll_degrees || 0)),
                    MyAvatar.orientation);
            } catch (turnError) {
                fail("turn-exception", { error: String(turnError) });
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "jump":
            result = Test.executeIOSAutomationCommand("jump", {});
            if (!result) {
                fail("jump-rejected");
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "tap":
            result = Test.executeIOSAutomationCommand("tap", {
                x: Number(action.x),
                y: Number(action.y),
                normalized: action.normalized !== false
            });
            if (!result) {
                fail("tap-rejected");
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "swipe":
            result = Test.executeIOSAutomationCommand("swipe", {
                start_x: Number(action.start_x),
                start_y: Number(action.start_y),
                end_x: Number(action.end_x),
                end_y: Number(action.end_y),
                normalized: action.normalized !== false
            });
            if (!result) {
                fail("swipe-rejected");
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "type_text":
            result = Test.executeIOSAutomationCommand("type_text", { text: String(action.text || "") });
            if (!result) {
                fail("type-text-rejected");
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "key":
            result = Test.executeIOSAutomationCommand("key", { name: String(action.name || "") });
            if (!result) {
                fail("key-rejected", { name: action.name });
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "clear_caches":
            result = Test.executeIOSAutomationCommand("clear_caches", {});
            if (!result) {
                fail("clear-caches-rejected");
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed" }); }, settleMs);
            return;

        case "set_render_scale":
            result = Test.executeIOSAutomationCommand("set_render_scale", { scale: Number(action.scale) });
            if (!result) {
                fail("render-scale-rejected", { scale: action.scale });
                return;
            }
            Script.setTimeout(function () { nextAction({ status: "passed", snapshot: snapshot() }); }, settleMs);
            return;

        case "snapshot":
            nextAction({ status: "passed", label: String(action.label || "sample"), snapshot: snapshot() });
            return;

        case "screenshot":
            event("screenshot_requested", { label: String(action.label || ("action-" + actionIndex)) });
            Script.setTimeout(function () { nextAction({ status: "passed" }); }, settleMs);
            return;

        case "assert":
            assertion = evaluateAssertion(action);
            if (!assertion.passed) {
                fail("assertion-failed", { assertion: assertion });
                return;
            }
            nextAction({ status: "passed", assertion: assertion });
            return;

        case "finish":
            finishRunner(String(action.status || "passed"), String(action.reason || "explicit-finish"));
            return;

        default:
            fail("unsupported-command", { requested_command: command });
        }
    }

    function runNextAction() {
        var action;
        if (finished) {
            return;
        }
        actionIndex += 1;
        actionGeneration += 1;
        if (actionIndex >= actions.length) {
            finishRunner("passed", "all-actions-completed");
            return;
        }
        action = actions[actionIndex];
        currentCommand = String(action.command || "");
        // Do not mirror the full action into syslog: type_text may contain
        // private input. The plan and detailed result remain on Fedora.
        event("action_started", {
            label: String(action.label || ""),
            timeout_ms: Number(action.timeout_ms || 0)
        });
        try {
            runAction(action);
        } catch (error) {
            fail("action-exception", { error: String(error) });
        }
    }

    function onTabletScreenChanged(type, url) {
        tabletScreen = { type: String(type), url: String(url || "") };
        event("tablet_screen_changed", tabletScreen);
    }

    Script.scriptEnding.connect(function () {
        try {
            tablet.screenChanged.disconnect(onTabletScreenChanged);
        } catch (error) {
            // The tablet can already have been destroyed during app shutdown.
        }
    });
    tablet.screenChanged.connect(onTabletScreenChanged);

    event("runner_ready", {
        schema_version: plan.schema_version,
        action_count: actions.length,
        heartbeat_seconds: heartbeatMs / 1000,
        timeout_seconds: globalTimeoutMs / 1000,
        initial_delay_ms: initialDelayMs,
        snapshot: snapshot()
    });

    heartbeatTimer = Script.setInterval(function () {
        if (!finished) {
            event("heartbeat", { snapshot: snapshot() });
        }
    }, heartbeatMs);
    globalTimeoutTimer = Script.setTimeout(function () {
        fail("global-timeout", { timeout_ms: globalTimeoutMs, snapshot: snapshot() });
    }, globalTimeoutMs);
    Script.setTimeout(runNextAction, initialDelayMs);
}());
