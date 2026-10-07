// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Group,Mesh,MeshBasicMaterial,PlaneGeometry,Vector3} from 'three';
import {MeshCollision} from '../src/mesh-collision';
import {InitialSurfaceWait} from '../src/initial-surface-wait';
import {PLAYER_HALF_HEIGHT,PLAYER_RADIUS} from '../src/world-data';
function floor(angle=0,width=20){const root=new Group(),mesh=new Mesh(new PlaneGeometry(width,20),new MeshBasicMaterial());mesh.rotation.x=-Math.PI/2;root.add(mesh);root.rotation.z=angle;return{root,collision:new MeshCollision(root)};}
test('actual floor support is nonmutating and its 20mm tolerance does not turn airborne poses into ground',()=>{
 const {collision}=floor(),position=new Vector3(0,.85,0),before=position.clone();assert.equal(collision.supports(position),true);assert(position.equals(before));
 assert.equal(collision.supports(new Vector3(0,.85+.019999,0)),true);assert.equal(collision.supports(new Vector3(0,.85+.020001,0)),false);
 assert.equal(collision.supports(new Vector3(0,1.5,0)),false);assert.equal(collision.supports(new Vector3(0,-.85,0)),false);assert.equal(collision.supports(new Vector3(NaN,.85,0)),false);assert.throws(()=>collision.supports(position,.1),/tolerance/);collision.dispose();
});
test('genuine sloping floor and ledge contacts match capsule geometry rather than a center-only ray',()=>{
 const angle=.7,{collision}=floor(angle),position=new Vector3(0,PLAYER_HALF_HEIGHT-PLAYER_RADIUS+PLAYER_RADIUS/Math.cos(angle),0);assert.equal(collision.supports(position),true);
 const resolved=position.clone().add(new Vector3(0,-.01,0)),normal=collision.resolve(resolved);assert(normal&&normal.y>.5);collision.dispose();
 const edge=floor(0,2);assert.equal(edge.collision.supports(new Vector3(1.15,.8,0),0),true);assert.equal(edge.collision.supports(new Vector3(1.4,.8,0)),false);edge.collision.dispose();
 const steep=floor(1.3);assert.equal(steep.collision.supports(new Vector3(0,PLAYER_HALF_HEIGHT-PLAYER_RADIUS+PLAYER_RADIUS/Math.cos(1.3),0)),false);steep.collision.dispose();
});
test('nearby wall/ceiling geometry cannot qualify and native movement requires refreshed world-space triangles',()=>{
 const root=new Group(),wall=new Mesh(new PlaneGeometry(20,20),new MeshBasicMaterial());wall.rotation.y=Math.PI/2;wall.position.x=.1;root.add(wall);
 const ceiling=new Mesh(new PlaneGeometry(20,20),new MeshBasicMaterial());ceiling.rotation.x=-Math.PI/2;ceiling.position.y=.35;root.add(ceiling);const collision=new MeshCollision(root);assert.equal(collision.supports(new Vector3(0,.85,0)),false);collision.dispose();
 const f=floor();assert.equal(f.collision.supports(new Vector3(0,.85,0)),true);f.root.position.y=3;const refreshed=new MeshCollision(f.root);assert.equal(refreshed.supports(new Vector3(0,.85,0)),false);assert.equal(refreshed.supports(new Vector3(0,3.85,0)),true);f.collision.dispose();assert.equal(f.collision.supports(new Vector3(0,.85,0)),false);assert.equal(f.collision.resolve(new Vector3(0,.75,0)),undefined);refreshed.dispose();
});
test('huge pending bounds delay only unsupported initial spawn, never establish support and release on genuine floor contact',()=>{
 const episode=new InitialSurfaceWait();assert.deepEqual(episode.update(100,true,false),{waiting:true,started:true});assert.equal(episode.state.verified,false);
 assert.equal(episode.update(1000,true,true).waiting,false);assert.equal(episode.state.verified,true);
 // Feet leave the floor during a legitimate jump/fall. Unrelated pending
 // bounds cannot reactivate the already released initial safeguard.
 assert.equal(episode.update(1500,true,false).waiting,false);assert.equal(episode.update(5000,true,false).waiting,false);
 episode.reset();assert.equal(episode.state.verified,false);assert.equal(episode.update(6000,true,false).waiting,true);
});
test('initial waiting retains its 15-second spawn scope across temporary missing bounds and clock regression',()=>{
 const episode=new InitialSurfaceWait();assert.equal(episode.update(0,true,false).waiting,true);assert.equal(episode.update(1000,false,false).waiting,false);
 assert.equal(episode.update(14999,true,false).waiting,true);assert.equal(episode.update(15000,true,false).waiting,false);assert.equal(episode.needsSupport,false);assert.equal(episode.state.expired,true);assert.equal(episode.state.verified,false);assert.equal(episode.update(100,true,false).waiting,false);assert.equal(episode.update(100000,true,false).started,false);
 episode.reset();assert.equal(episode.needsSupport,true);assert.equal(episode.state.expired,false);assert.deepEqual(episode.update(20000,false,false),{waiting:false,started:false});assert.equal(episode.update(21000,true,false).waiting,true);assert.throws(()=>episode.update(NaN,true,false),/timestamp/);
});
