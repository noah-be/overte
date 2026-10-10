"""Run the production actor script against explicit native-operation responses."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CollaborationActorTests(unittest.TestCase):
    def test_exact_native_edits_and_failed_observations(self):
        program = r'''
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
function fixture() {
    const posted = [], delayed = [], stored = new Map();
    const actor = 'aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb';
    let command = {schemaVersion:1,pending:false}, interval, editCount = 0, broken = false;
    const context = {
        Agent:{sessionUUID:'{'+actor+'}'}, print:()=>{},
        EntityViewer:{
            setPosition:p=>{assert.deepEqual(JSON.parse(JSON.stringify(p)),{x:0,y:0,z:0});},
            setCenterRadius:r=>{assert.equal(r,1000);},
            queryOctree:()=>{}},
        Script:{resolvePath:p=>p, setTimeout:f=>delayed.push(f), setInterval:f=>{interval=f;}},
        Entities:{serversExist:()=>true,canRez:()=>true,
            findEntities:()=>Array.from(stored.keys()), deleteEntity:id=>stored.delete(id),
            addEntity:(p,host)=>{assert.equal(host,'domain');const id=String(stored.size+1);stored.set(id,JSON.parse(JSON.stringify(p)));return id;},
            getEntityProperties:id=>JSON.parse(JSON.stringify(stored.get(id))),
            editEntity:(id,p)=>{++editCount;stored.set(id,{...stored.get(id),...p});
                if (broken) {stored.get(id).color={red:0,green:0,blue:0};}}},
        XMLHttpRequest:function(){this.open=(method,path)=>{this.method=method;this.path=path;};
            this.setRequestHeader=()=>{};this.send=content=>{
                if(this.method==='POST'){posted.push([this.path,JSON.parse(content)]);return;}
                this.readyState=4;this.status=200;this.responseText=JSON.stringify(command);this.onreadystatechange();};}
    };
    vm.runInNewContext(source,context);
    assert.equal(stored.size,5);
    assert.equal(posted.find(([path])=>path==='domain-ready')[1].markerCount,4);
    assert.equal(posted.find(([path])=>path==='actor-state')[1].actorSessionId,actor);
    return {stored,posted,poll:c=>{command=c;interval();},drain:()=>{while(delayed.length){delayed.shift()();}},
        edits:()=>editCount,breakEdits:()=>{broken=true;},actor};
}
const f=fixture();
const valid={schemaVersion:1,commandId:'1'.repeat(32),entityName:'OVERTE_E2E_SHARED_COLOR',
    revision:1,value:'orange',actorSessionId:f.actor};
const seedCount=f.posted.length;
for(const mutation of [{revision:true},{revision:'1'},{revision:2},{revision:-1},{revision:Infinity},
    {revision:9007199254740992},{value:'red'},{actorSessionId:'bbbbbbbb-1111-2222-3333-aaaaaaaaaaaa'},
    {entityName:'OTHER'},{commandId:'untrusted'}]){f.poll({...valid,...mutation});}
assert.equal(f.edits(),0);
assert.equal(f.posted.length,seedCount);
f.poll(valid);
assert.equal(f.edits(),1);
assert.equal(f.posted.length,seedCount); // A requested edit is not an observation.
f.drain();
const receipt=f.posted[f.posted.length-1][1];
assert.equal(receipt.revision,1);assert.equal(receipt.value,'orange');assert.equal(receipt.commandId,valid.commandId);
f.poll(valid);assert.equal(f.edits(),1); // Duplicate delivery cannot create revision two.
const broken=fixture();broken.breakEdits();const count=broken.posted.length;
broken.poll({...valid,actorSessionId:broken.actor});broken.drain();
assert.equal(broken.edits(),1);assert.equal(broken.posted.length,count); // Wrong actual color never ACKs.
'''
        subprocess.run(['node', '-e', program, str(ROOT / 'fixture/domain_content_agent.js')],
                       check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
