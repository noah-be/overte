# Software-rendered TopBar colors

Five actual TopBar Image/ColorOverlay pairs now use SharedAudio.TintedImage
with the resolved source Image URL, existing geometry and hover/color bindings.
The status circle uses its actual Rectangle color/opacity directly. The unused
GraphicalEffects import is removed. Existing hidden experimental containers stay
hidden; the fixtures expose only their extracted image pairs for verification.

TintedImage retries initial loading when its Canvas becomes available and paints
when made visible. Its previous implementation accepted an early source binding
but left four tested hidden-source icon pairs blank. Actual six source regions
run with Qt6 software rendering and the real SVG assets: visible pixels, intended
tint, hover alpha, empty-source clearing and four status colors are checked.
UI theme/audio/HMD/mouse state and parent layout are explicit seams, not the full
TopBar application. The status icon's existing visible original Image is retained.
A transparent-tint mutation fails the four hidden-source image cases. The existing
complete TintedImage component fixture remains passing.

No native Qt5/Qt6 backend, whole widget journey, image-cache lifetime/performance,
accessibility or original 39-node artifact/hardware acceptance is claimed.
