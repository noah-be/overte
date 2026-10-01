// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { SkinnedMesh, Vector3, type Mesh } from 'three';
import { deflateSync } from 'node:zlib';
import { adaptBakedFbx, normalizeNativeFbxTransparency, type DecodedBakedGeometry } from '../src/baked-fbx';
import {applyNativeFbxOpacity} from '../src/fbx-materials';
interface FixtureNode { name: string; props: Uint8Array[]; children: FixtureNode[] }
function property(value: string | number | Uint8Array): Uint8Array {
  if (typeof value === 'number') { const bytes = new Uint8Array(9); bytes[0] = 68; new DataView(bytes.buffer).setFloat64(1, value, true); return bytes; }
  const data = typeof value === 'string' ? new TextEncoder().encode(value) : value;
  const bytes = new Uint8Array(5 + data.length); bytes[0] = 83; new DataView(bytes.buffer).setUint32(1, data.length, true); bytes.set(data, 5); return bytes;
}
function n(name: string, values: (string | number | Uint8Array)[] = [], children: FixtureNode[] = []): FixtureNode { return { name, props: values.map(property), children }; }
function fixture(wide = false, arrayProperty?: Uint8Array, opacity?: number, extras: { objects: FixtureNode[]; connections: FixtureNode[]; materialProperties?:FixtureNode[]; creator?:string; legacy?:boolean } = { objects: [], connections: [] }): ArrayBuffer {
  const roots = [n('FBXHeaderExtension', [], [n('FBXVersion', [wide ? 7500 : 7400])]), n('Objects', [], [
    n('Geometry', [1, 'TestGeometry\0\x01Geometry', 'Mesh'], [n('DracoMesh', [new TextEncoder().encode('DRACOfixture')], [n('MaterialList', ['101', '102'])])]),
    n('Model', [10, 'TestModel\0\x01Model', 'Mesh'], [n('Properties70', [], [n('P', ['Lcl Translation', 'Lcl Translation', '', 'A', 10, 20, 30])])]),
    ...[101, 102].map(id => n('Material', [id, `Material${id}\0\x01Material`, ''], [n('ShadingModel', ['phong']), ...(id === 101 && extras.materialProperties ? [n(extras.legacy?'Properties60':'Properties70',[],extras.materialProperties)] : []), ...(id === 101 && opacity !== undefined ? [n('Properties70', [], [n('P', ['Opacity', 'double', 'Number', '', opacity])])] : [])])),
  ]), n('Connections', [], [n('C', ['OO', 1, 10]), n('C', ['OO', 102, 10]), n('C', ['OO', 101, 10]), n('C', ['OO', 10, 0])])];
  if(extras.creator)roots.push(n('Creator',[extras.creator]));
  roots[1].children.push(...extras.objects); roots[2].children.push(...extras.connections);
  if (arrayProperty) roots[1].children.push({ name: 'UncompressedMetadata', props: [arrayProperty], children: [] });
  const header = wide ? 25 : 13;
  function size(node: FixtureNode): number { return header + new TextEncoder().encode(node.name).length + node.props.reduce((n, p) => n + p.length, 0) + node.children.reduce((n, c) => n + size(c), 0) + (node.children.length ? header : 0); }
  const data = new Uint8Array(27 + roots.reduce((n, r) => n + size(r), 0) + header + 176), view = new DataView(data.buffer);
  data.set(new TextEncoder().encode('Kaydara FBX Binary  \0\x1a\0')); view.setUint32(23, wide ? 7500 : 7400, true);
  function write(node: FixtureNode, offset: number): number {
    const start = offset, end = offset + size(node), label = new TextEncoder().encode(node.name);
    function integer(at: number, value: number) { if (wide) view.setBigUint64(at, BigInt(value), true); else view.setUint32(at, value, true); }
    integer(offset, end); integer(offset + (wide ? 8 : 4), node.props.length); integer(offset + (wide ? 16 : 8), node.props.reduce((n, p) => n + p.length, 0)); data[offset + header - 1] = label.length;
    offset += header; data.set(label, offset); offset += label.length;
    for (const prop of node.props) { data.set(prop, offset); offset += prop.length; }
    for (const child of node.children) offset = write(child, offset);
    assert.equal(end, start + size(node)); return end;
  }
  let offset = 27; for (const root of roots) offset = write(root, offset); return data.buffer;
}
const geometry: DecodedBakedGeometry = { positions: [0, 0, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0, 3, 0, 0, 2, 0, 1],
  indices: [0, 1, 2, 3, 4, 5], normals: Array.from({ length: 6 }, () => [0, 1, 0]).flat(), uv: Array.from({ length: 6 }, () => [0.5, -0.25]).flat(), materialIDs: [0, 0, 0, 1, 1, 1] };
