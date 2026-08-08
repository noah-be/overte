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
        Window.location = "file:///~/serverless/tutorial.json";
    });
    addGotoButton("Home", function () {
        var home = LocationBookmarks.getHomeLocationAddress();
        if (home) {
            location.handleLookupString(home);
        } else {
            Window.location = "file:///~/serverless/tutorial.json";
        }
    });

}()); // END LOCAL_SCOPE
