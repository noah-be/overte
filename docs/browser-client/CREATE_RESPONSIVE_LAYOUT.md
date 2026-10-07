# Native Create Properties at browser tablet width

The genuine 2026.04.1 Properties page uses a fixed 160-pixel property label,
three 124-pixel tuple controls and two 28-pixel gaps. Its body hides horizontal
overflow. The actual 480-pixel native Tablet capture measured Dimensions inputs
at x=222–346, 374–498 and 526–650: the Z control was entirely outside the visible
surface. Opening Create and discovering a Shape therefore did not prove a usable
three-axis edit flow.

The proposed private-worker override inserts only scoped CSS into the exact
installed `system/create/entityProperties/html/entityProperties.html`. The original
HTML, scripts, native widgets, validators and event handlers remain byte-identical.
The shared stylesheet and other applications remain unchanged. At viewport widths
up to 600 pixels, Properties labels sit above their controls, the tab table has a
fixed available width and the original numeric tuple controls share that width.
Axis labels, drag surfaces and arrow controls remain visible; no fields are hidden
or disabled. Above 600 pixels the original layout remains unchanged.

The startup package validates SHA256 of five reviewed files: Properties HTML,
shared edit/tabs CSS, Properties JavaScript and DraggableNumber JavaScript. The
supported sources are those packaged in 2026.04.1; an unknown version fails closed.
Source reads are bounded regular-file reads without final symlink traversal.
Each visitor receives one new mode-0600 HTML file, mounted read-only at the actual
installed Properties path by the existing isolated worker. No visitor paths,
selectors, source code or account settings enter the override.

The proposal passed two CPU source/path tests, strict TypeScript and a direct
load/prepare check against the actual packaged release. That check verified one
private HTML override, its exact installed target, mode0600 and refusal to overwrite
a previously prepared file. No native process or browser was launched for these
checks.

Two browser component scaffolds exercise the original licensed native
DraggableNumber widget and tuple-building functions with the real native CSS:
320/480/600-pixel geometry, genuine pointer/keyboard number entry, the unadapted
480-pixel negative control and unchanged 800-pixel geometry. They are layout/widget
tests, not a replacement for native entity delivery. Their runtime execution is
pending the parent-owned browser run.

Remaining acceptance uses the existing isolated native Create journey and its
fixed read-only DOM geometry audit: capture Shape and Spatial, confirm all three
actual inputs fit the captured private native surface, calibrate their new centers,
then use genuine Qt input to edit Name, RGB and XYZ dimensions. Independent native
and browser observations must agree before selecting the unique owned entity from
List and deleting it. The exact seven pre-existing entity identities must remain
unchanged on success and failure. No public-domain entity mutation is authorized
by this fixture. Full Create acceptance remains pending.

## Actual browser correction on2026-10-01

The genuine native global `tbody {display:block}` collapsed the adapted content
cell, so its two20px glyph-arrow targets overlapped the editable text. Restoring
`table-row-group` only inside the owned narrow Properties table fixes the actual
hit geometry. All four Chromium/Firefox cases now pass in15.21seconds:
320/480/600-pixel true center hit targets and genuine XYZ Enter handlers, the
unadapted480-pixel clipped negative control, and unchanged800-pixel rectangles.
The native widget/font bytes and numeric-format oracle remain unchanged. The
component fixture observes emitted axis/value through a controlled property
callback; it does not execute the full native domain-property transport. Earlier
timeouts remain retained in the combined GPU evidence. Native domain edits and
List deletion still require their separate genuine acceptance.
