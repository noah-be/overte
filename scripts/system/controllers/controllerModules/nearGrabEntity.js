"use strict";

//  nearGrabEntity.js
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html


/* global Script, Entities, MyAvatar, Controller, RIGHT_HAND, LEFT_HAND, getControllerJointIndex, enableDispatcherModule,
   disableDispatcherModule, Messages, HAPTIC_PULSE_STRENGTH, HAPTIC_PULSE_DURATION, TRIGGER_OFF_VALUE,
   makeDispatcherModuleParameters, entityIsGrabbable, makeRunningValues, NEAR_GRAB_RADIUS, findGrabbableGroupParent, Vec3,
   cloneEntity, entityIsCloneable, HAPTIC_PULSE_STRENGTH, HAPTIC_PULSE_DURATION, BUMPER_ON_VALUE,
   distanceBetweenPointAndEntityBoundingBox, getGrabbableData, getEnabledModuleByName, DISPATCHER_PROPERTIES, HMD,
   NEAR_GRAB_DISTANCE, console, Settings, PICO_TRIGGER_OFF_VALUE, PICO_GRIP_ON_VALUE, PICO_GRIP_OFF_VALUE
*/

Script.include("/~/system/libraries/controllerDispatcherUtils.js");
Script.include("/~/system/libraries/cloneEntityUtils.js");
Script.include("/~/system/libraries/controllers.js");

