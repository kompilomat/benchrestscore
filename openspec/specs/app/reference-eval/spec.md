# app/reference-eval Specification

## Purpose
Erfasst die manuelle Bewertung einer Zielscheibe als vollständigen, selbst-
enthaltenen Referenz-Snapshot (Bilder, Kalibrierung, Untergrund, Messpunkte),
damit Erkennungs-Verfahren headless gegen die Bewertung eines Menschen geprüft
werden können.

## Requirements

### Requirement: Manueller Referenz-Modus
Das System SHALL einen Referenz-Modus als orthogonalen Schalter anbieten
(Eintrag „Referenz-Modus" im Reiter „Messen" der Menüleiste). Im Messmodus mit
aktivem Referenz-Modus SHALL das Messung-Fenster einen Button „Referenz
speichern" anzeigen; ohne aktiven Referenz-Modus SHALL kein Speicher-Button
erscheinen.

#### Scenario: Referenz-Modus aktivieren
- **WHEN** der Nutzer im Messmodus den Menü-Eintrag „Referenz-Modus" unter
  „Messen" wählt
- **THEN** ist der Referenz-Modus aktiv und das Messung-Fenster zeigt den
  Button „Referenz speichern"

#### Scenario: Referenz-Modus deaktiviert
- **WHEN** der Referenz-Modus ausgeschaltet ist
- **THEN** erscheint kein Speicher-Button im Messung-Fenster

### Requirement: Referenz-Sample in nummeriertem Dataset-Ordner speichern
Das System SHALL beim Betätigen von „Referenz speichern" (Messmodus, aktiver
Referenz-Modus, mindestens ein Messpunkt gesetzt) ein **neues, aufsteigend
nummeriertes Sample** anlegen — `sample_NN/` in der Dataset-Wurzel
(`BRS_REFERENCE_DATASET` oder Repo-`datasets/`). Ein Sample SHALL alles
Selbst-enthaltene enthalten:
- `raw.png` + `evaluation.png`: rohes und LUT-entzerrtes Kamerabild.
- `calibration.json`/`calibration.png`/`calibration_overlay.png`: Kalibrierung
  (Sidecar + Karten-Bilder).
- `background.json`/`background.png`: gelerntes Untergrund-Modell (Keypoints +
  dichte Referenz in nativer Auflösung).
- `metrics.json`: Breite/Höhe, aktives Kaliber (Name, Radius in mm), die manuellen
  Messpunkte in Weltmetrik (x, y in mm) und die Kalibrier-Matrizen (`mat`/`mati`).
Die Nummerierung SHALL aufsteigend fortlaufend sein (ab der höchsten vorhandenen
Sample-Nummer). Ohne gelerntes Untergrund-Modell oder ohne Messpunkte SHALL das
Speichern abgelehnt werden.

#### Scenario: Erfolgreiches Speichern
- **WHEN** der Nutzer im Referenz-Modus mindestens einen Messpunkt gesetzt hat und „Referenz speichern" betätigt
- **THEN** wird `sample_NN/` (nächste freie Nummer) mit Bildern, Kalibrierung, Background und `metrics.json` angelegt

#### Scenario: Aufsteigende Nummerierung
- **WHEN** der Nutzer mehrfach „Referenz speichern" betätigt
- **THEN** entstehen aufsteigend nummerierte Ordner (`sample_01`, `sample_02`, …)

#### Scenario: Ohne Messpunkte
- **WHEN** der Nutzer „Referenz speichern" betätigt, aber keine Messpunkte gesetzt hat
- **THEN** wird nicht gespeichert und eine Meldung erscheint

