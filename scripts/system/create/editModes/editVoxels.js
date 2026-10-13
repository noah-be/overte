//
//  editModes.js
//
//  Created by dr Karol Suprynowicz on 2022.05.17.
//  Copyright 2022 Overte e.V.
//
//  Based on voxels.js
//  Created by Seth Alves on 2015-08-25
//  Copyright 2015 High Fidelity, Inc.
//
//  Based on entitySelectionTool.js
//  Created by Brad hefta-Gaub on 10/1/14.
//    Modified by Daniela Fontes * @DanielaFifo and Tiago Andrade @TagoWill on 4/7/2017
//    Modified by David Back on 1/9/2018
//  Copyright 2014 High Fidelity, Inc.
//  Copyright 2020 Vircadia contributors
//
//  This script implements voxel edit mode
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

Script.include([
    "../../libraries/utils.js",
    "../entitySelectionTool/entitySelectionTool.js"
]);

var selectionManager = SelectionManager;


EditVoxels = function() {
    var self = this;
    var that = {};

    const NO_HAND = -1;
    var controllerStandard = Controller.Standard;

    var controlHeld = false;
    var shiftHeld = false;
    var isLeftGripPressed = false;
    var isRightGripPressed = false;

    var editEnabled = false;
    var editSingleVoxels = false;
    var editSpheres = false;
    var editCubes = false;
    var continuousEditing = false;
    var editAdd = true; // Remove voxels if false
    var inverseOperation = false; // True when middle mouse button or grip is pressed
    var brushPointer = false;
    var isActive = true;
    
    var editSphereRadius = 0.15;
    var brushLength = 0.5;
    // Vector calculated from editSphereRadius for adding/remiving cubes
    var cubeSize = null;
    
    // Local plane for continuous voxel editing
    // 0 - plane parallel to YZ plane
    // 1 - plane parallel to XZ plane
    // 2 - plane parallel to YZ plane
    var editPlane = 0;
    // Is true when mouse button is pressed
    var isEditing = false;
    var editedVoxelEntity = null;
    // Position of last edit in voxel space
    var oldEditPosition = null;
    // True when original operation added voxels, false otherwise
    var lastEditValue = 255;
    var isOnUpdateConnected = false;
    var isSphereResizingStarted = false;
    var sphereResizingInitialHandDistance = 0.1;
    var sphereInitialRadius = editSphereRadius;
    var sphereEntityID = null;
    var stroke = {};
    var strokeTimer = null;
    var strokePolls = 0;

    that.triggerClickMapping = Controller.newMapping(Script.resolvePath('') + '-click-voxels');
    that.triggerPressMapping = Controller.newMapping(Script.resolvePath('') + '-press-voxels');
    that.gripPressMapping = Controller.newMapping(Script.resolvePath('') + '-grip-voxels');
    that.triggeredHand = NO_HAND;
    that.pressedHand = NO_HAND;
    
    var soundAdd = SoundCache.getSound(Script.resourcesPath() + "sounds/Button05.wav");
    var soundDelete = SoundCache.getSound(Script.resourcesPath() + "sounds/Tab03.wav");
    
    // Continuous start timer prevents activating continuous mode on short button presses
    // and adding multiple voxels when only one was intended
    
    var continuousStartTimerMax = 0.200;
    var continuousStartTimer = 0.0;
    
    that.setActive = function(active) {
        isActive = (active === true);
        if (!isActive) {
            mouseReleaseEvent({});
            stopSphereResizing();
            that.triggeredHand = that.pressedHand = NO_HAND;
            that.disableTriggerMapping();
        } else { that.enableTriggerMapping(); }
    }
    that.isStrokePending = function() { return Object.keys(stroke).length > 0; };
    that.getLocalEntityToExclude = function() { return sphereEntityID ? [sphereEntityID] : []; };

    function editable(properties) {
        if (properties.type !== "PolyVox" || properties.locked) { return false; }
        if (properties.avatarEntity || properties.entityHostType === "avatar") {
            return Entities.canRezAvatarEntities()
                && (properties.owningAvatarID === MyAvatar.sessionUUID || properties.owningAvatarID === MyAvatar.SELF_ID);
        }
        return properties.entityHostType === "local" || Entities.canRez() || Entities.canRezTmp();
    }

    function rememberChange(id, before, changed) {
        if (!changed) { return false; }
        if (!stroke[id]) { stroke[id] = before; }
        strokePolls = 0;
        return true;
    }

    // Readiness comes from the renderer's locked state, never elapsed time or
    // unchanged compressed bytes: workers can publish an intermediate result.
    function settleStroke() {
        if (isEditing) { return; }
        var ids = Object.keys(stroke);
        if (!ids.length) { return; }
        strokePolls++;
        var supported = typeof Entities.isVoxelDataReady === "function";
        var ready = supported && ids.every(function(id) { return Entities.isVoxelDataReady(id); });
        var after = ready ? ids.map(function(id) { return Entities.getEntityProperties(id); }) : [];
        ready = ready && after.every(function(properties, index) {
            return properties.type === "PolyVox" && Entities.isVoxelDataReady(ids[index]);
        });
        var completed = null;
        if (ready) {
            completed = ids.map(function(id, index) { return { entityID: id, before: stroke[id], after: after[index] }; })
                .filter(function(edit) { return edit.before.voxelData !== edit.after.voxelData; });
        } else if (supported && strokePolls < 50) { return; }
        else if (typeof that.onStrokeStatus === "function") {
            that.onStrokeStatus("Voxel changes did not settle; undo is unavailable for this stroke.", true);
        }
        stroke = {};
        Script.clearInterval(strokeTimer);
        strokeTimer = null;
        if (completed && completed.length && selectionManager.createApp && selectionManager.createApp.pushVoxelStroke) {
            selectionManager.createApp.pushVoxelStroke(completed);
        } else if (completed && typeof that.onStrokeStatus === "function") {
            that.onStrokeStatus("Voxel stroke did not change saved data.", false);
        }
        if (typeof that.onStrokeSettled === "function") { that.onStrokeSettled(); }
    }
    
    that.updateEditSettings = function(data) {
        
        if (data.createAppMode) {
            if (data.createAppMode === "voxel"){
                editEnabled = true;
            } else {
                editEnabled = false;
                mouseReleaseEvent({});
                stopSphereResizing();
            }
        }
        
        if (data.voxelEditMode) {
            if (data.voxelEditMode === "single") {
                editSpheres = false;
                editSingleVoxels = true;
                editCubes = false;
            } else if (data.voxelEditMode === "sphere") {
                editSpheres = true;
                editSingleVoxels = false;
                editCubes = false;
            } else if (data.voxelEditMode === "cube") {
                editSpheres = false;
                editSingleVoxels = false;
                editCubes = true;
            }
        }
        if (data.voxelRemove !== undefined) { editAdd = !data.voxelRemove; }
        if (data.voxelEditDynamics !== undefined) { continuousEditing = data.voxelEditDynamics === "continuous"; }
        
        if (data.voxelSphereSize) {
            editSphereRadius = parseFloat(data.voxelSphereSize) / 2.0;
        }
        
        if (data.voxelPointerMode) {
            if (data.voxelPointerMode === "brush") {
                brushPointer = true;
            } else {
                brushPointer = false;
            }
        }
        
        if (data.voxelBrushLength !== undefined) {
            brushLength = parseFloat(data.voxelBrushLength);
        }
        
    }

    function floorVector(v) {
        return {
            x: Math.floor(v.x),
            y: Math.floor(v.y),
            z: Math.floor(v.z)
        };
    }
    
    function ceilVector(v) {
        return {
            x: Math.ceil(v.x),
            y: Math.ceil(v.y),
            z: Math.ceil(v.z)
        };
    }

    function attemptVoxelChangeForEntity(entityID, pickRayDir, intersectionLocation) {
        var wantDebug = false;
        if (wantDebug) {
            print("=============== eV::attemptVoxelChangeForEntity BEG =======================");
        }

        if (!stroke[entityID] && typeof Entities.isVoxelDataReady === "function"
                && !Entities.isVoxelDataReady(entityID)) { return false; }
        var properties = Entities.getEntityProperties(entityID);
        if (!editable(properties) || (!stroke[entityID] && typeof Entities.isVoxelDataReady === "function"
                && !Entities.isVoxelDataReady(entityID))) {
            return false;
        }
        
        if (!editEnabled || !isActive) {
            return false;
        }

        if (editSingleVoxels === false && editSpheres === false && editCubes === false) {
            return false;
        }

        var voxelOrigin = Entities.worldCoordsToVoxelCoords(entityID, Vec3.subtract(intersectionLocation, pickRayDir));
        var voxelPosition = Entities.worldCoordsToVoxelCoords(entityID, intersectionLocation);
        var pickRayDirInVoxelSpace = Vec3.subtract(voxelPosition, voxelOrigin);
        pickRayDirInVoxelSpace = Vec3.normalize(pickRayDirInVoxelSpace);
        
        var absX = Math.abs(pickRayDirInVoxelSpace.x);
        var absY = Math.abs(pickRayDirInVoxelSpace.y);
        var absZ = Math.abs(pickRayDirInVoxelSpace.z);
        if(absX >= absY && absX >= absZ){
            editPlane = 0;
        }else if(absY >= absX && absY >= absZ){
            editPlane = 1;
        }else if(absZ >= absX && absZ >= absY){
            editPlane = 2;
        }

        if (wantDebug) {
            print("voxelOrigin: " + JSON.stringify(voxelOrigin));
            print("voxelPosition: " + JSON.stringify(voxelPosition));
            print("pickRayDirInVoxelSpace: " + JSON.stringify(pickRayDirInVoxelSpace));
        }
        
        lastEditValue = 0;
        if((editAdd && !inverseOperation) || (!editAdd && inverseOperation)){
            lastEditValue = 255;
        }

        var toDrawPosition = null;

        if(lastEditValue === 255){
            toDrawPosition = Vec3.subtract(voxelPosition, Vec3.multiply(pickRayDirInVoxelSpace, 0.1));
        }else{
            toDrawPosition = Vec3.subtract(voxelPosition, Vec3.multiply(pickRayDirInVoxelSpace, -0.1));
        }

        if (editSingleVoxels) {
            if (wantDebug) {
                print("Calling setVoxel");
                print("entityID: " + JSON.stringify(entityID));
                print("floorVector(toDrawPosition): " + JSON.stringify(floorVector(toDrawPosition)));
            }
            oldEditPosition = floorVector(toDrawPosition);
            if (rememberChange(entityID, properties, Entities.setVoxel(entityID, oldEditPosition, lastEditValue))){
                Audio.playSystemSound((lastEditValue === 255) ? soundAdd : soundDelete);
                return true;
            }else{
                return false;
            }
        }
        if (editSpheres) {
            if (wantDebug) {
                print("Calling setVoxelSphere");
                print("entityID: " + JSON.stringify(entityID));
                print("editSphereRadius: " + JSON.stringify(editSphereRadius));
                print("floorVector(toDrawPosition): " + JSON.stringify(floorVector(toDrawPosition)));
            }
            oldEditPosition = floorVector(toDrawPosition);
            var toDrawPositionWorld = Entities.voxelCoordsToWorldCoords(entityID, oldEditPosition);
            if (rememberChange(entityID, properties, Entities.setVoxelSphere(entityID, toDrawPositionWorld, editSphereRadius, lastEditValue))){
                Audio.playSystemSound((lastEditValue === 255) ? soundAdd : soundDelete);
                return true;
            }else{
                return false;
            }
        }
        if (editCubes) {
            if (wantDebug) {
                print("Calling setVoxelsInCuboid");
                print("entityID: " + JSON.stringify(entityID));
                print("editSphereRadius: " + JSON.stringify(editSphereRadius));
                print("floorVector(toDrawPosition): " + JSON.stringify(floorVector(toDrawPosition)));
            }
            oldEditPosition = floorVector(toDrawPosition);
            var cubeSizeWorld = {x : editSphereRadius * 2, y : editSphereRadius * 2, z : editSphereRadius * 2};
            var zeroVecWorld = {x : 0, y: 0, z: 0};
            var zeroVecLocal = Entities.worldCoordsToVoxelCoords(entityID, zeroVecWorld);
            var cubeSizeVecLocal = Entities.worldCoordsToVoxelCoords(entityID, cubeSizeWorld);
            cubeSize = ceilVector(Vec3.subtract(cubeSizeVecLocal, zeroVecLocal));
            var lowPosition = Vec3.subtract(oldEditPosition, Vec3.multiply(cubeSize, 0.5));
            if (rememberChange(entityID, properties, Entities.setVoxelsInCuboid(entityID, lowPosition, cubeSize, lastEditValue))){
                Audio.playSystemSound((lastEditValue === 255) ? soundAdd : soundDelete);
                return true;
            }else{
                return false;
            }
        }
    }

    function attemptVoxelChange(pickRayDir, intersection) {
        var wantDebug = false;
        if (wantDebug) {
            print("=============== eV::attemptVoxelChange BEG =======================");
        }

        var ids;

        ids = Entities.findEntities(intersection.intersection, editSphereRadius + 1.0);
        if (ids.indexOf(intersection.entityID) < 0) {
            ids.push(intersection.entityID);
        }

        if (wantDebug) {
            print("Entities: " + JSON.stringify(ids));
        }

        var success = false;
        for (var i = 0; i < ids.length; i++) {
            var entityID = ids[i];
            success |= attemptVoxelChangeForEntity(entityID, pickRayDir, intersection.intersection)
        }
        return success;
    }
    
    function controllerComputePickRay() {
        var hand = triggered() ? that.triggeredHand : that.pressedHand;
        var controllerPose = getControllerWorldLocation(hand, true);
        if (controllerPose.valid) {
            var controllerPosition = controllerPose.translation;
            // This gets point direction right, but if you want general quaternion it would be more complicated:
            var controllerDirection = Quat.getUp(controllerPose.rotation);
            return {origin: controllerPosition, direction: controllerDirection};
        }
    }

    function generalComputePickRay(x, y) {
        return controllerComputePickRay() || Camera.computePickRay(x, y);
    }
    function brushChange(pickRay) {
        var point = Vec3.sum(pickRay.origin, Vec3.multiply(pickRay.direction, brushLength));
        var ids = Entities.findEntities(point, editSphereRadius + 1.0);
        var changed = false;
        ids.forEach(function(id) {
            changed = attemptVoxelChangeForEntity(id, pickRay.direction, point) || changed;
        });
        return changed;
    }

    function pointingAtUI(hand) {
        var left = selectionManager.pointingAtTabletLeft || selectionManager.pointingAtDesktopWindowLeft;
        var right = selectionManager.pointingAtTabletRight || selectionManager.pointingAtDesktopWindowRight;
        return (hand === controllerStandard.LeftHand && left)
            || (hand === controllerStandard.RightHand && right) || (hand === NO_HAND && (left || right));
    }

    function mousePressEvent(event) {
        var wantDebug = false;
        var attemptChangeOnEmpty = false;
        if (!editEnabled || !isActive) {
            return false;
        }
        var hand = triggered() ? that.triggeredHand : that.pressedHand;
        if (pointingAtUI(hand)) { return; }

        if (wantDebug) {
            print("=============== eV::mousePressEvent BEG =======================");
        }

        if (!(event.isLeftButton || event.isMiddleButton) && !triggered()) {
            return;
        }
        
        if (event.isLeftButton || event.isMiddleButton){
            if (event.isMiddleButton){
                inverseOperation = true;
            }else{
                inverseOperation = false;
            }
        }else{
            inverseOperation = false;
            if(that.triggeredHand === controllerStandard.RightHand && Controller.getValue(controllerStandard.RightGrip) > 0.5){
                inverseOperation = true;
            }
            if(that.triggeredHand === controllerStandard.LeftHand && Controller.getValue(controllerStandard.LeftGrip) > 0.5){
                inverseOperation = true;
            }
        }

        continuousStartTimer = 0;

        var pickRay = generalComputePickRay(event.x, event.y);
        if (!pickRay) { return; }
        if (brushPointer && hand !== NO_HAND) {
            if (brushChange(pickRay)) {
                isEditing = true;
                if (continuousEditing) { Script.update.connect(onUpdateHandler); isOnUpdateConnected = true; }
            }
            return;
        }
        var intersection = Entities.findRayIntersection(pickRay, Picks.PICK_DOMAIN_ENTITIES | Picks.PICK_AVATAR_ENTITIES | Picks.PICK_LOCAL_ENTITIES); // accurate picking

        if (wantDebug) {
            print("Pick ray: " + JSON.stringify(pickRay));
            print("Intersection: " + JSON.stringify(intersection));
        }

        if (intersection.intersects) {
            if (attemptVoxelChangeForEntity(intersection.entityID, pickRay.direction, intersection.intersection)) {
                if (continuousEditing) { Script.update.connect(onUpdateHandler); isOnUpdateConnected = true; }
                isEditing = true;
                editedVoxelEntity = intersection.entityID;
                if (wantDebug) {
                    print("onUpdateHandler connected");
                }
                return;
            }
        }

        // if the PolyVox entity is empty, we can't pick against its "on" voxels.  try picking against its
        // bounding box, instead.
        if (attemptChangeOnEmpty) {
            intersection = Entities.findRayIntersection(pickRay, false); // bounding box picking
            if (intersection.intersects) {
                if(attemptVoxelChange(pickRay.direction, intersection)){
                    Script.update.connect(onUpdateHandler);
                    isOnUpdateConnected = true;
                    if (wantDebug) {
                        print("onUpdateHandler connected");
                    }
                }
            }
        }
    }

    function mouseReleaseEvent(event) {
        var wantDebug = false;

        if (wantDebug) {
            print("=============== eV::mouseReleaseEvent BEG =======================");
        }
        if(isOnUpdateConnected){
            Script.update.disconnect(onUpdateHandler);
            isOnUpdateConnected = false;
        }
        isEditing = false;
        editedVoxelEntity = null;
        if (Object.keys(stroke).length && strokeTimer === null) { strokeTimer = Script.setInterval(settleStroke, 100); }
        return;
    }

    function keyPressEvent(event) {
        if (event.text == "CONTROL") {
            controlHeld = true;
        }
        if (event.text == "SHIFT") {
            shiftHeld = true;
        }
    }

    function keyReleaseEvent(event) {
        if (event.text == "CONTROL") {
            controlHeld = false;
        }
        if (event.text == "SHIFT") {
            shiftHeld = false;
        }
    }

    function triggered() {
        return that.triggeredHand !== NO_HAND;
    };
    
    function makeClickHandler(hand) {
        return function (clicked) {
            if (!editEnabled || !isActive) {
                return;
            }
            // Don't allow both hands to trigger at the same time
            if (triggered() && hand !== that.triggeredHand) {
                return;
            }
            if (!triggered() && clicked) {
                that.triggeredHand = hand;
                mousePressEvent({});
            } else if (triggered() && !clicked) {
                that.triggeredHand = NO_HAND;
                mouseReleaseEvent({});
            }
        };
    }

    function makePressHandler(hand) {
        return function (value) {
            if (!editEnabled || !isActive) {
                return;
            }
            if (value >= TRIGGER_ON_VALUE && !triggered()) {
                that.pressedHand = hand;
            } else {
                that.pressedHand = NO_HAND;
                if(isOnUpdateConnected){
                    Script.update.disconnect(onUpdateHandler);
                    isOnUpdateConnected = false;
                }
            }
        }
    }

    function getDistanceBetweenControllers(){
        var poseLeft = getControllerWorldLocation(controllerStandard.LeftHand, true);
        var poseRight = getControllerWorldLocation(controllerStandard.RightHand, true);
        return poseLeft.valid && poseRight.valid ? Vec3.distance(poseLeft.translation, poseRight.translation) : 0;
    }
    function getEditSpherePosition( radius ){
        var poseLeft = getControllerWorldLocation(controllerStandard.LeftHand, true);
        var poseRight = getControllerWorldLocation(controllerStandard.RightHand, true);
        var handsPosition = Vec3.multiply(Vec3.sum(poseLeft.translation, poseRight.translation), 0.5);
        return Vec3.sum(handsPosition, Vec3.multiplyQbyV(MyAvatar.orientation, { x: 0, y: 0, z: radius * -2.0 }));
    }

    function updateSphereResizing(delta) {
        var wantDebug = false;
        var newDistance = getDistanceBetweenControllers();
        if (!isFinite(newDistance) || newDistance <= 0.001) { stopSphereResizing(); return; }
        var newRadius = (sphereInitialRadius / sphereResizingInitialHandDistance) * newDistance;
        var newPosition = getEditSpherePosition(newRadius);
        var newDimensions = Vec3.multiply({ x: 1.0, y: 1.0, z: 1.0 }, newRadius * 2.0);
        if (wantDebug) {
            print("newDistance: " + JSON.stringify(newDistance));
            print("newRadius: " + JSON.stringify(newRadius));
            print("newPosition: " + JSON.stringify(newPosition));
            print("newDimensions: " + JSON.stringify(newDimensions));
        }
        Entities.editEntity(sphereEntityID, {
            position: newPosition,
            dimensions: newDimensions
        });
        if( that.editTools ) {
            that.editTools.setVoxelSphereSize(newRadius * 2);
        }
        editSphereRadius = newRadius;
    }

    function startSphereResizing() {
        var wantDebug = false;
        if (wantDebug) {
            print("=============== eV::startSphereResizing BEG =======================");
        }
        Script.update.connect(updateSphereResizing);
        sphereResizingInitialHandDistance = getDistanceBetweenControllers();
        if (sphereResizingInitialHandDistance <= 0.001) { Script.update.disconnect(updateSphereResizing); return false; }
        sphereInitialRadius = editSphereRadius;
        var spherePosition = getEditSpherePosition(sphereInitialRadius);
        var sphereDimensions = Vec3.multiply({ x: 1.0, y: 1.0, z: 1.0 }, sphereInitialRadius * 2.0);
        sphereEntityID = Entities.addEntity({
            type: "Shape",
            shape: "Sphere",
            name: "voxelEditSphere",
            position: spherePosition,
            color: { r: 60, g: 100, b: 60 },
            alpha: 0.5,
            dimensions: sphereDimensions,
            collisionless: true,
            ignorePickIntersection: true,
            grab: { grabbable: false },
        }, "local");
        return true;
    }

    function stopSphereResizing() {
        var wantDebug = false;
        if (wantDebug) {
            print("=============== eV::stopSphereResizing BEG =======================");
        }
        Script.update.disconnect(updateSphereResizing);
        if (sphereEntityID !== null) {
            Entities.deleteEntity(sphereEntityID);
        }
        sphereEntityID = null;
        isSphereResizingStarted = false;
    }

    function makeGripPressHandler(hand) {
        return function (value) {
            if (!editEnabled || !isActive) {
                return;
            }
            if (value > 0.5) {
                if (hand === controllerStandard.LeftHand) {
                    isLeftGripPressed = true;
                } else if (hand === controllerStandard.RightHand) {
                    isRightGripPressed = true;
                }
            } else if (value < 0.4){
                if (hand === controllerStandard.LeftHand) {
                    isLeftGripPressed = false;
                } else if (hand === controllerStandard.RightHand) {
                    isRightGripPressed = false;
                }
            }
            if ( isLeftGripPressed && isRightGripPressed) {
                if( !isSphereResizingStarted ) {
                    isSphereResizingStarted = startSphereResizing();
                }
            } else {
                if( isSphereResizingStarted ) {
                    isSphereResizingStarted = false;
                    stopSphereResizing();
                }
            }
        }
    }
    
    function onUpdateHandler(delta){
        var wantDebug = false;

        if (!editEnabled || !isActive || !isEditing) {
            mouseReleaseEvent({});
            return;
        }
        if (!brushPointer && (editedVoxelEntity === null || !editable(Entities.getEntityProperties(editedVoxelEntity)))) {
            mouseReleaseEvent({});
            return;
        }

        continuousStartTimer += delta;
        
        if (continuousStartTimer < continuousStartTimerMax) {
            return;
        }

        // Get pick ray origin and direction

        var pickRay = null;
        var hand = triggered() ? that.triggeredHand : that.pressedHand;
        
        if (hand === NO_HAND) {
            pickRay = Camera.computePickRay(Controller.getValue(Controller.Hardware.Keyboard.MouseX), Controller.getValue(Controller.Hardware.Keyboard.MouseY));
        }else{
            pickRay = controllerComputePickRay();
        }

        if (!pickRay || pointingAtUI(hand)) { return; }
        if (brushPointer && hand !== NO_HAND) { brushChange(pickRay); return; }


        // Compute intersection of pick ray with given plane in local coordinates

        var globalOriginInVoxelSpace = Entities.worldCoordsToVoxelCoords(editedVoxelEntity, { x: 0, y: 0, z: 0 });
        var pickRayDirInVoxelSpace = Vec3.subtract(Entities.worldCoordsToVoxelCoords(editedVoxelEntity, pickRay.direction), globalOriginInVoxelSpace);
        var voxelPickRayOrigin = Entities.worldCoordsToVoxelCoords(editedVoxelEntity, pickRay.origin);
        pickRayDirInVoxelSpace = Vec3.normalize(pickRayDirInVoxelSpace);
        var directionMultiplier = 1.0;
        var offsetVector = { x: 0, y: 0, z: 0 };
        switch (editPlane) {
            // 0 - plane parallel to YZ plane
            case 0:
                offsetVector.x = 0.5;
                offsetVector.y = (offsetVector.x / pickRayDirInVoxelSpace.x) * pickRayDirInVoxelSpace.y;
                offsetVector.z = (offsetVector.x / pickRayDirInVoxelSpace.x) * pickRayDirInVoxelSpace.z;
                directionMultiplier = (oldEditPosition.x - voxelPickRayOrigin.x) / pickRayDirInVoxelSpace.x;
                break;
            // 1 - plane parallel to XZ plane
            case 1:
                offsetVector.y = 0.5;
                offsetVector.x = (offsetVector.y / pickRayDirInVoxelSpace.y) * pickRayDirInVoxelSpace.x;
                offsetVector.z = (offsetVector.y / pickRayDirInVoxelSpace.y) * pickRayDirInVoxelSpace.z;
                directionMultiplier = (oldEditPosition.y - voxelPickRayOrigin.y) / pickRayDirInVoxelSpace.y;
                break;
            // 2 - plane parallel to XY plane
            case 2:
                offsetVector.z = 0.5;
                offsetVector.x = (offsetVector.z / pickRayDirInVoxelSpace.z) * pickRayDirInVoxelSpace.x;
                offsetVector.y = (offsetVector.z / pickRayDirInVoxelSpace.z) * pickRayDirInVoxelSpace.y;
                directionMultiplier = (oldEditPosition.z - voxelPickRayOrigin.z) / pickRayDirInVoxelSpace.z;
                break;
            default:
                return;
        }
        if (!isFinite(directionMultiplier) || !isFinite(offsetVector.x)
                || !isFinite(offsetVector.y) || !isFinite(offsetVector.z)) { return; }
        var intersectionPoint = Vec3.sum(Vec3.multiply(pickRayDirInVoxelSpace, directionMultiplier), voxelPickRayOrigin);
        var newEditPosition = floorVector(Vec3.sum(intersectionPoint, offsetVector));

        if (Vec3.equal(newEditPosition, oldEditPosition)) {
            return;
        }

        if (wantDebug) {
            print("Old edit position: " + JSON.stringify(oldEditPosition));
            print("New edit position: " + JSON.stringify(newEditPosition));
            print("directionMultiplier: " + JSON.stringify(directionMultiplier) + " pickRay.direction: " + JSON.stringify(pickRay.direction) + " pickRayDirInVoxelSpace: " + JSON.stringify(pickRayDirInVoxelSpace) + " voxelPickRayOrigin: " + JSON.stringify(voxelPickRayOrigin) + " editPlane: " + JSON.stringify(editPlane));
        }

        if (editSingleVoxels) {
            if (Entities.setVoxel(editedVoxelEntity, newEditPosition, lastEditValue)){
                oldEditPosition = newEditPosition;
                Audio.playSystemSound((lastEditValue === 255) ? soundAdd : soundDelete);
            }
        } else if (editSpheres) {
            var toDrawPositionWorld = Entities.voxelCoordsToWorldCoords(editedVoxelEntity, newEditPosition);
            if (Entities.setVoxelSphere(editedVoxelEntity, toDrawPositionWorld, editSphereRadius, lastEditValue)){
                oldEditPosition = newEditPosition;
                Audio.playSystemSound((lastEditValue === 255) ? soundAdd : soundDelete);
            }
        } else if (editCubes) {
            var lowPosition = Vec3.subtract(newEditPosition, Vec3.multiply(cubeSize, 0.5));
            if (Entities.setVoxelsInCuboid(editedVoxelEntity, lowPosition, cubeSize, lastEditValue)){
                oldEditPosition = newEditPosition;
                Audio.playSystemSound((lastEditValue === 255) ? soundAdd : soundDelete);
            }
        }

    }

    function cleanup() {
        mouseReleaseEvent({});
        stopSphereResizing();
        if (strokeTimer !== null) { Script.clearInterval(strokeTimer); strokeTimer = null; }
        stroke = {};
        Controller.mousePressEvent.disconnect(mousePressEvent);
        Controller.mouseReleaseEvent.disconnect(mouseReleaseEvent);
        Controller.keyPressEvent.disconnect(keyPressEvent);
        Controller.keyReleaseEvent.disconnect(keyReleaseEvent);
    }

    Controller.mousePressEvent.connect(mousePressEvent);
    Controller.mouseReleaseEvent.connect(mouseReleaseEvent);
    Controller.keyPressEvent.connect(keyPressEvent);
    Controller.keyReleaseEvent.connect(keyReleaseEvent);
    that.triggerClickMapping.from(controllerStandard.RTClick).peek().to(makeClickHandler(controllerStandard.RightHand));
    that.triggerClickMapping.from(controllerStandard.LTClick).peek().to(makeClickHandler(controllerStandard.LeftHand));
    that.triggerPressMapping.from(controllerStandard.RT).peek().to(makePressHandler(controllerStandard.RightHand));
    that.triggerPressMapping.from(controllerStandard.LT).peek().to(makePressHandler(controllerStandard.LeftHand));
    that.gripPressMapping.from(controllerStandard.LeftGrip).peek().to(makeGripPressHandler(controllerStandard.LeftHand));
    that.gripPressMapping.from(controllerStandard.RightGrip).peek().to(makeGripPressHandler(controllerStandard.RightHand));
    that.enableTriggerMapping = function() {
        that.triggerClickMapping.enable();
        that.triggerPressMapping.enable();
        that.gripPressMapping.enable();
    };
    that.disableTriggerMapping = function() {
        that.triggerClickMapping.disable();
        that.triggerPressMapping.disable();
        that.gripPressMapping.disable();
    };
    that.enableTriggerMapping();
    
    Script.scriptEnding.connect(cleanup);
    Script.scriptEnding.connect(that.disableTriggerMapping);

    return that;
}
