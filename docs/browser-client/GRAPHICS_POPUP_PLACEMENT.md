# Resolution-preset popup placement candidate

This is a source-backed, unqualified GUI correction proposal. The normal shipping
Firefox journey retains its failure after ten real effects: selected80% opens
with painted row0 instead of row1. The source-coherent passive state cohort also
has selected60% with highlighted/painted0. The copied pointer cohort passes all
seventeen controls and Scan, so it does not establish the failing run's exact
pointer delivery or prove a global-focus problem.

The six hash-pinned installed Settings inputs provide a concrete layout defect:
SettingComboBox's custom Popup supplies no y binding. Qt5.15.3 initializes popup
y to zero. The failed capture places its first popup row over the physical
indicator-click row (the bounded comparison of retained geometry is true).
Qt's popup-open path initially highlights the selected index, but an actually
hovered delegate may subsequently change the highlight without changing the
selected index; leaving the popup does not automatically restore selection.
A copied observer pass and a normal failure can therefore differ without an
incorrect persisted setting. This is a supported causal candidate, not a proven
complete explanation of every historical failure.

Primary source at the exact5.15.3-lts-lgpl tag:

- [QQuickPopup default position](https://github.com/qt/qtquickcontrols2/blob/v5.15.3-lts-lgpl/src/quicktemplates2/qquickpopup_p_p.h#L166).
- [ComboBox popup-open/current selection and actual hover](https://github.com/qt/qtquickcontrols2/blob/v5.15.3-lts-lgpl/src/quicktemplates2/qquickcombobox.cpp#L315).
- [Standard ComboBox popup below its control](https://github.com/qt/qtquickcontrols2/blob/v5.15.3-lts-lgpl/src/imports/controls/ComboBox.qml#L103).

The candidate adds exactly one conditional native QML layout binding to the
existing per-worker override: for the browser-only "Resolution preset", popup
y equals its own ComboBox height. All other native settings retain y0 and their
original bytes/behavior. The installed source hashes and six exact mount targets
remain unchanged; unknown sources refuse before override generation. No native
index/highlight/focus setter, timer, input retry, browser graphic change, capture
mapping change or permission/deadline adjustment is added. Selected/custom state,
real widgets, original callbacks and other five generated overrides remain exact.

The original combo source-equality test now removes only the exact reviewed y
binding before comparing **all remaining bytes**. Four additional controls
require the exact binding, preserve every other output, evaluate it for multiple
native control heights and unrelated labels, reproduce the old overlapped hit,
and refuse unknown sources/channels. This is geometry/source qualification,
not a fake Qt or actual hover/pixel success claim.

```bash
node --test browser-client/gateway/browser-graphics.test.mjs browser-client/gateway/browser-graphics-popup-placement.test.mjs
```

The TMP packet passes all fifteen cases; actual GUI is pending. Root must restart
only its owned gateway so import-time package copies use the candidate, then run
the **unchanged** seventeen-control stock Firefox Graphics/Scan/hidden/leave
journey, including popup pixels, correlated native ACK/cache, Custom up-arrow,
persisted reconnect state, original fifteen-second popup deadline and cleanup.
The existing popup oracle searches actual painted popup position; no target row,
threshold or row-position assertion is changed. Repeat Chrome before any general
acceptance claim. Keep previous failures and source/module/browser/service pins.


## Current actual qualification

The initial below-control-only pair fails after nine effects in both stocks
(Firefox75.070s; Chromium71.150s): the unchanged popup oracle cannot qualify the
visible popup while native description/slider pixels bleed through its90%
background. The retained frame and actual selected row do not prove an ACK/index
failure. The generated browser Resolution preset background now uses alpha1;
all other combos retain0.9. Removing only this exact color expression recovers
the28f5 placement source; removing it plus the y binding recovers the entire
original installed widget. All seventeen focused controls pass.

The unchanged complete original native Graphics/Scan journey now passes in
Firefox (167.778s) and Chromium (158.872s), including seventeen actual effects,
thirteen painted-popup checks, Scan, genuine hidden/leave cancellation and
persisted rejoin. Original pixels/row/currentIndex/ACK/deadlines remain. The real
view recommends retaining settings in both engines; optional Apply is still
pending. Source/distribution/ELF/baseline/owned cleanup and all nine services pass.
[Safe exact-source proof](evidence/tablet-graphics-popup-opaque-stock-20261002.json).
