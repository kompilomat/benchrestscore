# Calibration Specification

## Purpose

Definiert die Diagnose- und Bewertungsmöglichkeiten des Kalibrierungs-Workflows:
Fehlschläge werden mit konkretem Grund (Raster nicht erkannt, fehlgeschlagener
Farbkanal) und gefundener Kreisanzahl dargestellt; erfolgreiche Kalibrierungen
erhalten eine farbliche Genauigkeits-Bewertung samt Warnhinweis bei
ungenügender Qualität.

## Requirements

### Requirement: Fehlschlag-Grund im Start-Dialog
Das System SHALL bei einem fehlgeschlagenen Kalibrierversuch die konkrete Ursache im
Kalibrierungs-Start-Dialog anzeigen. Schlägt die Rastererkennung fehl, SHALL die Meldung
angeführt werden, dass die Kalibrierkarte nicht erkannt wurde, und die Anzahl der
gefundenen Kreise enthalten. Schlägt die Erkennung in einem einzelnen Farbkanal fehl,
SHALL die Meldung den betroffenen Kanal (B/G/R) sowie die Anzahl der in diesem Kanal
gefundenen Kreise anführen.

#### Scenario: Raster nicht erkannt
- **WHEN** der Nutzer eine Kalibrierung startet und die Rastererkennung des Gesamtbilds
  fehlschlägt
- **THEN** zeigt der Start-Dialog die Meldung „Kalibrierkarte nicht erkannt …" samt Anzahl
  der gefundenen Kreise, und der Kalibriervorgang bleibt abgebrochen

#### Scenario: Farbkanal fehlgeschlagen
- **WHEN** der Nutzer eine Kalibrierung startet, das Raster gefunden wurde, aber ein
  einzelner Farbkanal (Rot, Grün oder Blau) bei der Rastererkennung scheitert
- **THEN** zeigt der Start-Dialog die Meldung unter Nennung des betroffenen Kanals und der
  in diesem Kanal gefundenen Kreisanzahl

#### Scenario: Fehlermeldung zurücksetzen
- **WHEN** nach einem Fehlschlag ein neuer Kalibrierversuch gestartet wird
- **THEN** wird die vorherige Fehlermeldung ausgeblendet, bis der neue Versuch
  fehlschlägt

### Requirement: Genauigkeits-Bewertung im Ergebnis-Dialog
Das System SHALL den mittleren Reprojektionsfehler (AVG) einer erfolgreichen
Kalibrierung im Ergebnis-Dialog farblich bewerten: gut (≤ 50 µm, grün), akzeptabel
(≤ 75 µm, gelb), schlecht (≤ 100 µm, orange) und ungenügend (> 100 µm, rot). Bei einer
Varianz-Bewertung schlecht oder ungenügend SHALL zusätzlich ein Warnhinweis erscheinen,
der zu einer erneuten Kalibrierung rät.

#### Scenario: Gute Genauigkeit
- **WHEN** eine Kalibrierung erfolgreich abgeschlossen wurde und der mittlere Fehler
  ≤ 50 µm ist
- **THEN** wird die AVG/VAR-Zeile im Ergebnis-Dialog grün dargestellt und es erscheint
  kein Warnhinweis

#### Scenario: Ungenügende Genauigkeit
- **WHEN** eine Kalibrierung erfolgreich abgeschlossen wurde und der mittlere Fehler
  > 100 µm ist
- **THEN** wird die AVG/VAR-Zeile rot dargestellt und ein Warnhinweis rät zu einer
  erneuten Kalibrierung

### Requirement: Kalibrier-Ergebnis nur als volles Set speichern (mit Hintergrund)
Das System SHALL Kalibrierung und Hintergrund **ausschließlich gemeinsam** als volles Set
persistieren — und nur, wenn der Kalibrier-Workflow vollständig abgeschlossen ist
(Ergebnis akzeptiert + Hintergrund mit Keypoints gelernt + Messmodus erreicht). Ein
Kalibrier-Versuch allein (Erfolg oder Fehlschlag) SHALL keine `last_calibration.*`-Dateien
schreiben; die Persistenz übernimmt die finale Session. Im Config-Verzeichnis entstehen
dabei zusammen:
- `last_calibration.png` (Roh-Frame der Karte), `last_calibration_overlay.png` (Visual) und
  `last_calibration.json` (Sidecar mit `mean`/`sd`/`quality`, A/B-Korrektur, Matrizen,
  Diagnose **und** `width`/`height`/`has_background`).
- `last_background.png`, `last_background_overlay.png` und `last_background.json`
  (Keypoints) sowie `last_session.json` (Erfolgs-Marker).
