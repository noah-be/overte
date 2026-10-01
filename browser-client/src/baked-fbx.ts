// SPDX-License-Identifier: Apache-2.0
// Restore Overte's native DracoMesh extension to standard FBX arrays, retaining
// original model connections/transforms. Native format: FBXSerializer_Mesh.cpp.
import { bakedIndexMap } from './baked-deformation';

export interface DecodedBakedGeometry {
  positions: ArrayLike<number>; indices: ArrayLike<number>; normals?: ArrayLike<number>;
  uv?: ArrayLike<number>; uv1?: ArrayLike<number>; colors?: ArrayLike<number>; materialIDs?: ArrayLike<number>; originalIndices?: ArrayLike<number>;
}
export type BakedDracoDecoder = (bytes: ArrayBuffer, options: { materialIDs: boolean; uv1: boolean; originalIndices: boolean }) => Promise<DecodedBakedGeometry>;
interface Node { name: Uint8Array; properties: Uint8Array; propertyCount: number; children: Node[]; terminator: boolean }
const magic = 'Kaydara FBX Binary  \0\x1a\0';
const MAX_BYTES = 32 * 1024 * 1024, MAX_OUTPUT = 256 * 1024 * 1024, MAX_VERTICES = 2_000_000;
const encoder = new TextEncoder(), text = new TextDecoder();
const name = (node: Node) => text.decode(node.name);
function safe(value: number, maximum: number, label: string): number {
  if (!Number.isSafeInteger(value) || value < 0 || value > maximum) throw Error(`Invalid baked FBX ${label}`);
  return value;
}
function concatenate(parts: Uint8Array[]): Uint8Array {
  const size = parts.reduce((sum, part) => sum + part.length, 0); safe(size, MAX_OUTPUT, 'output length');
  const result = new Uint8Array(size); let offset = 0;
  for (const part of parts) { result.set(part, offset); offset += part.length; }
  return result;
}
function scalar(type: 'I' | 'S', value: number | string): Uint8Array {
  const string = type === 'S' ? encoder.encode(String(value)) : null;
  const result = new Uint8Array(5 + (string?.length || 0)); result[0] = type.charCodeAt(0);
  new DataView(result.buffer).setUint32(1, string ? string.length : Number(value), true);
  if (string) result.set(string, 5); return result;
}
function array(type: 'd' | 'i', values: ArrayLike<number>): Uint8Array {
  const width = type === 'd' ? 8 : 4; safe(values.length, MAX_OUTPUT / width, 'array length');
  const result = new Uint8Array(13 + values.length * width), view = new DataView(result.buffer);
  result[0] = type.charCodeAt(0); view.setUint32(1, values.length, true); view.setUint32(5, 0, true); view.setUint32(9, values.length * width, true);
  for (let i = 0; i < values.length; i++) {
    if (!Number.isFinite(values[i])) throw Error('Non-finite baked FBX geometry');
    if (type === 'd') view.setFloat64(13 + i * width, values[i], true);
    else { if (!Number.isInteger(values[i]) || values[i] < -2147483648 || values[i] > 2147483647) throw Error('Invalid baked FBX integer'); view.setInt32(13 + i * width, values[i], true); }
  }
  return result;
}
function node(label: string, properties: Uint8Array[] = [], children: Node[] = []): Node {
  return { name: encoder.encode(label), properties: concatenate(properties), propertyCount: properties.length, children, terminator: children.length > 0 };
}
function values(node: Node): (number | string | Uint8Array)[] {
  const data = node.properties, view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let offset = 0; const result: (number | string | Uint8Array)[] = [];
  function require(bytes: number) { if (offset + bytes > data.length) throw Error('Truncated baked FBX property'); }
  for (let i = 0; i < node.propertyCount; i++) {
    require(1); const type = String.fromCharCode(data[offset++]);
    if (type === 'S' || type === 'R') {
      require(4); const length = view.getUint32(offset, true); offset += 4; require(length);
      const bytes = data.subarray(offset, offset + length); offset += length;
      result.push(name(node) === 'DracoMesh' || type === 'R' ? bytes : text.decode(bytes));
    } else if (type === 'I' || type === 'L' || type === 'Y' || type === 'C' || type === 'F' || type === 'D') {
      const size = ({ I: 4, L: 8, Y: 2, C: 1, F: 4, D: 8 })[type]; require(size); let value: number;
      if (type === 'L') value = Number(view.getBigInt64(offset, true));
      else if (type === 'I') value = view.getInt32(offset, true);
      else if (type === 'Y') value = view.getInt16(offset, true);
      else if (type === 'C') value = data[offset];
      else if (type === 'F') value = view.getFloat32(offset, true);
      else value = view.getFloat64(offset, true);
      result.push(value); offset += size;
    } else if ('fdlibc'.includes(type)) {
      require(12); const length = view.getUint32(offset + 8, true); offset += 12; require(length); offset += length;
    } else throw Error('Unsupported baked FBX property encoding');
  }
  if (offset !== data.length) throw Error('Baked FBX property lengths disagree'); return result;
}
// Native streaming zlib decompression validates Adler32 and rejects trailing
// bytes (https://compression.spec.whatwg.org/#supported-formats). Feed 1KiB
// input chunks and cancel as soon as advertised output is exceeded, avoiding a
// synchronous JavaScript inflate loop or attacker-chosen output allocations.
async function numericArray(node: Node): Promise<Float64Array> {
  if (node.propertyCount !== 1 || node.properties.length < 13) throw Error('Invalid baked deformation array');
  const data = node.properties, view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const type = String.fromCharCode(data[0]), width = ({ i: 4, l: 8, d: 8, f: 4 } as Record<string, number>)[type];
  if (!width) throw Error('Invalid baked deformation numeric type');
  const count = view.getUint32(1, true), encoding = view.getUint32(5, true), length = view.getUint32(9, true);
  safe(count, MAX_VERTICES * 3, 'deformation array count');
  if (length !== data.length - 13 || encoding > 1) throw Error('Invalid baked deformation array encoding');
  let raw = data.subarray(13);
  if (encoding) {
    if (raw.length < 6) throw Error('Truncated baked deformation zlib stream');
    const output = new Uint8Array(count * width);
    let inputOffset = 0, outputOffset = 0;
    const compressed = raw;
    const stream = new ReadableStream<BufferSource>({ pull(controller) {
      if (inputOffset >= compressed.length) { controller.close(); return; }
      const end = Math.min(compressed.length, inputOffset + 1024);
      controller.enqueue(new Uint8Array(compressed.subarray(inputOffset, end))); inputOffset = end;
    } }).pipeThrough(new DecompressionStream('deflate'));
    const reader = stream.getReader();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; void reader.cancel('Baked deformation decompression timed out').catch(() => {}); }, 30000);
    try {
      while (true) {
        const chunk = await reader.read();
        if (timedOut) throw Error('Baked deformation decompression timed out');
        if (chunk.done) break;
        if (outputOffset + chunk.value.length > output.length) { await reader.cancel(); throw Error('Baked deformation decompressed length exceeds declared bounds'); }
        output.set(chunk.value, outputOffset); outputOffset += chunk.value.length;
      }
      if (outputOffset !== output.length) throw Error('Baked deformation decompressed length mismatch');
      raw = output;
    } catch (error) {
      if (error instanceof TypeError) throw new Error('Invalid baked deformation zlib stream', { cause: error });
      throw error;
    } finally { clearTimeout(timer); reader.releaseLock(); }
  }
  if (raw.length !== count * width) throw Error('Baked deformation array length mismatch');
  const source = new DataView(raw.buffer, raw.byteOffset, raw.byteLength), result = new Float64Array(count);
  for (let i = 0; i < count; i++) {
    result[i] = type === 'i' ? source.getInt32(i * width, true) : type === 'l' ? Number(source.getBigInt64(i * width, true)) : type === 'f' ? source.getFloat32(i * width, true) : source.getFloat64(i * width, true);
    if (!Number.isFinite(result[i])) throw Error('Non-finite baked deformation array');
  }
  return result;
}
function replaceArray(target: Node, type: 'i' | 'd', data: ArrayLike<number>): void {
  target.properties = array(type, data); target.propertyCount = 1; target.children = []; target.terminator = false;
}
function validateProperties(node: Node): number {
  const data = node.properties, view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let offset = 0, declaredArrays = 0;
  const require = (length: number) => { if (offset + length > data.length) throw Error('Truncated baked FBX property'); };
  for (let i = 0; i < node.propertyCount; i++) {
    require(1); const type = String.fromCharCode(data[offset++]);
    const scalarWidths: Record<string, number> = { I: 4, L: 8, Y: 2, C: 1, F: 4, D: 8 };
    if (scalarWidths[type]) { require(scalarWidths[type]); offset += scalarWidths[type]; }
    else if (type === 'S' || type === 'R') { require(4); const length = view.getUint32(offset, true); offset += 4; require(length); offset += length; }
    else if ('fdlibc'.includes(type)) {
      require(12); const count = view.getUint32(offset, true), encoding = view.getUint32(offset + 4, true), length = view.getUint32(offset + 8, true);
      const width = ({ f: 4, d: 8, l: 8, i: 4, b: 1, c: 1 } as Record<string, number>)[type];
      const expanded = safe(count * width, MAX_OUTPUT, 'expanded array length');
      if (encoding > 1 || (encoding === 0 && length !== expanded)) throw Error('Invalid baked FBX array encoding');
      declaredArrays += expanded; offset += 12; require(length); offset += length;
    } else throw Error('Unsupported baked FBX property encoding');
  }
  if (offset !== data.length) throw Error('Baked FBX property lengths disagree');
  return declaredArrays;
}
function layer(label: string, arrayName: string, data: ArrayLike<number>, index = 0): Node {
  return node(label, [scalar('I', index)], [node('Version', [scalar('I', 101)]), node('Name', [scalar('S', '')]),
    node('MappingInformationType', [scalar('S', 'ByVertice')]), node('ReferenceInformationType', [scalar('S', 'Direct')]), node(arrayName, [array('d', data)])]);
}
// Native FBXSerializer_Mesh.cpp groups one mesh part per material, retaining
// first-appearance order. Do the same for opaque triangles so FBXLoader emits
// one draw group per material rather than one per alternating face. Transparent
// or unrecognized opacity data retains the source face order.
function opaqueMaterial(material: Node, connections: (number | string | Uint8Array)[][]): boolean {
  const id = values(material)[0];
  if (connections.some(connection => connection[0] === 'OP' && connection[2] === id && /opacity|transparen/i.test(String(connection[3])))) return false;
  // TransparentColor alone is ignored by both native material opacity and the
  // current FBXLoader; only a connected transparency texture affects opacity.
  const properties = material.children.filter(child => ['Opacity', 'TransparencyFactor'].includes(name(child))).map(child => [name(child), ...values(child)]);
  for (const container of material.children.filter(child => ['Properties70', 'Properties60'].includes(name(child)))) {
    for (const property of container.children.filter(child => name(child) === 'P' || name(child) === 'Property')) {
      const propertyValues = values(property);
      if (['Opacity', 'TransparencyFactor'].includes(String(propertyValues[0]))) properties.push([propertyValues[0], ...propertyValues.slice(name(property) === 'P' ? 4 : 3)]);
    }
  }
  for (const [label, ...data] of properties) {
    if (!data.length || data.some(value => typeof value !== 'number' || !Number.isFinite(value))) return false;
    if (label === 'Opacity' ? data.some(value => value !== 1) : data.some(value => value !== 0)) return false;
  }
  return true;
}
function groupOpaqueFaces(indices: Int32Array, faceMaterials: Int32Array): void {
  const buckets = new Map<number, { count: number; next: number }>();
  for (let face = 0; face < faceMaterials.length; face++) {
    const material = faceMaterials[face]; let bucket = buckets.get(material);
    if (!bucket) { bucket = { count: 0, next: 0 }; buckets.set(material, bucket); }
    bucket.count++;
  }
  if (buckets.size < 2) return;
  let offset = 0; for (const bucket of buckets.values()) { bucket.next = offset; offset += bucket.count; }
  const groupedIndices = new Int32Array(indices.length), groupedMaterials = new Int32Array(faceMaterials.length);
  for (let face = 0; face < faceMaterials.length; face++) {
    const material = faceMaterials[face], target = buckets.get(material)!.next++;
    groupedIndices.set(indices.subarray(face * 3, face * 3 + 3), target * 3);
    groupedMaterials[target] = material;
  }
  indices.set(groupedIndices); faceMaterials.set(groupedMaterials);
}
interface BinaryFbx { bytes:Uint8Array; wide:boolean; header:number; roots:Node[]; tail:number }
function parseBinaryFbx(input:ArrayBuffer):BinaryFbx|null {
  const bytes = new Uint8Array(input); if (bytes.length < 27 || text.decode(bytes.subarray(0, 23)) !== magic) return null;
  safe(bytes.length, MAX_BYTES, 'input length');
  const view = new DataView(input), wide = view.getUint32(23, true) >= 7500, header = wide ? 25 : 13; let nodeCount = 0, declaredArrays = 0;
  function integer(offset: number): number { return wide ? safe(Number(view.getBigUint64(offset, true)), bytes.length, 'node field') : view.getUint32(offset, true); }
  function parse(offset: number, parentEnd: number, depth: number): { node?: Node; end: number } {
    if (++nodeCount > 100_000 || depth > 128 || offset + header > parentEnd) throw Error('Invalid baked FBX node hierarchy');
    const end = integer(offset); if (!end) return { end: offset + header };
    const count = integer(offset + (wide ? 8 : 4)), length = integer(offset + (wide ? 16 : 8));
    const nameLength = bytes[offset + header - 1], start = offset + header;
    if (end < start || end > parentEnd || start + nameLength + length > end || count > length) throw Error('Invalid baked FBX node bounds');
    const result: Node = { name: bytes.subarray(start, start + nameLength), properties: bytes.subarray(start + nameLength, start + nameLength + length), propertyCount: count, children: [], terminator: false };
    declaredArrays += validateProperties(result); safe(declaredArrays, MAX_OUTPUT, 'total expanded arrays');
    let cursor = start + nameLength + length;
    while (cursor < end) { const child = parse(cursor, end, depth + 1); cursor = child.end; if (!child.node) { result.terminator = true; break; } result.children.push(child.node); }
    if (cursor !== end) throw Error('Invalid baked FBX child lengths'); return { node: result, end };
  }
  const roots: Node[] = []; let offset = 27, tail = offset;
  while (offset + header <= bytes.length) { const parsed = parse(offset, bytes.length, 0); if (!parsed.node) { tail = offset; break; } roots.push(parsed.node); offset = parsed.end; tail = offset; }
  return {bytes,wide,header,roots,tail};
}
/** Returns the original buffer unchanged when it contains no native baked mesh. */
export async function adaptBakedFbx(input: ArrayBuffer, decode?: BakedDracoDecoder, options: { preserveTriangleOrder?: boolean } = {}): Promise<ArrayBuffer> {
  const parsed=parseBinaryFbx(input);if(!parsed)return input;
  const {roots}=parsed;
  const objects = roots.find(root => name(root) === 'Objects');
  const geometries = objects?.children.filter(child => name(child) === 'Geometry' && child.children.some(child => name(child) === 'DracoMesh')) || [];
  if (!geometries.length) return input;
  const connections = roots.find(root => name(root) === 'Connections')?.children.filter(child => name(child) === 'C').map(values) || [];
  const objectMap = new Map(objects?.children.map(object => [values(object)[0], object]));
  const childConnections = new Map<typeof connections[number][0], typeof connections>();
  for (const connection of connections) { if (connection[0] !== 'OO') continue; const list = childConnections.get(connection[2]) ?? []; list.push(connection); childConnections.set(connection[2], list); }
  const deformationBudget = { generatedBytes: 0 };
  const remappedNodes = new Map<Node, { geometry: number | string | Uint8Array; original?: ArrayLike<number>; vertices: number }>();
  const decoder = decode || (await import('./baked-draco')).decodeBakedDraco;
  for (const geometry of geometries) {
    const compressed = geometry.children.find(child => name(child) === 'DracoMesh')!, payload = values(compressed)[0];
    if (!(payload instanceof Uint8Array) || payload.length < 5 || text.decode(payload.subarray(0, 5)) !== 'DRACO') throw Error('Invalid native DracoMesh payload');
    const materialList = compressed.children.find(child => name(child) === 'MaterialList'), materials = materialList ? values(materialList).map(String) : [];
    const extraUV = geometry.children.some(child => name(child) === 'Layer' && child.children.some(child => name(child) === 'LayerElement' && child.children.some(child => name(child) === 'Type' && values(child)[0] === 'LayerElementUV') && child.children.some(child => name(child) === 'TypedIndex' && values(child)[0] === 1)));
    const geometryID = values(geometry)[0], parent = connections.find(connection => connection[0] === 'OO' && connection[1] === geometryID)?.[2];
    const attached = connections.filter(connection => connection[0] === 'OO' && connection[2] === parent && objects?.children.some(object => name(object) === 'Material' && values(object)[0] === connection[1])).map(connection => String(connection[1]));
    const requireMaterials = (materials.length || attached.length) > 1;
    const deformations: Node[] = [];
    const pending = [geometryID], visited = new Set<typeof geometryID>();
    while (pending.length) {
      const id = pending.pop()!; if (visited.has(id)) throw Error('Cyclic baked deformation connections'); visited.add(id);
      for (const connection of childConnections.get(id) ?? []) {
        const child = objectMap.get(connection[1]); if (!child) continue;
        if (name(child) === 'Deformer') { pending.push(connection[1]); if (values(child)[2] === 'Cluster') deformations.push(child); }
        else if (name(child) === 'Geometry' && values(child)[2] === 'Shape') deformations.push(child);
      }
    }
    const decoded = await decoder(payload.slice().buffer, { materialIDs: requireMaterials, uv1: extraUV, originalIndices: deformations.length > 0 }), vertices = decoded.positions.length / 3;
    if (requireMaterials && !decoded.materialIDs) throw Error('Baked mesh has no required material IDs');
    if (extraUV && !decoded.uv1) throw Error('Baked mesh has no required secondary texture coordinates');
    safe(vertices, MAX_VERTICES, 'vertex count'); safe(decoded.indices.length / 3, MAX_VERTICES * 2, 'triangle count');
    if (!vertices || !decoded.indices.length) throw Error('The baked model contains no decoded mesh');
    if (deformations.length) {
      const remap = bakedIndexMap(vertices, decoded.originalIndices, deformationBudget);
      for (const deformation of deformations) {
        const previous = remappedNodes.get(deformation);
        if (previous) {
          let same = previous.vertices === vertices;
          for (let index = 0; same && index < vertices; index++) same = (previous.original?.[index] ?? index) === (decoded.originalIndices?.[index] ?? index);
          if (!same) throw Error('Unsupported shared baked deformation with different vertex mappings');
          continue;
        }
        remappedNodes.set(deformation, { geometry: geometryID, original: decoded.originalIndices, vertices });
        const indexes = deformation.children.find(child => name(child) === 'Indexes');
        if (!indexes) throw Error('Baked deformation has no source indexes');
        const original = await numericArray(indexes);
        if (name(deformation) === 'Deformer') {
          const weights = deformation.children.find(child => name(child) === 'Weights');
          if (!weights) throw Error('Baked skin cluster has no source weights');
          const expanded = remap.expand(original, await numericArray(weights), 1);
          replaceArray(indexes, 'i', expanded.indices); replaceArray(weights, 'd', expanded.values);
        } else {
          const positions = deformation.children.find(child => name(child) === 'Vertices');
          if (!positions) throw Error('Baked blendshape has no source vertices');
          const expanded = remap.expand(original, await numericArray(positions), 3);
          replaceArray(positions, 'd', expanded.values);
          const normals = deformation.children.find(child => name(child) === 'Normals');
          if (normals) replaceArray(normals, 'd', remap.expand(original, await numericArray(normals), 3).values);
          replaceArray(indexes, 'i', expanded.indices);
        }
      }
    }
    const indices = new Int32Array(decoded.indices.length);
    for (let i = 0; i < indices.length; i++) { const vertex = decoded.indices[i]; safe(vertex, vertices - 1, 'triangle vertex'); indices[i] = i % 3 === 2 ? -vertex - 1 : vertex; }
    const replacement = [node('Vertices', [array('d', decoded.positions)])];
    if (decoded.normals) { if (decoded.normals.length !== vertices * 3) throw Error('Invalid baked mesh normals'); replacement.push(layer('LayerElementNormal', 'Normals', decoded.normals)); }
    for (const [index, uv] of [decoded.uv, decoded.uv1].entries()) {
      if (!uv) continue; if (uv.length !== vertices * 2) throw Error('Invalid baked mesh texture coordinates');
      const restored = Float64Array.from(uv); for (let i = 1; i < restored.length; i += 2) restored[i] = -restored[i]; replacement.push(layer('LayerElementUV', 'UV', restored, index));
    }
    if (decoded.colors) {
      if (decoded.colors.length !== vertices * 3 && decoded.colors.length !== vertices * 4) throw Error('Invalid baked mesh vertex colors');
      const width = decoded.colors.length / vertices, rgba = new Float64Array(vertices * 4);
      for (let i = 0; i < vertices; i++) { for (let j = 0; j < 3; j++) rgba[i * 4 + j] = decoded.colors[i * width + j]; rgba[i * 4 + 3] = width === 4 ? decoded.colors[i * width + 3] : 1; } replacement.push(layer('LayerElementColor', 'Colors', rgba));
    }
    // Version-one assets have no MaterialList; native readers use connection order.
    const mapping = materials.length ? materials.map((id, index) => attached.length ? attached.indexOf(id) : index) : attached.map((_, index) => index);
    if (mapping.some(index => index < 0)) throw Error('Baked mesh references an unattached material');
    const faceMaterials = new Int32Array(decoded.indices.length / 3);
    if (decoded.materialIDs && decoded.materialIDs.length !== vertices) throw Error('Invalid baked mesh material IDs');
    for (let face = 0; face < faceMaterials.length; face++) { const index = decoded.materialIDs ? decoded.materialIDs[decoded.indices[face * 3]] : 0; safe(index, Math.max(0, mapping.length - 1), 'material index'); faceMaterials[face] = mapping[index] ?? 0; }
    const materialNodes = attached.map(id => objects?.children.find(object => name(object) === 'Material' && String(values(object)[0]) === id));
    if (!options.preserveTriangleOrder && materialNodes.length && materialNodes.every(material => material && opaqueMaterial(material, connections))) groupOpaqueFaces(indices, faceMaterials);
    replacement.push(node('PolygonVertexIndex', [array('i', indices)]));
    replacement.push(node('LayerElementMaterial', [scalar('I', 0)], [node('Version', [scalar('I', 101)]), node('Name', [scalar('S', '')]), node('MappingInformationType', [scalar('S', 'ByPolygon')]), node('ReferenceInformationType', [scalar('S', 'IndexToDirect')]), node('Materials', [array('i', faceMaterials)])]));
    const replaced = new Set(['DracoMesh', 'Vertices', 'PolygonVertexIndex', 'LayerElementNormal', 'LayerElementUV', 'LayerElementColor', 'LayerElementMaterial']); geometry.children = geometry.children.filter(child => !replaced.has(name(child))).concat(replacement); geometry.terminator = true;
  }
  return serializeBinaryFbx(parsed);
}

