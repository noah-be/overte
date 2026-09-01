# Codex-Auftrag: Pico-4-Adapter für Tablet-E2E

Arbeite ausschließlich im Worktree:

`/home/user/Documents/github/overte-pico4`

Der vorgesehene Produktbranch ist `android-vr-pico`. Er muss vor Beginn über
folgende Kette mit dem fertigen Common Contract synchronisiert worden sein:

`main -> android-main -> android-vr -> android-vr-pico`

## Unmittelbar nach Erhalt dieses Auftrags: pausieren

Die Common-Contract-Arbeit auf `main` ist noch nicht fertig beziehungsweise
noch nicht bis `android-vr-pico` synchronisiert. Unternimm deshalb in deinem
ersten Turn keinerlei Arbeit:

- keine Tools aufrufen;
- keine Dateien oder Git-Refs untersuchen;
- keine Dateien verändern;
- keine Tests, Builds oder Jenkins-Jobs starten;
- keine Git-Operationen ausführen;
- keine weiteren Agents oder Sessions starten;
- keine Operationsnamen, Schemas oder semantischen IDs vorwegnehmen.

Antworte zunächst nur sinngemäß:

> Die Pico-4-Adapter-Session ist vorbereitet und wartet auf die ausdrückliche
> Freigabe nach der Synchronisierung des Common Contracts.

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
- die Android-, Pico- und OpenXR-Adapterdokumentation;
- `tests/device/openxr_input/` und die relevanten Protokolle/Self-Tests;
- `android/vr/pico/tests/` sowie vorhandene Tablet-, Settings- und
  Controller-Tests;
- die vorhandenen Pico-Gerätelabor-Runbooks.

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
3. dass `main -> android-main -> android-vr -> android-vr-pico` vollständig
   synchronisiert wurde;
4. dass Contract-Dokumentation, Registry, Schemas, gemeinsame Module, Mock und
   Self-Tests dieselbe finale Version verwenden;
5. dass der vom Benutzer genannte Common-Contract-Commit im Produktstand
   enthalten ist, sofern ein Commit genannt wurde.

Wenn der Contract fehlt, nur teilweise synchronisiert ist oder seine Dateien
nicht zusammenpassen, ändere nichts. Berichte den exakten Unterschied und
warte auf Korrektur. Synchronisiere oder reconcile die Branch-Kette nicht
selbst.

## Ziel, Scope und Branch-Grenze

Implementiere ausschließlich die Pico-4-Adapter- und Produktseite des finalen
gemeinsamen Tablet-E2E-Contracts:

- eine eingecheckte Pico-4-Produkt-Policy nach dem finalen Schema;
- Mapping der gemeinsamen semantischen Tablet-IDs auf die reale Pico-Oberfläche;
- die final definierten semantischen Tablet-Operationen im vorgesehenen
  Pico-/Android-/OpenXR-Adapter;
- Beobachtung von tatsächlichem Screen, Ready-Zustand und tatsächlich
  sichtbaren semantischen Controls;
- Aktivierung sichtbarer Controls über die reale VR-Benutzerinteraktion;
- notwendige Pico-spezifische QML-, Accessibility-, Probe-, Controller- oder
  OpenXR-Anbindung;
- Adapter-Self-Tests, Produkt-Tests, Dokumentation und Runbook;
- physische Akzeptanzvalidierung, sofern das lokale Lab verfügbar und die
  Ausführung im Scope liegt.

Nicht in Scope sind Änderungen am gemeinsamen Contract nach eigener
Vorstellung, neue gemeinsame Operationsnamen, Android-Phone-, iOS-, Quest-,
macOS- oder Desktop-Adapter, private Targetdaten und eine Umgehung sichtbarer
Tablet-Interaktion über direkte interne Navigation.

Der Pico-Adapter darf nicht vom Android-Phone-Produktadapter abhängen.
Wiederverwendet werden dürfen nur wirklich gemeinsame Android- oder
plattformneutrale Bausteine der korrekten Elternbranch-Ebene. Nimm keine
Promotion, Rückwärts-Merges oder Branch-Synchronisierung selbst vor.

Wenn der finale Common Contract einen nachweisbaren Fehler enthält, ändere ihn
nicht stillschweigend im Produktbranch. Liefere einen minimalen Reproduktionsfall
und melde den benötigten Common-Fix zurück.

## Architekturregeln

- Der Adapter beobachtet den Istzustand; die getrennte Produkt-Policy definiert
  den Sollzustand.
- Der Adapter darf nicht dieselbe Policy zurückgeben, gegen die er geprüft wird.
- Adapter-Capabilities beschreiben Automation, nicht Produktfeatures.
- Ein absichtlich vorhandenes oder fehlendes Feature ist kein Skip.
- Negative Assertions erfolgen erst nach eindeutigem, stabilem Screen-Ready.
- Verwende ausschließlich allgemeine semantische IDs aus dem Common Contract.
- Die konkrete Pico-Auflösungseinstellung wird auf das allgemeine Feature für
  VR-Renderauflösung beziehungsweise VR-Render-Scale abgebildet.
- Führe keine gemeinsame ID wie `settings.pico-resolution` ein.
- Ein emulierter Controller-Input allein ist kein Pass. Der resultierende
  UI-Zustand muss unabhängig beobachtet werden.
