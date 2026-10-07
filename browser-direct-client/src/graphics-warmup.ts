// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { DoubleSide, Material, Object3D, type Camera, type Scene } from 'three';
import { WorkerTaskYield } from './worker-task-yield';

interface Draw { object: Object3D; material: Material }
interface Renderable extends Object3D { material: Material | Material[]; isMesh?: boolean; isPoints?: boolean; isLine?: boolean; isSprite?: boolean }
interface Compiler {
  compile(object: Object3D, camera: Camera, scene: Scene): unknown;
  compileAsync(object: Object3D, camera: Camera, scene: Scene): Promise<unknown>;
}
export interface GraphicsWarmupStatistics {
  bindings: number; batches: number; yielded: number; planningMs: number; submitMs: number; maxSubmitMs: number; finalSubmitMs: number; readinessWaitMs: number;
  fallback: 'small-root' | 'node-material' | 'two-pass-transparent' | null;
}
interface Options {
  signal?: AbortSignal; isCurrent?(): boolean;
  /** Trusted construction-time bounds, not a browser quality/transport setting. */
  bindingsPerBatch?: number; clock?(): number;
  readinessTimeoutMs?: number;
  preparationTimeoutMs?: number;
  taskFactory?(signal?: AbortSignal): { yield(): Promise<void>; close(): void };
}
const aborted = () => new DOMException('The graphics preparation owner was cancelled', 'AbortError');

function collect(root: Object3D): { draws: Draw[]; fallback: GraphicsWarmupStatistics['fallback'] } {
  const draws: Draw[] = []; let fallback: GraphicsWarmupStatistics['fallback'] = null;
  root.traverse(object => {
    const candidate = object as Renderable;
    if (!candidate.isMesh && !candidate.isPoints && !candidate.isLine && !candidate.isSprite) return;
    const materials = Array.isArray(candidate.material) ? candidate.material : [candidate.material];
    // Repeating one material on the same object cannot change its program
    // parameters. Different objects still have separate bindings: skinning,
    // instancing and morph geometry must never be deduplicated by material alone.
    for (const material of new Set(materials)) {
      if (!material) continue;
      if (draws.length >= 65536) throw Error('Graphics preparation exceeds its bounded binding budget');
      if ((material as Material & { isNodeMaterial?: boolean }).isNodeMaterial) fallback = 'node-material';
      // Public Three.compile mutates this legacy material's side/version to
      // compile its two passes. An extra pass would change version behavior;
      // preserve the original one-call path instead of touching its settings.
      if (material.transparent && material.side === DoubleSide && !material.forceSinglePass) fallback = 'two-pass-transparent';
      draws.push({ object, material });
    }
  });
  return { draws, fallback };
}

/** A compile-only view. Prototype delegation preserves the actual object
 * flags/geometry/skeleton/morph/instance inputs. Actual parents, children,
 * material arrays and visibility remain untouched. This view is never rendered. */
export function graphicsWarmupView(root: Object3D, draws: readonly Draw[], targetScene?:Scene): Object3D {
  const view = new Object3D(), values = draws.map(({ object, material }) => {
    const value = Object.create(object) as Renderable;
    Object.defineProperty(value, 'material', { value: material, writable: false });
    return value;
  });
  view.traverse = callback => { callback(view); for (const value of values) callback(value); };
  view.traverseVisible = callback => {
    callback(view);
    // Public compile gathers targetScene first. A view of that exact Scene
    // must not contribute its lights again through the new-object branch.
    if(root!==targetScene)root.traverseVisible(object => { if ((object as Object3D & { isLight?: boolean }).isLight) callback(object); });
  };
  return view;
}

