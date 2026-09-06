# Shared rounded avatar image through public Qt capture

RoundImage retains Qt Image source loading, requested sourceSize, mipmap, smooth,
status and progress. The naturally-sized Image remains visible with opacity zero;
public grabToImage captures its decoded pixels into a retained in-memory result.
Canvas loads that result URL with one argument and paints the rounded shape and
original border. No optional Canvas loadImage size overload or image export is
used. One capture is in flight; source/size/visibility generations reject obsolete
results, and pending changes coalesce after bindings settle.

Stretch, aspect fit/crop, pad and all three tile modes retain centered layout.
The full actual Qt6 software component compares interior regions with a real Qt
Image for all seven modes. Border, clipping, error/empty clearing and provider
counts pass. A size request while hidden obtains one additional provider result,
and showing again paints its distinct pixels; radius repaint requests no new
source. The four real avatar caller subtrees and TopBar update functions remain
passing. Making the captured source invisible rather than transparent fails the
pixel check. The public zero-opacity capture probe is retained with the evidence.

This removes an unverified Canvas overload dependency. It does not prove native
Qt5 compatibility: the exact pinned Qt5 archive/header and runtime were not tested.
Native Qt5/Qt6, DPR, filtering equivalence, large-image capture memory/cadence and
full resource lifetime remain open. The snapshot adds a render/capture step; no
performance budget is claimed. Existing interpolation differences and explicit
CPU tile loops remain, with native/avatar journey and original39 acceptance open.
