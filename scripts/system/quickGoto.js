"use strict";

//
//  quickGoto.js
//  scripts/system/
//
//  Created by Dante Ruiz
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
/* globals Tablet, Script, Window, location, LocationBookmarks */

(function() { // BEGIN LOCAL_SCOPE

    var FALLBACK_DESTINATION = "file:///~/serverless/tutorial.json";
    var MAX_HOME_DESTINATION_LENGTH = 4096;

    function validHomeDestination(candidate) {
        if (typeof candidate !== "string") {
            return "";
        }
        candidate = candidate.trim();
        // Do not pass malformed persisted data to AddressManager. In
        // particular, embedded control characters can turn one bookmark into
        // a different lookup when it crosses the script/C++ boundary.
        if (!candidate || candidate.length > MAX_HOME_DESTINATION_LENGTH ||
                /[\u0000-\u001f\u007f]/.test(candidate)) {
            return "";
        }
        return candidate;
    }

    function addGotoButton(name, navigate) {
        var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
        var button = tablet.addButton({
            icon: "icons/tablet-icons/goto-i.svg",
            activeIcon: "icons/tablet-icons/goto-a.svg",
            text: name
        });
        button.clicked.connect(function() {
            if (typeof tablet.hideAndroidTablet === "function") {
                tablet.hideAndroidTablet();
            }
            navigate();
        });
        Script.scriptEnding.connect(function () {
            tablet.removeButton(button);
        });
    }

    addGotoButton("Tutorial", function () {
        Window.location = FALLBACK_DESTINATION;
    });
    addGotoButton("Home", function () {
        var home = validHomeDestination(LocationBookmarks.getHomeLocationAddress());
        if (home) {
            location.handleLookupString(home);
        } else {
            Window.location = FALLBACK_DESTINATION;
        }
    });

}()); // END LOCAL_SCOPE