export function waitGraphicsReadiness(promise: Promise<unknown>, signal: AbortSignal | undefined, timeout: number): Promise<void> {
  if(!Number.isFinite(timeout)||timeout<1||timeout>120000)throw Error('Invalid bounded graphics readiness timeout');
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error?: unknown) => {
      if (settled) return; settled = true;
      clearTimeout(timer); signal?.removeEventListener('abort', cancel);
      if (error === undefined) resolve(); else reject(error);
    };
    const cancel = () => finish(aborted());
    const timer = setTimeout(() => finish(Error('Graphics readiness exceeded its bounded timeout')), timeout);
    signal?.addEventListener('abort', cancel, { once: true });
    // Consume late rejection too. Cancelling the owner does not pretend to
    // cancel an already submitted driver's compile or Three's internal poll.
    void promise.then(() => finish(), error => finish(error));
    if (signal?.aborted) cancel();
  });
}

/** Source-backed proposal, not activated by BrowserWorld. The current public
 * Three compileAsync first compiles its whole input synchronously. Submit large
 * roots in owned task-sized slices, then preserve its original compileAsync
 * call for the exact final object/lighting/program-readiness contract.
 * A single driver compile/link call cannot be preempted. Without KHR, Three's
 * final wait does not prove actual asynchronous driver completion. */
export async function prepareGraphicsYielding(compiler: Compiler, camera: Camera, scene: Scene, root: Object3D,
  options: Options = {}): Promise<GraphicsWarmupStatistics> {
  const size = options.bindingsPerBatch ?? 4;
  if (!Number.isSafeInteger(size) || size < 1 || size > 16) throw Error('Invalid graphics preparation batch bound');
  const timeout = options.readinessTimeoutMs ?? 30000;
  if (!Number.isSafeInteger(timeout) || timeout < 1 || timeout > 60000) throw Error('Invalid graphics readiness timeout');
  const preparationTimeout=options.preparationTimeoutMs??60000;
  if(!Number.isSafeInteger(preparationTimeout)||preparationTimeout<1||preparationTimeout>120000)throw Error('Invalid graphics preparation timeout');
  const clock = options.clock ?? (() => performance.now());
  const deadline=clock()+preparationTimeout;
  const check = () => { if (options.signal?.aborted || options.isCurrent?.() === false) throw aborted();
    if(clock()>=deadline)throw Error('Graphics preparation exceeded its bounded timeout'); };
  const remaining=()=>Math.max(1,Math.min(preparationTimeout,deadline-clock()));
  check();
  const planning = clock(), { draws, fallback } = collect(root);
  const statistics: GraphicsWarmupStatistics = { bindings: draws.length, batches: 0, yielded: 0, planningMs: Math.max(0, clock() - planning), submitMs: 0, maxSubmitMs: 0, finalSubmitMs: 0,
    readinessWaitMs: 0, fallback: fallback ?? (draws.length <= size ? 'small-root' : null) };
  let tasks: ReturnType<NonNullable<Options['taskFactory']>> | undefined;
  try {
    if (!statistics.fallback) {
      tasks = options.taskFactory?.(options.signal) ?? new WorkerTaskYield({ signal: options.signal });
      for (let offset = 0; offset < draws.length; offset += size) {
        check();
        const started = clock();
        compiler.compile(graphicsWarmupView(root, draws.slice(offset, offset + size),scene), camera, scene);
        const submitted = Math.max(0, clock() - started);
        statistics.submitMs += submitted; statistics.maxSubmitMs = Math.max(statistics.maxSubmitMs, submitted); statistics.batches++;
        check();
        // Yield even after the last synchronous slice so the final original
        // traversal is not appended to the same potentially long JS task.
        await waitGraphicsReadiness(tasks.yield(),options.signal,remaining()); statistics.yielded++; check();
      }
    }
    check(); const started = clock();
    const readiness = compiler.compileAsync(root, camera, scene);
    statistics.finalSubmitMs = Math.max(0, clock() - started);
    const waiting = clock();
    await waitGraphicsReadiness(readiness, options.signal, Math.min(timeout,remaining()));
    statistics.readinessWaitMs = Math.max(0, clock() - waiting); check();
    return statistics;
  } finally { tasks?.close(); }
}
