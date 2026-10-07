// SPDX-License-Identifier: Apache-2.0
// Exact source composition checks. No native/GUI/browser process is started.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const read=path=>readFile(new URL(path,import.meta.url),'utf8');
const hash=source=>createHash('sha256').update(source).digest('hex');
function removeOnce(source,addition){assert.equal(source.split(addition).length,2);return source.replace(addition,'');}
const cpp=await read('../native-input/native-input.cpp');
const qml=await read('./tablet-capture.qml');
const builder=await read('../tools/build-native-input.py');
const worldKeyRecovery=JSON.parse(await read('./fixtures/world-key-historical-recovery.json'));
function recoverWorldKey(kind,source){
 const row=worldKeyRecovery[kind];assert(row);
 assert.equal(hash(source),row.afterSha256,'Exact reviewed current World-X source');
 for(const replacement of row.replacements){
  assert(replacement.after.length>0);
  assert.equal(source.split(replacement.after).length,2,'Exactly one reviewed World-X addition');
  source=source.replace(replacement.after,replacement.before);
 }
 assert.equal(hash(source),row.beforeSha256,'Full reviewed pre-World-X source recovered');
 return source;
}
const historicalCpp=recoverWorldKey('cpp',cpp),historicalQml=recoverWorldKey('qml',qml),historicalBuilder=recoverWorldKey('builder',builder);
const delegate=`    // Use this worker's own original GLCanvas/OffscreenUi route. Native editors
    // retain first refusal; never emit Controller or animation state directly.
    Q_INVOKABLE bool clickApplicationKey(QObject* surface, const QString& key, int modifiers) {
        return BrowserApplicationKey::click(this, ownerItem(), surface, key, modifiers);
    }
`;
test('entire current native text/IME/password/grab CPP is byte-identical after only the owned route additions are removed',()=>{
 const original=removeOnce(removeOnce(historicalCpp,'#include "application-key-route.h"\n'),delegate);
 assert.equal(hash(original),'c4edbad2ea9697cc969b0ab965ad5c834119a553465ae5ef7d95205d73f2d3ca');
 assert.notEqual(hash(original.replace('Qt::ImhHiddenText','Qt::ImhNone')),'c4edbad2ea9697cc969b0ab965ad5c834119a553465ae5ef7d95205d73f2d3ca');
});
test('the entire current captured-surface QML differs only in its ordinary key dispatch branch',()=>{
 const added=`                    if(code!==undefined || (message.key.length===1&&message.key.charCodeAt(0)>=32&&message.key.charCodeAt(0)<=126))
                        accepted=nativeInput.clickApplicationKey(targetItem,message.key,mods);
`;
 const original=`                    if(code!==undefined)accepted=events.keyClick(code,mods,0);
                    else if(message.key.length===1&&message.key.charCodeAt(0)>=32&&message.key.charCodeAt(0)<=126)accepted=events.keyClickChar(message.key,mods,0);
`;
 assert.equal(historicalQml.split(added).length,2);
 assert.equal(hash(historicalQml.replace(added,original)),'f990c2ed3f5b0d68e50b959774214f4b7637e332b1c9613567c8ea9252f5f1bc');
});
test('builder preserves all current package/version/resources/atomic tests and adds only matching Widgets, route tests and attestation',()=>{
 let original=historicalBuilder.replace("for module in ['QtCore', 'QtGui', 'QtQml', 'QtQuick', 'QtWidgets']:","for module in ['QtCore', 'QtGui', 'QtQml', 'QtQuick']:").replace("for module in ['Widgets', 'Quick', 'Qml', 'Gui', 'Core']]","for module in ['Quick', 'Qml', 'Gui', 'Core']]");
 original=removeOnce(original,`    run([moc, *flags[6:], SOURCE / 'application-key-route-test.cpp', '-o', output / 'application-key-route-test.moc'], env=environment)
    run(['g++', *flags, '-I', output, SOURCE / 'application-key-route-test.cpp', '-o', output / 'application-key-route-test', *libraries])
    run(['g++', *flags, SOURCE / 'application-key-code-test.cpp', '-o', output / 'application-key-code-test', *libraries])
`);
 original=original.replace(`        'sourceSha256': hashlib.sha256((SOURCE / 'native-input.cpp').read_bytes()).hexdigest(),
        'applicationKeyRouteSha256': hashlib.sha256((SOURCE / 'application-key-route.h').read_bytes()).hexdigest(),
        'pluginSha256': hashlib.sha256((modules / 'libbrowsernativeinput.so').read_bytes()).hexdigest()}`,`        'sourceSha256': hashlib.sha256((SOURCE / 'native-input.cpp').read_bytes()).hexdigest()}`);
 original=removeOnce(original,`                run([output / 'application-key-code-test'], env=environment)
                run([output / 'application-key-route-test'], env=environment)
`);
 assert.equal(hash(original),'09d1aa93dc612d6a9229ca58ae214b3d4e51bd9bf62009f7ea4d921db51741e4');
});
test('native target/window/focus/class/modifier/lifetime guard header remains the exact reviewed 5cb bytes',async()=>{
 const header=await read('../native-input/application-key-route.h');
 assert.equal(hash(header),'5cb4125f1b309d77a8866311fec4b078486727c82a02d85eda6fe3cdd0dd6203');
 assert(header.includes('QCoreApplication::sendEvent(target.canvas, &press)'));
 assert(header.includes('QCoreApplication::sendEvent(target.canvas, &release)'));
 assert(!header.includes('QCoreApplication::sendEvent(application'));
});
test('explicit authentic native policy changes only the two historically wrong Web global expectations, not literals/deadlines/controls',async()=>{
 const negative=await read('../native-input/application-key-web/key-fixture.qml');
 const authentic=await read('../native-input/application-key-web/authentic-policy/key-fixture.qml');
 assert.equal(hash(authentic),'c59133db99b69f5425b5135d3809ed4e30858fcbaa66a87edbb1fce9092ab009');
 assert.equal(authentic,negative.replace('{kind:"web-disabled",id:"disabled",editable:false,body:true,global:true}', '{kind:"web-disabled",id:"disabled",editable:false,body:true}').replace('{kind:"web-noneditable",id:"body",editable:false,body:true,global:true}', '{kind:"web-noneditable",id:"body",editable:false,body:true}'));
});

test('World-X historical recovery rejects mutations missing duplicated and relocated additions before old composition checks',()=>{
 for(const [kind,value] of [['cpp',cpp],['qml',qml],['builder',builder]]){
  const row=worldKeyRecovery[kind],addition=row.replacements[0].after;
  assert.throws(()=>recoverWorldKey(kind,value+'\n'));
  assert.throws(()=>recoverWorldKey(kind,value.replace(addition,'')));
  assert.throws(()=>recoverWorldKey(kind,value.replace(addition,addition+addition)));
  assert.throws(()=>recoverWorldKey(kind,value.replace(addition,'')+addition));
  assert.throws(()=>recoverWorldKey(kind,value.replace(row.replacements.at(-1).after,row.replacements.at(-1).after+' ')));
 }
});
