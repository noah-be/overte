// SPDX-License-Identifier: Apache-2.0
// Share the production module graph: direct and optimized Three build imports
// otherwise have distinct constructors and material callback prototypes.
import * as THREE from 'three';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { batchStaticModel } from '../src/static-model-batch';
export async function auditNativeStaticPixels() {
        const manager = new THREE.LoadingManager();
        const loaded = new Promise<void>((resolve, reject) => { manager.onLoad = resolve; manager.onError = () => reject(Error('Actual native embedded texture failed to decode')); });
        const bytes = await (await fetch('/default-avatar/mannequin/mannequin.fbx')).arrayBuffer();
        const native = new FBXLoader(manager).parse(bytes, '/default-avatar/mannequin/');
        await loaded;
        let body: any;
        native.traverse((object: any) => { if (object.name === 'body' && object.isSkinnedMesh) body = object; });
        if (!body) throw Error('Native body geometry is missing');
        const geometry = body.geometry.clone(); geometry.deleteAttribute('skinIndex'); geometry.deleteAttribute('skinWeight'); geometry.morphAttributes = {};
        const root = new THREE.Group(); root.scale.setScalar(.01);
        const meshes = [-160, 0, 160].map((x, index) => { const mesh = new THREE.Mesh(geometry, body.material); mesh.position.set(x, index * 8, index * -30); root.add(mesh); return mesh; });
        const scene = new THREE.Scene(); scene.background = new THREE.Color(0x102030); scene.add(root);
        scene.add(new THREE.HemisphereLight(0xffffff, 0x808080, 2));
        const light = new THREE.DirectionalLight(0xffffff, 3); light.position.set(3, 5, 4); scene.add(light);
        const camera = new THREE.PerspectiveCamera(40, 1, .1, 100); camera.position.set(0, 2.2, 7); camera.lookAt(0, .9, 0);
        const canvas = document.createElement('canvas'); document.body.append(canvas);
        const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true }); renderer.setSize(512, 512, false);
        await renderer.compileAsync(scene, camera);
        const pixels = () => { renderer.render(scene, camera); const bytes = new Uint8Array(512 * 512 * 4), gl = renderer.getContext(); gl.readPixels(0, 0, 512, 512, gl.RGBA, gl.UNSIGNED_BYTE, bytes); return { bytes, draws: renderer.info.render.calls, triangles: renderer.info.render.triangles }; };
        const before = pixels(); const batch = batchStaticModel(root); const after = pixels();
        let different = 0, visible = 0;
        for (let i = 0; i < before.bytes.length; i += 4) {
            if (before.bytes[i] !== after.bytes[i] || before.bytes[i + 1] !== after.bytes[i + 1] || before.bytes[i + 2] !== after.bytes[i + 2]) different++;
            if (before.bytes[i] !== 16 || before.bytes[i + 1] !== 32 || before.bytes[i + 2] !== 48) visible++;
        }
        const unchangedMaterial = batch.batches.every((mesh: any) => mesh.material === body.material);
        batch.restore(); const restored = pixels();
        let restoredDifferences = 0; for (let i = 0; i < before.bytes.length; i++) if (before.bytes[i] !== restored.bytes[i]) restoredDifferences++;
        renderer.dispose(); geometry.dispose();
        return { before: { draws: before.draws, triangles: before.triangles }, after: { draws: after.draws, triangles: after.triangles }, saved: batch.savedDrawCalls, different, visible, unchangedMaterial, restoredDifferences, meshCount: meshes.length, nativeVertices: body.geometry.attributes.position.count };
}

