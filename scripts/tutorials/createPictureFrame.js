//
//  Created by James B. Pollack @imgntn on April 18, 2016.
//  Copyright 2016 High Fidelity, Inc.
//
// This script shows how to create an entity with a picture texture on it that
// you can change either in script or in the entity's textures property.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

var NASA_API_ENDPOINT = "https://api.nasa.gov/planetary/apod";
var MODEL_URL = "https://content.overte.org/Developer/Tutorials/pictureFrame/finalFrame.fbx";
var OUTER_FRAME_MODEL_URL = "https://content.overte.org/Developer/Tutorials/pictureFrame/outer_frame.fbx";

// Ask for the credential for this invocation only. Do not persist it in the
// script, Settings, logs, or entity properties.
var nasaApiKey = Window.prompt(
    "Enter a NASA API key for this run. The key is not stored by this script.",
    ""
);

function getDataFromNASA(apiKey) {
    var request = new XMLHttpRequest();
    var url = NASA_API_ENDPOINT + "?api_key=" + encodeURIComponent(apiKey);
    request.open("GET", url, false);
    request.send();

    if (request.status !== 200) {
        throw new Error("NASA APOD request failed with HTTP status " + request.status);
    }
    return JSON.parse(request.responseText);
}

function makePictureFrame(apiKey) {
    var center = Vec3.sum(Vec3.sum(MyAvatar.position, {
        x: 0,
        y: 0.5,
        z: 0
    }), Vec3.multiply(1, Quat.getForward(Camera.getOrientation())));
    var rotation = Quat.multiply(Quat.fromPitchYawRollDegrees(0, 180, 0), Camera.getOrientation());
    rotation.x = 0;
    rotation.z = 0;

    var data = getDataFromNASA(apiKey);
    var pictureFrame = Entities.addEntity({
        name: "Tutorial Picture Frame",
        description: data.explanation,
        type: "Model",
        dimensions: {
            x: 1.2,
            y: 0.9,
            z: 0.075
        },
        position: center,
        rotation: rotation,
        textures: JSON.stringify({
            Picture: data.url
        }),
        modelURL: MODEL_URL,
        lifetime: 3600,
        dynamic: true
    });

    Entities.addEntity({
        name: "Tutorial Outer Frame",
        type: "Model",
        position: center,
        rotation: rotation,
        modelURL: OUTER_FRAME_MODEL_URL,
        lifetime: 3600,
        dynamic: true,
        dimensions: {
            x: 1.4329,
            y: 1.1308,
            z: 0.0464
        },
        parentID: pictureFrame
    });
}

if (!nasaApiKey) {
    Window.alert("A NASA API key is required; no request was sent.");
} else {
    try {
        makePictureFrame(nasaApiKey);
    } catch (error) {
        Window.alert("The NASA picture could not be loaded. Check the API configuration and try again.");
    }
}

Script.stop();
