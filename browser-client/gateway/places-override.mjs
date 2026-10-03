// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { readFile, writeFile, lstat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

function replaceOnce(source, before, after) {
    if (source.split(before).length !== 2) throw Error('The installed Places app does not match the supported navigation adapter.');
    return source.replace(before, after);
}

function javascriptStringLiteral(value) {
    // JSON quoting also needs HTML delimiters and legacy JS line separators escaped.
    return JSON.stringify(value).replace(/[<>&\u2028\u2029]/g,
        character => '\\u' + character.charCodeAt(0).toString(16).padStart(4, '0'));
}

export function adaptPlacesScript(source, { channel, homeDomain }) {
    if (!/^browser-places-[a-f0-9-]{36}$/.test(channel) || typeof homeDomain !== 'string') throw Error('Invalid trusted Places adapter configuration.');
    const bootstrap = `\n    var browserPlacesChannel = ${JSON.stringify(channel)};
    var browserPlacesHistory = {canGoBack:false,canGoForward:false};
    function browserPlacesNavigate(request) { Messages.sendLocalMessage(browserPlacesChannel,JSON.stringify(request)); }
    function browserPlacesSendHistory() { if(!tablet)return;tablet.emitScriptEvent({channel:channel,action:'BROWSER_HISTORY',canGoBack:browserPlacesHistory.canGoBack,canGoForward:browserPlacesHistory.canGoForward}); }
    function browserPlacesHistoryMessage(sourceChannel,text,sender,localOnly) {
        if(sourceChannel!==browserPlacesChannel||!localOnly)return;
        var message;try{message=JSON.parse(text);}catch(error){return;}
        if(message.kind!=='historyState'||typeof message.canGoBack!=='boolean'||typeof message.canGoForward!=='boolean')return;
        browserPlacesHistory={canGoBack:message.canGoBack,canGoForward:message.canGoForward};browserPlacesSendHistory();
    }
    Messages.subscribe(browserPlacesChannel);Messages.messageReceived.connect(browserPlacesHistoryMessage);
    Script.scriptEnding.connect(function(){Messages.messageReceived.disconnect(browserPlacesHistoryMessage);Messages.unsubscribe(browserPlacesChannel);});
`;
    source = replaceOnce(source, '(function() {', '(function() {' + bootstrap);
    source = replaceOnce(source, 'function getLocationBookmarks() {', "function getLocationBookmarks() {\n        browserPlacesNavigate({kind:'preferencesChanged'});");
    source = replaceOnce(source, 'LocationBookmarks.setHomeLocationToAddress(location.href);', "LocationBookmarks.setHomeLocationToAddress(location.href);\n                browserPlacesNavigate({kind:'preferencesChanged'});");
    source = replaceOnce(source, 'Window.location = messageObj.address;', "browserPlacesNavigate({kind:'target',address:messageObj.address});");
    source = replaceOnce(source, 'location.handleLookupString(LocationBookmarks.getHomeLocationAddress());', "browserPlacesNavigate({kind:'target',address:LocationBookmarks.getHomeLocationAddress()});");
    source = replaceOnce(source, 'Window.location = "file:///~/serverless/tutorial.json";', `browserPlacesNavigate({kind:'target',address:${javascriptStringLiteral(homeDomain)}});`);
    source = replaceOnce(source, 'location.goBack();', "browserPlacesNavigate({kind:'history',direction:'back'});");
    source = replaceOnce(source, 'location.goForward();', "browserPlacesNavigate({kind:'history',direction:'forward'});");
    source = replaceOnce(source, 'tablet.screenChanged.connect(onScreenChanged);', "tablet.screenChanged.connect(onScreenChanged);\n    Messages.sendLocalMessage(browserPlacesChannel,JSON.stringify({kind:'historyRequest'}));");
    source = replaceOnce(source, 'transmitPortalList();\n                sendCurrentLocationToUI();', 'transmitPortalList();\n                sendCurrentLocationToUI();\n                browserPlacesSendHistory();');
    if (/\bWindow\.location\s*=|\blocation\.(?:handleLookupString|goBack|goForward)\s*\(/.test(source)) throw Error('The installed Places app contains an unreviewed native navigation path.');
    return source;
}

export function adaptPlacesUI(source) {
    return replaceOnce(source, 'EventBridge.scriptEventReceived.connect(function (message) {', `EventBridge.scriptEventReceived.connect(function (message) {
    if(message.channel===channel&&message.action==='BROWSER_HISTORY'){
        var back=document.querySelector('#navigationBar input[onclick="goBack();"]');
        var forward=document.querySelector('#navigationBar input[onclick="goForward();"]');
        if(back){back.disabled=!message.canGoBack;back.style.opacity=message.canGoBack?'1':'.35';}
        if(forward){forward.disabled=!message.canGoForward;forward.style.opacity=message.canGoForward?'1':'.35';}
        return;
    }`);
}

export async function preparePlacesOverride(directory, { defaultScriptsURL, channel, homeDomain }) {
    const defaults = new URL(defaultScriptsURL);
    if (defaults.protocol !== 'file:' || defaults.host) throw Error('Places must use version-matched installed local scripts.');
    const folder = join(dirname(fileURLToPath(defaults)), 'system/places');
    const scriptTarget = join(folder, 'places.js'), uiTarget = join(folder, 'placesHtml.js');
    const records = await Promise.all([scriptTarget, uiTarget].map(async target => {
        const info = await lstat(target);
        if (!info.isFile() || info.isSymbolicLink() || info.size > 1024 * 1024) throw Error('Invalid installed Places app source.');
        return readFile(target, 'utf8');
    }));
    const script = adaptPlacesScript(records[0], { channel, homeDomain }), ui = adaptPlacesUI(records[1]);
    const source = join(directory, 'browser-places.js'), uiSource = join(directory, 'browser-places-ui.js');
    await writeFile(source, script, { mode: 0o600, flag: 'wx' });
    await writeFile(uiSource, ui, { mode: 0o600, flag: 'wx' });
    return [{ source, target: scriptTarget }, { source: uiSource, target: uiTarget }];
}
