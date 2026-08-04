"use strict";

//  controllerDispatcher.js
//
//  Created by Seth Alves, July 27th, 2017.
//  Copyright 2017 High Fidelity, Inc.
//  Copyright 2023, Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

/* jslint bitwise: true */

/* global Script, Entities, Overlays, Controller, Vec3, Quat, getControllerWorldLocation,
   controllerDispatcherPlugins:true, controllerDispatcherPluginsNeedSort:true,
   LEFT_HAND, RIGHT_HAND, NEAR_GRAB_PICK_RADIUS, DEFAULT_SEARCH_SPHERE_DISTANCE, DISPATCHER_PROPERTIES,
   getGrabPointSphereOffset, HMD, MyAvatar, Messages, findHandChildEntities, Picks, PickType, Pointers,
   PointerManager, getGrabPointSphereOffset, HMD, MyAvatar, Messages, findHandChildEntities, print, Keyboard,
   Tablet, Settings, isInEditMode
*/

var controllerDispatcherPlugins = {};
var controllerDispatcherPluginsNeedSort = false;

Script.include("/~/system/libraries/utils.js");
Script.include("/~/system/libraries/controllers.js");
Script.include("/~/system/libraries/controllerDispatcherUtils.js");

(function() {
    Script.include("/~/system/libraries/pointersUtils.js");

    var controllerStandard = Controller.Standard;

    var NEAR_MAX_RADIUS = 0.1;
    var NEAR_TABLET_MAX_RADIUS = 0.05;

    var TARGET_UPDATE_HZ = 60; // 50hz good enough, but we're using update
    var BASIC_TIMER_INTERVAL_MS = 1000 / TARGET_UPDATE_HZ;
    var PICO_IDLE_UPDATE_HZ = 30;
    var PICO_IDLE_TIMER_INTERVAL_MS = 1000 / PICO_IDLE_UPDATE_HZ;

    var PROFILE = false;
    var DEBUG = false;
    var SHOW_GRAB_SPHERE = false;
    var picoLazyHandRays = Settings.getValue("deferTabletCreationUntilOpen", false);
    var systemTablet = picoLazyHandRays
        ? Tablet.getTablet("com.highfidelity.interface.tablet.system")
        : null;

    if (typeof Test !== "undefined") {
        PROFILE = true;
    }

    function ControllerDispatcher() {
        var _this = this;
        this.lastInterval = Date.now();
        this.intervalCount = 0;
        this.totalDelta = 0;
        this.totalVariance = 0;
        this.highVarianceCount = 0;
        this.veryhighVarianceCount = 0;
        this.orderedPluginNames = [];
        this.tabletID = null;
        this.blocklist = [];
        this.picoEditingHand = null;
        this.pointerManager = new PointerManager();
        this.grabSphereOverlays = [null, null];
        this.targetIDs = {};
        this.debugPanelID = null;
        this.debugLines = [];

        this.pointerUsedByAnotherRunningPlugin = function(stoppingPluginName, laserParams) {
            if (!laserParams || laserParams.hand < 0) {
                return false;
            }
            for (var pluginName in _this.runningPluginNames) {
                if (_this.runningPluginNames.hasOwnProperty(pluginName) &&
                        pluginName !== stoppingPluginName) {
                    var otherPlugin = controllerDispatcherPlugins[pluginName];
                    var otherLaser = otherPlugin && otherPlugin.parameters &&
                        otherPlugin.parameters.handLaser;
                    if (otherLaser && otherLaser.hand === laserParams.hand) {
                        return true;
                    }
                }
            }
            return false;
        };

        // a module can occupy one or more "activity" slots while it's running.  If all the required slots for a module are
        // not set to false (not in use), a module cannot start.  When a module is using a slot, that module's name
        // is stored as the value, rather than false.
        this.activitySlots = {
            head: false,
            leftHand: false,
            rightHand: false,
            rightHandTrigger: false,
            leftHandTrigger: false,
            rightHandEquip: false,
            leftHandEquip: false,
            mouse: false
        };

        this.laserVisibleStatus = [false, false, false, false];
        this.laserLockStatus = [false, false, false, false];

        this.slotsAreAvailableForPlugin = function (plugin) {
            for (var i = 0; i < plugin.parameters.activitySlots.length; i++) {
                if (_this.activitySlots[plugin.parameters.activitySlots[i]]) {
                    return false; // something is already using a slot which _this plugin requires
                }
            }
            return true;
        };

        this.markSlots = function (plugin, pluginName) {
            for (var i = 0; i < plugin.parameters.activitySlots.length; i++) {
                _this.activitySlots[plugin.parameters.activitySlots[i]] = pluginName;
            }
        };

        this.unmarkSlotsForPluginName = function (runningPluginName) {
            // this is used to free activity-slots when a plugin is deactivated while it's running.
            for (var activitySlot in _this.activitySlots) {
                if (activitySlot.hasOwnProperty(activitySlot) && _this.activitySlots[activitySlot] === runningPluginName) {
                    _this.activitySlots[activitySlot] = false;
                }
            }
        };

        this.runningPluginNames = {};

        this.leftTriggerValue = 0;
        this.leftTriggerClicked = 0;
        this.leftTrackerClicked = false; // is leftTriggerClicked == 1 because a hand tracker set it?
        this.leftSecondaryValue = 0;

        this.rightTriggerValue = 0;
        this.rightTriggerClicked = 0;
        this.rightTrackerClicked = false; // is rightTriggerClicked == 1 because a hand tracker set it?
        this.rightSecondaryValue = 0;

        this.leftTriggerPress = function (value) {
            _this.leftTriggerValue = value;
        };
        this.leftTriggerClick = function (value) {
            _this.leftTriggerClicked = value;
        };
        this.rightTriggerPress = function (value) {
            _this.rightTriggerValue = value;
        };
        this.rightTriggerClick = function (value) {
            _this.rightTriggerClicked = value;
        };
        this.leftSecondaryPress = function (value) {
            _this.leftSecondaryValue = value;
        };
        this.rightSecondaryPress = function (value) {
            _this.rightSecondaryValue = value;
        };

        this.dataGatherers = {};
        this.dataGatherers.leftControllerLocation = function () {
            return getControllerWorldLocation(controllerStandard.LeftHand, true);
        };
        this.dataGatherers.rightControllerLocation = function () {
            return getControllerWorldLocation(controllerStandard.RightHand, true);
        };

        this.updateTimings = function () {
            _this.intervalCount++;
            var thisInterval = Date.now();
            var deltaTimeMsec = thisInterval - _this.lastInterval;
            var deltaTime = deltaTimeMsec / 1000;
            _this.lastInterval = thisInterval;

            _this.totalDelta += deltaTimeMsec;

            var variance = Math.abs(deltaTimeMsec - BASIC_TIMER_INTERVAL_MS);
            _this.totalVariance += variance;

            if (variance > 1) {
                _this.highVarianceCount++;
            }

            if (variance > 5) {
                _this.veryhighVarianceCount++;
            }

            return deltaTime;
        };

        this.setIgnorePointerItems = function() {
            if (HMD.tabletID && HMD.tabletID !== this.tabletID) {
                this.tabletID = HMD.tabletID;
                Pointers.setIgnoreItems(_this.leftPointer, _this.blocklist);
                Pointers.setIgnoreItems(_this.rightPointer, _this.blocklist);
            }
        };

        this.checkForHandTrackingClick = function() {

            var pinchOnBelowDistance = 0.016;
            var pinchOffAboveDistance = 0.035;

            var leftIndexPose = Controller.getPoseValue(controllerStandard.LeftHandIndex4);
            var leftThumbPose = Controller.getPoseValue(controllerStandard.LeftHandThumb4);
            var leftThumbToIndexDistance = Vec3.distance(leftIndexPose.translation, leftThumbPose.translation);
            if (leftIndexPose.valid && leftThumbPose.valid && leftThumbToIndexDistance < pinchOnBelowDistance) {
                _this.leftTriggerClicked = 1;
                _this.leftTriggerValue = 1;
                _this.leftTrackerClicked = true;
            } else if (_this.leftTrackerClicked && leftThumbToIndexDistance > pinchOffAboveDistance) {
                _this.leftTriggerClicked = 0;
                _this.leftTriggerValue = 0;
                _this.leftTrackerClicked = false;
            }

            var rightIndexPose = Controller.getPoseValue(controllerStandard.RightHandIndex4);
            var rightThumbPose = Controller.getPoseValue(controllerStandard.RightHandThumb4);
            var rightThumbToIndexDistance = Vec3.distance(rightIndexPose.translation, rightThumbPose.translation);
            if (rightIndexPose.valid && rightThumbPose.valid && rightThumbToIndexDistance < pinchOnBelowDistance) {
                _this.rightTriggerClicked = 1;
                _this.rightTriggerValue = 1;
                _this.rightTrackerClicked = true;
            } else if (_this.rightTrackerClicked && rightThumbToIndexDistance > pinchOffAboveDistance) {
                _this.rightTriggerClicked = 0;
                _this.rightTriggerValue = 0;
                _this.rightTrackerClicked = false;
            }
        };

        this.hasActiveInteraction = function () {
            if ((systemTablet && systemTablet.tabletShown) || HMD.showTablet ||
                    isInEditMode() || Keyboard.raised || _this.picoEditingHand !== null ||
                    _this.leftTriggerValue > 0.01 || _this.rightTriggerValue > 0.01 ||
                    _this.leftTriggerClicked || _this.rightTriggerClicked ||
                    _this.leftSecondaryValue > 0.01 || _this.rightSecondaryValue > 0.01) {
                return true;
            }

            for (var runningPluginName in _this.runningPluginNames) {
                if (_this.runningPluginNames.hasOwnProperty(runningPluginName)) {
                    return true;
                }
            }
            return false;
        };

        this.update = function () {
            try {
                _this.updateInternal();
            } catch (e) {
                print(e);
            }
            // Controller mappings update the trigger/grip state independently,
            // so an idle standalone headset can poll the expensive dispatcher
            // less often without missing the start of an interaction. Return to
            // the full rate as soon as the tablet, keyboard, edit mode, an input,
            // or a dispatcher module becomes active.
            var nextInterval = picoLazyHandRays && !_this.hasActiveInteraction()
                ? PICO_IDLE_TIMER_INTERVAL_MS
                : BASIC_TIMER_INTERVAL_MS;
            Script.setTimeout(_this.update, nextInterval);
        };

        this.addDebugLine = function(line) {
            if (this.debugLines.length > 8) {
                this.debugLines.shift();
            }
            this.debugLines.push(line);
            var debugPanelText = "";
            this.debugLines.forEach(function(debugLine) {
                debugPanelText += debugLine + "\n";
            });
            Entities.editEntity(this.debugPanelID, { text: debugPanelText });
        };

        this.updateInternal = function () {
            if (PROFILE) {
                Script.beginProfileRange("dispatch.pre");
            }
            var sensorScaleFactor = MyAvatar.sensorToWorldScale;
            var deltaTime = _this.updateTimings();
            _this.setIgnorePointerItems();

            if (controllerDispatcherPluginsNeedSort) {
                _this.orderedPluginNames = [];
                for (var pluginName in controllerDispatcherPlugins) {
                    if (controllerDispatcherPlugins.hasOwnProperty(pluginName)) {
                        _this.orderedPluginNames.push(pluginName);
                    }
                }
                _this.orderedPluginNames.sort(function (a, b) {
                    return controllerDispatcherPlugins[a].parameters.priority -
                        controllerDispatcherPlugins[b].parameters.priority;
                });

                controllerDispatcherPluginsNeedSort = false;
            }

            if (PROFILE) {
                Script.endProfileRange("dispatch.pre");
            }

            if (PROFILE) {
                Script.beginProfileRange("dispatch.gather");
            }

            var controllerLocations = [
                _this.dataGatherers.leftControllerLocation(),
                _this.dataGatherers.rightControllerLocation()
            ];

            // find 3d overlays/Local Entities near each hand
            var nearbyOverlayIDs = [];
            var h;
//V8TODO: Overlays.findOverlays might not work here
            for (h = LEFT_HAND; h <= RIGHT_HAND; h++) {
                if (controllerLocations[h].valid) {
                    var nearbyOverlays =
                        Overlays.findOverlays(controllerLocations[h].position, NEAR_MAX_RADIUS * sensorScaleFactor);

                    // Tablet and mini-tablet must be within NEAR_TABLET_MAX_RADIUS in order to be grabbed.
                    // Mini tablet can only be grabbed the hand it's displayed on.
                    var tabletIndex = nearbyOverlays.indexOf(HMD.tabletID);
                    var miniTabletIndex = nearbyOverlays.indexOf(HMD.miniTabletID);
                    if (tabletIndex !== -1 || miniTabletIndex !== -1) {
                        var closebyOverlays =
                            Overlays.findOverlays(controllerLocations[h].position, NEAR_TABLET_MAX_RADIUS * sensorScaleFactor);
                        // Assumes that the tablet and mini-tablet are not displayed at the same time.
                        if (tabletIndex !== -1 && closebyOverlays.indexOf(HMD.tabletID) === -1) {
                            nearbyOverlays.splice(tabletIndex, 1);
                        }
                        if (miniTabletIndex !== -1 &&
                            ((closebyOverlays.indexOf(HMD.miniTabletID) === -1) || h !== HMD.miniTabletHand)) {
                            nearbyOverlays.splice(miniTabletIndex, 1);
                        }
                    }

                    nearbyOverlays.sort(function (a, b) {
                        var aPosition = Entities.getEntityProperties(a, ["position"]).position;
                        var aDistance = Vec3.distance(aPosition, controllerLocations[h].position);
                        var bPosition = Entities.getEntityProperties(b, ["position"]).position;
                        var bDistance = Vec3.distance(bPosition, controllerLocations[h].position);
                        return aDistance - bDistance;
                    });

                    nearbyOverlayIDs.push(nearbyOverlays);
                } else {
                    nearbyOverlayIDs.push([]);
                }
            }

            // find entities near each hand
            var nearbyEntityProperties = [[], []];
            var nearbyEntityPropertiesByID = {};
            for (h = LEFT_HAND; h <= RIGHT_HAND; h++) {
                if (controllerLocations[h].valid) {
                    var controllerPosition = controllerLocations[h].position;
                    var findRadius = NEAR_MAX_RADIUS * sensorScaleFactor;

                    if (SHOW_GRAB_SPHERE) {
                        if (this.grabSphereOverlays[h]) {
                            Entities.editEntity(this.grabSphereOverlays[h], { "position": controllerLocations[h].position });
                        } else {
                            var grabSphereSize = findRadius * 2;
                            this.grabSphereOverlays[h] = Entities.addEntity({
                                "type": "Shape",
                                "shape": "Sphere",
                                "position": controllerLocations[h].position,
                                "dimensions": { 
                                    "x": grabSphereSize, 
                                    "y": grabSphereSize, 
                                    "z": grabSphereSize 
                                },
                                "color": { 
                                    "red": 30, 
                                    "green": 30, 
                                    "blue": 255 
                                },
                                "alpha": 0.3,
                                "primitiveMode": "solid",
                                "visible": true,
                                "renderLayer": "front",
                                "grab": {
                                    "grabbable": false
                                }
                            }, "local");
                        }
                    }

                    var nearbyEntityIDs = Entities.findEntities(controllerPosition, findRadius);

                    for (var j = 0; j < nearbyEntityIDs.length; j++) {
                        var entityID = nearbyEntityIDs[j];
                        var props = Entities.getEntityProperties(entityID, DISPATCHER_PROPERTIES);
                        props.id = entityID;
                        props.distance = Vec3.distance(props.position, controllerLocations[h].position);
                        nearbyEntityPropertiesByID[entityID] = props;
                        nearbyEntityProperties[h].push(props);
                    }
                }
            }

            // On Pico, two continuously active world rays cost roughly 5 ms
            // even while the user is simply walking.  Keep them hot for the
            // tablet/keyboard and while an interaction control is held, but
            // do not ray-pick an idle world every simulation update.
            var handRaysNeeded = !picoLazyHandRays ||
                (systemTablet && systemTablet.tabletShown) ||
                HMD.showTablet ||
                isInEditMode() ||
                Keyboard.raised ||
                _this.leftTriggerValue > 0.01 ||
                _this.rightTriggerValue > 0.01 ||
                _this.leftSecondaryValue > 0.01 ||
                _this.rightSecondaryValue > 0.01;

            // Enable/disable controller raypicking depending on whether we are in HMD.
            if (HMD.active && handRaysNeeded) {
                // Once a Create handle has been acquired, its drag math uses
                // the current controller pose directly.  Keep only the
                // grabbing hand's world pointer alive; repicking the other
                // hand and both HUD rays just steals time from the drag loop.
                if (picoLazyHandRays && systemTablet && systemTablet.tabletShown &&
                        _this.picoEditingHand === null) {
                    // Precise tablet rays can each exceed the pick budget in
                    // a dense scene. Keep one stable interaction hand instead
                    // of alternating stale hover/click results between both.
                    var tabletHand = MyAvatar.getDominantHand() === "left" ? LEFT_HAND : RIGHT_HAND;
                    if (_this.leftTriggerValue > 0.01 && _this.rightTriggerValue <= 0.01) {
                        tabletHand = LEFT_HAND;
                    } else if (_this.rightTriggerValue > 0.01 && _this.leftTriggerValue <= 0.01) {
                        tabletHand = RIGHT_HAND;
                    }
                    if (tabletHand === LEFT_HAND) {
                        Pointers.enablePointer(_this.leftPointer);
                        Pointers.disablePointer(_this.rightPointer);
                    } else {
                        Pointers.disablePointer(_this.leftPointer);
                        Pointers.enablePointer(_this.rightPointer);
                    }
                    if (_this.leftHudPointer !== _this.leftPointer) {
                        Pointers.disablePointer(_this.leftHudPointer);
                    }
                    if (_this.rightHudPointer !== _this.rightPointer) {
                        Pointers.disablePointer(_this.rightHudPointer);
                    }
                } else if (picoLazyHandRays && _this.picoEditingHand !== null) {
                    if (_this.picoEditingHand === LEFT_HAND) {
                        Pointers.enablePointer(_this.leftPointer);
                        Pointers.disablePointer(_this.rightPointer);
                    } else {
                        Pointers.disablePointer(_this.leftPointer);
                        Pointers.enablePointer(_this.rightPointer);
                    }
                    Pointers.disablePointer(_this.leftHudPointer);
                    Pointers.disablePointer(_this.rightHudPointer);
                } else {
                    Pointers.enablePointer(_this.leftPointer);
                    Pointers.enablePointer(_this.rightPointer);
                    Pointers.enablePointer(_this.leftHudPointer);
                    Pointers.enablePointer(_this.rightHudPointer);
                }
                Pointers.disablePointer(_this.mouseRayPointer);
            } else {
                Pointers.disablePointer(_this.leftPointer);
                Pointers.disablePointer(_this.rightPointer);
                Pointers.disablePointer(_this.leftHudPointer);
                Pointers.disablePointer(_this.rightHudPointer);
                Pointers.disablePointer(_this.mouseRayPointer);
            }

            // raypick for each controller
            var rayPicks = [
                Pointers.getPrevPickResult(_this.leftPointer),
                Pointers.getPrevPickResult(_this.rightPointer)
            ];
            var hudRayPicks = [
                Pointers.getPrevPickResult(_this.leftHudPointer),
                Pointers.getPrevPickResult(_this.rightHudPointer)
            ];
            var mouseRayPointer = Pointers.getPrevPickResult(_this.mouseRayPointer);
            // if the pickray hit something very nearby, put it into the nearby entities list
            for (h = LEFT_HAND; h <= RIGHT_HAND; h++) {

                // XXX find a way to extract searchRay from samuel's stuff
                if (controllerLocations[h].valid) {
                    rayPicks[h].searchRay = {
                        origin: controllerLocations[h].position,
                        direction: Quat.getUp(controllerLocations[h].orientation),
                        length: 1000
                    };

                    if (rayPicks[h].type === Picks.INTERSECTED_ENTITY) {
                        // XXX check to make sure this one isn't already in nearbyEntityProperties?
                        if (rayPicks[h].distance < NEAR_GRAB_PICK_RADIUS * sensorScaleFactor) {
                            var nearEntityID = rayPicks[h].objectID;
                            var nearbyProps = Entities.getEntityProperties(nearEntityID, DISPATCHER_PROPERTIES);
                            nearbyProps.id = nearEntityID;
                            nearbyProps.distance = rayPicks[h].distance;
                            nearbyEntityPropertiesByID[nearEntityID] = nearbyProps;
                            nearbyEntityProperties[h].push(nearbyProps);
                        }
                    }

                    // sort by distance from each hand
                    nearbyEntityProperties[h].sort(function (a, b) {
                        return a.distance - b.distance;
                    });
                }
            }

            // sometimes, during a HMD snap-turn, an equipped or held item wont be near
            // the hand when the findEntities is done.  Gather up any hand-children here.
            for (h = LEFT_HAND; h <= RIGHT_HAND; h++) {
                var handChildrenIDs = findHandChildEntities(h);
                handChildrenIDs.forEach(function (handChildID) {
                    if (handChildID in nearbyEntityPropertiesByID) {
                        return;
                    }
                    var props = Entities.getEntityProperties(handChildID, DISPATCHER_PROPERTIES);
                    props.id = handChildID;
                    nearbyEntityPropertiesByID[handChildID] = props;
                });
            }

            // also make sure we have the properties from the current module's target
            for (var tIDRunningPluginName in _this.runningPluginNames) {
                if (_this.runningPluginNames.hasOwnProperty(tIDRunningPluginName)) {
                    var targetIDs = _this.targetIDs[tIDRunningPluginName];
                    if (targetIDs) {
                        for (var k = 0; k < targetIDs.length; k++) {
                            var targetID = targetIDs[k];
                            if (!nearbyEntityPropertiesByID[targetID]) {
                                var targetProps = Entities.getEntityProperties(targetID, DISPATCHER_PROPERTIES);
                                targetProps.id = targetID;
                                nearbyEntityPropertiesByID[targetID] = targetProps;
                            }
                        }
                    }
                }
            }


            // TODO: These are not used currently, but have severe impact on performace. They can be re-enabled when we have OpenXR support
            // check for hand-tracking "click"
            //_this.checkForHandTrackingClick();

            // bundle up all the data about the current situation
            var controllerData = {
                triggerValues: [_this.leftTriggerValue, _this.rightTriggerValue],
                triggerClicks: [_this.leftTriggerClicked, _this.rightTriggerClicked],
                secondaryValues: [_this.leftSecondaryValue, _this.rightSecondaryValue],
                controllerLocations: controllerLocations,
                nearbyEntityProperties: nearbyEntityProperties,
                nearbyEntityPropertiesByID: nearbyEntityPropertiesByID,
                nearbyOverlayIDs: nearbyOverlayIDs,
                rayPicks: rayPicks,
                hudRayPicks: hudRayPicks,
                mouseRayPointer: mouseRayPointer
            };
            if (PROFILE) {
                Script.endProfileRange("dispatch.gather");
            }

            if (PROFILE) {
                Script.beginProfileRange("dispatch.isReady");
            }
            // check for plugins that would like to start.  ask in order of increasing priority value
            for (var pluginIndex = 0; pluginIndex < _this.orderedPluginNames.length; pluginIndex++) {
                var orderedPluginName = _this.orderedPluginNames[pluginIndex];
                var candidatePlugin = controllerDispatcherPlugins[orderedPluginName];

                if (_this.slotsAreAvailableForPlugin(candidatePlugin)) {
                    if (PROFILE) {
                        Script.beginProfileRange("dispatch.isReady." + orderedPluginName);
                    }
                    var readiness = candidatePlugin.isReady(controllerData, deltaTime);
                    if (readiness.active) {
                        // this plugin will start.  add it to the list of running plugins and mark the
                        // activity-slots which this plugin consumes as "in use"
                        _this.runningPluginNames[orderedPluginName] = true;
                        _this.markSlots(candidatePlugin, orderedPluginName);
                        _this.pointerManager.makePointerVisible(candidatePlugin.parameters.handLaser);
                        if (DEBUG) {
                            _this.addDebugLine("running " + orderedPluginName);
                        }
                    }
                    if (PROFILE) {
                        Script.endProfileRange("dispatch.isReady." + orderedPluginName);
                    }
                }
            }
            if (PROFILE) {
                Script.endProfileRange("dispatch.isReady");
            }

            if (PROFILE) {
                Script.beginProfileRange("dispatch.run");
            }
            // give time to running plugins
            for (var runningPluginName in _this.runningPluginNames) {
                if (_this.runningPluginNames.hasOwnProperty(runningPluginName)) {
                    var plugin = controllerDispatcherPlugins[runningPluginName];
                    if (!plugin) {
                        // plugin was deactivated while running.  find the activity-slots it was using and make
                        // them available.
                        delete _this.runningPluginNames[runningPluginName];
                        _this.unmarkSlotsForPluginName(runningPluginName);
                    } else {
                        if (PROFILE) {
                            Script.beginProfileRange("dispatch.run." + runningPluginName);
                        }
                        var runningness = plugin.run(controllerData, deltaTime);

                        if (DEBUG) {
                            if (JSON.stringify(_this.targetIDs[runningPluginName]) != JSON.stringify(runningness.targets)) {
                                _this.addDebugLine("targetIDs[" + runningPluginName + "] = " +
                                                  JSON.stringify(runningness.targets));
                            }
                        }

                        _this.targetIDs[runningPluginName] = runningness.targets;
                        if (!runningness.active) {
                            // plugin is finished running, for now.  remove it from the list
                            // of running plugins and mark its activity-slots as "not in use"
                            delete _this.runningPluginNames[runningPluginName];
                            delete _this.targetIDs[runningPluginName];
                            if (DEBUG) {
                                _this.addDebugLine("deleted targetIDs[" + runningPluginName + "]");
                            }
                            _this.markSlots(plugin, false);
                            // Multiple dispatcher modules share each physical
                            // hand pointer.  A tablet/web module may stop on
                            // the same frame that the Create edit module takes
                            // ownership.  Do not let the stopping module hide
                            // a pointer that is still in use.
                            if (!_this.pointerUsedByAnotherRunningPlugin(
                                    runningPluginName, plugin.parameters.handLaser)) {
                                _this.pointerManager.makePointerInvisible(plugin.parameters.handLaser);
                            }
                            if (DEBUG) {
                                _this.addDebugLine("stopping " + runningPluginName);
                            }
                        }
                        _this.pointerManager.lockPointerEnd(plugin.parameters.handLaser, runningness.laserLockInfo);
                        if (PROFILE) {
                            Script.endProfileRange("dispatch.run." + runningPluginName);
                        }
                    }
                }
            }
            // Create's edit affordances use the same physical ray pointers as
            // tablet, web and grab modules.  Make the final visibility
            // decision here so module transition order cannot erase the edit
            // laser before render-state selection.
            if (picoLazyHandRays && isInEditMode()) {
                if (_this.picoEditingHand !== null) {
                    _this.pointerManager.forceHandPointerVisible(_this.picoEditingHand);
                } else {
                    _this.pointerManager.forceHandPointerVisible(LEFT_HAND);
                    _this.pointerManager.forceHandPointerVisible(RIGHT_HAND);
                }
            }
            _this.pointerManager.updatePointersRenderState(controllerData.triggerClicks, controllerData.triggerValues);
            if (PROFILE) {
                Script.endProfileRange("dispatch.run");
            }
        };

        this.leftBlocklistTabletIDs = [];
        this.rightBlocklistTabletIDs = [];

        this.setLeftBlocklist = function () {
            Pointers.setIgnoreItems(_this.leftPointer, _this.blocklist.concat(_this.leftBlocklistTabletIDs));
        };
        this.setRightBlocklist = function () {
            Pointers.setIgnoreItems(_this.rightPointer, _this.blocklist.concat(_this.rightBlocklistTabletIDs));
        };

        this.setBlocklist = function() {
            _this.setLeftBlocklist();
            _this.setRightBlocklist();
        };

        var MAPPING_NAME = "com.highfidelity.controllerDispatcher";
        var mapping = Controller.newMapping(MAPPING_NAME);
        mapping.from([controllerStandard.RT]).peek().to(_this.rightTriggerPress);
        mapping.from([controllerStandard.RTClick]).peek().to(_this.rightTriggerClick);
        mapping.from([controllerStandard.LT]).peek().to(_this.leftTriggerPress);
        mapping.from([controllerStandard.LTClick]).peek().to(_this.leftTriggerClick);

        mapping.from([controllerStandard.RB]).peek().to(_this.rightSecondaryPress);
        mapping.from([controllerStandard.LB]).peek().to(_this.leftSecondaryPress);
        mapping.from([controllerStandard.LeftGrip]).peek().to(_this.leftSecondaryPress);
        mapping.from([controllerStandard.RightGrip]).peek().to(_this.rightSecondaryPress);

        Controller.enableMapping(MAPPING_NAME);

        this.leftPointer = this.pointerManager.createPointer(false, PickType.Ray, {
            joint: "_CAMERA_RELATIVE_CONTROLLER_LEFTHAND",
            maxDistance: picoLazyHandRays ? 20.0 : DEFAULT_SEARCH_SPHERE_DISTANCE,
            filter: Picks.PICK_OVERLAYS | Picks.PICK_LOCAL_ENTITIES | Picks.PICK_ENTITIES |
                Picks.PICK_INCLUDE_NONCOLLIDABLE |
                (Settings.getValue("combineHudAndWorldPointers", false) ? Picks.PICK_HUD : 0),
            triggers: [
                {action: controllerStandard.LTClick, button: "Primary"},
                {action: controllerStandard.LX, button: "ScrollX"},
                {action: controllerStandard.LY, button: "ScrollY"},
            ],
            posOffset: getGrabPointSphereOffset(controllerStandard.LeftHand, true),
            hover: true,
            scaleWithParent: true,
            distanceScaleEnd: true,
            hand: LEFT_HAND,
            delay: 0
        });
        Keyboard.setLeftHandLaser(this.leftPointer);
        this.rightPointer = this.pointerManager.createPointer(false, PickType.Ray, {
            joint: "_CAMERA_RELATIVE_CONTROLLER_RIGHTHAND",
            maxDistance: picoLazyHandRays ? 20.0 : DEFAULT_SEARCH_SPHERE_DISTANCE,
            filter: Picks.PICK_OVERLAYS | Picks.PICK_LOCAL_ENTITIES | Picks.PICK_ENTITIES |
                Picks.PICK_INCLUDE_NONCOLLIDABLE |
                (Settings.getValue("combineHudAndWorldPointers", false) ? Picks.PICK_HUD : 0),
            triggers: [
                {action: controllerStandard.RTClick, button: "Primary"},
                {action: controllerStandard.RX, button: "ScrollX"},
                {action: controllerStandard.RY, button: "ScrollY"},
            ],
            posOffset: getGrabPointSphereOffset(controllerStandard.RightHand, true),
            hover: true,
            scaleWithParent: true,
            distanceScaleEnd: true,
            hand: RIGHT_HAND,
            delay: 0
        });
        Keyboard.setRightHandLaser(this.rightPointer);
        this.leftHudPointer = Settings.getValue("combineHudAndWorldPointers", false) ? this.leftPointer :
            this.pointerManager.createPointer(true, PickType.Ray, {
            joint: "_CAMERA_RELATIVE_CONTROLLER_LEFTHAND",
            filter: Picks.PICK_HUD,
            maxDistance: DEFAULT_SEARCH_SPHERE_DISTANCE,
            posOffset: getGrabPointSphereOffset(controllerStandard.LeftHand, true),
            triggers: [
                {action: controllerStandard.LTClick, button: "Primary"},
                {action: controllerStandard.LT, button: "ScrollActive"},
                {action: controllerStandard.LX, button: "ScrollX"},
                {action: controllerStandard.LY, button: "ScrollY"},
            ],
            hover: true,
            scaleWithParent: true,
            distanceScaleEnd: true,
            hand: LEFT_HAND,
            delay: 0
        });
        this.rightHudPointer = Settings.getValue("combineHudAndWorldPointers", false) ? this.rightPointer :
            this.pointerManager.createPointer(true, PickType.Ray, {
            joint: "_CAMERA_RELATIVE_CONTROLLER_RIGHTHAND",
            filter: Picks.PICK_HUD,
            maxDistance: DEFAULT_SEARCH_SPHERE_DISTANCE,
            posOffset: getGrabPointSphereOffset(controllerStandard.RightHand, true),
            triggers: [
                {action: controllerStandard.RTClick, button: "Primary"},
                {action: controllerStandard.RT, button: "ScrollActive"},
                {action: controllerStandard.RX, button: "ScrollX"},
                {action: controllerStandard.RY, button: "ScrollY"},
            ],
            hover: true,
            scaleWithParent: true,
            distanceScaleEnd: true,
            hand: RIGHT_HAND,
            delay: 0
        });

        this.mouseRayPointer = Pointers.createRayPointer({
            joint: "Mouse",
            maxDistance: picoLazyHandRays ? 20.0 : 0.0,
            filter: Picks.PICK_OVERLAYS | Picks.PICK_LOCAL_ENTITIES | Picks.PICK_ENTITIES |
                Picks.PICK_INCLUDE_NONCOLLIDABLE | (picoLazyHandRays ? Picks.PICK_COARSE : 0),
            enabled: true
        });
        this.handleMessage = function (channel, data, sender) {
            var message;
            if (sender === MyAvatar.sessionUUID) {
                try {
                    if (channel === 'Hifi-Hand-RayPick-Blocklist') {
                        message = JSON.parse(data);
                        var action = message.action;
                        var id = message.id;
                        var index = _this.blocklist.indexOf(id);

                        if (action === 'add' && index === -1) {
                            _this.blocklist.push(id);
                            _this.setBlocklist();
                        }

                        if (action === 'remove') {
                            if (index > -1) {
                                _this.blocklist.splice(index, 1);
                                _this.setBlocklist();
                            }
                        }

                        if (action === "tablet") {
                            var tabletIDs = message.blocklist ?
                                [HMD.tabletID, HMD.tabletScreenID, HMD.homeButtonID, HMD.homeButtonHighlightID] :
                                [];
                            if (message.hand === LEFT_HAND) {
                                _this.leftBlocklistTabletIDs = tabletIDs;
                                _this.setLeftBlocklist();
                            } else {
                                _this.rightBlocklistTabletIDs = tabletIDs;
                                _this.setRightBlocklist();
                            }
                        }
                    } else if (channel === "Hifi-InEdit-Status") {
                        message = JSON.parse(data);
                        if (message.method === "editing") {
                            _this.picoEditingHand = message.editing ? message.hand : null;
                        }
                    }
                } catch (e) {
                    print("WARNING: handControllerGrab.js -- error parsing message: " + data);
                }
            }
        };

        this.handLaserDelayChanged = function (delay) {
            Pointers.setDelay(_this.leftPointer, delay);
            Pointers.setDelay(_this.rightPointer, delay);
            Pointers.setDelay(_this.leftHudPointer, delay);
            Pointers.setDelay(_this.rightHudPointer, delay);
        };

        this.cleanup = function () {
            Controller.disableMapping(MAPPING_NAME);
            _this.pointerManager.removePointers();
            Pointers.removePointer(this.mouseRayPointer);
            Entities.mouseReleaseOnEntity.disconnect(mouseReleaseOn);
            Entities.mousePressOnEntity.disconnect(mousePress);
            Messages.messageReceived.disconnect(controllerDispatcher.handleMessage);
            if (_this.debugPanelID) {
                Entities.deleteEntity(_this.debugPanelID);
                _this.debugPanelID = null;
            }
        };

        if (DEBUG) {
            this.debugPanelID = Entities.addEntity({
                "name": "controllerDispatcher debug panel",
                "type": "Text",
                "dimensions": { "x": 1.0, "y": 0.3, "z": 0.01 },
                "parentID": MyAvatar.sessionUUID,
                // parentJointIndex: MyAvatar.getJointIndex("_CAMERA_MATRIX"),
                "parentJointIndex": -1,
                "localPosition": { "x": -0.25, "y": 0.8, "z": -1.2 },
                "textColor": { "red": 255, "green": 255, "blue": 255},
                "backgroundColor": { "red": 0, "green": 0, "blue": 0},
                "text": "",
                "lineHeight": 0.03,
                "leftMargin": 0.015,
                "topMargin": 0.01,
                "backgroundAlpha": 0.7,
                "textAlpha": 1.0,
                "unlit": true,
                "ignorePickIntersection": true
            }, "local");
        }
    }

    function mouseReleaseOn(id, event) {
        if (HMD.homeButtonID && id === HMD.homeButtonID && event.button === "Primary") {
            Messages.sendLocalMessage("home", id);
        }
    }

    var HAPTIC_STYLUS_STRENGTH = 1.0;
    var HAPTIC_STYLUS_DURATION = 20.0;
    function mousePress(id, event) {
        if (HMD.active) {
            var runningPlugins = controllerDispatcher.runningPluginNames;
            if (event.id === controllerDispatcher.leftPointer && event.button === "Primary" && runningPlugins.LeftWebSurfaceLaserInput) {
                Controller.triggerHapticPulse(HAPTIC_STYLUS_STRENGTH, HAPTIC_STYLUS_DURATION, LEFT_HAND);
            } else if (event.id === controllerDispatcher.rightPointer && event.button === "Primary" && runningPlugins.RightWebSurfaceLaserInput) {
                Controller.triggerHapticPulse(HAPTIC_STYLUS_STRENGTH, HAPTIC_STYLUS_DURATION, RIGHT_HAND);
            }
        }
    }

    Entities.mouseReleaseOnEntity.connect(mouseReleaseOn);
    Entities.mousePressOnEntity.connect(mousePress);

    var controllerDispatcher = new ControllerDispatcher();
    Messages.subscribe('Hifi-Hand-RayPick-Blocklist');
    Messages.subscribe("Hifi-InEdit-Status");
    Messages.messageReceived.connect(controllerDispatcher.handleMessage);

    Picks.handLaserDelayChanged.connect(controllerDispatcher.handLaserDelayChanged);

    Script.scriptEnding.connect(function () {
        controllerDispatcher.cleanup();
    });
    Script.setTimeout(controllerDispatcher.update, BASIC_TIMER_INTERVAL_MS);
}());
