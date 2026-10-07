// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {VisitorPreferenceStore} from './visitor-preferences.ts';
const KEY = 'overte.browser.visitor-preferences.v1';
function memory() {
    const values = new Map<string,string>(), notices:string[] = [];
    const storage = {getItem:(key:string) => values.get(key) ?? null,setItem:(key:string,value:string) => {values.set(key,value);}};
    return {values,notices,storage,create:() => new VisitorPreferenceStore(storage,message=>notices.push(message))};
}
test('visitor bookmarks and home survive fresh store/session instances without shared object mutation', () => {
    const fixture = memory(), store = fixture.create();
    store.update({bookmarks:[{name:'Überte 世界 👋',address:'overte://overte_hub/1,2,3/0,0,0,1'}],home:'overte://overte_hub'});
    const snapshot = store.snapshot(); snapshot.bookmarks[0].name = 'foreign change';
    assert.equal(store.snapshot().bookmarks[0].name,'Überte 世界 👋');
    assert.deepEqual(fixture.create().snapshot(),store.snapshot());
    assert.equal(fixture.notices.length,0);
});
test('invalid saved data is preserved and foreign storage keys are never copied into a worker', () => {
    const fixture = memory(); fixture.values.set(KEY,'{"bookmarks":[{"name":"private","address":"file:///operator/profile"}]}');
    fixture.values.set('foreign-account-token','synthetic other app value');
    const original = fixture.values.get(KEY), store = fixture.create();
    assert.deepEqual(store.snapshot(),{bookmarks:[]}); assert.equal(fixture.values.get(KEY),original);
    assert.equal(fixture.values.get(`${KEY}.recovery`),original);
    store.update({bookmarks:[{name:'Hub',address:'overte://overte_hub'}]});
    assert.equal(fixture.values.get(`${KEY}.recovery`),original);
    assert.equal(fixture.values.get('foreign-account-token'),'synthetic other app value');
    assert.equal(fixture.notices.length,1);
});
test('storage refusal retains current visitor changes and reports the real failure', () => {
    const notices:string[] = [];
    const store = new VisitorPreferenceStore({getItem:()=>null,setItem:()=>{throw Error('quota');}},message=>notices.push(message));
    store.update({bookmarks:[{name:'Hub',address:'overte://overte_hub'}]});
    assert.equal(store.snapshot().bookmarks.length,1); assert.match(notices[0],/could not save/);
    assert.throws(()=>store.update({bookmarks:[{name:'Unsupported resource',address:'qrc:/operator'}]}));
    assert.equal(store.snapshot().bookmarks.length,1);
});

test('an unreadable original cannot be overwritten when bounded recovery cannot preserve it', () => {
    for (const reason of ['quota','oversize','different-recovery']) {
        const fixture = memory(), original = reason === 'oversize' ? 'x'.repeat(192 * 1024 + 1) : '{invalid record';
        fixture.values.set(KEY,original);
        if (reason === 'different-recovery') fixture.values.set(`${KEY}.recovery`,'an earlier distinct record');
        const storage = {...fixture.storage,setItem:(key:string,value:string) => {
            if (reason === 'quota' && key.endsWith('.recovery')) throw Error('quota');
            fixture.storage.setItem(key,value);
        }};
        const store = new VisitorPreferenceStore(storage,message=>fixture.notices.push(message));
        store.update({bookmarks:[{name:'Hub',address:'overte://overte_hub'}]});
        assert.equal(store.snapshot().bookmarks.length,1);
        assert.equal(fixture.values.get(KEY),original);
        assert.match(fixture.notices.at(-1)!,/cannot be backed up/);
        if (reason === 'oversize') assert.equal(fixture.values.has(`${KEY}.recovery`),false);
    }
});
