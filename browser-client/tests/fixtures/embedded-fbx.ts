// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Ordinary authored binary FBX, with exact raw PNG content; no public data.
interface Node {name:string;properties:Uint8Array[];children:Node[]}
const text=new TextEncoder();
function property(value:string|number|Uint8Array){
 if(typeof value==='number'){const out=new Uint8Array(9);out[0]=68;new DataView(out.buffer).setFloat64(1,value,true);return out;}
 const bytes=typeof value==='string'?text.encode(value):value,out=new Uint8Array(5+bytes.length);out[0]=typeof value==='string'?83:82;new DataView(out.buffer).setUint32(1,bytes.length,true);out.set(bytes,5);return out;
}
function n(name:string,values:(string|number|Uint8Array)[]=[],children:Node[]=[]):Node{return {name,properties:values.map(property),children};}
function array(name:string,values:number[],integer=false):Node{const width=integer?4:8,out=new Uint8Array(13+width*values.length),view=new DataView(out.buffer);out[0]=integer?105:100;view.setUint32(1,values.length,true);view.setUint32(9,values.length*width,true);values.forEach((v,i)=>integer?view.setInt32(13+width*i,v,true):view.setFloat64(13+width*i,v,true));return {name,properties:[out],children:[]};}
export const embeddedPNG=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=='),c=>c.charCodeAt(0));
export function embeddedFbx(bytes=embeddedPNG,extension='png',wide=false){
 const roots=[n('FBXHeaderExtension',[],[n('FBXVersion',[wide?7500:7400])]),n('Objects',[],[
  n('Geometry',[1,'FixtureGeometry\0\x01Geometry','Mesh'],[array('Vertices',[0,0,0,1,0,0,0,1,0]),array('PolygonVertexIndex',[0,1,-3],true)]),
  n('Model',[10,'FixtureModel\0\x01Model','Mesh']),n('Material',[101,'FixtureMaterial\0\x01Material',''],[n('ShadingModel',['phong'])]),
  n('Texture',[301,'FixtureTexture\0\x01Texture','TextureVideoClip'],[n('FileName',['embedded.'+extension]),n('RelativeFilename',['embedded.'+extension])]),
  n('Video',[401,'FixtureVideo\0\x01Video','Clip'],[n('Filename',['embedded.'+extension]),n('RelativeFilename',['embedded.'+extension]),n('Content',[bytes])]),
 ]),n('Connections',[],[n('C',['OO',1,10]),n('C',['OO',101,10]),n('C',['OO',10,0]),n('C',['OO',401,301]),n('C',['OP',301,101,'DiffuseColor'])])];
 const header=wide?25:13,size=(v:Node):number=>header+text.encode(v.name).length+v.properties.reduce((sum,p)=>sum+p.length,0)+v.children.reduce((sum,c)=>sum+size(c),0)+(v.children.length?header:0);
 const out=new Uint8Array(27+roots.reduce((sum,r)=>sum+size(r),0)+header+176),view=new DataView(out.buffer);out.set(text.encode('Kaydara FBX Binary  \0\x1a\0'));view.setUint32(23,wide?7500:7400,true);
 const integer=(at:number,v:number)=>wide?view.setBigUint64(at,BigInt(v),true):view.setUint32(at,v,true);
 const write=(v:Node,at:number):number=>{const end=at+size(v),label=text.encode(v.name);integer(at,end);integer(at+(wide?8:4),v.properties.length);integer(at+(wide?16:8),v.properties.reduce((sum,p)=>sum+p.length,0));out[at+header-1]=label.length;at+=header;out.set(label,at);at+=label.length;for(const p of v.properties){out.set(p,at);at+=p.length;}for(const c of v.children)at=write(c,at);return end;};
 let at=27;for(const r of roots)at=write(r,at);return out.buffer;
}
