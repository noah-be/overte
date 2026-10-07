// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
interface Node {name:string;properties:Uint8Array[];children:Node[]}
const text=new TextEncoder();
function property(value:string|number|Uint8Array){
 if(typeof value==='number'){const out=new Uint8Array(9);out[0]=68;new DataView(out.buffer).setFloat64(1,value,true);return out;}
 const bytes=typeof value==='string'?text.encode(value):value,out=new Uint8Array(5+bytes.length);out[0]=typeof value==='string'?83:82;new DataView(out.buffer).setUint32(1,bytes.length,true);out.set(bytes,5);return out;
}
function n(name:string,values:(string|number|Uint8Array)[]=[],children:Node[]=[]):Node{return {name,properties:values.map(property),children};}
function array(name:string,values:number[],integer=false):Node{const width=integer?4:8,out=new Uint8Array(13+width*values.length),view=new DataView(out.buffer);out[0]=integer?105:100;view.setUint32(1,values.length,true);view.setUint32(9,values.length*width,true);values.forEach((v,i)=>integer?view.setInt32(13+width*i,v,true):view.setFloat64(13+width*i,v,true));return {name,properties:[out],children:[]};}
export const admissionPNG=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=='),c=>c.charCodeAt(0));
export function replacementMaterialFbx(options:{ignoredSlot?:string;ignoredDDS?:boolean; mixedConsumer?:boolean; videoShared?:boolean; unknownIncoming?:boolean; noVideo?:boolean;vertexColors?:boolean;wide?:boolean;embedded?:boolean;duplicateVideoName?:boolean;unknownTextureConsumer?:boolean;skin?:boolean;nativeEndRecords?:boolean;invalidUnnamedNode?:'object'|'connection'|'objectChildren';ambiguousID?:'duplicate'|'nonnumeric'|'unsafe'|'negative';withoutOriginalTextures?:boolean}={}){
 const wide=options.wide??false;
 const videos=[['Shared','shared.png'],['OnlyA',options.duplicateVideoName?'shared.png':options.ignoredDDS?'unused-a.dds':'unused-a.png'],['OnlyB','only-b.png']];
 const roots=[n('FBXHeaderExtension',[],[n('FBXVersion',[wide?7500:7400])]),n('Objects',[],[
  ...(options.invalidUnnamedNode==='object'?[n('',['NotAnObjectID'])]:options.invalidUnnamedNode==='objectChildren'?[n('',[],[n('Unknown')])]:[]),
  ...(options.ambiguousID?[n('Unknown',[options.ambiguousID==='duplicate'?101:options.ambiguousID==='nonnumeric'?'NotAnObjectID':options.ambiguousID==='unsafe'?2**53:-10])]:[]),
  n('Geometry',[1,'FixtureGeometry\0\x01Geometry','Mesh'],[
   array('Vertices',[-.9,-.6,0,-.1,-.6,0,-.5,.6,0,.1,-.6,0,.9,-.6,0,.5,.6,0]),array('PolygonVertexIndex',[0,1,-3,3,4,-6],true),
   n('LayerElementNormal',[0],[n('Version',[101]),n('Name',['']),n('MappingInformationType',['ByVertice']),n('ReferenceInformationType',['Direct']),array('Normals',Array.from({length:6},()=>[0,0,1]).flat())]),
   n('LayerElementUV',[0],[n('Version',[101]),n('Name',['uv']),n('MappingInformationType',['ByVertice']),n('ReferenceInformationType',['Direct']),array('UV',[0,0,1,0,.5,1,0,0,1,0,.5,1])]),
   ...(options.vertexColors?[n('LayerElementColor',[0],[n('Version',[101]),n('Name',['color']),n('MappingInformationType',['ByVertice']),n('ReferenceInformationType',['Direct']),array('Colors',[1,.4,.2,1,1,.4,.2,1,1,.4,.2,1,.2,.8,1,1,.2,.8,1,1,.2,.8,1,1])])]:[]),
   n('LayerElementMaterial',[0],[n('Version',[101]),n('Name',['']),n('MappingInformationType',['ByPolygon']),n('ReferenceInformationType',['IndexToDirect']),array('Materials',[0,1],true)]),
  ]),n('Model',[10,'FixtureModel\0\x01Model','Mesh']),
  ...['A','B'].map((label,index)=>n('Material',[101+index,label+'\0\x01Material',''],[n('ShadingModel',['phong'])])),
  ...videos.map(([label,file],index)=>n('Texture',[301+index,label+'\0\x01Texture','TextureVideoClip'],[n('FileName',[file]),n('RelativeFilename',[file]),n('WrapModeU',[1]),n('WrapModeV',[0])])),
  ...videos.map(([label,file],index)=>n('Video',[401+index,label+'\0\x01Video','Clip'],[n('Filename',[file]),n('RelativeFilename',[file]),...(options.embedded?[n('Content',[new Uint8Array([...admissionPNG,...Array(index).fill(0)])])]:[])])),
  ...(options.skin?[n('Model',[11,'Hips\0\x01Model','LimbNode']),n('Deformer',[500,'Skin\0\x01Deformer','Skin']),n('Deformer',[501,'Cluster\0\x01Deformer','Cluster'],[array('Indexes',[0,1,2,3,4,5],true),array('Weights',[1,1,1,1,1,1]),array('Transform',[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]),array('TransformLink',[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])])]:[]),
 ]),n('Connections',[],[
  ...(options.invalidUnnamedNode==='connection'?[n('',['OO',1,10])]:[]),
  n('C',['OO',1,10]),n('C',['OO',101,10]),n('C',['OO',102,10]),n('C',['OO',10,0]),
  n('C',['OO',401,301]),...(options.noVideo?[]:[n('C',['OO',402,302])]),n('C',['OO',403,303]),
  n('C',['OP',301,101,'DiffuseColor']),n('C',['OP',301,102,'DiffuseColor']),n('C',['OP',302,101,options.ignoredSlot||'NormalMap']),n('C',['OP',303,102,'NormalMap']),
  ...(options.skin?[n('C',['OO',500,1]),n('C',['OO',501,500]),n('C',['OO',11,501]),n('C',['OO',11,0])]:[]),
  ...(options.mixedConsumer?[n('C',['OP',302,102,'DiffuseColor'])]:[]),
  ...(options.videoShared?[n('C',['OO',402,303])]:[]),
  ...(options.unknownIncoming?[n('C',['OO',10,302])]:[]),
  ...(options.unknownTextureConsumer?[n('C',['OP',302,999,'UnknownConsumer'])]:[]),
 ])];
 if(options.withoutOriginalTextures){roots[1].children=roots[1].children.filter(child=>!['Texture','Video'].includes(child.name));roots[2].children=roots[2].children.filter(child=>{const childID=new DataView(child.properties[1].buffer).getFloat64(1,true),parentID=new DataView(child.properties[2].buffer).getFloat64(1,true);return ![301,302,303,401,402,403].includes(childID)&&![301,302,303,401,402,403].includes(parentID);});}
 const header=wide?25:13,size=(v:Node):number=>header+text.encode(v.name).length+v.properties.reduce((sum,p)=>sum+p.length,0)+v.children.reduce((sum,c)=>sum+size(c),0)+(v.children.length?header:0);
 const out=new Uint8Array(27+roots.reduce((sum,r)=>sum+size(r),0)+header+176),view=new DataView(out.buffer);out.set(text.encode('Kaydara FBX Binary  \0\x1a\0'));view.setUint32(23,wide?7500:7400,true);
 const integer=(at:number,v:number)=>wide?view.setBigUint64(at,BigInt(v),true):view.setUint32(at,v,true);
 const write=(v:Node,at:number):number=>{const end=at+size(v),label=text.encode(v.name);integer(at,end);integer(at+(wide?8:4),v.properties.length);integer(at+(wide?16:8),v.properties.reduce((sum,p)=>sum+p.length,0));out[at+header-1]=label.length;at+=header;out.set(label,at);at+=label.length;for(const p of v.properties){out.set(p,at);at+=p.length;}for(const c of v.children)at=write(c,at);if(options.nativeEndRecords&&v.children.length)integer(at,end);return end;};
 let at=27;for(const root of roots)at=write(root,at);return out.buffer;
}

export const replacementRGBA=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGNg+A+GDAwM/xkaQEwAN10GewTS8ikAAAAASUVORK5CYII='),value=>value.charCodeAt(0));
