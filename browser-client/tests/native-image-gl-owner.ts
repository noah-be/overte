// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Test-only, bounded 2D public GL call/identity diagnostics. A successful delete
// submission is not a physical GPU-memory measurement. Borrowed global Texture
// objects can retain a separate allocation in this renderer's context.
export function trackNativeImageTextures(gl:WebGL2RenderingContext){
 const created=new Set<WebGLTexture>(),deleted=new Set<WebGLTexture>(),ownedImages=new Set<object>(),bindings=new Map<string,WebGLTexture|null>(),uploads:{handle:WebGLTexture;image:object}[]=[];
 let unit=Number(gl.getParameter(gl.ACTIVE_TEXTURE)),deleteFailures=0;
 const original={createTexture:gl.createTexture,deleteTexture:gl.deleteTexture,activeTexture:gl.activeTexture,bindTexture:gl.bindTexture,texImage2D:gl.texImage2D,texSubImage2D:gl.texSubImage2D};
 gl.createTexture=function(){if(created.size>=256)throw Error('Authored Image fixture allocation diagnostics exceeded their bound');const handle=Reflect.apply(original.createTexture,gl,[]) as WebGLTexture;if(handle)created.add(handle);return handle;};
 gl.deleteTexture=function(handle){
  let result:unknown;
  try{result=Reflect.apply(original.deleteTexture,gl,[handle]);if(gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Authored Image fixture delete submission failed');}
  catch(error){deleteFailures++;throw error;}
  if(handle&&created.has(handle))deleted.add(handle);
  return result;
 };
 gl.activeTexture=function(value){const result=Reflect.apply(original.activeTexture,gl,[value]);unit=value;return result;};
 gl.bindTexture=function(target,handle){const result=Reflect.apply(original.bindTexture,gl,[target,handle]);bindings.set(unit+':'+target,handle);return result;};
 const record=(args:unknown[])=>{const handle=bindings.get(unit+':'+args[0]);if(!handle)return;for(const value of args){if(value&&typeof value==='object'){if(uploads.length>=256)throw Error('Authored Image fixture upload diagnostics exceeded their bound');uploads.push({handle,image:value});}}};
 gl.texImage2D=function(...args:unknown[]){const result=Reflect.apply(original.texImage2D,gl,args);record(args);return result;} as typeof gl.texImage2D;
 gl.texSubImage2D=function(...args:unknown[]){const result=Reflect.apply(original.texSubImage2D,gl,args);record(args);return result;} as typeof gl.texSubImage2D;
 return {
  own(image:unknown){if(!image||typeof image!=='object')throw Error('Owned Image upload source must be the actual Texture.source.data object');if(ownedImages.size>=256&&!ownedImages.has(image))throw Error('Authored Image fixture source diagnostics exceeded their bound');ownedImages.add(image);},
  report(borrowedImage?:object){
   const owned=new Set(uploads.filter(entry=>ownedImages.has(entry.image)).map(entry=>entry.handle)),borrowed=new Set(uploads.filter(entry=>entry.image===borrowedImage).map(entry=>entry.handle)),remaining=[...created].filter(handle=>!deleted.has(handle));
   return {created:created.size,deleted:deleted.size,deleteFailures,ownedUploaded:owned.size,ownedRemaining:remaining.filter(handle=>owned.has(handle)).length,borrowedUploaded:borrowed.size,borrowedRemaining:remaining.filter(handle=>borrowed.has(handle)).length,unrecognizedRemaining:remaining.filter(handle=>!borrowed.has(handle)).length};
  },
  restore(){Object.assign(gl,original);uploads.length=0;ownedImages.clear();bindings.clear();}
 };
}