for (const wide of [false, true]) test(`restores ${wide ? 64 : 32}-bit native geometry, UVs and material groups without changing model transforms`, async () => {
  const restored = await adaptBakedFbx(fixture(wide), async (bytes, options) => {
    assert.equal(new TextDecoder().decode(bytes), 'DRACOfixture'); assert.equal(options.materialIDs, true); return geometry;
  });
  const group = new FBXLoader().parse(restored, '');
  let mesh: Mesh | undefined; group.traverse(object => { if ((object as Mesh).isMesh) mesh = object as Mesh; });
  assert(mesh); assert.equal(mesh.geometry.getAttribute('position').count, 6);
  assert.deepEqual(mesh.position.toArray(), [10, 20, 30]);
  assert.deepEqual(mesh.geometry.groups.map(group => [group.start, group.count, group.materialIndex]), [[0, 3, 1], [3, 3, 0]]);
  assert.equal(mesh.geometry.getAttribute('uv').getY(0), 0.25);
});
test('leaves ASCII and non-baked binary inputs unchanged', async () => {
  const ascii = new TextEncoder().encode('; FBX 7.4 text').buffer;
  assert.equal(await adaptBakedFbx(ascii), ascii);
  const restored = await adaptBakedFbx(fixture(), async () => geometry);
  assert.equal(await adaptBakedFbx(restored), restored);
});
test('actual binary FBX material parsing follows native nonpositive-opacity fallback without losing fractional transparency',async()=>{
  for(const opacity of [0,-1,.28,1]) {
    const group=new FBXLoader().parse(await adaptBakedFbx(fixture(false,undefined,opacity),async()=>geometry),'');
    let mesh:Mesh|undefined;group.traverse(object=>{if((object as Mesh).isMesh)mesh=object as Mesh;});assert(mesh);
    const materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
    const source=materials.find(material=>material.name==='Material101')!;assert(source);
    assert.equal(source.opacity,opacity,'The production Three FBX parser retains the authored zero or negative opacity');
    applyNativeFbxOpacity(group);
    assert.equal(source.opacity,opacity<=0?1:opacity);
    assert.equal(source.transparent,opacity>0&&opacity<1);
    assert.equal(mesh.geometry.getAttribute('position').count,6);
    assert.deepEqual(mesh.geometry.groups.map(part=>part.materialIndex),[1,0]);
  }
});
test('rejects malformed node boundaries before decoding untrusted bytes', async () => {
  for (const wide of [false, true]) {
    const input = fixture(wide), view = new DataView(input);
    if (wide) view.setBigUint64(27, BigInt(Number.MAX_SAFE_INTEGER) + 1n, true); else view.setUint32(27, input.byteLength + 1, true);
    await assert.rejects(adaptBakedFbx(input, async () => { assert.fail('Decoder must not see an invalid node'); }), /Invalid baked FBX/);
  }
});
test('rejects invalid decoded indices and non-finite positions', async () => {
  await assert.rejects(adaptBakedFbx(fixture(), async () => ({ ...geometry, indices: [0, 1, 100] })), /triangle vertex/);
  await assert.rejects(adaptBakedFbx(fixture(), async () => ({ ...geometry, positions: [NaN, ...Array(17).fill(0)] })), /Non-finite/);
  await assert.rejects(adaptBakedFbx(fixture(), async () => ({ ...geometry, positions: { length: 6_000_003 } as ArrayLike<number> })), /vertex count/);
});
test('rejects material references outside the native material list', async () => {
  await assert.rejects(adaptBakedFbx(fixture(), async () => ({ ...geometry, materialIDs: [2, 2, 2, 2, 2, 2] })), /material index/);
});

