# Circular avatar callers on the software QML renderer

NameCard, DisplayNameHeader, AvatarAppListDelegate and SimplifiedTopBar now use
Shared RoundImage instead of an Image with an OpacityMask layer. Existing image
IDs, dimensions, visibility, fill modes, source-size requests, mipmap settings,
status consumers and TopBar mouse handlers remain. Relative URLs are resolved
at the original caller, including TopBar inventory and script-driven updates.
Empty sources remain empty rather than resolving to the caller document.

RoundImage uses a zero-delay Timer to refresh its Canvas cache after Image
bindings settle. The cache request includes the requested source size. A real
counted provider returns different pixels for different requested sizes: changing
size requires one new provider fetch and displays the new pixels; radius repaint
requires none. Removing the Canvas size argument fails that pixel check. This
proves the tested synchronous Qt6 provider/cache paths only. Async network/cache
lifetime and Qt5/native behavior remain acceptance gaps.

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