### Requirement: Headless-Auswertung gegen die manuelle Bewertung
Das System SHALL einen headless Auswertungs-Pfad anbieten, der ein Sample lädt
(`load_reference_sample`) und die Klick-Automation pro manuellem Punkt ausführt
(`evaluate_automation`, Identitäts-View auf Frame-Größe): für jeden manuellen Punkt
wird der Fehler des verfeinerten Zentrums gegen die manuelle Weltmetrik (mm)
geliefert; schlägt die Automation fehl, wird der Punkt als nicht gefunden gewertet.
Die Auswertung SHALL pro Punkt zusätzlich kennzeichnen, ob das detektierte Zentrum
auf ein anderes manuelles Loch „gelatcht" ist (näher an einer anderen manuellen
Position als an der des angeklickten Lochs, mit kleiner Toleranz), und die
Gesamtzahl solcher Latch-Ereignisse des Samples liefern. Die Erweiterung SHALL die
bisherige Rückgabe-Struktur unverändert lassen (rückwärtskompatibel).

#### Scenario: Automation gegen manuelle Punkte
- **WHEN** ein Sample mit manuellen Punkten vorliegt und `evaluate_automation` läuft
- **THEN** liefert der Pfad pro Punkt den Fehler (mm) bzw. None für nicht gefundene Punkte sowie Mittel/Max über die gefundenen

#### Scenario: Latch-Kennzeichnung je Punkt
- **WHEN** das detektierte Zentrum eines Punkts näher an einer anderen manuellen Lochposition liegt als an der angeklickten
- **THEN** ist dieser Punkt als gelatcht markiert und die Gesamtzahl der Latch-Ereignisse ist im Ergebnis enthalten

### Requirement: Aggregierte Auswertung über ein Sample-Set
Das System SHALL eine headless Aggregations-Hilfe anbieten
(`evaluate_automation_dataset`), die `evaluate_automation` über eine beliebige
Menge von Samples ausführt und die Einzelergebnisse samt Samples-Namen,
Jitter-Parameter und Seed zusammenfasst. Ohne gültige Samples (nicht ladbar oder
leer) SHALL sie ein leeres Aggregat liefern statt zu scheitern.

#### Scenario: Alle Samples eines Datasets auswerten
- **WHEN** die Aggregations-Hilfe über alle Samples eines Datasets läuft
- **THEN** enthält das Ergebnis pro Sample den Namen, die Einzel-Fehler (mm je Punkt), die Anzahl gefundener Punkte, die Latch-Anzahl sowie Mittel/Max über das Sample und über das gesamte Set

#### Scenario: Leeres Datasets
- **WHEN** keine ladbaren Samples vorliegen
- **THEN** liefert die Aggregations-Hilfe ein leeres Ergebnis ohne Fehler

### Requirement: Automatisches Ausblenden der Referenz-Statusmeldung
Das System SHALL die Statusmeldung des Referenz-Speicherns im Messung-Fenster
(grüne Erfolgsmeldung „Referenz gespeichert" sowie rote Fehlermeldungen) nach
spätestens 5 Sekunden automatisch ausblenden. Der Button „Referenz speichern"
SHALL davon unberührt dauerhaft sichtbar bleiben. Ein erneutes Speichern bzw. ein
erneuter Fehlschlag innerhalb des 5-Sekunden-Fensters SHALL das Fenster neu
starten (die Meldung bleibt sichtbar).

#### Scenario: Erfolgsmeldung verschwindet nach 5 Sekunden
- **WHEN** der Nutzer „Referenz speichern" betätigt, das Speichern gelingt und
  5 Sekunden vergangen sind
- **THEN** ist die grüne Erfolgsmeldung nicht mehr sichtbar, der Button
  „Referenz speichern" bleibt sichtbar

#### Scenario: Fehlermeldung verschwindet nach 5 Sekunden
- **WHEN** „Referenz speichern" fehlschlägt (z.B. keine Messpunkte gesetzt) und
  5 Sekunden vergangen sind
- **THEN** ist die rote Fehlermeldung nicht mehr sichtbar

#### Scenario: Auffrischen bei erneutem Speichern
- **WHEN** der Nutzer innerhalb des 5-Sekunden-Fensters erneut „Referenz speichern"
  betätigt (erfolgreich oder fehlgeschlagen)
- **THEN** bleibt die Statusmeldung sichtbar und das 5-Sekunden-Fenster startet neu
