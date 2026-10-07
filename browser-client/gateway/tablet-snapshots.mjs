// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

/** Keep the real native app and its assets, replacing only the scene capture. */
export function patchSnapshotSource(source,channel){
    const original='Window.takeSnapshot(false, includeAnimated, 1.91);';
    const marker='}()); // END LOCAL_SCOPE';
    if(source.split(original).length!==2||source.split(marker).length!==2||!['function stillSnapshotTaken(', 'function processingGifStarted(', 'function processingGifCompleted('].every(text=>source.includes(text)))throw Error('This installed Snapshot app version cannot safely delegate browser capture');
    const literal=JSON.stringify(channel);
    const request=`Messages.sendLocalMessage(${literal}, JSON.stringify({kind:"request", animated:!!includeAnimated, aspectRatio:1.91}));`;
    const listener=`
// Browser scene pixels originate on the visitor's device. Preserve native review.
function browserSnapshotResult(channel, text, sender, localOnly) {
    if (channel !== ${literal} || !localOnly) { return; }
    var message;
    try { message = JSON.parse(text); } catch (error) { return; }
    if (message.kind !== "result") { return; }
    if (message.error) {
        Reticle.visible = reticleVisible;
        Reticle.allowMouseCapture = true;
        if (resetOverlays) { Menu.setIsOptionChecked("Show Overlays", true); }
        HMD.openTablet(); setTakePhotoControllerMappingStatus(true);
        ui.sendMessage({type:"snapshot",action:"captureFailed",message:message.error});
        return;
    }
    if (message.gifPath) {
        processingGifStarted(message.stillPath);
        Script.setTimeout(function () { processingGifCompleted(message.gifPath); }, 500);
    } else { stillSnapshotTaken(message.stillPath, false); }
}
Messages.subscribe(${literal});
Messages.messageReceived.connect(browserSnapshotResult);
Script.scriptEnding.connect(function () {
    Messages.messageReceived.disconnect(browserSnapshotResult);
    Messages.unsubscribe(${literal});
});
`;
    return source.replace(original,request).replace(marker,listener+'\n'+marker);
}
export async function prepareSnapshotOverride(directory,{defaultScriptsURL,channel}){
    const targetURL=new URL('system/snapshot.js',defaultScriptsURL);
    const source=await readFile(targetURL,'utf8');
    if(source.length>2*1024*1024)throw Error('Installed Snapshot app source is too large');
    const output=join(directory,'browser-snapshot.js');
    await writeFile(output,patchSnapshotSource(source,channel),{mode:0o600,flag:'wx'});
    return {source:output,target:fileURLToPath(targetURL)};
}
