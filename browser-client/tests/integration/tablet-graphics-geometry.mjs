// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Read only the genuine displayed canvas. This is deliberately serializable
 * into either driver; it sends no native command and creates no Qt state. */
export function measureNativeGraphicsRows(canvas, rect) {
    if (!rect || ![rect.x,rect.y,rect.width,rect.height].every(Number.isFinite) ||
        rect.x<0 || rect.y<0 || rect.width<1 || rect.height<1 ||
        rect.x+rect.width>canvas.width+1 || rect.y+rect.height>canvas.height+1 ||
        canvas.width*canvas.height>4_000_000) throw Error('Unsupported actual tablet canvas bounds');
    const context=canvas.getContext('2d');if(!context)throw Error('Native tablet canvas is unavailable');
    const pixels=context.getImageData(0,0,canvas.width,canvas.height).data,rows=[];
    // The exact pinned SettingSlider track is in this native480px interval.
    // Classify its painted white/purple track, not labels or guessed page Y.
    for(let y=70;y<650;y++){
        let slider=0,combo=0;
        for(let x=272;x<459;x++){
            const offset=(Math.min(canvas.height-1,Math.floor(rect.y+y*rect.height/706))*canvas.width+
                Math.min(canvas.width-1,Math.floor(rect.x+x*rect.width/480)))*4;
            const r=pixels[offset],g=pixels[offset+1],b=pixels[offset+2],a=pixels[offset+3];
            if(a>240&&((r>=245&&g>=245&&b>=245)||(Math.abs(r-81)<=3&&Math.abs(g-83)<=3&&Math.abs(b-189)<=3)))slider++;
            if(a>240&&Math.abs(r-g)<=2&&Math.abs(g-b)<=2&&(Math.abs(r-51)<=2||Math.abs(r-68)<=2))combo++;
        }
        rows.push({y,slider,combo});
    }
    return rows;
}
/** Require both actual painted native tracks; ambiguity fails the test. */
export function locateNativeGraphicsControls(rows) {
    if(!Array.isArray(rows)||rows.length!==580||rows.some((row,index)=>row.y!==70+index||
        !Number.isInteger(row.slider)||!Number.isInteger(row.combo)||row.slider<0||row.slider>187||row.combo<0||row.combo>187))
        throw Error('Invalid native Graphics row measurements');
    function runs(field,min,max){
        const found=[];let start=null;
        for(let index=0;index<=rows.length;index++){
            if(index<rows.length&&rows[index][field]>=110){if(start===null)start=index;}
            else if(start!==null){const length=index-start;if(length>=min&&length<=max)found.push((rows[start].y+rows[index-1].y)/2);start=null;}
        }
        return found;
    }
    const sliders=runs('slider',8,25);
    if(sliders.length!==2||Math.abs(sliders[1]-sliders[0]-60)>2)throw Error('Expected exactly two actual native slider tracks');
    const combos=runs('combo',25,45).filter(y=>y<sliders[0]-40);
    if(combos.length!==1)throw Error('Expected exactly one actual native resolution combo');
    return {profile:{x:360,y:combos[0]},fieldOfView:{y:sliders[0]},resolutionPercent:{y:sliders[1]},localLights:{x:410,y:sliders[1]+60},cameraClipping:{x:410,y:sliders[1]+120}};
}
/** Native track endpoints/20px thumb and pinned resolution10..200 mapping. */
export function resolutionSliderX(percent){
    if(!Number.isInteger(percent)||percent<10||percent>200||percent%10!==0)throw Error('Invalid native slider percentage');
    return 281+(459-281)*(percent-10)/(200-10);
}