function serializeBinaryFbx({bytes,wide,header,roots,tail}:BinaryFbx):ArrayBuffer {
  function size(node: Node): number { return header + node.name.length + node.properties.length + node.children.reduce((sum, child) => sum + size(child), 0) + (node.terminator ? header : 0); }
  const outputSize = 27 + roots.reduce((sum, root) => sum + size(root), 0) + bytes.length - tail; safe(outputSize, MAX_OUTPUT, 'output length');
  const output = new Uint8Array(outputSize), target = new DataView(output.buffer); output.set(bytes.subarray(0, 27));
  function write(node: Node, offset: number): number {
    const end = offset + size(node); const set = (at: number, value: number) => { if (wide) target.setBigUint64(at, BigInt(value), true); else target.setUint32(at, value, true); };
    set(offset, end); set(offset + (wide ? 8 : 4), node.propertyCount); set(offset + (wide ? 16 : 8), node.properties.length); output[offset + header - 1] = node.name.length;
    offset += header; output.set(node.name, offset); offset += node.name.length; output.set(node.properties, offset); offset += node.properties.length;
    for (const child of node.children) offset = write(child, offset); return offset + (node.terminator ? header : 0);
  }
  let offset = 27; for (const root of roots) offset = write(root, offset); output.set(bytes.subarray(tail), offset); return output.buffer;
}

