# Calibration-Monitor Specification

## Purpose

Definiert das workflow-gebundene Lernen des Tisch-Untergrunds im Kalibrier-Workflow (nach dem
Kalibrier-Ergebnis, vor dem Messmodus) und die periodische Erkennung, ob sich die Kamera
durch einen Stoß kritisch verschoben hat (Keypoint-Matching mit RANSAC-Homographie, Indikator
OK/verschoben/n/a in der Menüleiste, reine Warnung ohne Auto-Korrektur).

## Requirements

### Requirement: Workflow-Schritte des Hintergrund-Lernens
Das System SHALL nach erfolgreicher Kalibrierung und vor dem Messmodus zwei zusätzliche
Workflow-Schritte durchlaufen:
1. Nach dem Akzeptieren des Kalibrier-Ergebnisses SHALL eine Infobox den Nutzer auffordern,
   die Kalibrierkarte zu entfernen, mit einem Button „Hintergrund lernen (Enter)" und einem
   Button „Abbruch".
2. Nach erfolgreichem Lernen SHALL eine Infobox das Lern-Ergebnis (Keypoint-Visualisierung
   auf dem eingefrorenen Frame und Keypoint-Anzahl) zeigen, mit einem Button
   „Abschließen (Enter)". Erst danach SHALL der Messmodus erreicht werden.
Das Lernen ist damit verpflichtend; der Messmodus ist ohne erfolgreich gelerntes Modell
nicht erreichbar.

#### Scenario: Vollständiger Kalibrier-Workflow
- **WHEN** der Nutzer kalibriert, das Ergebnis akzeptiert, die Kalibrierkarte entfernt,
  „Hintergrund lernen" wählt und das Lernen gelingt
- **THEN** erscheint das Lern-Ergebnis mit Keypoint-Visualisierung und -Anzahl, und nach
  „Abschließen" erreicht die App den Messmodus mit gelerntem Untergrund-Modell

#### Scenario: Abbruch im Lern-Schritt
- **WHEN** der Nutzer im Lern-Schritt (Karte entfernen) „Abbruch" wählt
- **THEN** bricht die App den gesamten Kalibrier-Workflow ab (Zustand IDLE) und das
  Untergrund-Modell bleibt ungelernt

#### Scenario: Lernen nicht aus dem Messmodus
- **WHEN** die App sich im Messmodus befindet
- **THEN** ist kein weiteres Lernen des Untergrunds verfügbar; eine erneute Kalibrierung
  ist nötig, um den Workflow inkl. Hintergrund-Lernen erneut zu durchlaufen

### Requirement: Untergrund lernen
Das System SHALL beim Auslösen von „Hintergrund lernen" den aktuellen (eingefrorenen)
Kameraframe als Referenz-Untergrund lernen. Dafür SHALL die Kamera eingefroren werden
(Muster wie bei der Kalibrierung) und aus dem Frame markante Keypoints mit Descriptoren
extrahiert werden. Ist die Fläche zu strukturarm (zu wenige Keypoints), SHALL das Lernen
fehlschlagen, der Fehler in der Infobox angezeigt werden und die App im Lern-Schritt
verbleiben, sodass ein erneuter Versuch möglich ist.

#### Scenario: Lernen der freien Tischfläche
- **WHEN** der Nutzer „Hintergrund lernen" auslöst und der Tisch frei sichtbar ist
- **THEN** wird der eingefrorene Frame gelernt, das Modell ist verfügbar und der nächste
  Workflow-Schritt (Lern-Ergebnis) erscheint

#### Scenario: Zu strukturarme Fläche
- **WHEN** der Nutzer „Hintergrund lernen" auslöst und die Fläche zu wenig Struktur bietet
- **THEN** schlägt das Lernen fehl, die Infobox zeigt den Fehler an und das Lernen kann
  erneut ausgelöst werden

### Requirement: Lern-Ergebnis visualisieren
Das System SHALL nach erfolgreichem Lernen das Ergebnis visualisieren: die erkannten
Keypoints SHALL auf dem eingefrorenen Kamera-Frame eingezeichnet und dieses Bild angezeigt
werden. Die Infobox SHALL zusätzlich die Anzahl der gelernten Keypoints nennen.

#### Scenario: Keypoint-Visualisierung sichtbar
- **WHEN** ein Untergrund erfolgreich gelernt wurde und die App das Lern-Ergebnis anzeigt
- **THEN** zeigt das eingefrorene Kamera-Bild die gelernten Keypoints und die Infobox nennt
  die Keypoint-Anzahl

### Requirement: Periodischer Loss-of-Calibration-Check
Das System SHALL, sobald ein Untergrund-Modell gelernt wurde, im Messbetrieb automatisch in
regelmäßigen Abständen den aktuellen Kameraframe gegen das Modell prüfen. Der Check SHALL
dabei den Untergrund (Keypoint-Matching mit RANSAC-Homographie) verwenden und einen
Status liefern: `OK` (Kamera unverändert), `verschoben` (kritische Abweichung) oder
`n/a` (Untergrund nicht sichtbar).

