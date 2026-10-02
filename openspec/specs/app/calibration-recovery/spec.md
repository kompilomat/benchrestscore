# Calibration-Recovery Specification

## Purpose

Definiert das Persistieren der finalisierten Kalibrier-Session (Kalibrierung + gelernter
Tisch-Untergrund als JSON) und die Wiederherstellung der letzten Ergebnisse über das
Kalibrierung-Menü zurück in den Messmodus, inklusive Auflösungs-Validierung,
Session-Marker und sofortiger Loss-of-Calibration-Warnung.

## Requirements

### Requirement: Persistenz der finalisierten Session (volles Set)
Das System SHALL nach erfolgreicher Hintergrunderkennung (Workflow abgeschlossen, Messmodus
erreicht) Kalibrierung und Hintergrund **gemeinsam als volles Set** persistieren:
- `last_calibration.png` (Roh-Frame der Karte), `last_calibration_overlay.png` (Visual),
  `last_calibration.json` (Sidecar inkl. `width`/`height`/`has_background`).
- `last_background.png` (**LUT-entzerrter** Frame des freien Tischs),
  `last_background_overlay.png` (Keypoint-Visualisierung auf dem **entzerrten** Frame),
  `last_background.json` (die gelernten Keypoints inklusive ORB-Descriptors, einheitlich
  als JSON wie das Kalibrier-Sidecar, mit Breite/Höhe des Lern-Frames und Keypoint-Anzahl).
- `last_session.json`: Ein Erfolgs-Marker, der kennzeichnet, dass eine Kalibrier-Session
  finalisiert (inkl. Hintergrund) vorliegt und wiederherstellbar ist.
Alle Dateien SHALL überschreibend und ohne Zeitstempel geschrieben werden (kein Datenwachstum)
und Schreibfehler SHALL die Messung nicht blockieren. Kalibrier-Versuche ohne finalisierten
Hintergrund SHALL keine Kalibrier-Persistenz auslösen.

#### Scenario: Finalisierte Session persistiert
- **WHEN** die Hintergrunderkennung erfolgreich abgeschlossen wurde und der Messmodus erreicht
  ist
- **THEN** existieren `last_calibration.*`, `last_background.*` und `last_session.json` im
  Config-Verzeichnis, und `last_calibration.json` trägt die Rahmenmetadaten

#### Scenario: Erneutes Schreiben überschreibt
- **WHEN** nach einer finalisierten Session eine weitere Kalibrierung mit Hintergrund
  abgeschlossen wird
- **THEN** werden die Bestände überschrieben, nicht angehäuft; es bleiben dieselben
  Dateinamen

#### Scenario: Hintergrund-PNGs LUT-entzerrt
- **WHEN** eine Session finalisiert wird und die Kalibrierung gültige LUTs liefert
- **THEN** sind `last_background.png` und `last_background_overlay.png` die per Farbkanal
  LUT-korrigierte Version des Lern-Frames (Geometrie identisch zur Bildschirm-Anzeige),
  ohne Anzeige-Filter (Kontrast/Gamma/Negativ/Graustufen)

#### Scenario: Entzerrung ohne gültige LUTs
- **WHEN** eine Session finalisiert wird und keine gültigen LUTs vorliegen (nicht kalibriert)
- **THEN** werden die Hintergrund-PNGs unverändert als Lern-Frame geschrieben (kein
  Blockieren der Persistenz)

### Requirement: Wiederherstellung der letzten Ergebnisse
Das System SHALL die letzte finalisierte Session im Messmodus wiederherstellen können. Dazu
SHALL das Kalibrier-Sidecar (`mat`/`mati`, `channel_params`) geladen und der gelernte
Untergrund aus `last_background.json` wiederhergestellt werden; die LUTs SHALL daraus neu
berechnet und der Messmodus erreicht werden. Der Loss-of-Calibration-Monitor SHALL nach der
Wiederherstellung wie gewohnt laufen.