interface AlphaBinding { material:Node; diffuse?:number|string; diffuseConnection?:Node; eligible:boolean }
function nativeAlphaBindings(roots:Node[]):AlphaBinding[] {
  const objects=roots.find(root=>name(root)==='Objects')?.children||[];
  const connections=roots.find(root=>name(root)==='Connections')?.children.filter(child=>name(child)==='C')||[];
  const textureBindings=new Map<unknown,{diffuse?:number|string;transparent?:number|string;diffuseConnection?:Node}>();
  for(const entry of connections){
    const connection=values(entry);if(connection[0]!=='OP'||(typeof connection[1]!=='number'&&typeof connection[1]!=='string'))continue;
    const binding=textureBindings.get(connection[2])||{},kind=String(connection[3]).toLowerCase();
    // Current main AND pinned release f91d15a lowercase kind before testing
    // contains("DiffuseFactor"). That branch is unreachable; the subsequent
    // generic diffuse branch therefore makes factor/color order last-wins.
    if((kind.includes('diffuse')&&!kind.includes('tex_global_diffuse'))||kind.includes('tex_color_map')){binding.diffuse=connection[1];binding.diffuseConnection=entry;}
    else if(kind.includes('transparentcolor')||kind.includes('transparencyfactor'))binding.transparent=connection[1];
    textureBindings.set(connection[2],binding);
  }
  const embedded=new Set<string>();
  for(const object of objects.filter(object=>name(object)==='Video')){
    const filename=object.children.find(child=>name(child)==='RelativeFilename');
    const content=object.children.find(child=>name(child)==='Content');
    if(filename&&content&&values(content).some(value=>typeof value==='string'?value.length>0:value instanceof Uint8Array&&value.length>0))embedded.add(String(values(filename)[0]).replaceAll('\\','/'));
  }
  const filenames=new Map<number|string,string>();
  for(const object of objects.filter(object=>name(object)==='Texture')){
    const id=values(object)[0],filename=object.children.find(child=>name(child)==='RelativeFilename');
    if((typeof id!=='number'&&typeof id!=='string')||!filename)continue;
    const raw=String(values(filename)[0]).replaceAll('\\','/');
    // FBXSerializer::fileOnUrl discards directories for external images, while
    // getTexture keeps the full filepath for actual embedded Video content.
    filenames.set(id,embedded.has(raw)?raw:raw.slice(raw.lastIndexOf('/')+1));
  }
  const creator=roots.find(root=>name(root)==='Creator');
  const blender=creator?/Blender.*-\s(\d+)\.(\d+).*-/.exec(String(values(creator)[0])):null;
  const legacyBlender=!!blender&&(Number(blender[1])<2||(Number(blender[1])===2&&Number(blender[2])<80));
  const stingray=new Set(['Maya|use_normal_map','Maya|base_color','Maya|use_color_map','Maya|roughness','Maya|use_roughness_map','Maya|metallic','Maya|use_metallic_map','Maya|emissive','Maya|emissive_intensity','Maya|use_emissive_map','Maya|use_ao_map']);
  return objects.filter(object=>name(object)==='Material').map(material=>{
    const id=values(material)[0],{diffuse,transparent,diffuseConnection}=textureBindings.get(id)||{};let pbs=false;
    // Native material property order matters: ReflectionFactor can reset the
    // Blender legacy fallback, and a later Stingray property opts into PBS.
    for(const container of material.children.filter(child=>['Properties60','Properties70'].includes(name(child)))){
      for(const property of container.children.filter(child=>['P','Property'].includes(name(child)))){
        const key=String(values(property)[0]);if(key==='ReflectionFactor')pbs=!legacyBlender;else if(stingray.has(key))pbs=true;
      }
    }
    const filename=diffuse===undefined?'':filenames.get(diffuse)||'';
    return {material,diffuse,diffuseConnection,eligible:!!filename&&(pbs||(transparent!==undefined&&filenames.get(transparent)===filename))};
  });
}
function alphaConnections(connections:Node[]):Map<unknown,Node[]> {
  const result=new Map<unknown,Node[]>();
  for(const connection of connections){if(name(connection)!=='C')continue;const data=values(connection);if(data[0]!=='OP'||!/transparentcolor|transparencyfactor/i.test(String(data[3])))continue;const list=result.get(data[2])||[];list.push(connection);result.set(data[2],list);}
  return result;
}
/** Match native FBX diffuse-alpha eligibility without changing authored geometry or opacity.
 * PBS uses the albedo alpha; legacy FBX uses it only when its authored opacity
 * texture resolves to that same native filename. Native does not support a
 * distinct opacity image. Three's independent green-channel alphaMap is thus
 * rebound to the exact albedo Texture, for the caller to classify real RGBA.
 * Supports bounded binary and standard line-oriented ASCII FBX. Compact
 * in-line ASCII blocks fail explicitly, including compact geometry blocks;
 * this adapter does not claim support for every legal ASCII layout.
 */
