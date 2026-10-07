// SPDX-License-Identifier: Apache-2.0
// Authored geometry encoded by the real pinned Google Draco 1.3.4 API.
// No cached/public-world bytes, mocked decoder or encoded-byte patching.
import draco3d from 'draco3d';
import assert from 'node:assert/strict';
let codec;
const positions=new Float32Array([0,0,0,1,0,0,0,0,1,2,0,0,3,0,0,2,0,1]);
const uv=new Float32Array([0,0,1,0,0,1,0,0,1,0,0,1]);
const uv1=new Float32Array([.25,.25,.5,.25,.25,.5,.5,.5,.75,.5,.5,.75]);
const originalIndices=new Int32Array([5,4,3,2,1,0]);
const materialIDs=new Int32Array([0,0,0,1,1,1]);
function encode(custom) {
  const d=codec??=draco3d.createEncoderModule({print:()=>{},printErr:()=>{}});
  const builder=new d.MeshBuilder(),mesh=new d.Mesh(),encoder=new d.Encoder(),output=new d.DracoInt8Array();
  try {
    assert(builder.AddFacesToMesh(mesh,2,new Uint32Array([0,1,2,3,4,5])));
    assert.equal(builder.AddFloatAttributeToMesh(mesh,d.POSITION,6,3,positions),0);
    assert.equal(builder.AddFloatAttributeToMesh(mesh,d.NORMAL,6,3,new Float32Array([0,1,0,0,1,0,0,1,0,0,1,0,0,1,0,0,1,0])),1);
    assert.equal(builder.AddFloatAttributeToMesh(mesh,d.TEX_COORD,6,2,uv),2);
    if(custom){
      // The official JS API has no unique-ID setter. Real sequential attribute
      // allocation reaches native IDs without altering any encoded payload.
      for(let id=3;id<1000;id++)assert.equal(builder.AddInt32AttributeToMesh(mesh,d.GENERIC,6,1,new Int32Array(6).fill(id)),id);
      assert.equal(builder.AddInt32AttributeToMesh(mesh,d.GENERIC,6,1,materialIDs),1000);
      assert.equal(builder.AddFloatAttributeToMesh(mesh,d.GENERIC,6,2,uv1),1001);
      assert.equal(builder.AddInt32AttributeToMesh(mesh,d.GENERIC,6,1,originalIndices),1002);
    }
    encoder.SetSpeedOptions(10,10);encoder.SetEncodingMethod(d.MESH_SEQUENTIAL_ENCODING);
    const length=encoder.EncodeMeshToDracoBuffer(mesh,output);assert(length>0&&length<64*1024);
    const bytes=new Uint8Array(length);for(let i=0;i<length;i++)bytes[i]=output.GetValue(i)&255;
    return bytes;
  }finally{for(const value of [output,encoder,mesh,builder])d.destroy(value);}
}
function property(value){
  if(typeof value==='number'){const bytes=new Uint8Array(9);bytes[0]=68;new DataView(bytes.buffer).setFloat64(1,value,true);return bytes;}
  const data=typeof value==='string'?new TextEncoder().encode(value):value;
  const bytes=new Uint8Array(5+data.length);bytes[0]=83;new DataView(bytes.buffer).setUint32(1,data.length,true);bytes.set(data,5);return bytes;
}
const n=(name,values=[],children=[])=>({name,props:values.map(property),children});
function array(name,values,integer=false){
  const width=integer?4:8,bytes=new Uint8Array(13+values.length*width),view=new DataView(bytes.buffer);
  bytes[0]=(integer?'i':'d').charCodeAt(0);view.setUint32(1,values.length,true);view.setUint32(5,0,true);view.setUint32(9,values.length*width,true);
  for(let i=0;i<values.length;i++)if(integer)view.setInt32(13+i*width,values[i],true);else view.setFloat64(13+i*width,values[i],true);
  return{name,props:[bytes],children:[]};
}
function serialize(roots){
  const header=13,text=new TextEncoder();
  const size=node=>header+text.encode(node.name).length+node.props.reduce((sum,bytes)=>sum+bytes.length,0)+node.children.reduce((sum,node)=>sum+size(node),0)+(node.children.length?header:0);
  const result=new Uint8Array(27+roots.reduce((sum,node)=>sum+size(node),0)+header+176),view=new DataView(result.buffer);
  result.set(text.encode('Kaydara FBX Binary  \0\x1a\0'));view.setUint32(23,7400,true);
  const write=(node,at)=>{const end=at+size(node),name=text.encode(node.name);view.setUint32(at,end,true);view.setUint32(at+4,node.props.length,true);view.setUint32(at+8,node.props.reduce((sum,bytes)=>sum+bytes.length,0),true);result[at+12]=name.length;at+=header;result.set(name,at);at+=name.length;for(const bytes of node.props){result.set(bytes,at);at+=bytes.length;}for(const child of node.children)at=write(child,at);return end;};
  let at=27;for(const root of roots)at=write(root,at);return result.buffer;
}
export function createNativeBakedFbxFixture(custom=false){
  const encoded=encode(custom),identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  const geometryChildren=[n('DracoMesh',[encoded],[n('MaterialList',custom?['101','102']:['101'])])];
  if(custom)geometryChildren.push(n('Layer',[1],[n('LayerElement',[],[n('Type',['LayerElementUV']),n('TypedIndex',[1])])]));
  const objects=[n('Geometry',[1,'AuthoredGeometry\0\x01Geometry','Mesh'],geometryChildren),n('Model',[10,'AuthoredModel\0\x01Model','Mesh']),...Array.from({length:custom?2:1},(_,i)=>n('Material',[101+i,'AuthoredMaterial'+i+'\0\x01Material',''],[n('ShadingModel',['phong'])]))];
  const connections=[n('C',['OO',1,10]),n('C',['OO',101,10]),n('C',['OO',10,0])];if(custom)connections.push(n('C',['OO',102,10]));
  if(custom){
    objects.push(n('Model',[20,'JointA\0\x01Model','LimbNode']),n('Model',[21,'JointB\0\x01Model','LimbNode']),n('Deformer',[200,'Skin\0\x01Deformer','Skin']));connections.push(n('C',['OO',200,1]),n('C',['OO',20,0]),n('C',['OO',21,20]));
    for(let i=0;i<2;i++){objects.push(n('Deformer',[201+i,'Cluster'+i+'\0\x01Deformer','Cluster'],[array('Indexes',i?[3,4,5]:[0,1,2],true),array('Weights',[1,1,1]),array('Transform',identity),array('TransformLink',identity)]));connections.push(n('C',['OO',201+i,200]),n('C',['OO',20+i,201+i]));}
  }
  return {buffer:serialize([n('FBXHeaderExtension',[],[n('FBXVersion',[7400])]),n('Objects',[],objects),n('Connections',[],connections)]),encoded:encoded.buffer,custom,positions:positions.slice(),uv:uv.slice(),uv1:custom?uv1.slice():undefined,materialIDs:custom?materialIDs.slice():undefined,originalIndices:custom?originalIndices.slice():undefined};
}
