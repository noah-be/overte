// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {createHash,randomBytes} from 'node:crypto';
import {constants} from 'node:fs';
import {open,writeFile,realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
export const GRAPHICS_SOURCE_SHA256=Object.freeze({
    'qml/SettingBoolean.qml':'f043477adb67b59f8afda3a03870087a268283bb49045fabff3552a81178f093',
    'qml/SettingSlider.qml':'c2ec0136e4f0cf6e812e0e1c8f5628185ece3c1fd44eb75822e6ab411cc822c7',
    'qml/SettingComboBox.qml':'53577ed3a638d7f4db36b27ad4775eedf897073f6fd9b3923799414aabce13cf',
    'settings.js':'e5176a990cc09a9f0df1651dbd1483ffb7c52129702a42de34c60bef01e06129',
    'Settings.qml':'aed4ea8d5082510480aac302ddbc220c3bd4412018fa7130edf24dbfa686eece',
    'qml/pages/GraphicsSettings.qml':'f1eda115ef4504e355002dc5a2a238385374cd09f2247e187e5aa0392b75b313',
});
async function source(filename){const handle=await open(filename,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);try{const stat=await handle.stat();if(!stat.isFile()||stat.size>128*1024)throw Error('Unsupported installed Graphics Settings source');const bytes=Buffer.alloc(128*1024+1);const read=await handle.read(bytes,0,bytes.length,0);if(read.bytesRead>128*1024)throw Error('Unsupported installed Graphics Settings source');return bytes.subarray(0,read.bytesRead).toString('utf8');}finally{await handle.close();}}
const nativeGraphicsSource=await source(fileURLToPath(new URL('./native-browser-graphics.js',import.meta.url)));
function once(text,before,after){if(text.split(before).length!==2)throw Error('Unsupported installed Graphics Settings source');return text.replace(before,after);}
function widget(text,kind,label){
    const labelAt=text.indexOf('settingText: "'+label+'"'),start=text.lastIndexOf(kind+' {',labelAt);
    if(labelAt<0||start<0)throw Error('Unsupported installed Graphics Settings widget');
    let depth=0,quote='';for(let index=text.indexOf('{',start);index<text.length;index++){const char=text[index];if(quote){if(char==='\\')index++;else if(char===quote)quote='';continue;}if(char==='"'||char==="'"){quote=char;continue;}if(char==='{')depth++;else if(char==='}'&&--depth===0)return text.slice(start,index+1);}
    throw Error('Unsupported installed Graphics Settings widget');
}
/** Preserve the authentic installed native widgets. Unsupported controls are not enabled. */
export function buildBrowserGraphicsOverrides(sources,channel){
    if(!/^overte\.browser\.graphics\.[a-f0-9]{32}$/.test(channel))throw Error('Invalid private graphics channel');
    for(const [name,hash] of Object.entries(GRAPHICS_SOURCE_SHA256))if(typeof sources[name]!=='string'||createHash('sha256').update(sources[name]).digest('hex')!==hash)throw Error('Unsupported installed Graphics Settings version');
    const actual=sources['qml/pages/GraphicsSettings.qml'];
    let profile=widget(actual,'SettingComboBox','Graphics preset');
    profile=once(profile,'graphicsPresetCombobox','resolutionProfileControl');
    profile=once(profile,'"Graphics preset"','"Resolution preset"');
    profile=once(profile,'Performance.getPerformancePreset() - 1','graphicsPage.resolutionProfileIndex()');
    profile=once(profile,'["Low Power", "Low", "Medium", "High", "Custom"]','["Default (100%)", "Balanced (80%)", "Faster (60%)", "Custom"]');
    profile=once(profile,'Performance.setPerformancePreset(index + 1);\n                if (index !== 4) switchToAGraphicsPreset();','graphicsPage.selectResolutionProfile(index);');
    let lights=widget(actual,'SettingBoolean','Local Lights');
    lights=once(lights,'SettingBoolean {','SettingBoolean {\n            id: localLightsControl;');
    lights=once(lights,'Render.localLightingEnabled }','browserState.localLights }');
    lights=once(lights,'Render.localLightingEnabled = settingEnabled;','graphicsPage.publish("localLights",settingEnabled);');
    let clipping=widget(actual,'SettingBoolean','Allow camera clipping');
    clipping=once(clipping,'SettingBoolean {','SettingBoolean {\n            id: clippingControl;');
    clipping=once(clipping,'!Render.cameraClippingEnabled }','!browserState.cameraClipping }');
    clipping=once(clipping,'Render.cameraClippingEnabled = settingEnabled ? 0 : 1;','graphicsPage.publish("cameraClipping",!settingEnabled);');
    let fov=widget(actual,'SettingSlider','Field of View');
    fov=once(fov,'Render.verticalFieldOfView.toFixed(1)','browserState.fieldOfView.toFixed(1)');
    fov=once(fov,'Render.verticalFieldOfView = value.toFixed(1);','graphicsPage.publish("fieldOfView",Math.round(value));');
    let resolution=widget(actual,'SettingSlider','Resolution scale');
    resolution=once(resolution,'"Resolution scale"','"Resolution scale (%)"');
    resolution=once(resolution,'sliderStepSize: 0.1;','sliderStepSize: 10;\n            roundDisplay: 0;');
    resolution=once(resolution,'minValue: 0.1;','minValue: 10;');resolution=once(resolution,'maxValue: 2;','maxValue: 200;');
    resolution=once(resolution,'Render.viewportResolutionScale.toFixed(1)','browserState.resolutionPercent.toFixed(0)');
    resolution=once(resolution,'Render.viewportResolutionScale = value.toFixed(1)','graphicsPage.publish("resolutionPercent",Math.round(value/10)*10)');
    const graphics=`// Copyright 2024-2026 Overte contributors\n// SPDX-License-Identifier: Apache-2.0\n// Original installed native combo/slider/switch controls, browser effects.\nimport QtQuick 2.15\nimport QtQuick.Controls 2.15\nimport QtQuick.Layouts 1.3\nimport "../"\nFlickable {\n    id: graphicsPage;\n    property var browserState: ({version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true});\n    property bool browserReady: false;\n    property string browserMessage: "";\n    property bool hasPresetBeenModified: false;\n    property bool isChangingPreset: true;\n    signal browserSettingChanged(string field,var value);\n    signal browserPageReady();\n    visible: currentPage == "Graphics";width: parent.width;Layout.fillHeight: true;y: header.height + 10;\n    contentWidth: parent.width;contentHeight: graphicsPageColumn.height;clip: true;flickDeceleration:4000;\n    ScrollBar.vertical: ScrollBar {policy:Qt.ScrollBarAlwaysOn}\n    function publish(field,value){if(browserReady&&browserState[field]!==value)browserSettingChanged(field,value);}\n    function resolutionProfileIndex(){var index=[100,80,60].indexOf(browserState.resolutionPercent);return index<0?3:index;}\n    function selectResolutionProfile(index){if(!browserReady||typeof index!=="number"||index%1!==0||index<0||index>=3){if(resolutionProfileControl)resolutionProfileControl.setOptionIndex(resolutionProfileIndex());return;}publish("resolutionPercent",[100,80,60][index]);}\n    onVisibleChanged: {if(visible)browserPageReady();}\n    onBrowserStateChanged: {if(localLightsControl)localLightsControl.update();if(clippingControl)clippingControl.update();if(resolutionProfileControl)resolutionProfileControl.setOptionIndex(resolutionProfileIndex());}\n    Column {\n        id: graphicsPageColumn;width:parent.width-20;anchors.horizontalCenter:parent.horizontalCenter;spacing:10;\n        Text {width:parent.width;wrapMode:Text.Wrap;font.pixelSize:16;color:"white";text:browserMessage || (browserReady?"Settings affect your browser-rendered world.":"Waiting for the browser to confirm its graphics settings…")}\n        Column {width:parent.width;spacing:10;enabled:browserReady;\n        ${profile}\n        Text {width:parent.width;wrapMode:Text.Wrap;font.pixelSize:16;color:"#bbbbbb";text:"100% preserves the browser\'s initial device density, capped at 2. Presets change resolution only; select one explicitly to reduce pixel workload. Actual speed depends on your device and world."}\n        ${fov}\n        ${resolution}\n        ${lights}\n        ${clipping}\n        }\n        Text {width:parent.width;wrapMode:Text.Wrap;font.pixelSize:16;color:"#bbbbbb";text:"Additional graphics options are not yet available in this browser version."}\n    }\n}\n`;
    let qml=sources['Settings.qml'];
    qml=once(qml,'Rectangle {','Rectangle {\n    id: browserSettingsApp;\n    property var browserGraphicsState: ({version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true});\n    property bool browserGraphicsReady: false;\n    property string browserGraphicsMessage: "";');
    qml=once(qml,'GraphicsSettings {}',`GraphicsSettings {\n            browserState:browserSettingsApp.browserGraphicsState;browserReady:browserSettingsApp.browserGraphicsReady;browserMessage:browserSettingsApp.browserGraphicsMessage;\n            onBrowserSettingChanged: toScript({type:"browserGraphicsChange",field:field,value:value});\n            onBrowserPageReady: toScript({type:"browserGraphicsReady"});\n        }`);
    qml=once(qml,'switch (message.type){','switch (message.type){\n            case "browserGraphicsState":\n                browserGraphicsReady=false;browserGraphicsState=message.settings;browserGraphicsMessage=message.message||"";browserGraphicsReady=message.ready;break;');
    let js=sources['settings.js'];
    js=once(js,'\tvar tablet;',`\tvar tablet;\n    var browserGraphicsChannel=${JSON.stringify(channel)};var browserGraphicsSequence=0;\n    function browserGraphicsMessage(channel,text,sender,localOnly){\n        if(channel!==browserGraphicsChannel||!localOnly||typeof text!=="string"||text.length>4096)return;\n        var message;try{message=JSON.parse(text);}catch(error){return;}\n        if(!message||message.kind!=="effective"||typeof message.sequence!=="number"||message.sequence%1!==0||message.sequence<=browserGraphicsSequence||message.sequence>9007199254740991||typeof message.ready!=="boolean")return;
        var s=message.settings;if(!s||s.version!==1||Object.keys(s).length!==5||typeof s.fieldOfView!=="number"||s.fieldOfView%1!==0||s.fieldOfView<20||s.fieldOfView>130||typeof s.resolutionPercent!=="number"||s.resolutionPercent%10!==0||s.resolutionPercent<10||s.resolutionPercent>200||typeof s.localLights!=="boolean"||typeof s.cameraClipping!=="boolean"||(message.message!==undefined&&(typeof message.message!=="string"||message.message.length>512)))return;
        browserGraphicsSequence=message.sequence;
        tablet.sendToQml({type:"browserGraphicsState",settings:{version:1,fieldOfView:s.fieldOfView,resolutionPercent:s.resolutionPercent,localLights:s.localLights,cameraClipping:s.cameraClipping},ready:message.ready,message:message.message});\n    }`);
    js=once(js,'\t// Event listeners','\tMessages.subscribe(browserGraphicsChannel);Messages.messageReceived.connect(browserGraphicsMessage);\n\t// Event listeners');
    js=once(js,'\t\ttablet.removeButton(appButton);','\t\tMessages.messageReceived.disconnect(browserGraphicsMessage);Messages.unsubscribe(browserGraphicsChannel);\n\t\ttablet.removeButton(appButton);');
    js=once(js,'\t\tif (event.type === "switchApp") {','\t\tif(event.type==="browserGraphicsReady"||event.type==="browserGraphicsChange"){\n            Messages.sendLocalMessage(browserGraphicsChannel,JSON.stringify(event.type==="browserGraphicsReady"?{kind:"ready"}:{kind:"change",field:event.field,value:event.value}));return;\n        }\n\t\tif (event.type === "switchApp") {');
    const combo=once(sources['qml/SettingComboBox.qml'],'popup: Popup {','popup: Popup {\n                    y: root.settingText === \"Resolution preset\" ? control.height : 0;');
    const opaqueCombo=once(combo,'color: Qt.rgba(0,0,0,0.9)','color: Qt.rgba(0,0,0,root.settingText === "Resolution preset" ? 1 : 0.9)');
    return {'settings.js':js,'Settings.qml':qml,'qml/pages/GraphicsSettings.qml':graphics,'qml/SettingSlider.qml':sources['qml/SettingSlider.qml'],'qml/SettingBoolean.qml':sources['qml/SettingBoolean.qml'],'qml/SettingComboBox.qml':opaqueCombo};
}
/** Call at gateway startup with an operator-approved installed defaultScripts URL. */
export async function loadBrowserGraphicsPackage(defaultScriptsURL){
    const defaultPath=fileURLToPath(defaultScriptsURL);if(path.basename(defaultPath)!=='defaultScripts.js')throw Error('Unsupported installed Graphics Settings path');
    const root=await realpath(path.join(path.dirname(defaultPath),'system/settings')),sources={};
    for(const name of Object.keys(GRAPHICS_SOURCE_SHA256))sources[name]=await source(path.join(root,name));
    // Validate the actual package before creating any visitor worker files.
    buildBrowserGraphicsOverrides(sources,'overte.browser.graphics.'+'0'.repeat(32));
    return {sourceHashes:{...GRAPHICS_SOURCE_SHA256},async prepare(directory){
        const channel='overte.browser.graphics.'+randomBytes(16).toString('hex'),generated=buildBrowserGraphicsOverrides(sources,channel),readOnlyOverrides=[];
        const script=path.join(directory,'native-browser-graphics.js');await writeFile(script,nativeGraphicsSource,{mode:0o600,flag:'wx'});
        let index=0;for(const [name,text] of Object.entries(generated)){const filename=path.join(directory,'browser-graphics-override-'+(++index)+(name.endsWith('.qml')?'.qml':'.js'));await writeFile(filename,text,{mode:0o600,flag:'wx'});readOnlyOverrides.push({source:filename,target:path.join(root,name)});}
        return {scriptURL:pathToFileURL(script).href,channel,readOnlyOverrides,schemaVersion:1};
    }};
}
