# Pico world-loading special-path removal review

Reviewed base: `53557b256763e7f29f7a6f547f696a16d890f4bf`. This is a source dependency review, not successful device regression evidence. Phone comparison uses the Phone compile-time path in that same source, not another owner's worktree or installed Phone binary.

## Conclusion

Do not delete all Pico branches together. Destination selection and the entity parser are already shared. Several remaining branches mix presentation with state preservation, recovery and physics prerequisites. Their purpose can often be implemented in common code, but deleting them is not equivalent to doing that safely.

The native Pico overlay is temporarily disabled at its sole render call in GraphicsEngine::render, including the initial visible state. World-loading bookkeeping, input/audio lifecycle and physics checks are retained. This intentionally exposes partially rendered scenes; input can still remain unavailable until the existing readiness handoff. It does not claim a successful import or remove the underlying interstitial state. Track the decision about a future shared feature in https://github.com/overte-org/overte/issues/2391.

## Removal decisions

| Special path | Finding | Decision |
| --- | --- | --- |
| Hardcoded Hub destination and physics-loop import | Already removed in the reviewed source; standard Android destination selection is used. | Keep removed. |
| Automatic interaction test station | Application::update loads pico4InteractionTestStation.js once serverless import and physics are marked ready. It adds local platform/cubes and does not participate in parsing or readiness. | Can be disabled independently for normal operation; retain explicit invocation for interaction tests. Not changed by this presentation-only patch. |
| Direct synchronous QFile read | ResourceManager already supports file URLs through FileResourceRequest, expands the same local resource path, and additionally applies QFileSelector and request/stat bookkeeping. Pico bypasses that service for local files. | Strong candidate to replace with the common request path. Must test event ordering, first spawn, rapid navigation and malformed/missing files. Common async callback still has Pico state hooks, so changing the file branch alone does not remove the state machine. |
| Import-in-progress and deferred navigation | Prevents active import from recursively reentering itself. Only local changed URLs are queued; an HTTP/online destination during import falls through the early return and is not queued here. | Replace with generation-bound navigation handling rather than wholesale deletion. All supported URL schemes and queued completion must follow latest destination wins. |
| Same-URL/empty reset suppression | DomainHandler::setURL explicitly permits reloading a serverless domain even when the URL is unchanged, but Pico's committed same-URL guard returns without reimport. Blanket resettingDomain/clearDomainOctreeDetails guards also suppress clearing a committed world. | Existing rules can block legitimate reload/reset. Replace broad committed-state checks with evidence that an event belongs to an obsolete transition. Test reload, different world, background/resume and reconnect before removal. |
| Committed flag inferred from local URL | Application::update sets committed=true whenever physics is off and remembered URL is local, without checking completion in that branch. | Remove this inference only together with an authoritative import-completion transition and stale-reset repair. A local URL is not proof of successful import; current fallback hides state loss. |
| GPU readiness relaxation | Pico uses stable allocation + empty transfer queue instead of also requiring requested and populated GPU memory to match. A committed local scene with visible interstitial can immediately override textureMemoryReady; there is also a timeout fallback. | Separate useful streaming-aware readiness from unconditional overrides. Restoring the Phone equality check blindly may indefinitely block streaming worlds. Do not equate an empty queue, imported JSON, or a timeout with complete rendering. |
| Avatar default domain settings | Local serverless worlds have no domain server; Pico supplies default height limits when avatar readiness otherwise waits for settings. There is a timeout for online settings too. | Keep a valid local-world default or implement it in common code. Removing it can leave physics disabled. Online timeouts need separate validation. |
| Loading progress/recovery and final frame handoff | The interstitial block also updates timestamps used by physics fallback and initiates recovery of incomplete entity sequences. Final handoff closes the interstitial and releases input/audio. | Only rendering is independently disabled now. Deleting the full progress block could remove recovery; deleting finalization could leave input/audio paused. Extract real loading/recovery duties before deleting presentation bookkeeping. |
| Manual controller dismissal | X can close the interstitial and latch suppression of future presentation for the current transition. | Re-evaluate with cancellation/input semantics; do not use dismissal as successful world-load evidence. Retained to avoid removing the existing escape path in this narrow patch. |
| OpenXR display/input integration | Needed to present stereo frames and read headset/controllers, independent of destination or JSON import. | Keep platform-specific hardware integration. It is not an unnecessary world-loading workaround. |

## Concrete source evidence

- `interface/src/Application.cpp`: loadServerlessDomain, domainURLChanged, resetPhysicsReadyInformation, update, tryToEnablePhysics, updateVerboseLogging.
- `interface/src/Application_Entities.cpp`: clearDomainOctreeDetails and resettingDomain can return before invalidation/clear on committed Pico scenes.
- `libraries/networking/src/DomainHandler.cpp`: setURL deliberately resets and emits the URL even for a same-address serverless reload; connectedToServerless itself only assigns named paths and calls setIsConnected(true), which emits connectedToDomain. Comments claiming direct recursive reset from connectedToServerless are not by themselves runtime proof of that call chain.
- `libraries/networking/src/ResourceManager.cpp` and FileResourceRequest.cpp: file service, resource thread dispatch, path expansion and QFileSelector.
- `libraries/entities/src/EntityTree.cpp`: common sendEntities transfers entities; its body does not directly call processEvents. The historical nested-event explanation needs an actual callback trace before it is treated as established causation.
- `scripts/developer/debugging/pico4InteractionTestStation.js`: local fixtures only.

## Required regression evidence before declaring common loading safe

Fresh-data tutorial and saved/home/explicit destinations; missing and malformed local worlds; world A to B while A imports; local to HTTP/online while importing; same-URL reload; reconnect/background/resume; delayed/missing assets and collision shapes; correct named spawn; world-input/audio recovery. Test the loader/state transitions as well as actual Pico rendering. Repeat the shared behavior on Phone; iOS behavior requires its separately owned build/device path.

No such full regression matrix has passed in this review. Twelve existing Pico source-contract checks pass after the presentation gate; they do not execute Qt signal ordering or prove hardware behavior. The previous absence of qCInfo import traces is not negative evidence because updateVerboseLogging can disable hifi.*.info.
