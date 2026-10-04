// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {GIFEncoder,quantize,applyPalette} from 'gifenc';
const scope=globalThis as unknown as {onmessage:((event:MessageEvent)=>void)|null;postMessage:(message:unknown,transfer?:Transferable[])=>void};
const encoder=GIFEncoder();let frames=0,received=0,width=0,height=0,duration=0;let last:{indexed:Uint8Array;palette:number[][]}|undefined;
scope.onmessage=async(event:MessageEvent)=>{
    try {
        if(event.data.action==='finish'){
            if(frames<2)throw Error('The animated snapshot needs at least two frames');
            // Encoding backpressure can leave a sparse final sample. Preserve
            // the intended recording duration instead of shortening playback.
            if(duration<5000&&last){encoder.writeFrame(last.indexed,width,height,{palette:last.palette,delay:5000-duration,repeat:0});duration=5000;frames++;}
            encoder.finish();const bytes=Uint8Array.from(encoder.bytes());
            if(bytes.byteLength>64*1024*1024)throw Error('The animated snapshot exceeds the visitor file limit');
            scope.postMessage({id:event.data.id,bytes:bytes.buffer,frames,duration},[bytes.buffer]);return;
        }
        if(event.data.action!=='frame'||received>=50||!(event.data.blob instanceof Blob))throw Error('Invalid animated snapshot frame');
        received++;if(duration>=5000){scope.postMessage({id:event.data.id,frames});return;}
        const image=await createImageBitmap(event.data.blob);
        try {
            if(!frames){width=Math.min(640,image.width);height=Math.max(1,Math.round(image.height*width/image.width));}
            const canvas=new OffscreenCanvas(width,height);const context=canvas.getContext('2d',{willReadFrequently:true});
            if(!context)throw Error('Animated snapshot canvas is unavailable');
            context.drawImage(image,0,0,width,height);const pixels=context.getImageData(0,0,width,height).data;
            const palette=quantize(pixels,256),indexed=applyPalette(pixels,palette);
            const delay=Math.min(5000-duration,Math.max(10,Math.round(event.data.delay/10)*10));
            encoder.writeFrame(indexed,width,height,{palette,delay,repeat:0});duration+=delay;frames++;last={indexed,palette};
            scope.postMessage({id:event.data.id,frames});
        } finally {image.close();}
    }catch(error){scope.postMessage({id:event.data.id,error:error instanceof Error?error.message:String(error)});}
};
