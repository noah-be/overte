// SPDX-License-Identifier: Apache-2.0
// CPU adapter for the actual Vite-built worker; does not emulate its parser or preparation.
import {parentPort,workerData} from 'node:worker_threads';
globalThis.self=globalThis;self.location={href:workerData.workerURL};self.postMessage=(value,transfer)=>parentPort.postMessage(value,transfer);
await import(workerData.workerURL);
parentPort.on('message',data=>{void self.onmessage({data});});
parentPort.postMessage({type:'ready'});
