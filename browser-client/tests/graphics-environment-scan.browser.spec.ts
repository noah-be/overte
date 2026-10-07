// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
test('explicit scanner observes real current World renderer success callbacks, never hidden RAF, and preserves original quality',async({page})=>{
    await page.goto('/');
    const result=await page.evaluate(async()=>{
        const worldPath='/src/world.ts',scanPath='/src/graphics-environment-scan.ts',framesPath='/src/graphics-scan-frames.ts';
        const {BrowserWorld}=await import(worldPath),{GraphicsEnvironmentScan}=await import(scanPath);void framesPath;
        const host=document.createElement('div');Object.assign(host.style,{position:'fixed',inset:'0'});document.body.append(host);
        const warnings:string[]=[];const world=new BrowserWorld(host,{resolveAsset:(value:string)=>value,onPose(){},onInteract(){},onStatus:(message:string,kind:string)=>{if(kind==='warning'||kind==='error')warnings.push(message);}});
        const internal=world as any,renderer=internal.renderer,gl=renderer.getContext();const abort=new AbortController(),frames=world.getGraphicsScanFrames();let observed=0;
        const originalPublish=frames.publish.bind(frames);frames.publish=(value:any)=>{observed++;originalPublish(value);};
        const scanner=new GraphicsEnvironmentScan({frames,document,current:()=>!abort.signal.aborted,presentationVisible:()=>world.graphicsScanPresentationVisible(),settings:()=>world.graphics.snapshot(),
            capabilities:()=>({webgl2:gl instanceof WebGL2RenderingContext,contextAntialias:gl.getContextAttributes()?.antialias??null,maximumTextureDimension:gl.getParameter(gl.MAX_TEXTURE_SIZE),maximumRenderbufferDimension:gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),maximumViewportWidth:gl.getParameter(gl.MAX_VIEWPORT_DIMS)[0],maximumViewportHeight:gl.getParameter(gl.MAX_VIEWPORT_DIMS)[1],drawingBufferWidth:gl.drawingBufferWidth,drawingBufferHeight:gl.drawingBufferHeight}),applyResolution:async()=>{throw Error('This fidelity fixture never applies suggestions');}});
        try{
            world.setEntities([{id:'scan-authored-box',type:'Box',position:{x:0,y:.85,z:0},dimensions:{x:2,y:2,z:2},color:{red:80,green:180,blue:100},collisionless:true},{id:'scan-authored-floor',type:'Box',position:{x:0,y:-.25,z:0},dimensions:{x:20,y:.5,z:20},color:{red:40,green:40,blue:40},collisionless:false}]);world.setSpawn({x:0,y:.85,z:4});
            const deadline=performance.now()+15000;while(performance.now()<deadline&&(!internal.objects.get('scan-authored-box')?.userData.shadersReady||world.getPerformance().compilingGraphics))await new Promise<void>(r=>requestAnimationFrame(()=>r()));
            if(!internal.objects.get('scan-authored-box')?.userData.shadersReady)throw Error('Actual native entity geometry required');
            world.setEnabled(true);const before=world.graphics.snapshot();world.setPresentationEnabled(false);const hidden=await scanner.scan();const noActive=frames.active;world.setPresentationEnabled(true);
            const report=await scanner.scan();const current=world.graphics.snapshot();const rgba=new Uint8Array(4);gl.readPixels(Math.floor(gl.drawingBufferWidth/2),Math.floor(gl.drawingBufferHeight/2),1,1,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
            return {hidden,noActive,report,before,current,observed,rgba:[...rgba],warnings,listenerReleased:!frames.active};
        }finally{scanner.dispose();abort.abort();world.dispose();renderer.forceContextLoss();host.remove();}
    });
    expect(result.hidden.status).toBe('refused');expect(result.noActive).toBe(false);expect(result.report.status).toBe('complete');expect(result.current).toEqual(result.before);expect(result.listenerReleased).toBe(true);
    if(result.report.status==='complete'){expect(result.report.report.frameIntervals).toBeGreaterThanOrEqual(12);expect(result.report.report.frameIntervals).toBeLessThanOrEqual(512);expect(result.report.report.elapsedMs).toBeGreaterThanOrEqual(2000);expect(result.report.report.defaultRecommendation).toBe('keep-current-settings');expect(result.report.report.capabilities.webgl2).toBe(true);}
    expect(result.observed).toBeGreaterThanOrEqual(13);expect(result.rgba[3]).toBe(255);expect(result.rgba[1]).toBeGreaterThan(result.rgba[0]);expect(result.warnings).toEqual([]);
});

