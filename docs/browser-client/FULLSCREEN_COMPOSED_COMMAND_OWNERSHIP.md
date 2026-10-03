# Composed-output command ownership correction

The first actual Chromium and Firefox composed-output runs both refused before input because the new diagnostic incorrectly expected `navigationSequence` on an outgoing frame ACK. The shipping production sender carries only the ordinary command sequence there. The authored frame already binds its navigation to the actual `open.sequence`.

Read the actual latest navigation command and displayed ACK from the owned fixture queue. Require the latest navigation to be the original authored `open`, a positive command sequence, and a displayed ACK sent later than that command. Keep the exact original revision/frame predicates, owner/native-density/layout checks, unchanged before/after snapshot, strict screenshot bytes, physical click and original press/release wire assertion. Home/back/close, missing navigation, and an ACK predating a later open refuse. No field is synthesized into production packets.

The added portable CPU test extracts the exact actual production `BrowserTablet.send` body and demonstrates that the previous navigation-on-ACK assumption rejects its genuine wire shape. It then tests intervening navigation and stale ACK negatives. No browser execution is claimed. The original immutable composed-output candidate and both actual negative reports remain evidence. Screenshot output still does not guarantee compositor hit-target readiness.

Apply this two-code-file followup after the original four-file composed-output proposal and the separate composition-test followup. Its stock driver is unchanged (`c007015b...`); the original four registered bodies remain unchanged. Root owns actual qualification.