#### Scenario: Prüfung bei sichtbarem Untergrund
- **WHEN** ein Untergrund-Modell vorliegt, im Messbetrieb periodisch geprüft wird und die
  Tischfläche frei sichtbar ist
- **THEN** liefert der Check den Status `OK` oder `verschoben` je nach ermittelter
  Abweichung

#### Scenario: Prüfung bei belegter Fläche
- **WHEN** im Messbetrieb periodisch geprüft wird und die Tischfläche nicht sichtbar ist
  (z. B. ein Papierblatt liegt auf)
- **THEN** liefert der Check den Status `n/a`, ohne einen Verschiebungs-Alarm auszulösen

### Requirement: Verschiebungs-Erkennung mit metrischer Schwelle
Das System SHALL eine kritische Verschiebung erkennen, wenn die aus der RANSAC-Homographie
abgeleitete Abweichung zwischen Untergrund-Modell und aktuellem Frame einen Schwellenwert
überschreitet. Der Schwellenwert SHALL so gewählt sein, dass eine Verschiebung von etwa
0,04 mm (≈ 1 Pixel bei 4K-Auflösung) als kritisch gilt. Lokale Veränderungen (z. B. neue
Löcher im Papier) SHALL den Check nicht auslösen, da sie als Ausreißer behandelt werden.

#### Scenario: Kamera verschoben
- **WHEN** sich die Kamera um mehr als die Schwelle (≈ 0,04 mm) bewegt hat und der
  Untergrund sichtbar ist
- **THEN** liefert der Check den Status `verschoben` samt Abweichung in mm

#### Scenario: Lokale Änderung löst keinen Alarm aus
- **WHEN** der Untergrund bis auf lokale Änderungen (wenige Punkte) unverändert ist
- **THEN** wird die Verschiebung weiterhin aus den konsistenten Punkten geschätzt und der
  Status bleibt `OK` oder `n/a`, ohne falschen Verschiebungs-Alarm

### Requirement: Indikator in der Menüleiste
Das System SHALL den aktuellen Check-Status in der Menüleiste anzeigen, rechtsbündig:
grün hervorgehoben bei `OK`, in Warnfarbe samt Abweichung in mm bei `verschoben`, in
neutraler Farbe bei `n/a`. Der Indikator SHALL sichtbar sein, sobald ein
Untergrund-Modell gelernt wurde. Er ist der letzte rechtsbündige Eintrag der
Menüleiste (das Kaliber-Dropdown existiert dort nicht mehr; die Kaliber-Auswahl
liegt im Messung-Dialog). Alle Texte SHALL über das Übersetzungssystem laufen.

#### Scenario: Status OK
- **WHEN** der letzte Check `OK` ergab und ein Untergrund-Modell gelernt ist
- **THEN** zeigt die Menüleiste den Zustand `OK` grün hervorgehoben an

#### Scenario: Status verschoben
- **WHEN** der letzte Check `verschoben` ergab und ein Untergrund-Modell gelernt ist
- **THEN** zeigt die Menüleiste den Zustand `verschoben` samt Abweichung in mm in Warnfarbe
  an

#### Scenario: Status n/a
- **WHEN** der letzte Check `n/a` ergab und ein Untergrund-Modell gelernt ist
- **THEN** zeigt die Menüleiste den Zustand `n/a` neutral an

#### Scenario: Kein Modell gelernt
- **WHEN** kein Untergrund-Modell gelernt ist
- **THEN** zeigt die Menüleiste keinen Kalibrier-Status an

#### Scenario: Kein Kaliber-Dropdown in der Menüleiste
- **WHEN** die Anwendung läuft und die Menüleiste angezeigt wird
- **THEN** enthält die Menüleiste kein Kaliber-Dropdown; der Kaliber-Selektor befindet
  sich ausschließlich im Messung-Dialog

### Requirement: Reine Warnung ohne Auto-Korrektur
Das System SHALL bei Status `verschoben` nur warnen; die laufende Messung SHALL unverändert
weiterlaufen und es SHALL keine automatische Korrektur der Kalibrierung oder der Messwerte
erfolgen.

#### Scenario: Messung läuft trotz Warnung weiter
- **WHEN** der Check `verschoben` meldet und Messpunkte gesetzt sind
- **THEN** bleiben die Messpunkte und Messwerte unverändert und es erscheint ausschließlich
  der Warn-Status in der Menüleiste

### Requirement: Modell-Invalidierung
Das System SHALL das gelernte Untergrund-Modell verwerfen, wenn die zugrundeliegende
Kalibrierung ungültig wird (z. B. Auflösungs-/Gerätewechsel, Reset oder Abbruch des
Kalibrier-Workflows), sodass keine Prüfung gegen ein veraltetes Modell stattfindet.

#### Scenario: Modell nach Re-Kalibrierung verworfen
- **WHEN** die Kalibrierung zurückgesetzt oder die Kamera-Konfiguration (Gerät/Auflösung)
  geändert wird
- **THEN** ist das Untergrund-Modell ungültig und es findet bis zum erneuten Durchlaufen
  des Kalibrier-Workflows keine periodische Prüfung statt