// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from'node:assert/strict';import{BoxGeometry,Group,Mesh,MeshStandardMaterial,Texture}from'three';import{ReplacementMaterialClones}from'../../src/replacement-material-clones.ts';import{ModelResources}from'../../src/model-resources.ts';
assert.equal(typeof globalThis.gc,'function');let bank;let refs;
function create(){const template=new MeshStandardMaterial(),texture=new Texture({width:1,height:1}),resources=new ModelResources(),root=new Group();template.map=texture;const mesh=new Mesh(new BoxGeometry());root.add(mesh);resources.captureMaterial(template);bank=new ReplacementMaterialClones(template,resources,undefined,()=>{assert.equal(root.children.length,1);});const clone=bank.forMesh(mesh);assert.ok(clone);mesh.material=clone;resources.capture(root);refs=[template,resources,root,texture,clone].map(value=>new WeakRef(value));bank.close();resources.releaseKeeping();}
create();for(let i=0;i<80;i++){await new Promise(resolve=>setImmediate(resolve));globalThis.gc();await new Promise(resolve=>setImmediate(resolve));if(refs.every(ref=>ref.deref()===undefined))break;}
assert.equal(refs.filter(ref=>ref.deref()===undefined).length,5);assert.equal(bank.snapshot().created,1);console.log(JSON.stringify({bankRetained:true,weakReferences:5,released:5}));
