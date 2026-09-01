# Codex-Auftrag: iOS-/iPadOS-Adapter für Tablet-E2E

Arbeite ausschließlich im Worktree:

`/home/user/Documents/github/overte-ios`

Der vorgesehene Produktbranch ist `apple-ios`. Er muss vor Beginn über folgende
Kette mit dem fertigen Common Contract synchronisiert worden sein:

`main -> apple-main -> apple-ios`

## Unmittelbar nach Erhalt dieses Auftrags: pausieren

Die Common-Contract-Arbeit auf `main` ist noch nicht fertig beziehungsweise
noch nicht bis `apple-ios` synchronisiert. Unternimm deshalb in deinem ersten
Turn keinerlei Arbeit:

- keine Tools aufrufen;
- keine Dateien oder Git-Refs untersuchen;
- keine Dateien verändern;
- keine Tests, Builds oder Jenkins-Jobs starten;
- keine Git-Operationen ausführen;
- keine weiteren Agents oder Sessions starten;
- keine Operationsnamen, Schemas oder semantischen IDs vorwegnehmen.

Antworte zunächst nur sinngemäß:

> Die iOS-/iPadOS-Adapter-Session ist vorbereitet und wartet auf die
> ausdrückliche Freigabe nach der Synchronisierung des Common Contracts.

Beende danach den Turn. Beginne erst, wenn der Benutzer ausdrücklich mitteilt,
dass der Common Contract fertig und vollständig synchronisiert ist und du mit
der Arbeit anfangen kannst.

## Vorgehen nach der ausdrücklichen Freigabe

Arbeite anschließend möglichst vollständig autonom. Lies zuerst vollständig:

- alle geltenden `AGENTS.md`-Dateien;
- `docs/BRANCH_WORKFLOW.md`;
- `tests/device/README.md` und `tests/device/E2E_STRATEGY.md`;
- die final synchronisierte Tablet-Contract-Dokumentation;
- die finalen Capability-, Policy- und Snapshot-Schemas;
- die gemeinsamen Tablet-Module, Mock-Policies und Self-Tests;
- die Appium-/iOS-Adapterdokumentation und `tests/device/ios/`;
- vorhandene iOS-E2E-Test-Build-, Artifact- und Security-Verträge;
- vorhandene iOS-Accessibility-, Tablet-, QML- und Touch-UI-Tests;
- die vorhandene native iOS-Touch-/Accessibility-Bridge.

Der dann synchronisierte Repository-Stand ist die maßgebliche Wahrheit. Nutze
keine vorläufigen Namen aus früheren Diskussionen, wenn der finale Common
Contract andere Namen oder Formate definiert.

Diese Datei ist absichtlich untracked. Sie darf weder gestaged, committed,
gelöscht noch als Produktänderung behandelt werden. Bei der Prüfung der
Worktree-Sauberkeit ist genau diese eine Bootstrap-Datei zulässig.

## Synchronisierungs-Gate

Prüfe vor jeder Änderung:

1. den absoluten Worktree-Pfad, den aktuellen Branch und den Git-Status;
2. dass außer dieser Promptdatei keine fremden Änderungen vorliegen;
3. dass die vollständige Branch-Kette `main -> apple-main -> apple-ios`
   synchronisiert wurde;
4. dass Contract-Dokumentation, Registry, Schemas, gemeinsame Module, Mock und
   Self-Tests dieselbe finale Version verwenden;
5. dass der vom Benutzer genannte Common-Contract-Commit im Produktstand
   enthalten ist, sofern ein Commit genannt wurde.

Wenn der Contract fehlt, nur teilweise synchronisiert ist oder seine Dateien
nicht zusammenpassen, ändere nichts. Berichte den exakten Unterschied und
warte auf Korrektur. Synchronisiere oder reconcile die Branch-Kette nicht
selbst.

Der separate Branch `fix/ios/ipad-fast-dev-texture-reuse` enthält eigenständige,
noch nicht in `apple-ios` enthaltene Arbeit. Er darf im Rahmen dieses Auftrags
nicht gelöscht, umgeschrieben oder ungeprüft übernommen werden.

