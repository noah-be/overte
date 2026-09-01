# Codex-Auftrag: Android-Phone-Adapter für Tablet-E2E

Arbeite ausschließlich im Worktree:

`/home/user/Documents/github/overte-android-phone`

Der vorgesehene Produktbranch ist `android-phone`. Er muss vor Beginn über
folgende Kette mit dem fertigen Common Contract synchronisiert worden sein:

`main -> android-main -> android-phone`

## Unmittelbar nach Erhalt dieses Auftrags: pausieren

Die Common-Contract-Arbeit auf `main` ist noch nicht fertig beziehungsweise
noch nicht bis `android-phone` synchronisiert. Unternimm deshalb in deinem
ersten Turn keinerlei Arbeit:

- keine Tools aufrufen;
- keine Dateien oder Git-Refs untersuchen;
- keine Dateien verändern;
- keine Tests, Builds oder Jenkins-Jobs starten;
- keine Git-Operationen ausführen;
- keine weiteren Agents oder Sessions starten;
- keine Operationsnamen, Schemas oder semantischen IDs vorwegnehmen.

Antworte zunächst nur sinngemäß:

> Die Android-Phone-Adapter-Session ist vorbereitet und wartet auf die
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
- die Android-/Appium-Adapterdokumentation;
- die vorhandenen Android-Phone-Tablet-, Touch-UI-, QML- und JavaScript-Tests.

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
3. dass die vollständige Branch-Kette `main -> android-main -> android-phone`
   synchronisiert wurde;
4. dass Contract-Dokumentation, Registry, Schemas, gemeinsame Module, Mock und
   Self-Tests dieselbe finale Version verwenden;
5. dass der vom Benutzer genannte Common-Contract-Commit im Produktstand
   enthalten ist, sofern ein Commit genannt wurde.

Wenn der Contract fehlt, nur teilweise synchronisiert ist oder seine Dateien
nicht zusammenpassen, ändere nichts. Berichte den exakten Unterschied und
warte auf Korrektur. Synchronisiere oder reconcile die Branch-Kette nicht
selbst.

## Ziel und Scope

Implementiere ausschließlich die Android-Phone-Adapter- und Produktseite des
finalen gemeinsamen Tablet-E2E-Contracts:

- eine eingecheckte Android-Phone-Produkt-Policy nach dem finalen Schema;
- Mapping der gemeinsamen semantischen Tablet-IDs auf die reale Oberfläche;
- die final definierten semantischen Tablet-Operationen im vorgesehenen
  Android-/Appium-Adapter;
- Beobachtung von tatsächlichem Screen, Ready-Zustand und tatsächlich
  sichtbaren semantischen Controls;
- Aktivierung sichtbarer Controls durch echte Benutzerinteraktion;
- notwendige Android-Phone-spezifische Accessibility-, QML-Selector- oder
  UiAutomator2-Anbindung;
- Adapter-Self-Tests, Produkt-Tests, Dokumentation und Runbook;
- physische Akzeptanzvalidierung, sofern das lokale Lab verfügbar und die
  Ausführung im Scope liegt.

Nicht in Scope sind Änderungen am gemeinsamen Contract nach eigener
Vorstellung, neue gemeinsame Operationsnamen, iOS-, Pico-, Quest-, macOS- oder
Desktop-Adapter, private Targetdaten und eine Umgehung sichtbarer UI-Pfade über
direkte interne Navigation.

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
- Verwende stabile, nicht lokalisierte semantische Accessibility-IDs.
- Sichtbare übersetzte Texte sind keine primären Selektoren.
- Koordinaten sind höchstens ein auditierter Bootstrap-Fallback, nicht die
  Grundlage der vollständigen Navigation.
- Ein erfolgreicher Tap allein ist kein Pass. Der resultierende UI-Zustand muss
  unabhängig beobachtet werden.
- Screenshots sind nur redigierte Diagnoseartefakte.
- Keine privaten Android-Geräteserials, Appium-Selektoren, Credentials oder
  geheimen Targetwerte in Kommandos, Logs oder Artefakten ausgeben.

## Android-Phone-Policy

Android Phone ist für diesen Vertrag ein Flat-Touch-Produkt. Leite die exakten
Erwartungen aus dem finalen Schema und der vorgesehenen Produktoberfläche ab.
Insbesondere sollen verpflichtend geprüft werden:

