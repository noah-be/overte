// SPDX-License-Identifier: Apache-2.0
// Operator-selected branded Chrome; this selector does not infer browser branding.
import {lstatSync,accessSync,constants} from 'node:fs';
import {isAbsolute} from 'node:path';
export function googleChromeLaunchOptions(value=process.env.OVERTE_BROWSER_CHROME_EXECUTABLE) {
 if(value===undefined)return {channel:'chrome'};
 if(typeof value!=='string'||value.length===0||value.length>4096||value.includes('\0')||!isAbsolute(value))throw Error('Google Chrome executable selection refused');
 try{const file=lstatSync(value);if(!file.isFile()||file.isSymbolicLink())throw Error();accessSync(value,constants.X_OK);}catch{throw Error('Google Chrome executable selection refused');}
 return {executablePath:value};
}