## Ziel und Scope

Implementiere ausschließlich die iOS-/iPadOS-Adapter- und Produktseite des
finalen gemeinsamen Tablet-E2E-Contracts:

- eine eingecheckte iOS-/iPadOS-Produkt-Policy nach dem finalen Schema;
- Mapping der gemeinsamen semantischen Tablet-IDs auf die reale iOS-Oberfläche;
- die final definierten semantischen Tablet-Operationen im vorgesehenen
  iOS-/Appium-Adapter;
- Beobachtung von tatsächlichem Screen, Ready-Zustand und tatsächlich
  sichtbaren semantischen Controls;
- Aktivierung sichtbarer Controls durch echte Benutzerinteraktion;
- notwendige XCUITest-, Accessibility- oder iOS-Bridge-Ergänzungen;
- Adapter-Self-Tests, Produkt-Tests, Dokumentation und Runbook;
- physische Akzeptanzvalidierung, sofern das lokale Lab verfügbar und die
  Ausführung im Scope liegt.

Nicht in Scope sind Änderungen am gemeinsamen Contract nach eigener
Vorstellung, neue gemeinsame Operationsnamen, Android-, Pico-, Quest-, macOS-
oder Desktop-Adapter, private Signing-/Targetdaten und eine Umgehung sichtbarer
UI-Pfade über direkte interne Navigation.

Wenn der finale Common Contract einen nachweisbaren Fehler enthält, ändere ihn
nicht stillschweigend im Produktbranch. Liefere einen minimalen Reproduktionsfall
und melde den benötigten Common-Fix zurück.

## Architekturregeln

- Der Adapter beobachtet den Istzustand; die getrennte Produkt-Policy definiert
  den Sollzustand.
- Der Adapter darf nicht dieselbe Policy zurückgeben, gegen die er geprüft wird.
- Adapter-Capabilities beschreiben Automation, nicht Produktfeatures.
- Ein absichtlich fehlendes Feature ist eine verpflichtende Abwesenheits-
  Assertion und kein Skip.
- Negative Assertions erfolgen erst nach eindeutigem, stabilem Screen-Ready.
- Verwende stabile, nicht lokalisierte Accessibility-Identifier.
- Sichtbare übersetzte Texte sind keine primären Selektoren.
- Ein erfolgreicher XCUITest-Tap allein ist kein Pass. Der resultierende
  UI-Zustand muss unabhängig beobachtet werden.
- Screenshots und Page Sources sind nur redigierte Diagnoseartefakte.
- Keine privaten UDIDs, Bundle-/Team-IDs, Signing-Werte, Appium-Selektoren oder
  Credentials in Kommandos, Logs oder Artefakten ausgeben.

## iOS-/iPadOS-Policy

iOS und iPadOS sind für diesen Vertrag Flat-Touch-Produkte. Leite die exakten
Erwartungen aus dem finalen Schema und der vorgesehenen Produktoberfläche ab.
Insbesondere sollen verpflichtend geprüft werden:

- Tablet Home und Settings sind erreichbar;
- allgemeine, Audio- und Security-Einstellungen sind vorhanden;
- HMD-/VR-Einstellungen sind abwesend;
- VR-/Desktop-Controller-Einstellungen sind abwesend;
- die allgemeine Funktion für VR-Renderauflösung beziehungsweise VR-Render-
  Scale ist abwesend.

iPhone und iPad dürfen unterschiedliche Geometrie-, Safe-Area- und
Layoutprofile verwenden, sollen aber dieselbe fachliche Flat-Touch-Policy
teilen, sofern der reale Produktvertrag keine begründete Abweichung vorsieht.
Erfinde keine Hardwareziele und dokumentiere, welche Formfaktoren tatsächlich
physisch validiert wurden.

Verwende ausschließlich die finalen allgemeinen semantischen IDs. Eine intern
vorhandene Eigenschaft wie `picoResolutionSettingsAvailable` darf nur als
Implementierungsdetail auf das allgemeine Feature abgebildet werden. Führe
keine produktbezogene ID in den Common Contract ein.

## Bedienung, Test-Build und Sicherheitsgrenze

