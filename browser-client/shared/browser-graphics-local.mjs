// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {validateBrowserGraphics,validateBrowserGraphicsChange} from './browser-graphics.mjs';
const id=value=>Number.isSafeInteger(value)&&value>=1;
export function graphicsBrowserRequestId(value){if(!id(value))throw Error('Invalid browser graphics intent');return value;}
export function validateGraphicsLocalChange(value){
 if(!value||typeof value!=='object'||Array.isArray(value)||value.schemaVersion!==1||value.field!=='resolutionPercent')throw Error('Invalid browser graphics intent');
 return {schemaVersion:1,browserRequestId:graphicsBrowserRequestId(value.browserRequestId),...validateBrowserGraphicsChange(value.field,value.value)};
}
export function validateGraphicsApplied(value){
 if(!value||typeof value!=='object'||Array.isArray(value)||value.schemaVersion!==1||typeof value.accepted!=='boolean'||(value.message!==undefined&&(typeof value.message!=='string'||value.message.length>512)))throw Error('Invalid browser graphics completion');
 const result={schemaVersion:1,browserRequestId:graphicsBrowserRequestId(value.browserRequestId),accepted:value.accepted};
 if(value.accepted||value.settings!==undefined)result.settings=validateBrowserGraphics(value.settings);
 if(value.message!==undefined)result.message=value.message;
 return result;
}
