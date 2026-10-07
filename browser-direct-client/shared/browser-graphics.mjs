// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Browser-owned graphics controls. No native worker Render defaults are read.
export const BROWSER_GRAPHICS_VERSION = 1;
export const BROWSER_GRAPHICS_FIELDS = Object.freeze(['fieldOfView','resolutionPercent','localLights','cameraClipping']);
export const DEFAULT_BROWSER_GRAPHICS = Object.freeze({version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true});
function object(value){return !!value&&typeof value==='object'&&!Array.isArray(value);}
export function validateBrowserGraphicsChange(field,value){
    if(!BROWSER_GRAPHICS_FIELDS.includes(field))throw Error('Unsupported browser graphics control');
    if(field==='fieldOfView'&&(!Number.isInteger(value)||value<20||value>130))throw Error('Invalid browser field of view');
    if(field==='resolutionPercent'&&(!Number.isInteger(value)||value<10||value>200||value%10!==0))throw Error('Invalid browser resolution percentage');
    if((field==='localLights'||field==='cameraClipping')&&typeof value!=='boolean')throw Error('Invalid browser graphics switch');
    return {field,value};
}
export function validateBrowserGraphics(value){
    if(!object(value)||value.version!==1||Object.keys(value).length!==5||Object.keys(value).some(key=>key!=='version'&&!BROWSER_GRAPHICS_FIELDS.includes(key)))throw Error('Invalid browser graphics settings');
    const result={version:1};for(const field of BROWSER_GRAPHICS_FIELDS)result[field]=validateBrowserGraphicsChange(field,value[field]).value;
    return result;
}
export function validateBrowserGraphicsRequest(value){
    if(!object(value)||value.schemaVersion!==1||!Number.isSafeInteger(value.requestId)||value.requestId<1||!['request','change'].includes(value.operation))throw Error('Invalid browser graphics request');
    const result={schemaVersion:1,requestId:value.requestId,operation:value.operation};
    if(value.operation==='change')Object.assign(result,validateBrowserGraphicsChange(value.field,value.value));
    else if(value.field!==undefined||value.value!==undefined)throw Error('Invalid browser graphics request');
    return result;
}
export function validateBrowserGraphicsResult(value){
    if(!object(value)||value.schemaVersion!==1||!Number.isSafeInteger(value.requestId)||value.requestId<1||typeof value.accepted!=='boolean'||(value.message!==undefined&&(typeof value.message!=='string'||value.message.length>512)))throw Error('Invalid browser graphics result');
    return {schemaVersion:1,requestId:value.requestId,accepted:value.accepted,settings:validateBrowserGraphics(value.settings),...(value.message===undefined?{}:{message:value.message})};
}
