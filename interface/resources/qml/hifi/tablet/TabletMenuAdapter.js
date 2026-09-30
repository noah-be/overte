// Both Controls 1 menus and the Controls 2 wrappers expose this tablet model.
.pragma library
var Separator = 0;
var Item = 1;
var Menu = 2;

function isVisible(item) {
    return !!item && (item.tabletVisible !== undefined ? item.tabletVisible : item.visible);
}
function isExclusive(item) {
    return !!item && (item.tabletExclusive !== undefined ? item.tabletExclusive : !!item.exclusiveGroup);
}
function shortcut(item) {
    return !item ? "" : (item.tabletShortcut !== undefined ? item.tabletShortcut : item.shortcut || "");
}
