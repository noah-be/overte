# Circular avatar callers on the software QML renderer

NameCard, DisplayNameHeader, AvatarAppListDelegate and SimplifiedTopBar now use
Shared RoundImage instead of an Image with an OpacityMask layer. Existing image
IDs, dimensions, visibility, fill modes, source-size requests, mipmap settings,
status consumers and TopBar mouse handlers remain. Relative URLs are resolved
at the original caller, including TopBar inventory and script-driven updates.
Empty sources remain empty rather than resolving to the caller document.

RoundImage schedules a public grabToImage capture of its transparent, naturally
sized Qt Image after bindings settle. Canvas consumes the retained in-memory
result URL; sourceSize stays with Qt Image. The real counted provider returns
different pixels for requested sizes and proves one new request after changing
size, including while hidden. The current negative omits loading the captured pixels and fails pixels. The earlier cache-size negative belongs to sealed
v017 evidence. Qt5/native and asynchronous lifetime acceptance remain open.

The caller fixture extracts each complete actual image subtree and uses the
original file URL and AvatarImages import. Real Qt6 software QQuickView tests
ready state, circular transparency, visible content and empty clearing. TopBar's
complete updatePreviewUrl/fromScript functions are also extracted and exercised
for default fallback and script-supplied provider/default images. Parent layout,
Account and the empty inventory model are explicit seams. This is not a complete
NameCard/avatar application, native render journey or hardware acceptance.

The remaining GraphicalEffects imports/effects in NameCard and TopBar are kept;
Header and Delegate no longer need that import. Full dynamic QML effect closure
and all original 39-node artifact/hardware/consent acceptance remain open.
