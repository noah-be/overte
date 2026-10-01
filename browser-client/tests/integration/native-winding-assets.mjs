// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Small indexed native-readable glTF; identical authored mesh in both nodes.
export function nativeWindingAsset(){
 const positions=new Float32Array([-1,-1,.1,1,-1,.1,0,1,.1,-1,-1,0,0,1,0,1,-1,0]);
 const normals=new Float32Array(Array.from({length:18},(_,i)=>i%3===2?1:0));
 const colors=new Float32Array([1,0,0,1,0,0,1,0,0,0,1,0,0,1,0,0,1,0]);
 const indices=new Uint16Array([0,1,2,3,4,5]),arrays=[positions,normals,colors,indices];
 let offset=0;const bufferViews=arrays.map(array=>{const result={buffer:0,byteOffset:offset,byteLength:array.byteLength};offset+=array.byteLength;return result;});
 const bytes=Buffer.concat(arrays.map(array=>Buffer.from(array.buffer)));
 return {asset:{version:'2.0'},scene:0,scenes:[{nodes:[0,1]}],nodes:[{name:'positive',mesh:0,translation:[-1.5,0,0]},{name:'mirrored',mesh:0,translation:[1.5,0,0],scale:[-1,1,1]}],
  meshes:[{primitives:[{attributes:{POSITION:0,NORMAL:1,COLOR_0:2},indices:3,material:0}]}],
  materials:[{name:'native-default-back',pbrMetallicRoughness:{baseColorFactor:[1,1,1,1],metallicFactor:0,roughnessFactor:1}}],
  buffers:[{byteLength:bytes.length,uri:'data:application/octet-stream;base64,'+bytes.toString('base64')}],bufferViews,
  accessors:[{bufferView:0,componentType:5126,count:6,type:'VEC3',min:[-1,-1,0],max:[1,1,.1]},{bufferView:1,componentType:5126,count:6,type:'VEC3'},{bufferView:2,componentType:5126,count:6,type:'VEC3'},{bufferView:3,componentType:5123,count:6,type:'SCALAR',min:[0],max:[5]}]};
}

export const nativeWindingCases=Object.freeze([
 {name:'default-back',cull:null,unlit:true,lightDirection:{x:0,y:0,z:-1},dominant:['red','green']},
 {name:'back',cull:'CULL_BACK',unlit:true,lightDirection:{x:0,y:0,z:-1},dominant:['red','green']},
 {name:'front',cull:'CULL_FRONT',unlit:true,lightDirection:{x:0,y:0,z:-1},dominant:['green','red']},
 {name:'none',cull:'CULL_NONE',unlit:true,lightDirection:{x:0,y:0,z:-1},dominant:['red','red']},
 {name:'lit-towards-viewer',cull:'CULL_NONE',unlit:false,lightDirection:{x:0,y:0,z:-1},brighter:'positive'},
 {name:'lit-away-from-viewer',cull:'CULL_NONE',unlit:false,lightDirection:{x:0,y:0,z:1},brighter:'mirrored'},
]);
