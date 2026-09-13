# Phone world loading: dependency scheduling follow-up (2026-09-13)

The shared two-worker processing pool queued already-compressed KTX tasks and model
parsing behind raw ETC encoding. Pixel Wi-Fi measurements of overte_hub recorded
KTX queue waits up to 79.277 s for tasks with median work of 4 ms. Geometry parsing
waited up to 32.219 s before discovering further material/texture dependencies.

Phone now assigns priority 1 to KTX tasks and geometry parsing, retaining the pool
size, compression quality, texture dimensions and other platforms' priority 0.
A deterministic real-Qt-pool test exercises the production KTX submission helper,
control ordering and exception isolation.

Seven mapped tree textures reached their first setImage call at 116.6–120.4 s
in a same-APK KTX-priority-off control, versus 27.6–38.7 s with priority on.
With model instrumentation in the same APK, KTX-only measured 34.9–49.0 s;
model priority reduced this to 25.4–28.3 s and maximum model queue wait to 4.876 s.
These are initial texture handoffs, not completed visual loading. The latter trial
actually drained all observed queues later (145.2 versus 112.8 s). Scheduling
improves dependency visibility but does not remove raw-image computation.

Four-download trials produced inconsistent 19.8–24.0 and 25.1–34.6 s tree results.
Production therefore retains the two-download baseline. Optional diagnostics allow
2/4 comparisons without another build; the CLI concurrent-downloads option remains
authoritative. No general download-limit improvement is claimed.

Diagnostics require debug.overte.loading=1 before process start. Optional controls:
debug.overte.loading.ktx_priority=0 and debug.overte.loading.model_priority=0 restore
old scheduling; debug.overte.loading.downloads accepts 2 or 4. Normal sessions do
not read these controls. Existing derived-cache namespaces permit isolated cold
texture-processing trials while preserving normal and HTTP caches.

The full local report, APK manifests, source patches, raw logs, screenshots, thermal
and memory samples, and reproduction scripts are retained under
/home/user/Documents/overte-phone-loading-20260913/followup/. No measured iPad/Pico
comparison is available. No world assets or other devices were modified.
