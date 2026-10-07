// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export interface BrowserGraphicsSettings {version:1;fieldOfView:number;resolutionPercent:number;localLights:boolean;cameraClipping:boolean}
export type BrowserGraphicsField='fieldOfView'|'resolutionPercent'|'localLights'|'cameraClipping';
export type BrowserGraphicsChange={field:'fieldOfView'|'resolutionPercent';value:number}|{field:'localLights'|'cameraClipping';value:boolean};
export type BrowserGraphicsRequest={schemaVersion:1;requestId:number;operation:'request'}|({schemaVersion:1;requestId:number;operation:'change'}&BrowserGraphicsChange);
export interface BrowserGraphicsResult {schemaVersion:1;requestId:number;accepted:boolean;settings:BrowserGraphicsSettings;message?:string}
export const BROWSER_GRAPHICS_VERSION:1;
export const BROWSER_GRAPHICS_FIELDS:readonly BrowserGraphicsField[];
export const DEFAULT_BROWSER_GRAPHICS:Readonly<BrowserGraphicsSettings>;
export function validateBrowserGraphicsChange(field:unknown,value:unknown):BrowserGraphicsChange;
export function validateBrowserGraphics(value:unknown):BrowserGraphicsSettings;
export function validateBrowserGraphicsRequest(value:unknown):BrowserGraphicsRequest;
export function validateBrowserGraphicsResult(value:unknown):BrowserGraphicsResult;
