// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {open,realpath,stat} from 'node:fs/promises';
import path from 'node:path';
export const REVIEWED_SCREENSHOT_ICC_SHA256='883a0b8b9fd4ed2381bf911b9ec7f5e59e93ae01440c34e9447aca0557a0b6e1';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
/** Exactly one audited profile; not a general ICC converter or name-based admission. */
export function qualifyReviewedScreenshotICC(bytes){
 assert(bytes instanceof Uint8Array&&bytes.byteLength===480,'Unsupported screenshot ICC profile size');
 const b=Buffer.from(bytes.buffer,bytes.byteOffset,bytes.byteLength);
 assert.equal(sha(b),REVIEWED_SCREENSHOT_ICC_SHA256,'Unsupported screenshot ICC profile bytes');
 assert.equal(b.readUInt32BE(0),480);assert.equal(b.readUInt32BE(8),0x04300000);
 assert.equal(b.toString('ascii',12,16),'mntr');assert.equal(b.toString('ascii',16,20),'RGB ');assert.equal(b.toString('ascii',20,24),'XYZ ');assert.equal(b.toString('ascii',36,40),'acsp');
 assert.equal(b.readUInt32BE(128),9);const tags=new Map();
 for(let i=0;i<9;i++){const at=132+i*12,name=b.toString('ascii',at,at+4),offset=b.readUInt32BE(at+4),length=b.readUInt32BE(at+8);assert(!tags.has(name)&&offset>=240&&offset+length<=480);tags.set(name,b.subarray(offset,offset+length));}
 assert.deepEqual([...tags.keys()],['desc','rXYZ','gXYZ','bXYZ','wtpt','rTRC','gTRC','bTRC','cprt']);
 const xyz=(name,expected)=>{const t=tags.get(name);assert.equal(t.length,20);assert.equal(t.toString('ascii',0,4),'XYZ ');assert.equal(t.readUInt32BE(4),0);const values=[8,12,16].map(at=>t.readInt32BE(at));assert.deepEqual(values,expected);return values;};
 const matrix=[xyz('rXYZ',[0x6fa2,0x38f5,0x0390]),xyz('gXYZ',[0x6299,0xb785,0x18da]),xyz('bXYZ',[0x24a0,0x0f84,0xb6cf])];
 xyz('wtpt',[0xf6d6,0x10000,0xd32d]);
 for(const name of ['rTRC','gTRC','bTRC']){const t=tags.get(name);assert.equal(t.length,16);assert.equal(t.toString('ascii',0,4),'para');assert.equal(t.readUInt32BE(4),0);assert.equal(t.readUInt32BE(8),0);assert.equal(t.readInt32BE(12),144179);}
 return {kind:'reviewed-srgb-primaries-gamma22-icc',profileSHA256:sha(b),profileBytes:b.length,matrixFixed16:matrix,gammaFixed16:144179};
}
export function expectedEmbeddingScreenshotColor(profile=null){
 const authored=[40,80,100,255];if(profile===null)return {expected:authored,encoding:{kind:'authored-srgb-no-icc'}};
 const encoding=qualifyReviewedScreenshotICC(profile),gamma=encoding.gammaFixed16/65536;
 // Pinned Skia source uses exactly the same fixed-point sRGB/D50 matrix.
 // Its matrix transform is identity; only the transfer curve differs.
 const rgb=authored.slice(0,3).map(v=>{const s=v/255,linear=s<=.04045?s/12.92:((s+.055)/1.055)**2.4;return Math.round(linear**(1/gamma)*255);});
 assert.deepEqual(rgb,[44,81,100]);return {expected:[...rgb,255],encoding};
}
/** Preserve exact owned element bytes before assertion, never overwrite or publish them. */
export async function preservePrivateComposedPng(bytes,filename){
 assert(bytes instanceof Uint8Array&&bytes.byteLength>=33&&bytes.byteLength<=4*1024*1024);
 assert(typeof filename==='string'&&path.isAbsolute(filename));
 assert(['embedding-negative-composed.png','delegated-positive-composed.png'].includes(path.basename(filename)));
 const parent=path.dirname(filename);assert.equal(await realpath(parent),parent);const directory=await stat(parent);
 assert(directory.isDirectory()&&(directory.mode&0o777)===0o700&&directory.uid===process.getuid());
 const handle=await open(filename,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW|constants.O_NONBLOCK,0o600);
 try{const own=await handle.stat();assert(own.isFile()&&(own.mode&0o777)===0o600&&own.uid===process.getuid());await handle.writeFile(bytes);assert.equal((await handle.stat()).size,bytes.byteLength);}finally{await handle.close();}
}
