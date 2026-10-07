// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// CPU historical input only: exact current bytes to authenticated whole58e bytes.
// No production imports, live admission, source fallback or unknown path allowance.
import {openSync,closeSync,fstatSync,readFileSync,realpathSync,constants} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,relative} from 'node:path';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const root=fileURLToPath(new URL('../../',import.meta.url));
const PINS={
  "browser-client/gateway/native-avatar-sample-diagnostics.js": {
    "before": "cd2f35f8bc04edfdb9c09fcd8b5399d1e03b5b3b40bbbf9a459620b68ad9be49",
    "after": "d59ff56f281fe91c19a16ff36686dcb29767405943023b11a76daa2c5a6a651e"
  },
  "browser-client/gateway/native-avatar-stdout-projection.mjs": {
    "before": "90c7c18ab0c35e85620bcfa94427253232715da53c0abaf781e817b14515ea3f",
    "after": "eb6a09fd81cf973077f40fcd0d108884c78aea60540782799acd0aca6c46b860"
  },
  "browser-client/gateway/native-bridge.js": {
    "before": "a0ad9878a10023646aad6ecd3a926cde1d364f441786c8a0cf0969ee536604d9",
    "after": "0ddc1fe1a664f9fc4b46ee85bb283d537c321285cee2b95f983a6d6ca7d536e9"
  },
  "browser-client/gateway/server.mjs": {
    "before": "e17fae1f721ed162e131309c983041ef824d5688080e5053b6b98f2f9f4722ea",
    "after": "6d5d81332a41a66df667fa1f8d75a5bbd1c29a345ccbb85fcb75e89419642099"
  },
  "browser-client/lab/curate-core-journey.py": {
    "before": "d879087afc510171c0e131c69ca40fd5127c77bbe78f6d8f86a4749c3cfb55b4",
    "after": "e6cf19232d627a7daa232cb299e365f4b2154b06bbf36f1946ce72f564ccb3e6"
  },
  "browser-client/tests/integration/native-peer-diagnostic.mjs": {
    "before": "3aec808022e1dd3fc95bdd895d370aae1eeb99386b0e90fb21f52f29a5029c1d",
    "after": "3f98145c4f78c9686a7df4bbeaf4ba0b67910a87ab8312d861ce0884aafa6cfe"
  },
  "browser-client/tests/integration/real-session.mjs": {
    "before": "daba35297a9090a29a916ddd7658c11b2713fcf1f25d78894e17d9ac922e915b",
    "after": "ca8f8f6502e569c130625ca72403b0a1bf145ac227645a16af88bb43aa7f94a7"
  },
  "browser-client/tests/integration/tablet-ptt-native-peer.mjs": {
    "before": "557f8cb9c6bec67c18dcbb2fcde5ea6ae4bcae58df57a628f69b18e290a6be89",
    "after": "51cb012c7e0e8882e6427dd409088fb427ee064a051c02684ed30a49d33accd9"
  }
};
const SAME={
 'browser-client/lab/manage.py':'84b4426187e078515b77984a3581a63130d2dbc0c5edf4230a66a17ecdbf8e66',
 'browser-client/lab/run-core-journey.sh':'9693ae82a858752909988534251b28c81bbc9a7c199328fc63915e77f84e25e4',
 'browser-client/lab/native-participant.js':'735a5ee9b4327963ea7fb2ebec5e2159c1196aa99d8b6e7fd996809f521b7ede'};
function fail(){throw Error('avatar-delivery-history-refused');}
function held(path,limit){
 let fd;
 try {
  if(realpathSync(path)!==path)fail();
  fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  const before=fstatSync(fd);
  if(!before.isFile()||before.uid!==process.getuid()||before.nlink!==1||(before.mode&0o022)||!Number.isSafeInteger(before.size)||before.size<0||before.size>limit)fail();
  const bytes=readFileSync(fd),after=fstatSync(fd);
  if(bytes.length!==before.size||!['dev','ino','size','uid','mode','nlink','mtimeMs','ctimeMs'].every(k=>before[k]===after[k]))fail();
  return bytes;
 }catch{fail();}finally{if(fd!==undefined)closeSync(fd);}
}
const compressed=held(fileURLToPath(new URL('./avatar-delivery-before.json.gz',import.meta.url)),65536);
if(sha(compressed)!=='f24bbe974e2213f83bdcb4f0abb6cc66d6b45d71d6c19243ce2e245f90cfd609')fail();
const archive=JSON.parse(gunzipSync(compressed,{maxOutputLength:512*1024}));
if(archive.schemaVersion!==1||Object.keys(archive).sort().join()!=='schemaVersion,sources'||Object.keys(archive.sources).sort().join()!==Object.keys(PINS).sort().join())fail();
for(const [path,pin] of Object.entries(PINS)){
 const row=archive.sources[path];
 if(!row||Object.keys(row).sort().join()!=='afterSHA256,beforeSHA256,beforeText'||row.beforeSHA256!==pin.before||row.afterSHA256!==pin.after||typeof row.beforeText!=='string'||sha(Buffer.from(row.beforeText))!==pin.before)fail();
}
export function recoverReviewedAvatarSource(path,bytes){
 const pin=PINS[path];if(!pin||!Buffer.isBuffer(bytes)||bytes.length>256*1024||sha(bytes)!==pin.after)fail();
 return Buffer.from(archive.sources[path].beforeText);
}
export function readReviewedAvatarSource(url,encoding){
 if(encoding!==undefined&&encoding!=='utf8')fail();
 if(!(url instanceof URL)||url.protocol!=='file:')fail();
 const path=fileURLToPath(url),key='browser-client/'+relative(root,path).replaceAll('\\','/');
 if(!PINS[key]&&!SAME[key])fail();
 const bytes=held(path,256*1024);
 if(SAME[key]&&sha(bytes)!==SAME[key])fail();
 const result=SAME[key]?bytes:recoverReviewedAvatarSource(key,bytes);
 return encoding===undefined?result:result.toString('utf8');
}
for(const pin of Object.values(PINS))Object.freeze(pin);
export const avatarDeliverySourcePins=Object.freeze(PINS);
