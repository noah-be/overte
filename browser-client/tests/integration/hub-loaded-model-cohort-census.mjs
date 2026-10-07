// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Exact serializable page collector: one explicit diagnostic after measured gates.
 * No graph/matrix update, permissions change, instance admission or retry. */
export async function collectHubLoadedModelCohortCensus(admissionOrdinal) {
    if (admissionOrdinal !== 1 && admissionOrdinal !== 2) throw Error('Invalid async census admission ordinal');
    const api = window.__overte;
    if (!api?.connected || typeof api.drawModelCohortAsync !== 'function') throw Error('Async draw census is unavailable in this connected browser bundle');
    const used = window.__hubLoadedModelCohortUsed ?? new Set();
    if (!(used instanceof Set) || used.size > 2 || used.has(admissionOrdinal)) throw Error('Async census already attempted for this admission');
    window.__hubLoadedModelCohortUsed = used;
    used.add(admissionOrdinal);
    const startedAt = Date.now();
    let timer;
    try {
        const work = Promise.resolve().then(() => api.drawModelCohortAsync());
        // The reviewed World owns its 5 s wall timer. This independent failure guard
        // adds no time to existing movement/loading gates; outer harness finally
        // closes the browser if a broken/stale diagnostic fails to settle.
        const deadline = new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Async census diagnostic deadline')), 6000); });
        const raw = await Promise.race([work, deadline]);
        if (!api.connected || window.__overte !== api) throw Error('Async census admission ended during the diagnostic');
        const scalar = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= Number.MAX_SAFE_INTEGER;
        const integer = value => Number.isSafeInteger(value) && value >= 0;
        function numbers(value, keys, integers = false) {
            if (!value || typeof value !== 'object') throw Error('Invalid async census report');
            const out = {};
            for (const key of keys) {
                if (!(integers ? integer(value[key]) : scalar(value[key]))) throw Error('Invalid async census report');
                out[key] = value[key];
            }
            return out;
        }
        const countKeys = ['owners', 'nodes', 'meshes', 'drawParts', 'candidateParts', 'geometryBytesRead', 'metadataBytes', 'textureBindings'];
        const resourceKeys = ['geometryIdentities', 'geometryByteClasses', 'materialIdentities', 'textureIdentities', 'sourceIdentities', 'sharedSources', 'samplerSourceBindings'];
        const countLimits = {maximumOwners:1024, maximumNodes:16384, maximumParts:8192, maximumBytes:67108864, maximumMetadataBytes:2097152};
        if (!raw || raw.version !== 2 || typeof raw.partial !== 'boolean' || !scalar(raw.elapsedMs)) throw Error('Invalid async census report');
        const counts = numbers(raw.counts, countKeys, true), bounds = numbers(raw.bounds, Object.keys(countLimits), true);
        const cohort = raw.modelCohort;
        if (!cohort || cohort.scope !== 'captured-static-loaded-Model-cohort' || cohort.maximumSelectedOwners !== 64 || cohort.wholeWorldCoverage !== false || typeof cohort.selectionPartial !== 'boolean' || !scalar(cohort.sourcePreparationMs)) throw Error('Invalid Model cohort scope');
        const modelCohort = {...numbers(cohort,['selectedOwners','eligibleAtCapture','modelOwnersAtCapture'],true),
            scope:cohort.scope, maximumSelectedOwners:64, wholeWorldCoverage:false, selectionPartial:cohort.selectionPartial,sourcePreparationMs:cohort.sourcePreparationMs};
        if (modelCohort.selectedOwners > 64 || modelCohort.selectedOwners > modelCohort.eligibleAtCapture || modelCohort.eligibleAtCapture > modelCohort.modelOwnersAtCapture || modelCohort.modelOwnersAtCapture > 1024 || counts.owners > modelCohort.selectedOwners || modelCohort.selectionPartial !== (modelCohort.selectedOwners < modelCohort.eligibleAtCapture)) throw Error('Invalid Model cohort coverage');

        if (!scalar(raw.counts.triangles)) throw Error('Invalid async census report');
        counts.triangles = raw.counts.triangles;
        for (const key of Object.keys(countLimits)) if (bounds[key] < 1 || bounds[key] > countLimits[key]) throw Error('Invalid async census report');
        if (counts.owners > bounds.maximumOwners || counts.nodes > bounds.maximumNodes || counts.drawParts > bounds.maximumParts || counts.geometryBytesRead > bounds.maximumBytes || counts.metadataBytes > bounds.maximumMetadataBytes || counts.candidateParts > counts.drawParts || counts.meshes > counts.nodes) throw Error('Invalid async census report');
        const resources = numbers(raw.resources, resourceKeys, true);
        const scheduling = numbers(raw.scheduling, ['taskSlices','totalCpuMs','maximumTaskSliceMs','wallMs','requestedSliceMs','maximumTotalCpuMs','maximumWallMs']);
        if (!integer(scheduling.taskSlices) || scheduling.taskSlices > 1025 || scheduling.requestedSliceMs < 1 || scheduling.requestedSliceMs > 8 || scheduling.maximumTotalCpuMs < 1 || scheduling.maximumTotalCpuMs > 2000 || scheduling.maximumWallMs < 1 || scheduling.maximumWallMs > 5000) throw Error('Invalid async census report');
        const allowedReasons = new Set(['dynamic','scripted','native-parent','material-child','animation',
            'revision-admission-or-unsettled','revision-scene-identity','revision-owner-map-size','revision-entity-map-size','revision-root-identity','revision-root-status','revision-root-signature','revision-entity-record','revision-scene-transform',
            'unsupported-node-own-accessor','unsupported-node-transform-accessor','unsupported-node-field-bound','unsupported-node-transform-field-bound','unsupported-node-transform-prototype','unsupported-node-known-light-prototype','unsupported-node-known-camera-prototype','unsupported-node-known-sprite-prototype','unsupported-node-other-prototype','unsupported-node-unclassified',
            'owner-revoked','owner-revision-changed','resource-revision-changed','wall-deadline','total-cpu-deadline','slice-count-budget',
            'draw-part-budget','geometry-byte-budget','group-count-budget','incomplete-stable-census','metadata-byte-budget','node-count-budget','owner-count-budget',
            'animation-or-morph','animation-owner-prior-parts','custom-render-callback','custom-shadow-material','mirrored-or-singular-transform','multipart-or-partial-range','nonopaque-or-wireframe','not-loaded','skin-or-existing-instance',
            'unsupported-geometry','unsupported-geometry-accessor-or-class','unsupported-material-hooks-or-class','unsupported-material-value','unsupported-node-accessor-or-class',
            'material-signature-budget','unsupported-accessor','unsupported-array','unsupported-array-accessor','unsupported-array-bound','unsupported-attribute-name','unsupported-defines','unsupported-euler-order','unsupported-geometry-buffer','unsupported-geometry-layout','unsupported-material-field','unsupported-mipmap','unsupported-nonfinite-math','unsupported-object-field-bound','unsupported-object-prototype','unsupported-shared-buffer','unsupported-source-version','unsupported-texture-binding','unsupported-typed-array','unsupported-typed-array-override']);
        const reasons = {}, hooks = {};
        if (!raw.reasons || typeof raw.reasons !== 'object' || Object.keys(raw.reasons).length > allowedReasons.size) throw Error('Invalid async census report');
        for (const [key,value] of Object.entries(raw.reasons)) {
            if (!allowedReasons.has(key) || !integer(value)) throw Error('Invalid async census report');
            reasons[key] = value;
        }
        if (scheduling.taskSlices > 1024 && (!raw.partial || !reasons['slice-count-budget'])) throw Error('Invalid async census report');
        if (!raw.hooks || typeof raw.hooks !== 'object' || Object.keys(raw.hooks).length > 4) throw Error('Invalid async census report');
        for (const [key,value] of Object.entries(raw.hooks)) {
            if (!['default','owned-native-alpha','owned-zero-light','foreign'].includes(key) || !integer(value)) throw Error('Invalid async census report');
            hooks[key] = value;
        }
        // Alpha-state JSON keys are deliberately never returned, even if a stale
        // bundle accidentally put private text into one. Only counts escape.
        if (!raw.alphaFlags || typeof raw.alphaFlags !== 'object' || Object.keys(raw.alphaFlags).length > 8192 || Object.values(raw.alphaFlags).some(value => !integer(value))) throw Error('Invalid async census report');
        const alphaFlagClasses = Object.keys(raw.alphaFlags).length, alphaFlagMaterials = Object.values(raw.alphaFlags).reduce((sum,value) => sum + value, 0);
        if (!integer(alphaFlagMaterials)) throw Error('Invalid async census report');
        const groupKeys = ['groups','members','sourceOnlyDrawReductionUpperBound','independentlyLoadedGeometryGroups','independentMaterialGroups'];
        function grouping(value) {
            const result = numbers(value, groupKeys, true);
            if (raw.partial && Object.values(result).some(value => value !== 0)) throw Error('Censored Model cohort cannot publish grouping');
            if (result.members > counts.candidateParts || result.groups > result.members || result.sourceOnlyDrawReductionUpperBound !== result.members - result.groups || result.independentlyLoadedGeometryGroups > result.groups || result.independentMaterialGroups > result.groups || (result.groups === 0 && result.members !== 0)) throw Error('Invalid async census report');
            return result;
        }
        return {admissionOrdinal, startedAt, finishedAt:Date.now(), data:{version:2,
            scope:'Captured eligible loaded Model subset only; no whole-world coverage or instance admission',modelCohort,
            partial:raw.partial, elapsedMs:raw.elapsedMs, bounds, counts, scheduling, reasons, resources, hooks, alphaFlagClasses, alphaFlagMaterials,
            exactGeometryAndMaterialIdentity:grouping(raw.exactGeometryAndMaterialIdentity), exactGeometryAndAuditedMaterialValues:grouping(raw.exactGeometryAndAuditedMaterialValues)}};
    } catch {
        // Never surface a private hook failure or malformed returned string.
        throw Error('Connected async draw census did not produce a valid bounded diagnostic');
    } finally { clearTimeout(timer); }
}
