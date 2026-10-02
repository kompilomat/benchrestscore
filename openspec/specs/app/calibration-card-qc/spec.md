# Calibration Card Quality Check Specification

## Purpose

Prüft neu eingelegte Kalibrierkarten gegen die Referenzkarte der aktiven
Kalibrierung, indem das Raster in Weltmetrik vermessen und per Punkt
verglichen wird — mit Mehr-Frame-Mittelung, Homographie-Ausgleichung und
einer farbcodierten Overlay-Anzeige der Abweichungen.

## Requirements

### Requirement: Karten-Qualitätscheck gegen die Referenzkarte
Das System SHALL im Modus „Karten-Qualitätscheck" (Eintrag im Reiter
„Kalibrierung" der Menüleiste) unter der kalibrierten Kamera das Raster einer
eingelegten Kalibrierkarte erkennen, die Punktpositionen in Weltmetrik
vermessen und gegen die Referenzkarte der aktiven Kalibrierung prüfen.

#### Scenario: Karte in Spec
- **WHEN** eine neue Kalibrierkarte eingelegt ist, deren Punkte nach der
  Homographie-Ausgleichung alle innerhalb ±0,075 mm der Referenz liegen
- **THEN** meldet der Check „in Spec" und zeigt pro Punkt die Abweichung sowie
  Max/Mean-Abweichung

#### Scenario: Karte nicht in Spec
- **WHEN** mindestens ein Punkt der eingelegten Karte nach der Ausgleichung
  mehr als ±0,075 mm von der Referenz abweicht
- **THEN** meldet der Check „nicht in Spec", nennt die Anzahl der
  Überschreitungen und zeigt die per-Punkt-Abweichungen

### Requirement: Mehr-Frame-Messung mit Mittelung
Das System SHALL die Punktpositionen der eingelegten Karte aus
**`QC_SAMPLE_FRAMES` (3) aufeinanderfolgenden Kameraframes** bestimmen, die
NDC-Gitter über die Frames **mitteln** (Rauschreduktion √N) und die
Rastererkennung mit derselben Pipeline wie die Kalibrierung ausführen
(`findCirclesGrid` → `get_target_grid` → `inv_distortion` → `mati`).

#### Scenario: Mehrere Frames werden gemittelt
- **WHEN** der Qualitätscheck eine Erfassung durchführt
- **THEN** werden 3 Live-Frames erfasst und das NDC-Gitter wird über die Frames
  gemittelt, bevor die Distortion-Inversion und die Metrik-Berechnung laufen

### Requirement: Erfassung im Hintergrund-Thread
Das System SHALL die Erfassung und Auswertung (Detektion, Ausgleichung) in einem
**Hintergrund-Thread** ausführen und dabei den GL/Render-Thread nicht blockieren;
eine laufende Erfassung ist über einen Status-Dialog sichtbar und abbrechbar.

#### Scenario: UI bleibt während der Erfassung flüssig
- **WHEN** der Qualitätscheck läuft
- **THEN** bleibt der GL-Thread bedienbar und die UI zeigt einen Status-Dialog
  („Messe Kalibrierkarte…") mit Abbruch-Möglichkeit

### Requirement: Ausgleichung per Homographie
Das System SHALL zwischen dem gemessenen Raster der eingelegten Karte und dem
Referenz-Raster eine **Least-Squares-Homographie** (DLT, alle Punkte) berechnen
und vor dem Punktvergleich anwenden — Versatz, Drehung, Skalierung und
Perspektive der Einlage werden herausgerechnet, **lokale** Kartenfehler bleiben
das eigentliche Fehlmaß. (Eine reine Rotation+Translation genügt nicht: das
Metrik-Mapping hat ein positionsabhängiges Fehlerfeld, das bei minimal anderer
Einlage als Schein-Abweichung erscheinen würde.)

#### Scenario: Einlage-Variation wird herausgerechnet
- **WHEN** die eingelegte Karte gegenüber der Referenz minimal verschoben,
  gedreht, skaliert oder geneigt ist, aber identische Punktabstände hat
- **THEN** bleibt die Karte „in Spec", sofern alle Punkte nach Ausgleichung
  innerhalb der Toleranz liegen

### Requirement: Ergebnis persistieren und anzeigen
Das System SHALL das Ergebnis des Qualitätschecks (Raster, per-Punkt-Abweichungen
in µm, Max/Mean, Bestanden/Failen, Zeitstempel) als JSON ins Config-Verzeichnis
(`last_card_check.json`) sowie ein Overlay-Bild (`last_card_check_overlay.png`)
mit eingezeichneten Punkten und Abweichungen schreiben. Das Overlay zeichnet die
Punkte auf den **Rohbild-Pixelpositionen** der Blobs (das Overlay wird auf den
Roh-Frame gezeichnet und erst danach LUT-entzerrt angezeigt; eine vorherige
Distortion-Inversion würde die Entzerrung doppelt anwenden und die Marker
verbiegen). Farbkodierung je Punkt: grün ≤ 50 µm, orange 50–75 µm (beides in
Spec), rot > 75 µm (out of spec).
Schreibfehler dürfen den Betrieb nicht blockieren.

#### Scenario: Ergebnis-Dateien entstehen
- **WHEN** ein Qualitätscheck abgeschlossen wurde
- **THEN** existieren `last_card_check.json` und `last_card_check_overlay.png` im
  Config-Verzeichnis

### Requirement: Fehlerfälle melden
Das System SHALL klare Fehlermeldungen liefern, wenn (a) keine aktive
Kalibrierung vorliegt, (b) die Referenz (`grid_metric`) fehlt, oder (c) das
Raster nicht erkannt wird.

#### Scenario: Ohne Kalibrierung
- **WHEN** der Qualitätscheck ohne aktive Kalibrierung gestartet wird
- **THEN** erscheint eine Meldung, dass zuerst kalibriert werden muss

#### Scenario: Ohne Referenz
- **WHEN** die aktive Kalibrierung kein `grid_metric` enthält
- **THEN** erscheint eine Meldung, dass die Referenzkarte fehlt (Re-Kalibrierung
  nötig)

#### Scenario: Raster nicht erkannt
- **WHEN** bei der Erfassung das Raster nicht erkannt wird
- **THEN** erscheint eine Meldung mit der Anzahl der gefundenen Kreise, und es
  kann erneut versucht werden