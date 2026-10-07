// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type {BrowserGraphicsSettings} from './browser-graphics.mjs';
export interface GraphicsLocalChange {schemaVersion:1;browserRequestId:number;field:'resolutionPercent';value:number}
export interface GraphicsApplied {schemaVersion:1;browserRequestId:number;accepted:boolean;settings?:BrowserGraphicsSettings;message?:string}
export function graphicsBrowserRequestId(value:unknown):number;
export function validateGraphicsLocalChange(value:unknown):GraphicsLocalChange;
export function validateGraphicsApplied(value:unknown):GraphicsApplied;