- Screenshots oder HMD-Frames sind nur redigierte Diagnoseartefakte.
- Keine privaten Geräteserials, ADB-/Lab-Selektoren, Credentials oder geheimen
  Controller-Targetwerte in Kommandos, Logs oder Artefakten ausgeben.

## Pico-4-Policy

Pico 4 ist ein VR-Produkt. Leite die exakten Erwartungen aus dem finalen Schema
und der tatsächlich vorgesehenen Produktoberfläche ab. Insbesondere sollen
verpflichtend geprüft werden:

- Tablet Home und Settings sind erreichbar;
- allgemeine sowie relevante Audio- und Security-Einstellungen sind vorhanden;
- relevante HMD-/VR-Einstellungen sind vorhanden;
- die vorgesehenen Controller-Einstellungen sind vorhanden;
- die allgemeine Funktion für VR-Renderauflösung beziehungsweise VR-Render-
  Scale ist vorhanden.

Ordne die konkrete Pico-Einstellung ausschließlich der allgemeinen semantischen
ID des Common Contracts zu. Erfinde keine erwarteten Settings. Falls das reale
Produkt von der Common-Mock-Policy absichtlich abweicht, dokumentiere den
Widerspruch und fordere eine Policy-Klärung an; umgehe ihn nicht durch einen
Capability-Skip.

## Bedienung und Beobachtung

Bevorzuge die vorhandene Pico-/OpenXR-Automation, echte Controller- oder
Pointer-Interaktion, kontrollierte OpenXR-Eingabe, semantische Tablet-Snapshots
und die In-Client-Probe für Tablet-, Screen- und Prozesszustand.

Die Automation muss den realen Benutzerpfad auslösen: Tablet öffnen, sichtbares
Settings-Control anvisieren, Aktivierung auslösen, Screenwechsel unabhängig
beobachten, zurück navigieren und Tablet schließen. Nutze keine direkte
QML-Routenmanipulation, Script-API oder Probe-Kommandos als Ersatz für die
Aktivierung sichtbarer Controls.

Falls der native Android-Accessibility-Tree das HMD-Tablet nicht repräsentiert,
implementiere die vom finalen Contract vorgesehene Beobachtung über eine kleine
Pico-spezifische Adapter-/Probe-Grenze. Sie muss den tatsächlichen gerenderten
und interaktiven Zustand beobachten und darf nicht lediglich die Produkt-Policy
zurückgeben. Tablet-fokussierte Controller-Eingabe darf nicht in Avatarbewegung
oder Weltinteraktion auslaufen.

## Erforderliche Validierung

Implementiere und führe mindestens aus, soweit lokal möglich:

- Adapterprotokoll-Self-Tests ohne Gerät;
- vollständige Sequenz: öffnen -> Home ready -> Settings aktivieren -> Settings
  ready -> Policy prüfen -> zurück -> schließen;
- negative Fälle für fehlende HMD-/VR-, Controller- und allgemeine
  VR-Renderauflösungs-IDs;
- nicht-ready, falscher Screen, Controller-Aktion ohne Zustandswechsel,
  Prozessneustart und malformed Snapshot;
- Nachweis, dass Tablet-Eingabe Avatarposition und Sicht nicht unbeabsichtigt
  verändert;
- Cleanup-Idempotenz und Redaction privater Selektoren;
- bestehende Pico-Tablet-, Settings-, OpenXR- und Controller-Tests;
- finalen gemeinsamen Adapter-Verifier;
- gemeinsame Tablet-Suite mit `--require-complete`.

Wenn das lokale Overte-Jenkins-Gerätelabor verwendet wird, lies und befolge die
Skill-Anweisungen von `jenkins-local-lab`. Verwende den offiziellen
`overte-jenkins` CLI-Wrapper und keine rohen HTTP-/curl-Aufrufe, sofern die CLI
die Operation unterstützt. Exponiere niemals Credentials, Geräteserials oder
geheime Target-Selektoren und verwende vorhandene Geräte-Locks sowie Cleanup.
Wenn kein physisches Pico-4-Ziel verfügbar ist, führe alle hardwarefreien Tests
aus und behaupte keinen physischen Pass.

## Arbeitsgrenzen und Abschluss

- Arbeite nach Freigabe autonom und behebe gefundene Fehler selbst.
- Bewahre fremde Änderungen und verwende keine destruktiven Git-Befehle.
- Erzeuge keine zusätzlichen Worktrees oder Agents.
- Nimm keine Commits, Pushes, Merges oder Branch-Synchronisationen vor.
- Frage nur bei objektiv fehlendem Contract, fehlerhafter Synchronisierung oder
  einer wesentlichen Scope-Entscheidung nach.

Die Arbeit ist abgeschlossen, wenn die Pico-4-Policy und alle finalen
Operationen implementiert sind, reale VR-Benutzerinteraktion und unabhängige
Beobachtung funktionieren, erwartete VR-Funktionen verbindlich vorhanden sind,
Tablet-Eingabe von Weltbewegung isoliert bleibt, Verifier und relevante Tests
bestehen und keine privaten Daten persistiert wurden.

Berichte abschließend Contract-Version und Ausgangscommit, Policy, Mapping der
allgemeinen IDs auf konkrete Pico-Funktionen, Controller-/OpenXR-Interaktions-
und Beobachtungspfad, geänderte Dateien, alle Testergebnisse, physische Evidenz
(falls tatsächlich ausgeführt), nicht ausführbare Tests, bekannte Grenzen und
eventuelle Common-Contract-Probleme.
