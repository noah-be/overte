// SPDX-License-Identifier: Apache-2.0
const vm = require('vm'), assert = require('assert'), fs = require('fs');
const source = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const secret = 'CANARY_private_user_path?token=canary_credential';
function harness() {
    const state = { logs: [], errors: [], calls: [], reloads: 0, timers: [], selected: [] };
    const context = vm.createContext({
        console: { log: (...args) => state.logs.push(args.join(' ')) },
        print: (...args) => state.logs.push(args.join(' ')),
        errorMessageBox: text => { state.errors.push(text); return {selected: {connect: f => state.selected.push(f)}}; },
        reload: () => state.reloads++, uploadOpen: false,
        fileDialogHelper: {urlToPath: url => url},
        assetProxyModel: {data: () => '/chosen/'},
        treeView: {selection: {currentIndex: 0}},
        uploadSpinner: {visible: false}, uploadButton: {enabled: true}, uploadProgressLabel: {text: ''},
        timer: {triggered: {connect: f => state.timers.push(f)}, start: () => {}},
        Assets: {
            isKnownFolder: () => false,
            deleteMappings: (paths, callback) => state.calls.push({kind: 'delete',paths,callback}),
            renameMapping: (oldPath,newPath,callback) => state.calls.push({kind:'rename',oldPath,newPath,callback}),
            uploadFile: (file,target,started,callback,dropping) => state.calls.push({kind:'upload',file,target,started,callback,dropping})
        }
    });
    vm.runInContext(source.functions, context);
    return {state,context};
}
function privateLogs(state) {
    assert(!state.logs.join('\n').includes('CANARY'), 'private canary reached diagnostics');
    assert(!state.logs.join('\n').includes('canary_credential'), 'credential reached diagnostics');
    assert(!state.logs.join('\n').includes('/chosen/'), 'mapping reached diagnostics');
}
for (const error of ['', secret]) {
    let {state,context:c} = harness();
    c.doDeleteFile([secret]);
    assert.strictEqual(state.calls.length,1);assert.strictEqual(state.calls[0].paths[0],secret);
    state.calls[0].callback(error);privateLogs(state);
    assert.strictEqual(state.errors.length,error ? 1 : 0);
    if (error) { state.selected[0](); assert.strictEqual(state.reloads,1); }
    else assert.strictEqual(state.reloads,1);
    assert(!Object.prototype.hasOwnProperty.call(c,'box'));

    ({state,context:c}=harness());
    c.doRenameFile('/'+secret+'/',secret);
    assert.strictEqual(state.calls.length,1);
    assert.strictEqual(state.calls[0].newPath,'/'+secret+'/');
    state.calls[0].callback(error);privateLogs(state);
    assert.strictEqual(state.reloads,1);assert.strictEqual(state.errors.length,error ? 1 : 0);
    assert(!Object.prototype.hasOwnProperty.call(c,'box'));
}
{
    const {state,context:c}=harness();c.Assets.isKnownFolder=()=>true;
    c.doRenameFile('/old/', '/existing/');
    assert.strictEqual(state.errors.length,1);
    assert.strictEqual(state.calls.length,0,'known directory must stop before rename');
}
for (const error of ['',secret,-1]) {
    const {state,context:c}=harness();
    c.uploadClicked('/local/'+secret);
    assert(c.uploadOpen);assert.strictEqual(state.calls.length,1);
    c.uploadClicked('/duplicate');assert.strictEqual(state.calls.length,1);
    const call=state.calls[0];assert.strictEqual(call.file,'/local/'+secret);
    assert.strictEqual(call.target,'/chosen/'+secret);assert.strictEqual(call.dropping,true);
    call.started();assert(c.uploadSpinner.visible);assert(!c.uploadButton.enabled);
    call.callback(error,'/chosen/'+secret);
    if (error==='') {assert.strictEqual(state.timers.length,1);state.timers[0]();assert.strictEqual(state.reloads,1);}
    assert(!c.uploadSpinner.visible);assert(c.uploadButton.enabled);assert(!c.uploadOpen);
    assert.strictEqual(state.errors.length,error!=='' && error!==-1 ? 1 : 0);
    privateLogs(state);
}
{
    const {state,context:c}=harness();
    Object.assign(c,{paths:[secret],oldPath:secret,newPath:secret,url:secret,name:secret,fileUrl:secret,err:secret,path:secret,mappings:[secret],checked:true});
    for (const diagnostic of source.diagnostics) vm.runInContext(diagnostic,c);
    privateLogs(state);
    assert(state.logs.length>0);
}