#### Scenario: Erfolgreiche Wiederherstellung
- **WHEN** eine valide finalisierte Session vorliegt und der Nutzer die Wiederherstellung
  wählt
- **THEN** wird die Kalibrierung angewandt (LUTs gesetzt), der Untergrund aus dem JSON
  wiederhergestellt und die App erreicht den Messmodus mit aktivem Monitor

### Requirement: Auflösungs-Validierung bei der Wiederherstellung
Das System SHALL die Wiederherstellung nur zulassen, wenn die aktuelle Kamera-Auflösung mit
der gespeicherten Breite/Höhe der Session übereinstimmt. Bei Abweichung SHALL die
Wiederherstellung verweigert werden (kein Messmodus) und der Grund angezeigt werden.

#### Scenario: Auflösung gewechselt
- **WHEN** der Nutzer die Wiederherstellung wählt und die aktuelle Kamera-Auflösung nicht zur
  gespeicherten Session passt
- **THEN** wird die Wiederherstellung verweigert und eine entsprechende Meldung angezeigt

#### Scenario: Auflösung passt
- **WHEN** der Nutzer die Wiederherstellung wählt und die aktuelle Auflösung zur gespeicherten
  passt
- **THEN** wird die Session wiederhergestellt und der Messmodus erreicht

### Requirement: Session-Marker-Lifecycle
Das System SHALL den Erfolgs-Marker nur für eine finalisierte (inkl. Hintergrund) Session
führen. Bei Abbruch des Kalibrier-Workflows, Zurücksetzen der Kalibrierung, Kamerageräte- oder
Auflösungswechsel SHALL der Marker entfernt werden, sodass keine veraltete Session
wiederherstellbar ist.

#### Scenario: Abbruch entfernt Marker
- **WHEN** der Kalibrier-Workflow abgebrochen (Esc/„Abbruch") oder die Kalibrierung
  zurückgesetzt wird
- **THEN** wird `last_session.json` entfernt und eine Wiederherstellung ist nicht mehr möglich

#### Scenario: Kein Marker ohne finale Session
- **WHEN** keine finalisierte Session mit Hintergrund existiert
- **THEN** ist die Wiederherstellung über das Menü nicht verfügbar (Eintrag ausgegraut)

### Requirement: Wiederherstellung im Kalibrierung-Menü
Das System SHALL im Menü unter „Kalibrierung" zwei direkte Einträge anbieten:
„Neu kalibrieren (K)" und „Kalibrierung wiederherstellen". Der
Wiederherstellungs-Eintrag SHALL nur aktiv sein (auswählbar), wenn eine
valide finalisierte Session vorliegt und sich die App im Ruhezustand (IDLE)
befindet.

#### Scenario: Menü führt zur Wiederherstellung
- **WHEN** der Nutzer im Kalibrierung-Menü „Kalibrierung wiederherstellen" wählt
- **THEN** wird die Wiederherstellung der letzten finalisierten Session
  ausgelöst

#### Scenario: Eintrag ausgegraut
- **WHEN** keine valide Session vorliegt oder die App nicht im Ruhezustand ist
- **THEN** ist der Wiederherstellungs-Eintrag ausgewählt nicht verfügbar

### Requirement: Sofort-Warnung nach Wiederherstellung
Das System SHALL nach einer erfolgreichen Wiederherstellung unverzüglich den Monitor auf den
wiederhergestellten Untergrund prüfen lassen; eine erkannte kritische Verschiebung SHALL wie
gewohnt über den Menü-Header-Indikator gemeldet werden (reine Warnung, kein Blockieren der
Messung).

#### Scenario: Verschiebung nach Wiederherstellung
- **WHEN** die Session wiederhergestellt wurde und die Kamera gegenüber dem gespeicherten
  Zustand kritisch verschoben ist
- **THEN** meldet der Indikator `verschoben` (mit mm) bzw. `n/a`, während die Messung
  weiterhin läuft