- Tablet Home und Settings sind erreichbar;
- allgemeine, Audio- und Security-Einstellungen sind vorhanden;
- HMD-/VR-Einstellungen sind abwesend;
- VR-/Desktop-Controller-Einstellungen sind abwesend;
- die allgemeine Funktion für VR-Renderauflösung beziehungsweise VR-Render-
  Scale ist abwesend.

Verwende ausschließlich die finalen allgemeinen semantischen IDs. Eine intern
vorhandene Eigenschaft wie `picoResolutionSettingsAvailable` darf nur als
Implementierungsdetail auf das allgemeine Feature abgebildet werden. Führe
keine produktbezogenen ID wie `settings.pico-resolution` in den Common Contract
ein.

## Bedienung und Beobachtung

Bevorzuge Appium W3C, UiAutomator2, stabile Accessibility-IDs, echte Click-/Tap-
Aktivierung sowie die vorhandene In-Client-Probe für Tablet-Zustand und
Prozessidentität. Die Aktion muss denselben Handler auslösen wie eine reale
Benutzerinteraktion. Nutze keine direkte QML-Routenmanipulation oder Script-API
als Ersatz für das Antippen eines sichtbaren Controls.

Wenn Qt/QML ein benötigtes Element nicht in den nativen Accessibility Tree
publiziert, prüfe zuerst die synchronisierten gemeinsamen IDs. Ergänze danach
nur die kleinste notwendige Android-Phone-Anbindung und dokumentiere ihre
Grenze.

## Erforderliche Validierung

Implementiere und führe mindestens aus, soweit lokal möglich:

- Adapterprotokoll-Self-Tests ohne Gerät;
- vollständige Sequenz: öffnen -> Home ready -> Settings aktivieren -> Settings
  ready -> Policy prüfen -> zurück -> schließen;
- negative Fälle für fehlende Pflicht-IDs und sichtbare verbotene HMD-,
  Controller- oder VR-Renderauflösungs-IDs;
- nicht-ready, falscher Screen, Aktion ohne Zustandswechsel, Prozessneustart
  und malformed Snapshot;
- Cleanup-Idempotenz und Redaction privater Selektoren;
- bestehende Android-Phone-Tablet-, QML-, JavaScript- und Touch-Tests;
- finalen gemeinsamen Adapter-Verifier;
- gemeinsame Tablet-Suite mit `--require-complete`.

Wenn das lokale Overte-Jenkins-Gerätelabor verwendet wird, lies und befolge die
Skill-Anweisungen von `jenkins-local-lab`. Verwende den offiziellen
`overte-jenkins` CLI-Wrapper und keine rohen HTTP-/curl-Aufrufe, sofern die CLI
die Operation unterstützt. Exponiere niemals Credentials, Geräteserials oder
geheime Target-Selektoren. Wenn kein physisches Ziel verfügbar ist, führe alle
hardwarefreien Tests aus und behaupte keinen physischen Pass.

## Arbeitsgrenzen und Abschluss

- Arbeite nach Freigabe autonom und behebe gefundene Fehler selbst.
- Bewahre fremde Änderungen und verwende keine destruktiven Git-Befehle.
- Erzeuge keine zusätzlichen Worktrees oder Agents.
- Nimm keine Commits, Pushes, Merges oder Branch-Synchronisationen vor.
- Frage nur bei objektiv fehlendem Contract, fehlerhafter Synchronisierung oder
  einer wesentlichen Scope-Entscheidung nach.

Die Arbeit ist abgeschlossen, wenn die Android-Phone-Policy und alle finalen
Operationen implementiert sind, reale Benutzerinteraktion und unabhängige
Beobachtung funktionieren, verbotene VR-Funktionen verbindlich abwesend sind,
Verifier und relevante Tests bestehen und keine privaten Daten persistiert
wurden.

Berichte abschließend Contract-Version und Ausgangscommit, Policy, Mapping der
semantischen IDs, geänderte Dateien, alle Testergebnisse, physische Evidenz
(falls tatsächlich ausgeführt), nicht ausführbare Tests, bekannte Grenzen und
eventuelle Common-Contract-Probleme.