export function normalizeNativeFbxTransparency(input:ArrayBuffer):ArrayBuffer {
  const parsed=parseBinaryFbx(input);
  if(!parsed)return normalizeAsciiFbxTransparency(input);
  const connections=parsed.roots.find(root=>name(root)==='Connections');if(!connections)return input;
  let changed=false;const removedTextures=new Set<number|string>(),removed=new Set<Node>(),additions:Node[]=[];
  const alphaByMaterial=alphaConnections(connections.children);
  for(const binding of nativeAlphaBindings(parsed.roots)){
    const id=values(binding.material)[0],existing=alphaByMaterial.get(id)||[];
    if(binding.diffuseConnection&&values(binding.diffuseConnection)[3]!=='DiffuseColor'){
      binding.diffuseConnection.properties=concatenate([scalar('S','OP'),scalarID(binding.diffuse!),scalarID(id),scalar('S','DiffuseColor')]);binding.diffuseConnection.propertyCount=4;changed=true;
    }
    if(binding.eligible&&existing.length===1&&values(existing[0])[1]===binding.diffuse&&values(existing[0])[3]==='TransparentColor')continue;
    if(!binding.eligible&&!existing.length)continue;
    for(const connection of existing){const texture=values(connection)[1];if(typeof texture==='number'||typeof texture==='string')removedTextures.add(texture);}
    existing.forEach(child=>removed.add(child));
    if(binding.eligible)additions.push(node('C',[scalar('S','OP'),scalarID(binding.diffuse!),scalarID(id),scalar('S','TransparentColor')]));
    changed=true;
  }
  // Three parses every Texture, including now-unused standalone opacity maps.
  // Keep those IDs structurally connected without any material channel binding.
  connections.children=connections.children.filter(child=>!removed.has(child)).concat(additions);
  const active=new Set(connections.children.filter(child=>name(child)==='C').flatMap(child=>values(child).slice(1,3)));
  for(const texture of removedTextures){if(!active.has(texture))connections.children.push(node('C',[scalar('S','OO'),scalarID(texture),scalarID(0)]));}
  if(connections.children.length)connections.terminator=true;
  return changed?serializeBinaryFbx(parsed):input;
}
function scalarID(value:number|string|Uint8Array):Uint8Array {
  if(typeof value==='string')return scalar('S',value);
  if(typeof value!=='number'||!Number.isSafeInteger(value))throw Error('Invalid native FBX material identity');
  const bytes=new Uint8Array(9);bytes[0]='L'.charCodeAt(0);new DataView(bytes.buffer).setBigInt64(1,BigInt(value),true);return bytes;
}