test('rejects missing required custom material IDs and invalid UV shapes', async () => {
  const { materialIDs: _, ...missing } = geometry;
  await assert.rejects(adaptBakedFbx(fixture(), async () => missing), /required material IDs/);
  await assert.rejects(adaptBakedFbx(fixture(), async () => ({ ...geometry, uv: [0, 0] })), /texture coordinates/);
  await assert.rejects(adaptBakedFbx(fixture(), async () => ({ ...geometry, normals: [0, 1, 0] })), /normals/);
});

test('bounds every declared array including compressed metadata before invoking a decoder', async () => {
  const compressed = new Uint8Array(14), view = new DataView(compressed.buffer); compressed[0] = 100;
  view.setUint32(1, 0xffffffff, true); view.setUint32(5, 1, true); view.setUint32(9, 1, true);
  await assert.rejects(adaptBakedFbx(fixture(false, compressed), async () => { assert.fail('Oversized metadata must fail before decoding'); }), /expanded array length/);
  view.setUint32(1, 1, true); view.setUint32(5, 0, true);
  await assert.rejects(adaptBakedFbx(fixture(true, compressed), async () => { assert.fail('Invalid metadata length must fail before decoding'); }), /array encoding/);
});

function trianglesWithMaterials(mesh: Mesh): string[] {
  const position = mesh.geometry.getAttribute('position'), uv = mesh.geometry.getAttribute('uv'), normal = mesh.geometry.getAttribute('normal');
  const result: string[] = [];
  for (const group of mesh.geometry.groups) for (let vertex = group.start; vertex < group.start + group.count; vertex += 3) {
    result.push(JSON.stringify({ material: group.materialIndex, corners: [0, 1, 2].map(offset => ({
      position: [position.getX(vertex + offset), position.getY(vertex + offset), position.getZ(vertex + offset)],
      uv: [uv.getX(vertex + offset), uv.getY(vertex + offset)], normal: [normal.getX(vertex + offset), normal.getY(vertex + offset), normal.getZ(vertex + offset)],
    })) }));
  }
  return result.sort();
}
test('coalesces interleaved opaque material parts without changing oriented triangles, UVs or normals', async () => {
  const interleaved = { ...geometry, indices: [0, 1, 2, 3, 4, 5, 2, 1, 0, 5, 4, 3] };
  const meshes: Mesh[] = [];
  for (const preserveTriangleOrder of [true, false]) {
    const loaded = new FBXLoader().parse(await adaptBakedFbx(fixture(), async () => interleaved, { preserveTriangleOrder }), '');
    loaded.traverse(object => { if ((object as Mesh).isMesh) meshes.push(object as Mesh); });
  }
  assert.equal(meshes[0].geometry.groups.length, 4);
  assert.equal(meshes[1].geometry.groups.length, 2);
  assert.deepEqual(meshes[1].geometry.groups.map(group => [group.start, group.count, group.materialIndex]), [[0, 6, 1], [6, 6, 0]]);
  assert.deepEqual(trianglesWithMaterials(meshes[0]), trianglesWithMaterials(meshes[1]));
  assert.deepEqual(meshes[1].position.toArray(), [10, 20, 30]);
});
test('retains mixed transparent source triangle order', async () => {
  const interleaved = { ...geometry, indices: [0, 1, 2, 3, 4, 5, 2, 1, 0, 5, 4, 3] };
  for (const opacity of [0.5, Number.NaN]) {
    const loaded = new FBXLoader().parse(await adaptBakedFbx(fixture(false, undefined, opacity), async () => interleaved), '');
    loaded.traverse(object => { if ((object as Mesh).isMesh) assert.equal((object as Mesh).geometry.groups.length, 4); });
  }
});