Bevorzuge Appium W3C, XCUITest, stabile Accessibility-Identifier, echte
XCUIElement-Aktivierung und die vorhandene In-Client-Probe. Nutze den
vorhandenen fail-closed iOS-E2E-Test-Build-Vertrag.

Eine test-only Accessibility-Bridge ist nur zulässig, wenn sie:

- ausschließlich im vorgesehenen E2E-Test-Build fail-closed aktiv ist;
- keine Release-Funktionalität öffnet;
- denselben Produktionshandler wie die sichtbare Benutzeraktion auslöst;
- nicht direkt zu internen Screens routet;
- räumlich und semantisch an die reale sichtbare UI gebunden ist;
- durch separate Release-/Test-Build-Tests abgesichert wird.

Nutze keine direkte QML-Routenmanipulation oder Script-API als Ersatz für die
Aktivierung eines sichtbaren Controls.

## Erforderliche Validierung

Implementiere und führe mindestens aus, soweit lokal möglich:

- Adapterprotokoll-Self-Tests ohne Gerät;
- vollständige Sequenz: öffnen -> Home ready -> Settings aktivieren -> Settings
  ready -> Policy prüfen -> zurück -> schließen;
- negative Fälle für fehlende Pflicht-IDs und sichtbare verbotene HMD-,
  Controller- oder VR-Renderauflösungs-IDs;
- nicht-ready, falscher Screen, Aktion ohne Zustandswechsel, Prozessneustart
  und malformed Accessibility-/Snapshot-Daten;
- Cleanup-Idempotenz und Redaction privater Selektoren/Signing-Daten;
- fail-closed Test-Build sowie fehlende E2E-only Controls im Release-Build;
- relevante iOS-, Accessibility-, Artifact-, QML- und Touch-Tests;
- Safe Areas, Rotation und unterstützte iPhone-/iPad-Geometrien, soweit die
  Infrastruktur sie bereitstellt;
- finalen gemeinsamen Adapter-Verifier;
- gemeinsame Tablet-Suite mit `--require-complete`.

Wenn das lokale Overte-Jenkins-Gerätelabor verwendet wird, lies und befolge die
Skill-Anweisungen von `jenkins-local-lab`. Verwende den offiziellen
`overte-jenkins` CLI-Wrapper und keine rohen HTTP-/curl-Aufrufe, sofern die CLI
die Operation unterstützt. Exponiere niemals Credentials, UDIDs oder geheime
Target-Selektoren. Beachte bestehende Sicherheitsregeln für signierte
Artefakte, Artifact Receipts, WebDriverAgent, RemoteXPC, Bundle- und
Prozessidentität. Wenn kein physisches Ziel verfügbar ist, führe alle
hardwarefreien Tests aus und behaupte keinen physischen Pass.

## Arbeitsgrenzen und Abschluss

- Arbeite nach Freigabe autonom und behebe gefundene Fehler selbst.
- Bewahre fremde Änderungen und verwende keine destruktiven Git-Befehle.
- Erzeuge keine zusätzlichen Worktrees oder Agents.
- Nimm keine Commits, Pushes, Merges oder Branch-Synchronisationen vor.
- Frage nur bei objektiv fehlendem Contract, fehlerhafter Synchronisierung oder
  einer wesentlichen Scope-Entscheidung nach.

Die Arbeit ist abgeschlossen, wenn die iOS-/iPadOS-Policy und alle finalen
Operationen implementiert sind, reale Benutzerinteraktion und unabhängige
Beobachtung funktionieren, verbotene VR-Funktionen verbindlich abwesend sind,
die Test-Build-Grenze fail-closed bleibt, Verifier und relevante Tests bestehen
und keine privaten Daten persistiert wurden.

Berichte abschließend Contract-Version und Ausgangscommit, Policy, Mapping der
semantischen IDs, verwendete Accessibility-/Test-Build-Grenze, geänderte
Dateien, alle Testergebnisse, tatsächlich validierte Formfaktoren und physische
Evidenz, nicht ausführbare Tests, bekannte Grenzen und eventuelle
Common-Contract-Probleme.