Die Dateien SHALL überschreibend und ohne Zeitstempel geschrieben werden (kein Wachstum),
und Schreibfehler SHALL den Messbetrieb nicht blockieren.

#### Scenario: Vollständige Kalibrierung erzeugt volles Set
- **WHEN** der Kalibrier-Workflow vollständig abgeschlossen wurde (inkl. Hintergrund)
- **THEN** existieren `last_calibration.png`/`_overlay.png`/`.json`,
  `last_background.png`/`_overlay.png`/`.json` und `last_session.json` im
  Config-Verzeichnis, und das Sidecar trägt `width`/`height`/`has_background=true`

#### Scenario: Fehlgeschlagene Kalibrierung schreibt nichts
- **WHEN** ein Kalibrier-Versuch fehlschlägt (Raster oder Kanal nicht erkannt)
- **THEN** werden keine `last_calibration.*`-Dateien geschrieben; eine evtl. frühere,
  vollständige Session bleibt unberührt

#### Scenario: Überschreiben statt Anhäufen
- **WHEN** nach einer finalisierten Session eine weitere vollständige Kalibrierung
  abgeschlossen wird
- **THEN** werden die Dateien überschrieben, nicht angehängt; es bleiben dieselben
  Dateinamen

### Requirement: Diagnose-Funktionen für den Reprojektionsfehler
Das System SHALL reine, headless testbare Funktionen bereitstellen, die die
per-Punkt-Fehlermatrix der Kalibrierung auswerten:
- **Fehler-über-Radius**: mittlerer Fehler (µm) in Radial-Bins um die Bildmitte —
  monotones Ansteigen nach außen deutet auf Oszillation/hohe Distorsions-Ordnungen,
  Wellen auf ein k4–k6-Problem.
- **Quadranten-Breakdown**: mittlerer Fehler pro Bildquadrant — eine Asymmetrie
  deutet auf eine dezentrierte Linse hin (Kandidat für `cx`/`cy`-Modell).

#### Scenario: Radius-Kurve
- **WHEN** die Fehler-über-Radius-Kurve berechnet wird
- **THEN** liefert sie je Radius-Bin einen Mittelwert (µm); äußere Bins sind
  als Vergleich verfügbar

#### Scenario: Quadranten-Asymmetrie
- **WHEN** der Quadranten-Breakdown berechnet wird
- **THEN** sind die vier Quadranten-Mittelwerte (µm) getrennt abrufbar, sodass
  eine systematische Dezentrierung von einer symmetrischen Oszillation
  unterschieden werden kann

### Requirement: Diagnose im Overlay einzeichnen
Das System SHALL die Diagnose-Befunde im Kalibrier-`visual`-Bild einzeichnen
(per-Punkt-Fehler in µm sowie Radius-/Quadranten-Hinweis), sodass die Fehler-
verteilung auch im Betrieb direkt sichtbar ist.

#### Scenario: Overlay sichtbar
- **WHEN** eine Kalibrierung erfolgreich war und das Ergebnis-Bild angezeigt wird
- **THEN** zeigt das Bild pro Rasterpunkt den Fehler in µm und den
  Radius-/Quadranten-Befund als Text

### Requirement: Regressionstest auf kommittierter Kalibrieraufnahme
Das System SHALL einen headless Regressionstest bereitstellen, der die Kalibrierung
auf einer kommittierten Kalibrierkarten-Aufnahme (`data/calibration_card.png`)
ausführtund Erfolg, Qualität und Diagnose-Werte gegen feste Schwellen prüft. Damit
wird eine deterministische Basis für spätere Modell-Änderungen geschaffen. Die
Grenzen folgen dem aktuell erreichbaren Niveau des Kalibrier-Modells.

#### Scenario: Fixture-Test läuft
- **WHEN** der Fixture-Test auf der kommittierten Aufnahme läuft
- **THEN** schlägt die Kalibrierung nicht fehl, der mittlere Reprojektionsfehler liegt
  **unter 20 µm** und die Standardabweichung **unter 12 µm**;die Diagnose-
  Funktionen liefern plausible Werte, und das Radius-Profil ist **weitgehend flach** —
  der äußerste Radius-Bin liegt **nicht wesentlich** über dem innersten (die
  historische Sattel-/Eck-Struktur ist verschwunden).

