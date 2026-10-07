// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { BufferGeometry, Float32BufferAttribute, HalfFloatType, LinearSRGBColorSpace, Mesh, NoBlending, NoToneMapping, OrthographicCamera, RGBAFormat, Scene, ShaderMaterial, SRGBColorSpace, UnsignedByteType, Vector4, WebGLRenderTarget, type Camera, type Object3D, type WebGLRenderer } from 'three';
import { nativeToneOutputFragment } from './native-tone-output';

export type NativeToneCurve = 'rgb' | 'srgb' | 'reinhard' | 'filmic';
export type PresentationPrecision = 'half-float' | 'unsigned-byte';
export interface PresentationCapabilities { maxTextureSize: number; maxRenderbufferSize: number; halfFloat: boolean; halfFloatSamples: readonly number[]; byteSamples: readonly number[] }
export const DEFAULT_PRESENTATION_BUDGET = 256 * 1024 * 1024;
export function nativeToneParameters(curve: NativeToneCurve = 'srgb', exposureEV = 0) {
  const curves: Record<NativeToneCurve, number> = { rgb: 0, srgb: 1, reinhard: 2, filmic: 3 };
  if (!Object.hasOwn(curves, curve) || !Number.isFinite(exposureEV)) throw Error('Unsupported native tone mapping parameters');
  const twoPowExposure = Math.fround(2 ** exposureEV);
  if (!Number.isFinite(twoPowExposure)) throw Error('Native exposure cannot be represented by the GPU');
  return { curve, index: curves[curve], exposureEV, twoPowExposure };
}
export function presentationAllocation(width: number, height: number, pixelRatio: number, samples: number, precision: PresentationPrecision, capabilities: PresentationCapabilities, budget = DEFAULT_PRESENTATION_BUDGET) {
  if (![width, height, pixelRatio, budget].every(value => Number.isFinite(value) && value > 0) || !Number.isInteger(samples) || samples < 0 || !['half-float', 'unsigned-byte'].includes(precision)) throw Error('Invalid world presentation allocation');
  const physicalWidth = Math.floor(width * pixelRatio), physicalHeight = Math.floor(height * pixelRatio);
  if (physicalWidth < 1 || physicalHeight < 1 || physicalWidth > Math.min(capabilities.maxTextureSize, capabilities.maxRenderbufferSize) || physicalHeight > Math.min(capabilities.maxTextureSize, capabilities.maxRenderbufferSize)) throw Error('World presentation resolution exceeds verified GPU limits');
  if (precision === 'half-float' && !capabilities.halfFloat) throw Error('Native linear HDR presentation requires a renderable half-float framebuffer');
  const supported = precision === 'half-float' ? capabilities.halfFloatSamples : capabilities.byteSamples;
  if (samples !== 0 && !supported.includes(samples)) throw Error('Requested world presentation antialiasing is unsupported');
  // Conservative upper bound: resolved color/depth plus multisampled
  // color/depth. Native HDR uses floating-point color; no hidden DPR cap.
  const estimatedBytes = physicalWidth * physicalHeight * ((precision === 'half-float' ? 8 : 4) + 4) * (samples + 1);
  if (!Number.isSafeInteger(estimatedBytes) || estimatedBytes > budget) throw Error('Requested world presentation exceeds its owned GPU memory budget');
  return { width, height, pixelRatio, physicalWidth, physicalHeight, samples, precision, estimatedBytes };
}

export interface WorldPresentationOptions { samples?: number; precision?: PresentationPrecision; maxBytes?: number; onWarning?: (message: string) => void }
/** Owned linear world target plus native final tone/encoding pass.
 * Prepared independently; importing this class does not alter BrowserWorld.
 * Default native tone is SRGB/EV0, rather than Three's ACES exposure/0.6.
 */
