// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type * as THREE from 'three';
import {validateBrowserGraphics,type BrowserGraphicsSettings} from '../shared/browser-graphics.mjs';
import type {BrowserGraphicsTarget} from './browser-graphics-controller';
export interface BrowserGraphicsBindings {
    camera:Pick<THREE.PerspectiveCamera,'fov'|'updateProjectionMatrix'>;
    renderer:Pick<THREE.WebGLRenderer,'getPixelRatio'|'setPixelRatio'>;
    /** Check the actual framebuffer allocation before any rendering state changes. */
    validatePixelRatio?(ratio:number):void;
    resize():void;
    localLights():boolean;
    setLocalLights(enabled:boolean):void;
    cameraClipping():boolean;
    setCameraClipping(enabled:boolean):void;
}
/** Preserves the World's established initial device ratio as its 100% value. */
export class WorldGraphicsTarget implements BrowserGraphicsTarget {
    private baseRatio:number;
    constructor(private bindings:BrowserGraphicsBindings){
        this.baseRatio=bindings.renderer.getPixelRatio();
        if(!Number.isFinite(this.baseRatio)||this.baseRatio<=0||this.baseRatio>8)throw Error('Invalid browser resolution base');
    }
    snapshot():BrowserGraphicsSettings {
        return validateBrowserGraphics({version:1,fieldOfView:this.bindings.camera.fov,resolutionPercent:Math.round(this.bindings.renderer.getPixelRatio()/this.baseRatio*100),localLights:this.bindings.localLights(),cameraClipping:this.bindings.cameraClipping()});
    }
    apply(input:BrowserGraphicsSettings):void {
        const settings=validateBrowserGraphics(input);
        const ratio=this.baseRatio*settings.resolutionPercent/100;
        this.bindings.validatePixelRatio?.(ratio);
        this.bindings.camera.fov=settings.fieldOfView;this.bindings.camera.updateProjectionMatrix();
        this.bindings.renderer.setPixelRatio(ratio);
        this.bindings.resize();
        this.bindings.setLocalLights(settings.localLights);
        this.bindings.setCameraClipping(settings.cameraClipping);
    }
}