function arrayNode(name: string, values: number[], type: 'd' | 'i' = 'd', compressed = true, advertisedCount = values.length): FixtureNode {
  const bytes = new Uint8Array(values.length * (type === 'd' ? 8 : 4)), view = new DataView(bytes.buffer);
  for (let i = 0; i < values.length; i++) if (type === 'd') view.setFloat64(i * 8, values[i], true); else view.setInt32(i * 4, values[i], true);
  const payload = compressed ? deflateSync(bytes) : bytes;
  const property = new Uint8Array(13 + payload.length), meta = new DataView(property.buffer); property[0] = type.charCodeAt(0);
  meta.setUint32(1, advertisedCount, true); meta.setUint32(5, compressed ? 1 : 0, true); meta.setUint32(9, payload.length, true); property.set(payload, 13);
  return { name, props: [property], children: [] };
}
function deformFixture(corrupt: boolean | 'overflow' | 'checksum' = false): ArrayBuffer {
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  return fixture(false, undefined, undefined, { objects: [
    n('Model', [20, 'JointA\0\x01Model', 'LimbNode']), n('Model', [21, 'JointB\0\x01Model', 'LimbNode']),
    n('Deformer', [200, 'Skin\0\x01Deformer', 'Skin']),
    ...[201, 202].map((id, index) => n('Deformer', [id, `Cluster${index}\0\x01Deformer`, 'Cluster'], [
      arrayNode('Indexes', index ? [1, 2] : [0], 'i'), (() => { const array = arrayNode('Weights', index ? [1, 1] : [1], 'd', true, corrupt === 'overflow' ? 0 : corrupt === true ? 3 : index ? 2 : 1); if (corrupt === 'checksum') array.props[0][array.props[0].length - 1] ^= 1; return array; })(),
      arrayNode('Transform', identity), arrayNode('TransformLink', identity),
    ])),
    n('Deformer', [300, 'Morph\0\x01Deformer', 'BlendShape']),
    n('Deformer', [301, 'Lift\0\x01Deformer', 'BlendShapeChannel'], [n('DeformPercent', [0]), arrayNode('FullWeights', [100])]),
    n('Geometry', [303, 'Lift\0\x01Geometry', 'Shape'], [arrayNode('Indexes', [0, 2], 'i'), arrayNode('Vertices', [0, 1, 0, 0, 0, 2]), arrayNode('Normals', [0, 0, 0, 0, 0, 0])]),
  ], connections: [
    n('C', ['OO', 200, 1]), n('C', ['OO', 201, 200]), n('C', ['OO', 202, 200]),
    n('C', ['OO', 20, 201]), n('C', ['OO', 21, 202]), n('C', ['OO', 20, 0]), n('C', ['OO', 21, 0]),
    n('C', ['OO', 300, 1]), n('C', ['OO', 301, 300]), n('C', ['OO', 303, 301]),
  ] });
}
test('original-index skin and blendshape restoration drives the unchanged FBXLoader across UV/material vertex splits', async () => {
  const restored = await adaptBakedFbx(deformFixture(), async (_, options) => {
    assert.equal(options.originalIndices, true); return { ...geometry, originalIndices: [2, 0, 1, 0, 2, 1] };
  });
  const loaded = new FBXLoader().parse(restored, ''); let mesh: SkinnedMesh | undefined;
  loaded.traverse(object => { if (object instanceof SkinnedMesh) mesh = object; });
  assert(mesh); assert.equal(mesh.skeleton.bones.length, 2);
  assert.deepEqual(Array.from(mesh.geometry.getAttribute('skinIndex').array).filter((_, index) => index % 4 === 0), [1, 0, 1, 0, 1, 1]);
  loaded.updateMatrixWorld(true); mesh.skeleton.update();
  const before = Array.from({ length: 6 }, (_, index) => mesh!.applyBoneTransform(index, new Vector3().fromBufferAttribute(mesh!.geometry.getAttribute('position'), index)).clone());
  mesh.skeleton.bones[0].position.y += 1; loaded.updateMatrixWorld(true); mesh.skeleton.update();
  const moved = before.map((vertex, index) => mesh!.applyBoneTransform(index, new Vector3().fromBufferAttribute(mesh!.geometry.getAttribute('position'), index)).distanceTo(vertex));
  assert.deepEqual(moved.map(value => Math.round(value)), [0, 1, 0, 1, 0, 0], 'Exactly both original-0 split points follow JointA');
  const morph = mesh.geometry.morphAttributes.position?.[0]; assert(morph);
  assert.deepEqual(Array.from({ length: 6 }, (_, index) => [morph.getX(index), morph.getY(index), morph.getZ(index)]), [[0, 0, 2], [0, 1, 0], [0, 0, 0], [0, 1, 0], [0, 0, 2], [0, 0, 0]]);
});
test('malformed compressed deformation lengths fail closed before producing a skin', async () => {
  await assert.rejects(adaptBakedFbx(deformFixture(true), async () => ({ ...geometry, originalIndices: [2, 0, 1, 0, 2, 1] })), /decompressed length mismatch/);
});