export class WorldPresentation {
  readonly capabilities: PresentationCapabilities;
  private target?: WebGLRenderTarget;
  private allocation?: ReturnType<typeof presentationAllocation>;
  private enabled = true;
  private tone = nativeToneParameters();
  private disposed = false;
  private busy = false;
  private peakEstimatedBytes = 0;
  private readonly output = new Scene();
  private readonly camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly geometry = new BufferGeometry();
  private readonly material = new ShaderMaterial({
    uniforms: { worldTexture: { value: null }, twoPowExposure: { value: 1 }, toneCurve: { value: 1 } },
    vertexShader: 'varying vec2 worldUV; void main(){worldUV=uv;gl_Position=vec4(position.xy,0.0,1.0);}', fragmentShader: nativeToneOutputFragment,
    depthTest: false, depthWrite: false, blending: NoBlending, toneMapped: false,
  });
  constructor(private readonly renderer: WebGLRenderer, private readonly options: WorldPresentationOptions = {}) {
    const context = renderer.getContext();
    if (!('getInternalformatParameter' in context)) throw Error('Native world presentation requires WebGL2');
    const gl = context as WebGL2RenderingContext;
    const halfFloat = !!gl.getExtension('EXT_color_buffer_float');
    const samples = (format: number): number[] => Array.from(gl.getInternalformatParameter(gl.RENDERBUFFER, format, gl.SAMPLES) as Int32Array).filter(value => Number.isInteger(value) && value > 0);
    this.capabilities = Object.freeze({ maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE), maxRenderbufferSize: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE), halfFloat, halfFloatSamples: Object.freeze(halfFloat ? samples(gl.RGBA16F) : []), byteSamples: Object.freeze(samples(gl.RGBA8)) });
    this.geometry.setAttribute('position', new Float32BufferAttribute([-1, 3, 0, -1, -1, 0, 3, -1, 0], 3));
    this.geometry.setAttribute('uv', new Float32BufferAttribute([0, 2, 0, 0, 2, 0], 2));
    const mesh = new Mesh(this.geometry, this.material); mesh.frustumCulled = false; this.output.add(mesh);
    if (options.precision === 'unsigned-byte') options.onWarning?.('Unsigned-byte linear presentation was explicitly selected; HDR values above one are clipped. Native HDR parity requires half-float.');
  }
  private live() { if (this.disposed) throw Error('World presentation has been disposed'); }
  private scoped<T>(operation: () => T): T {
    this.live(); if (this.busy) throw Error('World presentation cannot be reentered');
    const renderer = this.renderer, target = renderer.getRenderTarget(), face = renderer.getActiveCubeFace(), mip = renderer.getActiveMipmapLevel();
    const viewport = renderer.getViewport(new Vector4()), scissor = renderer.getScissor(new Vector4()), scissorTest = renderer.getScissorTest();
    // Renderer CSS defaults and the bound target's effective physical state
    // differ. Binding a target overwrites GL viewport/scissor from its metadata.
    const gl = renderer.getContext();
    const currentViewport = renderer.getCurrentViewport(new Vector4());
    const currentScissor = new Vector4().fromArray(gl.getParameter(gl.SCISSOR_BOX) as Int32Array);
    const currentScissorTest = gl.isEnabled(gl.SCISSOR_TEST);
    const state = { tone: renderer.toneMapping, color: renderer.outputColorSpace, autoClear: renderer.autoClear, autoClearColor: renderer.autoClearColor, autoClearDepth: renderer.autoClearDepth, autoClearStencil: renderer.autoClearStencil, infoAutoReset: renderer.info.autoReset };
    this.busy = true;
    try { return operation(); } finally {
      try {
      renderer.toneMapping = state.tone; renderer.outputColorSpace = state.color; renderer.autoClear = state.autoClear; renderer.info.autoReset = state.infoAutoReset;
      renderer.autoClearColor = state.autoClearColor; renderer.autoClearDepth = state.autoClearDepth; renderer.autoClearStencil = state.autoClearStencil;
      renderer.setViewport(viewport); renderer.setScissor(scissor); renderer.setScissorTest(scissorTest);
      if (target) {
        const targetViewport = target.viewport.clone(), targetScissor = target.scissor.clone(), targetScissorTest = target.scissorTest;
        try {
          target.viewport.copy(currentViewport); target.scissor.copy(currentScissor); target.scissorTest = currentScissorTest;
          renderer.setRenderTarget(target, face, mip);
        } finally { target.viewport.copy(targetViewport); target.scissor.copy(targetScissor); target.scissorTest = targetScissorTest; }
      } else renderer.setRenderTarget(null, face, mip);
      } finally { this.busy = false; }
    }
  }
  resize(width: number, height: number, pixelRatio = this.renderer.getPixelRatio()) {
    this.live();
    const allocation = presentationAllocation(width, height, pixelRatio, this.options.samples ?? 4, this.options.precision ?? 'half-float', this.capabilities, this.options.maxBytes);
    if (this.allocation && this.allocation.physicalWidth === allocation.physicalWidth && this.allocation.physicalHeight === allocation.physicalHeight && this.allocation.pixelRatio === pixelRatio && this.allocation.width === width && this.allocation.height === height) return;
    const peakBytes = (this.allocation?.estimatedBytes ?? 0) + allocation.estimatedBytes;
    if (!Number.isSafeInteger(peakBytes) || peakBytes > (this.options.maxBytes ?? DEFAULT_PRESENTATION_BUDGET)) throw Error('World presentation replacement exceeds its owned peak GPU memory budget');
    const candidate = new WebGLRenderTarget(allocation.physicalWidth, allocation.physicalHeight, { type: allocation.precision === 'half-float' ? HalfFloatType : UnsignedByteType, format: RGBAFormat, internalFormat: allocation.precision === 'half-float' ? 'RGBA16F' : 'RGBA8', colorSpace: LinearSRGBColorSpace, depthBuffer: true, stencilBuffer: false, samples: allocation.samples, resolveDepthBuffer: false, resolveStencilBuffer: false });
    try {
      this.peakEstimatedBytes = Math.max(this.peakEstimatedBytes, peakBytes);
      this.scoped(() => { this.renderer.initRenderTarget(candidate); this.renderer.setRenderTarget(candidate); const gl = this.renderer.getContext(); if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw Error('Native world presentation framebuffer is incomplete'); });
    } catch (error) { candidate.dispose(); throw error; }
    const old = this.target; this.target = candidate; this.allocation = allocation; this.material.uniforms.worldTexture.value = candidate.texture;
    this.renderer.setPixelRatio(pixelRatio); this.renderer.setSize(width, height, false); old?.dispose();
  }
  setTone(options: { curve?: NativeToneCurve; exposureEV?: number } = {}) { this.live(); const parameters = nativeToneParameters(options.curve ?? this.tone.curve, options.exposureEV ?? this.tone.exposureEV); this.tone = parameters; this.material.uniforms.toneCurve.value = parameters.index; this.material.uniforms.twoPowExposure.value = parameters.twoPowExposure; }
  setEnabled(enabled: boolean) { this.live(); this.enabled = enabled; }
  render(scene: Scene, camera: Camera, options: { force?: boolean } = {}): boolean {
    this.live(); if (!this.enabled && !options.force) return false;
    if (!this.target) throw Error('World presentation must be resized before rendering');
    this.scoped(() => {
      const renderer = this.renderer; renderer.toneMapping = NoToneMapping; renderer.outputColorSpace = LinearSRGBColorSpace; renderer.autoClear = true;
      renderer.autoClearColor = true; renderer.autoClearDepth = true; renderer.autoClearStencil = false;
      renderer.info.autoReset = false; renderer.info.reset(); renderer.setRenderTarget(this.target!); renderer.render(scene, camera);
      // setRenderTarget(null) restores the renderer's CSS viewport at its DPR.
      renderer.setRenderTarget(null); renderer.outputColorSpace = SRGBColorSpace; renderer.autoClear = false; renderer.setScissorTest(false); renderer.render(this.output, this.camera);
    }); return true;
  }
  prepare(scene: Object3D, camera: Camera, lightingScene?: Scene): Promise<unknown> {
    if (!this.target) throw Error('World presentation must be resized before preparation');
    // compileAsync creates/links programs synchronously before returning its
    // readiness promise. Restore renderer state immediately, not after await.
    return this.scoped(() => { this.renderer.toneMapping = NoToneMapping; this.renderer.outputColorSpace = LinearSRGBColorSpace; this.renderer.setRenderTarget(this.target!); return this.renderer.compileAsync(scene, camera, lightingScene); });
  }
  capture(scene: Scene, camera: Camera): Promise<Blob> {
    this.render(scene, camera, { force: true });
    return new Promise((resolve, reject) => this.renderer.domElement.toBlob(blob => blob ? resolve(blob) : reject(Error('Could not export the rendered visitor world')), 'image/png'));
  }
  getState() { return { enabled: this.enabled, disposed: this.disposed, allocation: this.allocation ? { ...this.allocation } : null, tone: { curve: this.tone.curve, exposureEV: this.tone.exposureEV }, nativeHDR: this.allocation?.precision === 'half-float' && !this.disposed, presentationDraws: 1, peakEstimatedBytes: this.peakEstimatedBytes };  }
  dispose() { if (this.disposed) return; if (this.busy) throw Error('Cannot dispose a world presentation while it is rendering'); this.disposed = true; this.target?.dispose(); this.target = undefined; this.material.uniforms.worldTexture.value = null; this.material.dispose(); this.geometry.dispose(); this.output.clear(); }
}
