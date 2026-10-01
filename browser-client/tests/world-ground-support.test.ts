// SPDX-License-Identifier: Apache-2.0
// Actual animation/capsule methods with presentation disabled. No GPU/domain claim.
import {test,type TestContext} from 'node:test';
import assert from 'node:assert/strict';
import {Group,Mesh,MeshBasicMaterial,PerspectiveCamera,PlaneGeometry,Vector2,Vector3} from 'three';
import {BrowserWorld} from '../src/world';
import {SimulationClock} from '../src/simulation-clock';
import {InitialSurfaceWait} from '../src/initial-surface-wait';
import {MeshCollision} from '../src/mesh-collision';
import {entityCollider} from '../src/world-data';

function fixture(t:TestContext,floor=true){
 const previous=globalThis.requestAnimationFrame;globalThis.requestAnimationFrame=()=>1;
 t.after(()=>{if(previous)globalThis.requestAnimationFrame=previous;else delete(globalThis as Partial<typeof globalThis>).requestAnimationFrame;});
 const model=new Group(),mesh=new Mesh(new PlaneGeometry(100,100),new MeshBasicMaterial());
 mesh.rotation.x=floor?-Math.PI/2:0;if(!floor)mesh.position.z=100;model.add(mesh);
 const collision=new MeshCollision(model),supports=collision.supports.bind(collision);let supportQueries=0,boundsQueries=0;
 collision.supports=(position,tolerance)=>{supportQueries++;return supports(position,tolerance);};
 t.after(()=>collision.dispose());
 const pending=[entityCollider({id:'unrelated',type:'Model',dimensions:{x:1000,y:1000,z:1000}},new Map())!];
 const some=pending.some.bind(pending);pending.some=(...args)=>{boundsQueries++;return some(...args);};
 const context=Object.create(BrowserWorld.prototype);
 Object.assign(context,{
  disposed:false,enabled:true,simulationClock:new SimulationClock(),initialSurfaceWait:new InitialSurfaceWait(),
  metrics:{sample(){}},pendingModelColliders:pending,objects:new Map([['unrelated',new Group()]]),
  keys:new Set(['KeyW']),touchMove:new Vector2(),yaw:0,pitch:0,
  position:new Vector3(0,.85,0),spawn:new Vector3(0,.85,0),velocity:new Vector3(),grounded:false,
  meshCollisions:new Map([['actual-triangles',{value:collision}]]),colliders:[],
  lastPose:0,lastLightSelection:0,options:{onStatus(){},onPose(){}},camera:new PerspectiveCamera(),thirdPerson:false,
  self:new Group(),avatars:new Map(),localLights:new Set(),pointSlots:[],spotSlots:[],presentationEnabled:false,
 });
 return{context,queries:()=>({supportQueries,boundsQueries})};
}

test('actual World releases initial huge bounds from real triangle support then stops support/bounds queries while walking and jumping',t=>{
 const f=fixture(t),world=f.context;world.animate(1000);assert.equal(world.initialSurfaceWait.state.verified,true);
 const afterSupport=f.queries();world.animate(1250);assert(Math.abs(world.position.z+.7)<1e-8);assert(Math.abs(world.position.y-.85001)<1e-8);
 world.keys.add('Space');world.animate(1500);world.keys.delete('Space');assert(world.position.y>1.1);
 for(let time=1750;time<=2750;time+=250)world.animate(time);
 assert(Math.abs(world.position.y-.85001)<1e-8);assert.deepEqual(f.queries(),afterSupport);
});

test('actual World stops unsuccessful triangle/bounds probes after timeout without pretending an airborne pose has support',t=>{
 const f=fixture(t,false),world=f.context;world.animate(1000);assert.equal(world.initialSurfaceWait.state.waiting,true);
 world.animate(16000);assert.equal(world.initialSurfaceWait.state.expired,true);assert.equal(world.initialSurfaceWait.state.verified,false);
 const afterExpiry=f.queries();world.animate(16250);world.animate(16500);
 assert.deepEqual(f.queries(),afterExpiry);assert(world.position.z<-.5);assert(world.position.y<.85);
});

test('actual fall-to-spawn resets both the initial support episode and elapsed simulation time',t=>{
 const f=fixture(t),world=f.context;world.animate(1000);assert.equal(world.initialSurfaceWait.state.verified,true);
 world.position.y=world.spawn.y-101;world.animate(1000);
 assert(world.position.equals(world.spawn));assert(world.velocity.equals(new Vector3()));assert.equal(world.initialSurfaceWait.state.verified,false);
 world.animate(10000);assert(world.position.equals(world.spawn),'Returning to spawn must not replay a long elapsed interval');
 assert.equal(world.initialSurfaceWait.state.verified,true);
});

test('actual authoritative airborne spawn starts a fresh bounded guard rather than borrowing support from the old floor',t=>{
 const f=fixture(t),world=f.context;world.animate(1000);assert.equal(world.initialSurfaceWait.state.verified,true);
 world.setSpawn({x:0,y:5,z:0});world.animate(2000);world.animate(2250);
 assert.equal(world.initialSurfaceWait.state.verified,false);assert.equal(world.initialSurfaceWait.state.waiting,true);
 assert.equal(world.position.y,5);assert.equal(world.position.z,0);
});