test('compressed deformation rejects excess expansion and corrupt zlib checksums', async () => {
  for (const corrupt of ['overflow', 'checksum'] as const) {
    await assert.rejects(adaptBakedFbx(deformFixture(corrupt), async () => ({ ...geometry, originalIndices: [2, 0, 1, 0, 2, 1] })), corrupt === 'overflow' ? /exceeds declared bounds/ : /Invalid baked deformation zlib stream/);
  }
});


// Use the unchanged production Three parser. Images need no pixel decoder for
// these binding/geometry tests; the actual RGBA classifier has separate tests.
function mockImageDocument<T>(run:()=>T):T {
  const previous=globalThis.document;
  const image=()=>({addEventListener(){},removeEventListener(){},setAttribute(){},src:''});
  Object.defineProperty(globalThis,'document',{configurable:true,value:{createElementNS:()=>image()}});
  try{return run();}finally{if(previous)Object.defineProperty(globalThis,'document',{configurable:true,value:previous});else delete (globalThis as any).document;}
}
function transparencyFixture(properties:FixtureNode[]=[],opacityFile?:string,extras:{creator?:string;legacy?:boolean;embedded?:boolean}={}){
 const texture=(id:number,file:string)=>n('Texture',[id,`Texture${id}\0\x01Texture`, 'TextureVideoClip'],[n('RelativeFilename',[file]),n('FileName',[file])]);
 return fixture(false,undefined,.28,{materialProperties:properties,creator:extras.creator,legacy:extras.legacy,
  objects:[texture(301,'images/body.png'),...(opacityFile?[texture(302,opacityFile)]:[]),...(extras.embedded?[n('Video',[303,'Embedded','Clip'],[n('RelativeFilename',['images/body.png']),n('Content',['pixels'])]),n('Video',[304,'Embedded2','Clip'],[n('RelativeFilename',[opacityFile||'']),n('Content',['other pixels'])])]:[])],
  connections:[n('C',['OP',301,101,'DiffuseColor']),...(opacityFile?[n('C',['OP',302,101,'TransparentColor'])]:[])]});
}
async function parsedOpacity(input:ArrayBuffer){
 const normalized=normalizeNativeFbxTransparency(input),restored=await adaptBakedFbx(normalized,async()=>geometry);
 return mockImageDocument(()=>{const group=new FBXLoader().parse(restored,'https://assets.example/');let mesh:Mesh|undefined;group.traverse(object=>{if((object as Mesh).isMesh)mesh=object as Mesh;});assert(mesh);
  const material=(Array.isArray(mesh.material)?mesh.material:[mesh.material]).find(material=>material.name==='Material101')!;
  assert.equal(material.opacity,.28,'Authored opacity is untouched by connection normalization');assert.deepEqual(mesh.position.toArray(),[10,20,30]);assert.equal(mesh.geometry.getAttribute('position').count,6);
  const maps=material as typeof material & {map?:unknown;alphaMap?:unknown};return {normalized,alpha:maps.alphaMap,map:maps.map,mesh};});
}
test('native non-PBS diffuse alpha requires matching authored opacity filename, while different opacity images are ignored',async()=>{
 for(const file of [undefined,'different/opacity.png','different/body.png']){
  const {alpha,map}=await parsedOpacity(transparencyFixture([],file));assert(map);assert.equal(Boolean(alpha),file==='different/body.png');if(alpha)assert.equal(alpha,map,'Matching native external basenames bind the same albedo texture, never a second green-channel alpha map');
 }
});
test('native PBS detection includes zero ReflectionFactor and every Stingray flag, regardless of its numeric value',async()=>{
 for(const key of ['ReflectionFactor','Maya|use_normal_map','Maya|base_color','Maya|use_color_map','Maya|roughness','Maya|use_roughness_map','Maya|metallic','Maya|use_metallic_map','Maya|emissive','Maya|emissive_intensity','Maya|use_emissive_map','Maya|use_ao_map']){
  const {alpha,map}=await parsedOpacity(transparencyFixture([n('P',[key,'double','Number','',0])],'opacity.png'));assert.equal(alpha,map,`Native ${key} presence opts into PBS even when zero; PBS overrides distinct authored opacity`);
 }
});
test('native ordered Blender legacy fallback and Properties60 preserve their actual PBS exceptions',async()=>{
 const reflection=n('Property',['ReflectionFactor','double','',0]),stingray=n('Property',['Maya|roughness','double','',0]);
 const old='Blender (stable FBX IO) - 2.78 (sub 0) - 3.7.7';
 assert.equal((await parsedOpacity(transparencyFixture([reflection],undefined,{legacy:true,creator:old}))).alpha,null);
 const modern=await parsedOpacity(transparencyFixture([reflection],undefined,{legacy:true,creator:'Blender (stable FBX IO) - 2.92.0 - 4.22.0'}));assert.equal(modern.alpha,modern.map);
 assert.equal((await parsedOpacity(transparencyFixture([stingray,reflection],undefined,{legacy:true,creator:old}))).alpha,null,'A later ReflectionFactor restores native legacy fallback');
 const later=await parsedOpacity(transparencyFixture([reflection,stingray],undefined,{legacy:true,creator:old}));assert.equal(later.alpha,later.map,'A later Stingray property opts back into PBS');
});
test('embedded Video opacity matching uses full native filepath instead of the external basename fallback',async()=>{
 const result=await parsedOpacity(transparencyFixture([],'other/body.png',{embedded:true}));assert.equal(result.alpha,null);
});
test('binary normalization is idempotent and does not touch a non-PBS FBX with no opacity bindings',()=>{
 const unchanged=transparencyFixture([]);assert.equal(normalizeNativeFbxTransparency(unchanged),unchanged);
 const normalized=normalizeNativeFbxTransparency(transparencyFixture([n('P',['ReflectionFactor','double','Number','',0])]));assert.equal(normalizeNativeFbxTransparency(normalized),normalized);
 const malformed=transparencyFixture([]);new DataView(malformed).setUint32(27,malformed.byteLength+1,true);assert.throws(()=>normalizeNativeFbxTransparency(malformed),/Invalid baked FBX/);
});
test('line-oriented ASCII FBX PBS and legacy authored bindings normalize while geometry, opacity and unrelated connections remain byte exact',()=>{
 const ascii=(property:string,opacity:string)=>`; FBX 7.4.0 project file\nObjects:  {\n\tMaterial: 101, "Material::Body", "" {\n\t\tProperties70:  {\n${property}\t\t\tP: "Opacity", "double", "Number", "", 0.28\n\t\t}\n\t}\n\tTexture: 301, "Texture::Body", "TextureVideoClip" {\n\t\tRelativeFilename: "images/body.png"\n\t}\n\tTexture: 302, "Texture::Opacity", "TextureVideoClip" {\n\t\tRelativeFilename: "${opacity}"\n\t}\n\tGeometry: 201, "Geometry::Body", "Mesh" {\n\t\tVertices: *9 {\n\t\t\ta: 0,0,0,1,0,0,0,1,0\n\t\t}\n\t}\n}\nConnections:  {\n\tC: "OO", 201, 401\n\tC: "OP", 301, 101, "DiffuseColor"\n\tC: "OP", 302, 101, "TransparentColor"\n}\n`;
 for(const [property,file,eligible] of [['','opacity.png',false],['','other/body.png',true],['\t\t\tP: "Maya|roughness", "double", "Number", "", 0\n','opacity.png',true]] as const){
  const input=new TextEncoder().encode(ascii(property,file)).buffer,normalized=normalizeNativeFbxTransparency(input),result=new TextDecoder().decode(normalized);
  assert.equal(result.includes('C: "OP", 301, 101, "TransparentColor"'),eligible);assert(!result.includes('C: "OP", 302, 101, "TransparentColor"'));
  assert(result.includes('\t\t\ta: 0,0,0,1,0,0,0,1,0\n'));assert(result.includes('P: "Opacity", "double", "Number", "", 0.28'));assert(result.includes('C: "OO", 201, 401'));
  assert.equal(normalizeNativeFbxTransparency(normalized),normalized);
 }
 assert.throws(()=>normalizeNativeFbxTransparency(new TextEncoder().encode('; FBX 7.4\nObjects: { Material: 1, "Name", "" {} }\n').buffer),/compact ASCII FBX/,'Unsupported compact metadata fails visibly rather than silently ignoring PBS');
});

