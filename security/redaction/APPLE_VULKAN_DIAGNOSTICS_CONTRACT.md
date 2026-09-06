# PX-16 direct Apple Vulkan OS payload closure v001

Requires px16-apple-runtime-diagnostics/v001 (which provides SafeDiagnostics via
the existing Shared IOSRuntimeLogging include). Preserved Apple source only.
All41 direct OS logging calls in VKBackend.cpp and3 in VKPipelineCache.cpp now
emit only the existing static Redacted event. Preserve each original info/fault
OS severity, conditional, counter and exception/rethrow; no renderer operation
or policy edits. Only complete call argument lists changed. No remaining direct
os_log variant in these two files falls outside the checked44-call inventory.

Original complete44 expressions compile/run with real Qt and a positively
probed raw Apple OS transport substitute. Every result is OVT_REDACTED and the
original per-call info/fault sequence is preserved. A normalized source diff
confirms no nonlogging token changes. This is not a complete renderer compile,
native os_log execution or proof of rendering/present/descriptor safety.

Legacy detailed renderer marker text, IDs, paths, fingerprints, numeric metrics
and exception messages are deliberately no longer public OS output. Do not
relax world/render evidence tests, manufacture marker records or treat generic
Redacted as an artifact-bound acceptance metric. A reviewed typed evidence
producer remains pending. Existing in-memory diagnostic strings/calculations,
pipeline quarantine persistence, other direct sinks/retention/crash/export and
full PX16/device acceptance remain separate work; this slice closes these sinks.