function normalizeAsciiFbxTransparency(input:ArrayBuffer):ArrayBuffer {
  const bytes=new Uint8Array(input);
  const prefix=text.decode(bytes.subarray(0,1024));
  if(!/^\s*;\s*FBX\b/.test(prefix)&&!/(?:^|\n)\s*FBXHeaderExtension\s*:/.test(prefix))return input;
  safe(bytes.length,MAX_BYTES,'input length');
  const source=text.decode(bytes);
  // Standard line-oriented ASCII FBX retains every original geometry line. A
  // compact/malformed metadata block fails visibly instead of guessing PBS.
  const roots:Node[]=[],stack:Node[]=[],ranges=new Map<Node,{start:number;end:number;close?:number;indent:string}>();
  let offset=0,count=0;
  for(const raw of source.split(/(?<=\n)/)){
    const lineStart=offset;offset+=raw.length;
    let quoted=false,comment=raw.length;
    for(let i=0;i<raw.length;i++){if(raw[i]==='"'&&raw[i-1]!=='\\')quoted=!quoted;else if(raw[i]===';'&&!quoted){comment=i;break;}}
    const line=raw.slice(0,comment).trim();if(!line)continue;
    if(/^}+$/.test(line)){
      for(let i=0;i<line.length;i++){const closing=stack.pop();if(!closing)throw Error('Invalid ASCII FBX hierarchy');ranges.get(closing)!.close=lineStart;}
      continue;
    }
    const match=/^(\s*)([A-Za-z0-9_]+)\s*:\s*(.*)$/.exec(raw.slice(0,comment).trimEnd());
    if(!match){if(line.includes('{')||line.includes('}'))throw Error('Unsupported compact ASCII FBX metadata');continue;}
    const [,indent,label]=match;let content=match[3].trim(),opens=false;
    if(content.endsWith('{')){opens=true;content=content.slice(0,-1).trim();}
    let inQuote=false;
    for(let i=0;i<content.length;i++){if(content[i]==='"'&&content[i-1]!=='\\')inQuote=!inQuote;else if(!inQuote&&/[{}]/.test(content[i]))throw Error('Unsupported compact ASCII FBX metadata');}
    if(inQuote)throw Error('Unterminated ASCII FBX metadata string');
    if(++count>100_000||stack.length>128)throw Error('Invalid ASCII FBX node hierarchy');
    const parent=stack.at(-1),parentName=parent?name(parent):'';
    const metadata=(parentName==='Objects'&&['Material','Texture','Video'].includes(label))||label==='Creator'
      ||(parentName==='Connections'&&label==='C')||(['Properties60','Properties70'].includes(parentName)&&['P','Property'].includes(label))
      ||(['Texture','Video'].includes(parentName)&&['RelativeFilename','Content'].includes(label));
    const properties=metadata?asciiProperties(content):[];
    const entry=node(label,properties);(parent?parent.children:roots).push(entry);ranges.set(entry,{start:lineStart,end:offset,indent});
    if(opens)stack.push(entry);
  }
  if(stack.length)throw Error('Unterminated ASCII FBX hierarchy');
  const connections=roots.find(root=>name(root)==='Connections');if(!connections)return input;
  const location=ranges.get(connections);if(location?.close===undefined)throw Error('Invalid ASCII FBX connection block');
  const edits:{start:number;end:number;text:string}[]=[],additions:string[]=[],removed=new Set<Node>(),removedTextures=new Set<number|string>(),addedIDs=new Set<number|string>();
  const alphaByMaterial=alphaConnections(connections.children);
  const newline=source.includes('\r\n')?'\r\n':'\n';
  const indent=connections.children.length?ranges.get(connections.children[0])!.indent:location.indent+'\t';
  for(const binding of nativeAlphaBindings(roots)){
    const id=values(binding.material)[0],existing=alphaByMaterial.get(id)||[];
    const identity=(value:number|string|Uint8Array)=>{if(typeof value==='string')return JSON.stringify(value);if(typeof value!=='number'||!Number.isSafeInteger(value))throw Error('Invalid native ASCII FBX material identity');return String(value);};
    if(binding.diffuseConnection&&values(binding.diffuseConnection)[3]!=='DiffuseColor'){const range=ranges.get(binding.diffuseConnection)!;edits.push({start:range.start,end:range.end,text:`${range.indent}C: \"OP\", ${identity(binding.diffuse!)}, ${identity(id)}, \"DiffuseColor\"${newline}`});}
    if(binding.eligible&&existing.length===1&&values(existing[0])[1]===binding.diffuse&&values(existing[0])[3]==='TransparentColor')continue;
    if(!binding.eligible&&!existing.length)continue;
    for(const entry of existing){removed.add(entry);const texture=values(entry)[1];if(typeof texture==='number'||typeof texture==='string')removedTextures.add(texture);const range=ranges.get(entry)!;edits.push({start:range.start,end:range.end,text:''});}
    if(binding.eligible){
      if(typeof binding.diffuse==='number'||typeof binding.diffuse==='string')addedIDs.add(binding.diffuse);
      additions.push(`${indent}C: "OP", ${identity(binding.diffuse!)}, ${identity(id)}, "TransparentColor"${newline}`);
    }
  }
  const active=new Set(connections.children.filter(child=>!removed.has(child)).flatMap(child=>values(child).slice(1,3)));
  for(const texture of removedTextures){if(!active.has(texture)&&!addedIDs.has(texture))additions.push(`${indent}C: \"OO\", ${typeof texture==='number'?texture:JSON.stringify(texture)}, 0${newline}`);}
  if(!edits.length&&!additions.length)return input;
  if(additions.length)edits.push({start:location.close,end:location.close,text:additions.join('')});
  // Build once rather than copying the full world asset for each material.
  // A large valid material collection must remain linear in source size.
  edits.sort((a,b)=>a.start-b.start);const pieces:string[]=[];let cursor=0;
  for(const edit of edits){if(edit.start<cursor)throw Error('Overlapping ASCII FBX metadata edits');pieces.push(source.slice(cursor,edit.start),edit.text);cursor=edit.end;}
  pieces.push(source.slice(cursor));const result=encoder.encode(pieces.join(''));safe(result.length,MAX_OUTPUT,'output length');return result.buffer;
}
function asciiProperties(source:string):Uint8Array[] {
  const entries:string[]=[];let quote=false,start=0;
  for(let i=0;i<source.length;i++){
    if(source[i]==='"'&&source[i-1]!=='\\')quote=!quote;
    else if(source[i]===','&&!quote){entries.push(source.slice(start,i).trim());start=i+1;}
  }
  if(quote)throw Error('Unterminated ASCII FBX property');entries.push(source.slice(start).trim());
  if(entries.length>1024)throw Error('ASCII FBX metadata properties exceed their limit');
  return entries.map(value=>{
    if(value.startsWith('"')&&value.endsWith('"'))return scalar('S',value.slice(1,-1).replaceAll('\\"','"'));
    if(value==='')return scalar('S','');
    const numeric=Number(value);if(!Number.isFinite(numeric))throw Error('Invalid ASCII FBX metadata property');
    const result=new Uint8Array(9);result[0]='D'.charCodeAt(0);new DataView(result.buffer).setFloat64(1,numeric,true);return result;
  });
}
