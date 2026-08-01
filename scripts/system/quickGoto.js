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
/* globals Tablet, Toolbars, Script, HMD, DialogsManager */

(function() { // BEGIN LOCAL_SCOPE

    function addGotoButton(name, destination) {
        var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
        var button = tablet.addButton({
            icon: "icons/tablet-icons/goto-i.svg",
            activeIcon: "icons/tablet-icons/goto-a.svg",
            text: name
        });
        var buttonDestination = destination;
        button.clicked.connect(function() {
            Window.location = buttonDestination;
        });
        Script.scriptEnding.connect(function () {
            tablet.removeButton(button);
        });
    }

    addGotoButton("Tutorial", "file:///~/serverless/tutorial.json");
    addGotoButton("Home", "file:///~/serverless/pico-debug.json");

}()); // END LOCAL_SCOPE
