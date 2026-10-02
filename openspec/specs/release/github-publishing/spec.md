# GitHub Publishing Specification

## Purpose

Definiert den öffentlichen GitHub-Release der Software: Lizenzierung,
Inhalt und Datenschutz-Grenzen des veröffentlichten Snapshots sowie den
reproduzierbaren Veröffentlichungsvorgang aus dem privaten Entwicklungsrepo.

## Requirements

### Requirement: Lizenz des öffentlichen Releases

Der öffentliche GitHub-Release SHALL unter der GNU General Public License
v3 stehen. Die Datei `LICENSE.md` SHALL den vollständigen GPLv3-Text und
eine Copyright-Zeile des Autors enthalten; Personen- oder Kontaktdaten
(u.a. private E-Mail-Adressen) SHALL die Lizenzdatei nicht enthalten.

#### Scenario: GPLv3 liegt bei

- **WHEN** ein Release-Snapshot veröffentlicht wird
- **THEN** enthält er `LICENSE.md` mit vollständigem GPLv3-Text und Copyright-Zeile

#### Scenario: Keine Kontaktdaten in der Lizenzdatei

- **WHEN** `LICENSE.md` auf personenbezogene Kontaktdaten geprüft wird
- **THEN** enthält die Datei keine E-Mail-Adressen oder ähnliche Kontaktangaben

### Requirement: Öffentlicher Snapshot ohne personenbezogene und interne Daten

Der veröffentlichte Snapshot SHALL frei sein von: (a) den privaten
Referenzfotos und abgeleiteten Bild-/Metrikdateien unter `datasets/`
(ausgenommen ist eine erklärende `datasets/README.md`), (b) dem
Nutzernamen/Heimpfad des Entwicklers, (c) internen Planungs- und
Toolingartefakten (`.opencode/`, `openspec/changes/`), (d)
Anbieter-/Modellnamen interner LLM-Infrastruktur und (e)
Git-Historie, Verlaufsversionen oder Metadaten des privaten Entwicklungsrepos
(Commit-Autoren, Remote-URLs, Zugriffstokens).

#### Scenario: Kein Dataset im Snapshot

- **WHEN** der Snapshot auf seinen Inhalt geprüft wird
- **THEN** enthält er unter `datasets/` ausschließlich die Platzhalter-`README.md`

#### Scenario: Kein Entwickler-Heimpfad

- **WHEN** der Snapshot-Dateibaum nach `/home/<nutzer>`-Mustern und
  Entwickler-Namen/Username durchsucht wird
- **THEN** finden sich keine Treffer (das Desktop-File nutzt ein generisches `Exec=`)

#### Scenario: Keine internen Planungsartefakte

- **WHEN** der Snapshot auf `.opencode/` und `openspec/changes/` geprüft wird
- **THEN** sind diese Verzeichnisse im öffentlichen Snapshot nicht enthalten

#### Scenario: Keine Anbieterreferenzen im Code

- **WHEN** der öffentliche Snapshot nach dem internen LLM-Anbieter- und
  Modellnamen durchsucht wird
- **THEN** finden sich keine Treffer in Code, Tests, Specs und Doku

#### Scenario: Keine private Git-Historie

- **WHEN** die Git-Historie des öffentlichen Repos betrachtet wird
- **THEN** besteht sie aus den Release-Squash-Commits mit der für GitHub
  gewählten Autorenidentität, ohne Bezug zu GitLab-Commits, -Autoren oder -Remotes

### Requirement: Reproduzierbarer Veröffentlichungsvorgang

Das Repository SHALL ein Skript `tools/publish_github.sh` enthalten, das
den Release-Snapshot aus einem definierten Stand des privaten Repos
erzeugt: Datenstand des `main`-Zweigs, Entfernen der unter
„Öffentlicher Snapshot" ausgeschlossenen Inhalte, Erzeugung eines
einzelnen Commits mit konfigurierbarer Autorenidentität, Tagging und
Push auf einen als Parameter übergebenen GitHub-Remote. Das Skript SHALL
Zugriffstokens ausschließlich über Umgebung/Credential-Mechanismen
beziehen und SHALL sie weder in Dateiinhalten noch in Remote-URLs
schreiben. Vor dem Push SHALL das Skript die Ausschlussprüfung
(„Öffentlicher Snapshot ohne personenbezogene und interne Daten")
automatisieren und bei Treffern abbrechen.

#### Scenario: Snapshot-Erzeugung bricht bei Ausschlussverstößen ab

- **WHEN** das Skript nach dem Aussortieren im Prüfscan verbliebene
  auszuschließende Inhalte findet
- **THEN** bricht es mit Fehlermeldung ab, ohne etwas auf GitHub zu pushen

#### Scenario: Erneuter Release vom gleichen Stand

- **WHEN** das Skript zweimal vom selben `main`-Stand ausgeführt wird
- **THEN** entsteht derselbe Snapshot-Inhalt (nur Tag/Commit-Zeitstempel
  können sich unterscheiden)

### Requirement: Privates Repo bleibt Referenzquelle für Tests

Das private Entwicklungsrepo SHALL die `datasets/`-Samples weiterhin
lokal enthalten; die Git-Verfolgung von `datasets/` SHALL enden
(`.gitignore`), ohne die Referenz-Tests zu brechen: diese erkennen
fehlende Samples und überspringen automatisch, lokal gesetzte
`BRS_REFERENCE_DATASET` bzw. ein lokales `datasets/` aktivieren sie voll.

#### Scenario: Tests ohne datasets-Verfolgung

- **WHEN** `datasets/` nicht mehr git-verfolgt, aber lokal vorhanden ist
- **THEN** laufen die Referenz-Tests unverändert gegen die lokalen Samples

#### Scenario: Öffentliche Umgebung ohne Samples

- **WHEN** der Repo-Stand ohne lokale Samples (Clone des öffentlichen
  Snapshots) getestet wird
- **THEN** überspringen die Referenz-Tests automatisch mit Skip-Grund