// Exact equal-depth transparent tie regression. The source Mesh ID must remain
// unchanged even when hierarchy order differs from object construction order.
export async function auditMixedStaticPixels() {
    const source = new THREE.BufferGeometry();
    const positions: number[] = [];
    for (const z of [0,.5]) for (const x of [-1,1]) positions.push(x-.8,-.9,z, x+.8,-.9,z, x+.8,.9,z, x-.8,-.9,z, x+.8,.9,z, x-.8,.9,z);
    source.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
    source.addGroup(0,6,0);source.addGroup(12,6,1);source.addGroup(6,6,0);source.addGroup(18,6,1);
    const opaque=new THREE.MeshBasicMaterial({color:0x228833});
    const blue=new THREE.MeshBasicMaterial({color:0x2255ff,transparent:true,opacity:.4});
    const orange=new THREE.MeshBasicMaterial({color:0xff7722,transparent:true,opacity:.3});
    const original=new THREE.Mesh(source,[opaque,blue]);const originalID=original.id;
    const otherGeometry=source.clone();otherGeometry.clearGroups();otherGeometry.addGroup(12,6,0);otherGeometry.addGroup(18,6,0);
    const other=new THREE.Mesh(otherGeometry,[orange]);
    const root=new THREE.Group();root.add(other,original);
    const scene=new THREE.Scene();scene.background=new THREE.Color(0x102030);scene.add(root);
    const camera=new THREE.OrthographicCamera(-3,3,2,-2,.1,10);camera.position.z=5;
    const renderer=new THREE.WebGLRenderer({antialias:false,preserveDrawingBuffer:true});renderer.setSize(256,256,false);
    await renderer.compileAsync(scene,camera);
    const pixels=()=>{renderer.render(scene,camera);const bytes=new Uint8Array(256*256*4),gl=renderer.getContext();gl.readPixels(0,0,256,256,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return{bytes,calls:renderer.info.render.calls,triangles:renderer.info.render.triangles};};
    const before=pixels(),batch=batchStaticModel(root),after=pixels();
    let different=0,visible=0;for(let i=0;i<before.bytes.length;i+=4){if(before.bytes[i]!==after.bytes[i]||before.bytes[i+1]!==after.bytes[i+1]||before.bytes[i+2]!==after.bytes[i+2])different++;if(before.bytes[i]!==16||before.bytes[i+1]!==32||before.bytes[i+2]!==48)visible++;}
    const originalIdentityPreserved=original.id===originalID&&original.parent===root&&original.visible;
    const residualOrder=original.geometry.groups.map(group=>({start:group.start,count:group.count,materialIndex:group.materialIndex}));
    const sourceGeometryUnchanged=source.groups.length===4&&source.attributes.position.count===24;
    batch.restore();const restored=pixels();let restoredDifferences=0;for(let i=0;i<before.bytes.length;i++)if(before.bytes[i]!==restored.bytes[i])restoredDifferences++;
    const exactReferenceRestored=original.geometry===source;
    renderer.dispose();source.dispose();otherGeometry.dispose();opaque.dispose();blue.dispose();orange.dispose();
    return{before:{draws:before.calls,triangles:before.triangles},after:{draws:after.calls,triangles:after.triangles},saved:batch.savedDrawCalls,different,visible,originalIdentityPreserved,residualOrder,sourceGeometryUnchanged,exactReferenceRestored,restoredDifferences};
}

export async function auditActualIslandBatch() {
    const {adaptBakedFbx}=await import('../src/baked-fbx');
    const raw=await(await fetch('/actual-island.fbx')).arrayBuffer();
    const checker=document.createElement('canvas');checker.width=2;checker.height=2;const context=checker.getContext('2d')!;
    ['#ffffff','#aaaaaa','#888888','#eeeeee'].forEach((color,index)=>{context.fillStyle=color;context.fillRect(index%2,Math.floor(index/2),1,1);});
    const manager=new THREE.LoadingManager();
    manager.setURLModifier(()=>checker.toDataURL('image/png'));
    const root=new FBXLoader(manager).parse(await adaptBakedFbx(raw),'/');
    // Native baked texture metadata may intentionally omit conventional FBX images.
    // This geometry audit uses a declared checker, while retaining actual native
    // material identity, opacity, group membership and transparent sorting.
    const texture=new THREE.CanvasTexture(checker);
    root.traverse(object=>{if(object instanceof THREE.Mesh)for(const material of Array.isArray(object.material)?object.material:[object.material]) {if(material instanceof THREE.MeshPhongMaterial){material.map=texture;material.normalMap=null;material.bumpMap=null;material.alphaMap=null;material.emissiveMap=null;}}});
    root.traverse(object=>{if((object as THREE.Light).isLight)object.visible=false;});
    const bounds=new THREE.Box3().setFromObject(root),center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
    const scale=3/Math.max(size.x,size.y,size.z);root.position.sub(center).multiplyScalar(scale);root.scale.multiplyScalar(scale);
    const originalMaterials: THREE.Material[]=[];root.traverse(object=>{if(object instanceof THREE.Mesh)originalMaterials.push(...(Array.isArray(object.material)?object.material:[object.material]));});
    const scene=new THREE.Scene();scene.background=new THREE.Color(0x102030);scene.add(root,new THREE.HemisphereLight(0xffffff,0x808080,2));
    const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(3,5,4);scene.add(light);
    const renderer=new THREE.WebGLRenderer({antialias:false,preserveDrawingBuffer:true});renderer.setSize(512,512,false);
    const camera=new THREE.PerspectiveCamera(40,1,.01,100);camera.position.set(3,3.2,4);camera.lookAt(0,0,0);
    await renderer.compileAsync(scene,camera);
    const pixels=()=>{renderer.render(scene,camera);const bytes=new Uint8Array(512*512*4),gl=renderer.getContext();gl.readPixels(0,0,512,512,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return{bytes,draws:renderer.info.render.calls,triangles:renderer.info.render.triangles};};
    const before=pixels();const originalMeshes: {mesh:THREE.Mesh;id:number;geometry:THREE.BufferGeometry;groups:THREE.BufferGeometry['groups']}[]=[];
    root.traverse(object=>{if(object instanceof THREE.Mesh)originalMeshes.push({mesh:object,id:object.id,geometry:object.geometry,groups:object.geometry.groups.map((group: THREE.BufferGeometry['groups'][number])=>({...group}))});});
    const batch=batchStaticModel(root);const after=pixels();let different=0,visible=0;
    for(let i=0;i<before.bytes.length;i+=4){if(before.bytes[i]!==after.bytes[i]||before.bytes[i+1]!==after.bytes[i+1]||before.bytes[i+2]!==after.bytes[i+2])different++;if(before.bytes[i]!==16||before.bytes[i+1]!==32||before.bytes[i+2]!==48)visible++;}
    const residualGroups=originalMeshes.filter(value=>value.mesh.visible).map(value=>({idUnchanged:value.id===value.mesh.id,groups:value.mesh.geometry.groups.length,sourceGroups:value.groups.length}));
    const materialsUnchanged=batch.batches.every(mesh=>originalMaterials.includes(mesh.material as THREE.Material));
    batch.restore();const restored=pixels();let restoredDifferences=0;for(let i=0;i<before.bytes.length;i++)if(before.bytes[i]!==restored.bytes[i])restoredDifferences++;
    const originalGeometryRestored=originalMeshes.every(value=>value.mesh.geometry===value.geometry&&JSON.stringify(value.mesh.geometry.groups)===JSON.stringify(value.groups));
    renderer.dispose();
    return{before:{draws:before.draws,triangles:before.triangles},after:{draws:after.draws,triangles:after.triangles},saved:batch.savedDrawCalls,generatedBytes:batch.generatedBytes,different,visible,residualGroups,materialsUnchanged,originalGeometryRestored,restoredDifferences,diagnosticTexture:true};
}