### Requirement: Distortion-Korrektur erreicht Sub-20-µm-Genauigkeit
Das System SHALL pro Farbkanal(B/G/R` eine Distortion-Korrektur anwenden,die den
mittleren Reprojektionsfehler der Kalibrierkarten-Aufnahme auf **unter 20 µm**
reduziert(gegenüber dem historischen ≈ 34,6 µm`. Die Korrektur ist die Grundlage
für die LUT-Erzeugung pro Kanal,und die Weltmetrik wird weiterhin über die
geteilte Homographie (`mat`/`mati`) definiert — die Korrektur darf die Metrik **nicht**
verändern. Die Inversion der Korrektur(für die Reprojektion gemessener Punkte in die
Weltmetrik` SHALL deterministisch und auf Maschinen-Genauigkeit konvergieren
(Roundtrip: Vorwärts- und Rückwärts-Korrektur reproduzieren die Ausgangspunkte
im Rahmen unter  1 µm`.

#### Scenario: Genauigkeitsverbesserung auf der Fixture-Aufnahme
- **WHEN** die Kalibrierung auf `data/calibration_card.png` ausgeführt wird
- **THEN** liegt der mittlere Reprojektionsfehler unter 20 µm und die
  Standardabweichung unter 12 µm,und die Verbesserung bleibt bei
  Kreuzvalidierung erhalten(keine Überanpassung an die Stützpunkte.

#### Scenario: Metrik bleibt über die geteilte Homographie definiert
- **WHEN** ein gemessener Punkt in die Weltmetrik umgerechnet wird
- **THEN** geschieht das ausschließlich über `mati` (und ggf. die Inversion der
  Kanal-Korrektur` — die geteilte Homographie und damit die Weltmetrik bleiben
  unverändert gegenüber der bisherigen Kalibrierung.


#### Scenario: Inversion konvergiert
- **WHEN** ein beobachteter Rasterpunkt(nach Vorwärts-Korrektur` zurück in die
  Modell-Weltprojektion invertiert wird
- **THEN** reproduziert die Inversion die Modellkoordinate mit einem Fehler unter
  1 µm (Roundtrip-Fehler`.

### Requirement: Persistierte Kalibrierungen beider Formate lesbar
Das System SHALL beim Wiederherstellen einer gespeicherten Kalibrier-Session die
`channel_params` in **beiden** Formaten akzeptieren: dem bisherigen Legacy-Format
(16 Werte pro Kanal: Affine + Radial/Tangential-Terme` sowie dem neuen Format
(20 Werte pro Kanal: Grad-3-Polynom-Koeffizienten`. Bestehende persistierte
Samples (`datasets/sample_*`, `last_calibration.json`) SHALL weiterhin ladbar bleiben,
ohne dass ihre Metrik-Daten (`mat`/`mati`, manuelle Messpunkte in Weltmetrik` angepasst
werden müssen.

#### Scenario: Legacy-Sidecar wird geladen
- **WHEN** eine mit dem bisherigen Verfahren persistierte Kalibrierung geladen wird
- **THEN** erkennt das System das Legacy-Format an der Parameter-Länge(16` und
  behandelt die geladenen Parameter weiterhin gemäß dem bisherigen
  Distortion-Modell, ohne Fehler oder Konvertierung.



#### Scenario: Neues Sidecar wird geladen
- **WHEN** eine mit dem neuen Verfahren persistierte Kalibrierung geladen wird
- **THEN** erkennt das System das neue Format an der Parameter-Länge(20` und
  wendet die Polynom-Distortion an.

### Requirement: Schritt-Anzeige in der Kalibrier-Dialog-Titelleiste
Das System SHALL in der Titelleiste aller Dialoge des Kalibrier-Workflows den aktuellen
Schritt als „Kalibrierung — Schritt `n/4`" anzeigen. Die Schritte sind fest an die
sichtbaren Dialog-Stationen gekoppelt: Schritt 1 im Start-Dialog (Karte ausrichten),
Schritt 2 im Ergebnis-Dialog, Schritt 3 in der Untergrund-Lern-Aufforderung, Schritt 4
im Lern-Ergebnis. Die laufende Kalibrierung (`CALIBRATING`) ist kein eigener sichtbarer
Schritt — sie läuft blockierend im GUI-Thread ohne eigenen Dialogtitel; der Schritt
„2/4" erscheint erst im anschließenden Ergebnis-Dialog. Der Messung-Dialog ist kein
Kalibrier-Schritt und SHALL keine Schritt-Anzeige tragen.

#### Scenario: Start-Dialog zeigt Schritt 1
- **WHEN** der Kalibrier-Workflow offen ist und der Nutzer die Kalibrierkarte
  ausrichten soll
- **THEN** trägt der Dialog-Titel „Kalibrierung — Schritt 1/4"

#### Scenario: Laufende Kalibrierung zeigt Schritt 2
- **WHEN** die Kalibrierung berechnet wird
- **THEN** läuft sie blockierend im GUI-Thread und zeigt keinen sichtbaren
  Dialogtitel; der Schritt „2/4" erscheint erst im Ergebnis-Dialog

#### Scenario: Ergebnis-Dialog zeigt Schritt 3
- **WHEN** eine Kalibrierung erfolgreich war und das Ergebnis angezeigt wird
- **THEN** trägt der Dialog-Titel „Kalibrierung — Schritt 2/4"

#### Scenario: Untergrund-Lernen zeigt Schritt 4
- **WHEN** sich der Workflow in den Untergrund-Lern-Schritten befindet
  (Lern-Aufforderung oder Lern-Ergebnis)
- **THEN** trägt die Lern-Aufforderung den Titel „Kalibrierung — Schritt 3/4" und das
  Lern-Ergebnis den Titel „Kalibrierung — Schritt 4/4"

#### Scenario: Messung-Dialog ohne Schritt-Anzeige
- **WHEN** der Messbetrieb aktiv ist und der Messung-Dialog angezeigt wird
- **THEN** trägt der Dialog-Titel weiterhin nur „Messung"

### Requirement: Zentrierte Startposition der Kalibrier-Dialoge
Das System SHALL die Dialoge des Kalibrier-Workflows (Start-/Ausrichten-Dialog,
laufende Kalibrierung, Ergebnis-Dialog, Untergrund-Lern-Schritte) beim ersten
Erscheinen zentriert in der Arbeitsfläche unterhalb der Menüleiste platzieren, sodass
geöffnete Menü-Dropdowns sie nicht überdecken. Nach dem Erscheinen SHALL der Nutzer
die Dialoge frei verschieben können, und die verschobene Position SHALL erhalten
bleiben. Der Messung-Dialog ist kein Kalibrier-Schritt und SHALL von dieser Regel
ausgenommen bleiben.

#### Scenario: Workflow-Dialog erscheint zentriert unter der Menüleiste
- **WHEN** ein Kalibrier-Workflow-Dialog (z.B. der Start-Dialog oder der
  Ergebnis-Dialog) zum ersten Mal angezeigt wird
- **THEN** ist er horizontal zentriert in der Arbeitsfläche unterhalb der Menüleiste
  platziert und wird von geöffneten Menü-Dropdowns nicht überdeckt

#### Scenario: Verschieben nach dem Erscheinen bleibt möglich
- **WHEN** der Nutzer einen bereits sichtbaren Workflow-Dialog verschiebt
- **THEN** bleibt die verschobene Position erhalten (auch über Sitzungen hinweg) und
  wird beim nächsten Anzeigen des Workflows wiederverwendet

### Requirement: Dialog-Titel nicht abschneiden
Das System SHALL die Kalibrier-Workflow-Dialoge so breit darstellen, dass ihr
Titel („Kalibrierung — Schritt `n/4`") vollständig sichtbar ist. Die Mindestbreite
SHALL sich aus der Titelbreite ableiten; ist der Inhalt breiter, SHALL das Fenster
wie bisher mit dem Inhalt wachsen.

#### Scenario: Schmaler Inhalt, breiter Titel
- **WHEN** ein Workflow-Dialog einen Titel hat, der breiter ist als sein Inhalt
  (z.B. der letzte Schritt mit kurzem Text)
- **THEN** ist das Fenster mindestens so breit wie der Titel, und der Titel ist
  vollständig sichtbar

#### Scenario: Breiter Inhalt wächst weiter
- **WHEN** der Inhalt eines Workflow-Dialogs breiter ist als der Titel
- **THEN** bleibt die automatische Größenanpassung an den Inhalt erhalten (das
  Fenster wird nicht auf die Titelbreite fixiert)
### Requirement: Referenz-Raster im Kalibrier-Sidecar
Das System SHALL im Kalibrier-Sidecar (`last_calibration.json`) zusätzlich das
gemessene Referenz-Raster der Kalibrierkarte in Weltmetrik (`grid_metric`,
`[rows, cols, 2]`) persistieren. Bestehende Sidecars ohne dieses Feld bleiben
lesbar und wiederherstellbar.

#### Scenario: Neues Sidecar enthält Referenz-Raster
- **WHEN** eine Kalibrierung abgeschlossen und als volles Set persistiert wird
- **THEN** enthält das Sidecar `grid_metric` mit den gemessenen Punktpositionen
  der Karte

#### Scenario: Altes Sidecar ohne Referenz-Raster bleibt gültig
- **WHEN** ein Sidecar ohne `grid_metric` geladen wird
- **THEN** bleibt die Wiederherstellung vollständig funktionsfähig; nur der
  Qualitätscheck meldet „Referenz fehlt"
