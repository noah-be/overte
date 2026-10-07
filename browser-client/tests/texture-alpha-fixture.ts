// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import { nativeTextureAlpha } from '../src/texture-alpha';

export async function auditAlphaPixels(url?: string) {
  const source = document.createElement('canvas'); source.width = source.height = 64;
  const context = source.getContext('2d')!;
  context.clearRect(0,0,64,64); context.fillStyle = '#00ff00'; context.fillRect(16,16,32,32);
  // A genuinely opaque black patch must remain visible; RGB black is not a mask.
  context.fillStyle = '#000000'; context.fillRect(24,24,8,8);
  const texture = url ? await new THREE.TextureLoader().loadAsync(url) : new THREE.CanvasTexture(source);
  texture.colorSpace = THREE.SRGBColorSpace; texture.magFilter = THREE.NearestFilter; texture.minFilter = THREE.NearestFilter;
  const alpha = await nativeTextureAlpha(texture);
  const shared = await Promise.all([nativeTextureAlpha(texture),nativeTextureAlpha(texture)]);
  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true }); renderer.setSize(512,512); renderer.setClearColor(0x3366ff);
  renderer.toneMapping = THREE.NoToneMapping;
  const scene = new THREE.Scene(), camera = new THREE.OrthographicCamera(-1,1,1,-1,.1,10); camera.position.z=2;
  const material = new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide,toneMapped:false});
  const geometry = new THREE.PlaneGeometry(2,2), mesh = new THREE.Mesh(geometry,material);scene.add(mesh);
  const gl=renderer.getContext();
  function read() {renderer.render(scene,camera);const pixels=new Uint8Array(512*512*4);gl.readPixels(0,0,512,512,gl.RGBA,gl.UNSIGNED_BYTE,pixels);let background=0,black=0,green=0;for(let i=0;i<pixels.length;i+=4){if(pixels[i]===51&&pixels[i+1]===102&&pixels[i+2]===255)background++;if(pixels[i]===0&&pixels[i+1]===0&&pixels[i+2]===0)black++;if(pixels[i+1]>200&&pixels[i]<40&&pixels[i+2]<40)green++;}return{background,black,green};}
  try {
    const before=read();material.alphaTest=alpha==='mask'?.5:0;material.transparent=alpha==='blend';material.needsUpdate=true;const after=read();
    return {alpha,shared,before,after};
  } finally {geometry.dispose();material.dispose();texture.dispose();renderer.dispose();}
}

export async function auditAlphaCancellation() {
  const canvas=document.createElement('canvas');canvas.width=canvas.height=2048;
  const c=canvas.getContext('2d')!;c.fillStyle='#000000';c.fillRect(0,0,2048,2048);
  const texture={image:canvas}, abort=new AbortController();
  const cancelled=nativeTextureAlpha(texture,abort.signal).then(()=>false,error=>error.name==='AbortError');
  const retained=nativeTextureAlpha(texture);abort.abort();
  const initial={cancelled:await cancelled,retained:await retained};
  const fresh=document.createElement('canvas');fresh.width=fresh.height=512;
  const stop=new AbortController();const abandoned=nativeTextureAlpha({image:fresh},stop.signal).catch(error=>error.name==='AbortError');
  stop.abort();await abandoned;
  return {...initial,retry:await nativeTextureAlpha({image:fresh})};
}