(function() {

    var PICO_TRACE_CHANNEL = "Pico4-Interaction-Diagnostics";
    var picoTraceEnabled = false;
    var picoInteractionThresholds = Settings.getValue("deferTabletCreationUntilOpen", false);

    function traceNearGrab(event, hand, details) {
        if (!picoTraceEnabled) {
            return;
        }
        details = details || {};
        details.event = event;
        details.time = Date.now();
        details.hand = hand === RIGHT_HAND ? "right" : "left";
        console.info("PICO4_NEAR_GRAB " + JSON.stringify(details));
    }

    function handleTraceMessage(channel, message, senderID, localOnly) {
        if (channel === PICO_TRACE_CHANNEL && localOnly) {
            picoTraceEnabled = message === "enable" || message === "edges";
        }
    }

    Messages.subscribe(PICO_TRACE_CHANNEL);
    Messages.messageReceived.connect(handleTraceMessage);

    function NearGrabEntity(hand) {
        this.hand = hand;
        this.targetEntityID = null;
        this.grabbing = false;
        this.cloneAllowed = true;
        this.grabID = null;

        this.parameters = makeDispatcherModuleParameters(
            500,
            this.hand === RIGHT_HAND ? ["rightHand"] : ["leftHand"],
            [],
            100);

        this.startGrab = function (targetProps) {
            if (this.grabID) {
                MyAvatar.releaseGrab(this.grabID);
            }

            var grabData = getGrabbableData(targetProps);

            var handJointIndex;
            if (HMD.mounted && HMD.isHandControllerAvailable() && grabData.grabFollowsController) {
                handJointIndex = getControllerJointIndex(this.hand);
            } else {
                handJointIndex = MyAvatar.getJointIndex(this.hand === RIGHT_HAND ? "RightHand" : "LeftHand");
            }

            this.targetEntityID = targetProps.id;

            traceNearGrab("my-avatar-grab-call", this.hand, {
                entity: targetProps.id,
                joint: handJointIndex
            });

            var relativePosition = Entities.worldToLocalPosition(targetProps.position, MyAvatar.SELF_ID, handJointIndex);
            var relativeRotation = Entities.worldToLocalRotation(targetProps.rotation, MyAvatar.SELF_ID, handJointIndex);
            this.grabID = MyAvatar.grab(targetProps.id, handJointIndex, relativePosition, relativeRotation);
            traceNearGrab("my-avatar-grab-return", this.hand, {
                entity: targetProps.id,
                grab: this.grabID
            });
        };

        this.startNearGrabEntity = function (targetProps) {
            Controller.triggerHapticPulse(HAPTIC_PULSE_STRENGTH, HAPTIC_PULSE_DURATION, this.hand);

            this.startGrab(targetProps);

            var args = [this.hand === RIGHT_HAND ? "right" : "left", MyAvatar.sessionUUID];
            Entities.callEntityMethod(targetProps.id, "startNearGrab", args);

            Messages.sendMessage('Hifi-Object-Manipulation', JSON.stringify({
                action: 'grab',
                grabbedEntity: targetProps.id,
                joint: this.hand === RIGHT_HAND ? "RightHand" : "LeftHand"
            }));

            this.grabbing = true;
        };

        this.endGrab = function () {
            if (this.grabID) {
                traceNearGrab("my-avatar-release-call", this.hand, {
                    entity: this.targetEntityID,
                    grab: this.grabID
                });
                MyAvatar.releaseGrab(this.grabID);
                traceNearGrab("my-avatar-release-return", this.hand, {
                    entity: this.targetEntityID,
                    grab: this.grabID
                });
                this.grabID = null;
            }
        };

        this.endNearGrabEntity = function () {
            this.endGrab();

            var args = [this.hand === RIGHT_HAND ? "right" : "left", MyAvatar.sessionUUID];
            Entities.callEntityMethod(this.targetEntityID, "releaseGrab", args);
            Messages.sendMessage('Hifi-Object-Manipulation', JSON.stringify({
                action: 'release',
                grabbedEntity: this.targetEntityID,
                joint: this.hand === RIGHT_HAND ? "RightHand" : "LeftHand"
            }));

            this.grabbing = false;
            this.targetEntityID = null;
        };

        this.getTargetProps = function (controllerData) {
            // nearbyEntityProperties is already sorted by length from controller
            var nearbyEntityProperties = controllerData.nearbyEntityProperties[this.hand];
            var sensorScaleFactor = MyAvatar.sensorToWorldScale;
            var nearGrabDistance = NEAR_GRAB_DISTANCE * sensorScaleFactor;
            var nearGrabRadius = NEAR_GRAB_RADIUS * sensorScaleFactor;
            for (var i = 0; i < nearbyEntityProperties.length; i++) {
                var props = nearbyEntityProperties[i];
                var grabPosition = controllerData.controllerLocations[this.hand].position; // Is offset from hand position.
                // TODO: this function gives incorrect result now and needs to be fixed later
                //var dist = distanceBetweenPointAndEntityBoundingBox(grabPosition, props);
                var dist = 0;
                var distance = Vec3.distance(grabPosition, props.position);
                if ((dist > nearGrabDistance) ||
                    (distance > nearGrabRadius)) { // Only smallish entities can be near grabbed.
                    continue;
                }
                if (entityIsGrabbable(props) || entityIsCloneable(props)) {
                    if (!entityIsCloneable(props)) {
                        // if we've attempted to grab a non-cloneable child, roll up to the root of the tree
                        var groupRootProps = findGrabbableGroupParent(controllerData, props);
                        if (entityIsGrabbable(groupRootProps)) {
                            return groupRootProps;
                        }
                    }
                    return props;
                }
            }
            return null;
        };

        this.isReady = function (controllerData, deltaTime) {
            this.targetEntityID = null;
            this.grabbing = false;

            var triggerOffValue = picoInteractionThresholds ? PICO_TRIGGER_OFF_VALUE : TRIGGER_OFF_VALUE;
            var gripOffValue = picoInteractionThresholds ? PICO_GRIP_OFF_VALUE : TRIGGER_OFF_VALUE;
            if (controllerData.triggerValues[this.hand] < triggerOffValue &&
                controllerData.secondaryValues[this.hand] < gripOffValue) {
                this.cloneAllowed = true;
                return makeRunningValues(false, [], []);
            }

            var scaleModuleName = this.hand === RIGHT_HAND ? "RightScaleEntity" : "LeftScaleEntity";
            var scaleModule = getEnabledModuleByName(scaleModuleName);
            if (scaleModule && (scaleModule.grabbedThingID || scaleModule.isReady(controllerData).active)) {
                // we're rescaling -- don't start a grab.
                return makeRunningValues(false, [], []);
            }

            var targetProps = this.getTargetProps(controllerData);
            if (targetProps) {
                this.targetEntityID = targetProps.id;
                return makeRunningValues(true, [this.targetEntityID], []);
            } else {
                return makeRunningValues(false, [], []);
            }
        };

        this.run = function (controllerData, deltaTime) {
            var gripOffValue = picoInteractionThresholds ? PICO_GRIP_OFF_VALUE : TRIGGER_OFF_VALUE;

            if (this.grabbing) {
                if (!controllerData.triggerClicks[this.hand] &&
                    controllerData.secondaryValues[this.hand] < gripOffValue) {
                    this.endNearGrabEntity();
                    return makeRunningValues(false, [], []);
                }

                var props = controllerData.nearbyEntityPropertiesByID[this.targetEntityID];
                if (!props) {
                    props = Entities.getEntityProperties(this.targetEntityID, "type");
                    if (!props) {
                        // entity was deleted
                        this.grabbing = false;
                        this.targetEntityID = null;
                        return makeRunningValues(false, [], []);
                    }
                }

                var args = [this.hand === RIGHT_HAND ? "right" : "left", MyAvatar.sessionUUID];
                Entities.callEntityMethod(this.targetEntityID, "continueNearGrab", args);
            } else {
                // still searching
                var readiness = this.isReady(controllerData);
                if (!readiness.active) {
                    return readiness;
                }
                var gripOnValue = picoInteractionThresholds ? PICO_GRIP_ON_VALUE : BUMPER_ON_VALUE;
                if (controllerData.triggerClicks[this.hand] ||
                        controllerData.secondaryValues[this.hand] > gripOnValue) {
                    // switch to grab
                    var targetProps = this.getTargetProps(controllerData);
                    traceNearGrab("dispatcher-start", this.hand, {
                        entity: targetProps ? targetProps.id : null,
                        triggerClick: controllerData.triggerClicks[this.hand],
                        grip: controllerData.secondaryValues[this.hand]
                    });
                    var targetCloneable = entityIsCloneable(targetProps);

                    if (targetCloneable) {
                        if (this.cloneAllowed) {
                            var cloneID = cloneEntity(targetProps);
                            if (cloneID !== null) {
                                var cloneProps = Entities.getEntityProperties(cloneID, DISPATCHER_PROPERTIES);
                                cloneProps.id = cloneID;
                                this.grabbing = true;
                                this.targetEntityID = cloneID;
                                this.startNearGrabEntity(cloneProps);
                                this.cloneAllowed = false; // prevent another clone call until inputs released
                            }
                        }
                    } else if (targetProps) {
                        this.grabbing = true;
                        this.startNearGrabEntity(targetProps);
                    }
                }
            }

            return makeRunningValues(true, [this.targetEntityID], []);
        };

        this.releaseOnPicoInput = function () {
            if (!this.grabbing || !this.targetEntityID) {
                return false;
            }
            this.endNearGrabEntity();
            return true;
        };

        this.cleanup = function () {
            if (this.targetEntityID) {
                this.endNearGrabEntity();
            }
        };
    }

    var leftNearGrabEntity = new NearGrabEntity(LEFT_HAND);
    var rightNearGrabEntity = new NearGrabEntity(RIGHT_HAND);

    enableDispatcherModule("LeftNearGrabEntity", leftNearGrabEntity);
    enableDispatcherModule("RightNearGrabEntity", rightNearGrabEntity);

    function cleanup() {
        leftNearGrabEntity.cleanup();
        rightNearGrabEntity.cleanup();
        disableDispatcherModule("LeftNearGrabEntity");
        disableDispatcherModule("RightNearGrabEntity");
        Messages.messageReceived.disconnect(handleTraceMessage);
        Messages.unsubscribe(PICO_TRACE_CHANNEL);
    }
    Script.scriptEnding.connect(cleanup);
}());
