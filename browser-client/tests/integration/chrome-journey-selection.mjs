// SPDX-License-Identifier: Apache-2.0
// Operator journeys only. Product browser compatibility and historical fixtures are unchanged.
import {googleChromeLaunchOptions} from '../google-chrome-selection.mjs';
export function selectGoogleChromeJourney(env=process.env) {
 const kind=env.OVERTE_LAB_BROWSER;
 if(kind!==undefined&&!['chrome','google-chrome','system-chromium'].includes(kind))throw Error('Current journey requires Google Chrome');
 const executable=env.OVERTE_LAB_CHROMIUM??env.OVERTE_BROWSER_CHROME_EXECUTABLE;
 if(kind==='system-chromium'&&executable===undefined)throw Error('Reviewed Google Chrome executable required');
 return executable===undefined?{channel:'chrome'}:googleChromeLaunchOptions(executable);
}
