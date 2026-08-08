// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

function finiteNumber(value) {
    return typeof value === "number" && isFinite(value);
}

function vector(value, minimum) {
    if (!value || !finiteNumber(value.x) || !finiteNumber(value.y) || !finiteNumber(value.z)) {
        return null;
    }
    if (minimum !== undefined) {
        return {
            x: Math.max(minimum, value.x),
            y: Math.max(minimum, value.y),
            z: Math.max(minimum, value.z)
        };
    }
    return { x: value.x, y: value.y, z: value.z };
}

function color(value) {
    if (!value || !finiteNumber(value.red) || !finiteNumber(value.green) ||
            !finiteNumber(value.blue)) {
        return null;
    }
    function component(number) {
        return Math.max(0, Math.min(255, Math.round(number)));
    }
    return {
        red: component(value.red),
        green: component(value.green),
        blue: component(value.blue)
    };
}

function validate(properties) {
    if (!properties || typeof properties.name !== "string" ||
            typeof properties.visible !== "boolean" ||
            typeof properties.dynamic !== "boolean" ||
            typeof properties.collisionless !== "boolean") {
        return null;
    }
    var position = vector(properties.position);
    var rotation = vector(properties.rotation);
    var dimensions = vector(properties.dimensions, 0.001);
    var entityColor = color(properties.color);
    if (!position || !rotation || !dimensions || !entityColor) {
        return null;
    }
    return {
        name: properties.name,
        position: position,
        rotation: rotation,
        dimensions: dimensions,
        color: entityColor,
        visible: properties.visible,
        dynamic: properties.dynamic,
        collisionless: properties.collisionless
    };
}

module.exports = validate;