test('actual shipped native lowercase dispatch makes DiffuseFactor and color last-wins, and normalizes the effective albedo for Three',async()=>{
 for(const channels of [['DiffuseColor','DiffuseFactor'],['DiffuseFactor','DiffuseColor'],['DiffuseFactor'],['Maya|TEX_color_map'],['maya|tex_color_map']]){
  const objects=channels.map((_,i)=>n('Texture',[401+i,`Texture${i}`, 'TextureVideoClip'],[n('RelativeFilename',[`body${i}.png`]),n('FileName',[`body${i}.png`])]));
  const input=fixture(false,undefined,.28,{objects,materialProperties:[n('P',['ReflectionFactor','double','Number','',0])],connections:channels.map((channel,i)=>n('C',['OP',401+i,101,channel]))});
  const {alpha,map}=await parsedOpacity(input);assert.equal((map as {ID:number}).ID,400+channels.length,'Effective native connection order survives into the unchanged Three loader');assert.equal(alpha,map,'PBS uses alpha from that same effective albedo');
 }
});
test('ASCII effective factor/Maya color bindings retain connection order and become the recognized Three albedo relation',()=>{
 const ascii='; FBX 7.4\nObjects: {\n\tMaterial: 101, "Material::Body", "" {\n\t\tProperties70: {\n\t\t\tP: "ReflectionFactor", "double", "Number", "", 0\n\t\t}\n\t}\n\tTexture: 301, "Texture::Body", "TextureVideoClip" {\n\t\tRelativeFilename: "body.png"\n\t}\n}\nConnections: {\n\tC: "OP", 301, 101, "DiffuseFactor"\n}\n';
 const result=new TextDecoder().decode(normalizeNativeFbxTransparency(new TextEncoder().encode(ascii).buffer));
 assert(result.includes('C: "OP", 301, 101, "DiffuseColor"'));assert(result.includes('C: "OP", 301, 101, "TransparentColor"'));assert(!result.includes('"DiffuseFactor"'));
});
test('standard unbaked ASCII normalization reaches the actual Three parser without changing vertices, transforms or authored opacity',()=>{
 const source=`; FBX 7.4.0 project file
FBXHeaderExtension:  {
\tFBXVersion: 7400
}
Objects:  {
\tGeometry: 201, "Geometry::Body", "Mesh" {
\t\tVertices: *9 {
\t\t\ta: 0,0,0,1,0,0,0,1,0
\t\t}
\t\tPolygonVertexIndex: *3 {
\t\t\ta: 0,1,-3
\t\t}
\t}
\tModel: 401, "Model::Body", "Mesh" {
\t\tProperties70:  {
\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",10,20,30
\t\t}
\t}
\tMaterial: 101, "Material::Body", "" {
\t\tShadingModel: "phong"
\t\tProperties70:  {
\t\t\tP: "ReflectionFactor", "double", "Number", "",0
\t\t\tP: "Opacity", "double", "Number", "",0.28
\t\t}
\t}
\tTexture: 301, "Texture::Body", "TextureVideoClip" {
\t\tRelativeFilename: "body.png"
\t\tFileName: "body.png"
\t}
}
Connections:  {
\tC: "OO",201,401
\tC: "OO",101,401
\tC: "OO",401,0
\tC: "OP",301,101,"DiffuseFactor"
}
`;
 const input=new TextEncoder().encode(source).buffer,normalized=normalizeNativeFbxTransparency(input);
 const headerOnly=normalizeNativeFbxTransparency(new TextEncoder().encode(source.slice(source.indexOf('\n')+1)).buffer);
 assert(new TextDecoder().decode(headerOnly).includes('"TransparentColor"'),'Metadata normalization also recognizes the actual FBX header without its optional comment');
 const group=mockImageDocument(()=>new FBXLoader().parse(normalized,'https://assets.example/'));let mesh:Mesh|undefined;
 group.traverse(object=>{if((object as Mesh).isMesh)mesh=object as Mesh;});assert(mesh);
 assert.deepEqual(Array.from(mesh.geometry.getAttribute('position').array),[0,0,0,1,0,0,0,1,0]);assert.deepEqual(mesh.position.toArray(),[10,20,30]);
 const material=mesh.material as typeof mesh.material & {map:unknown;alphaMap:unknown;opacity:number};assert.equal(material.opacity,.28);assert(material.map);assert.equal(material.alphaMap,material.map);
 assert.equal(normalizeNativeFbxTransparency(normalized),normalized);
});