test('browser-owned Tablet Scan button closes only its presentation and returns Home after actual completed World renders',async({page})=>{
    await page.setViewportSize({width:375,height:812});
    await page.goto('/');
    await page.evaluate(async()=>{
        const paths={world:'/src/world.ts',scan:'/src/graphics-environment-scan.ts',tablet:'/src/tablet.ts'};
        const {BrowserWorld}=await import(paths.world),{GraphicsEnvironmentScan}=await import(paths.scan),{BrowserTablet}=await import(paths.tablet);
        const host=document.createElement('div');Object.assign(host.style,{position:'fixed',inset:'0'});document.body.append(host);
        const world=new BrowserWorld(host,{resolveAsset:(value:string)=>value,onPose(){},onInteract(){},onStatus(){}}),internal=world as any;
        const frames=world.getGraphicsScanFrames();const commands:Record<string,unknown>[]=[];let tablet:any;
        const scanner=new GraphicsEnvironmentScan({frames,document,current:()=>!internal.abort.signal.aborted,presentationVisible:()=>world.graphicsScanPresentationVisible(),settings:()=>world.graphics.snapshot(),capabilities:()=>world.getGraphicsEnvironment(),applyResolution:async()=>{throw Error('No native engine is provided by this DOM/render fixture');}});
        tablet=new BrowserTablet(host,{graphicsEnvironment:scanner,onStatus(){},onVisibility:(visible:boolean)=>{world.setInputEnabled(!visible);world.setPresentationEnabled(!visible);},send:(value:Record<string,unknown>)=>commands.push(value)});
        try{
            world.setEntities([{id:'panel-floor',type:'Box',position:{x:0,y:-.25,z:0},dimensions:{x:20,y:.5,z:20},color:{red:40,green:40,blue:40},collisionless:false},{id:'panel-box',type:'Box',position:{x:0,y:1,z:0},dimensions:{x:2,y:2,z:2},color:{red:30,green:180,blue:60},collisionless:true}]);world.setSpawn({x:0,y:.85,z:4});world.setEnabled(true);
            const deadline=performance.now()+15000;while(performance.now()<deadline&&(!internal.objects.get('panel-box')?.userData.shadersReady||world.getPerformance().compilingGraphics))await new Promise<void>(r=>requestAnimationFrame(()=>r()));
            if(!internal.objects.get('panel-box')?.userData.shadersReady)throw Error('Actual authored World geometry required');
            tablet.setConnected(true);tablet.receive({type:'tablet',kind:'state',revision:7,visible:true,loading:false,screen:'Graphics'});
            // Authored protocol state opens this DOM scaffold. It does not claim a native Qt frame or GUI qualification.
            (window as any).__scanPanelFixture={commands,world,tablet,scanner,before:world.graphics.snapshot(),beforeFrames:world.getPerformance().renderedFrames,
                dispose(){tablet.dispose();scanner.dispose();world.dispose();internal.renderer.forceContextLoss();host.remove();}};
        }catch(error){tablet.dispose();scanner.dispose();world.dispose();internal.renderer.forceContextLoss();host.remove();throw error;}
    });
    try{
        await page.getByRole('button',{name:'Scan browser graphics',exact:true}).click();
        await expect.poll(()=>page.evaluate(()=>!(window as any).__scanPanelFixture.tablet.visible)).toBe(true);
        await expect.poll(()=>page.getByLabel('Browser graphics environment').textContent(),{timeout:10000}).toContain('observed');
        const result=await page.evaluate(()=>{const f=(window as any).__scanPanelFixture;return {visible:f.tablet.visible,commands:f.commands.map((c:any)=>c.action),before:f.before,after:f.world.graphics.snapshot(),released:!f.world.getGraphicsScanFrames().active,rendered:f.world.getPerformance().renderedFrames-f.beforeFrames};});
        expect(result.visible).toBe(true);expect(result.commands).toEqual(['close','open']);expect(result.after).toEqual(result.before);expect(result.released).toBe(true);expect(result.rendered).toBeGreaterThanOrEqual(13);
        await expect(page.getByRole('button',{name:'Fullscreen',exact:true})).toBeVisible();
        const buttons=await page.getByLabel('Browser graphics environment').locator('button').evaluateAll(elements=>elements.map(element=>{const r=element.getBoundingClientRect();return {width:r.width,height:r.height,left:r.left,right:r.right};}));
        expect(buttons).toHaveLength(2);for(const button of buttons){expect(button.width).toBeGreaterThan(0);expect(button.height).toBeGreaterThan(0);expect(button.left).toBeGreaterThanOrEqual(0);expect(button.right).toBeLessThanOrEqual(await page.evaluate(()=>window.innerWidth));}
    }finally{await page.evaluate(()=>{(window as any).__scanPanelFixture?.dispose();delete (window as any).__scanPanelFixture;});}
});
