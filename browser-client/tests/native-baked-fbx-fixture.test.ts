// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import createDecoder from 'draco3d/draco_decoder_nodejs.js';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {type Mesh, type SkinnedMesh} from 'three';
import {adaptBakedFbx,normalizeNativeFbxTransparency,type BakedDracoDecoder} from '../src/baked-fbx';
import {createNativeBakedFbxFixture} from './fixtures/native-baked-fbx.mjs';
const d=createDecoder({TOTAL_MEMORY:64*1024*1024,print:()=>{},printErr:()=>{}});
const decode:BakedDracoDecoder=async(bytes,options)=>{
  const decoder=new d.Decoder(),buffer=new d.DecoderBuffer(),mesh=new d.Mesh();let status:any;
  try{buffer.Init(new Int8Array(bytes),bytes.byteLength);status=decoder.DecodeBufferToMesh(buffer,mesh);assert(status.ok(),status.error_msg());
    const attribute=(semantic:number,width:number,unique=false)=>{const id=unique?semantic:decoder.GetAttributeId(mesh,semantic);assert(id>=0);const attribute=unique?decoder.GetAttributeByUniqueId(mesh,id):decoder.GetAttribute(mesh,id);assert(attribute.ptr);assert.equal(attribute.num_components(),width);const data=new d.DracoFloat32Array();try{assert(decoder.GetAttributeFloatForAllPoints(mesh,attribute,data));return Float32Array.from({length:data.size()},(_,i)=>data.GetValue(i));}finally{d.destroy(data);}};
    const indices=new Uint32Array(mesh.num_faces()*3),face=new d.DracoInt32Array();try{for(let i=0;i<mesh.num_faces();i++){assert(decoder.GetFaceFromMesh(mesh,i,face));for(let j=0;j<3;j++)indices[i*3+j]=face.GetValue(j);}}finally{d.destroy(face);}
    return{positions:attribute(d.POSITION,3),normals:attribute(d.NORMAL,3),uv:attribute(d.TEX_COORD,2),indices,...(options.materialIDs?{materialIDs:attribute(1000,1,true)}:{}),...(options.uv1?{uv1:attribute(1001,2,true)}:{}),...(options.originalIndices?{originalIndices:attribute(1002,1,true)}:{})};
  }finally{for(const value of [status,mesh,buffer,decoder])if(value)d.destroy(value);}
};
for(const custom of [false,true])test(`authored actual Draco fixture preserves ${custom?'native IDs1000–1002,UV1 and skin remap':'ordinary geometry and UVs'}`,async()=>{
  const fixture=createNativeBakedFbxFixture(custom);assert(fixture.buffer.byteLength<32*1024);assert(fixture.encoded.byteLength>5);
  const decoded=await decode(fixture.encoded,{materialIDs:custom,uv1:custom,originalIndices:custom});
  assert.deepEqual(Array.from(decoded.positions),[...fixture.positions]);assert.deepEqual(Array.from(decoded.uv!),[...fixture.uv]);
  if(custom){assert.deepEqual(Array.from(decoded.materialIDs!),[...fixture.materialIDs!]);assert.deepEqual(Array.from(decoded.uv1!),[...fixture.uv1!]);assert.deepEqual(Array.from(decoded.originalIndices!),[...fixture.originalIndices!]);}
  const restored=await adaptBakedFbx(normalizeNativeFbxTransparency(fixture.buffer),decode);
  const root=new FBXLoader().parse(restored,'');let mesh:Mesh|undefined;root.traverse(object=>{if((object as Mesh).isMesh)mesh=object as Mesh;});assert(mesh);
  assert.equal(mesh.geometry.attributes.position.count,6);assert.equal(mesh.geometry.groups.length,custom?2:1);
  if(custom){assert.equal(mesh.geometry.attributes.uv1.count,6);assert.equal((mesh as SkinnedMesh).skeleton.bones.length,2);
    // Original source indices are intentionally reversed: the first triangle
    // must bind JointB and the second JointA after actual native remapping.
    for(let i=0;i<6;i++){assert.equal(mesh.geometry.attributes.skinIndex.getX(i),i<3?1:0);assert.equal(mesh.geometry.attributes.skinWeight.getX(i),1);}
  }
});
