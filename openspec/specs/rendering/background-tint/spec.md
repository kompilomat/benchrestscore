# Background-Tint Specification

## Purpose

Anzeige-Option zur Sichtbarkeitsverbesserung: tisch-ähnliche Pixel (freier
Untergrund und Schusslöcher, die den gelernten Tisch zeigen) werden mit einer
festen homogenen Farbe gerendert, während das Papier unverändert bleibt. Reine
Anzeige — Messung und Erkennung bleiben unverfälscht.

## Requirements

### Requirement: Hintergrund-Einfärbung umschaltbar
Das System SHALL eine Anzeige-Option „Hintergrund einfärben" anbieten, die der
Nutzer über das Ansicht-Menü umschalten kann. Bei aktiver Option SHALL das System
Pixel, die dem gelernten Tisch-Untergrund entsprechen (freie Tischfläche **und**
Schusslöcher im Papier, die den Tisch sichtbar machen), mit einer festen, homogenen
Farbe rendern; die übrige Fläche (Papier) SHALL unverändert dargestellt werden.
Die Option SHALL nur verfügbar sein, wenn eine dichte Tisch-Referenz gelernt oder
wiederhergestellt wurde.

#### Scenario: Einfärben aktiviert
- **WHEN** eine dichte Tisch-Referenz vorliegt und der Nutzer die Option im Ansicht-Menü aktiviert
- **THEN** werden die tisch-ähnlichen Pixel im Live-View mit der festen Tint-Farbe angezeigt und das Papier bleibt unverändert

#### Scenario: Einfärben deaktiviert
- **WHEN** der Nutzer die Option deaktiviert
- **THEN** wird das Webcam-Bild ohne Hintergrund-Einfärbung angezeigt

#### Scenario: Keine Referenz verfügbar
- **WHEN** keine dichte Tisch-Referenz gelernt oder wiederhergestellt wurde
- **THEN** ist die Option nicht verfügbar und das Bild wird ohne Hintergrund-Einfärbung angezeigt

### Requirement: Tisch-Klassifikation aus der gelernten Referenz
Das System SHALL die Tisch-Ähnlichkeit jedes Pixels über die Distanz zur gelernten
Referenz bestimmen (lokal mittelwert-subtrahierte Farb- und Struktur-Distanz) und
die binäre Tisch-Maske über einen **statischen, festen Distanz-Schwellwert**
trennen. Der Schwellwert SHALL nicht datenabhängig aus der aktuellen Szene
abgeleitet werden — er SHALL für eine kalibrierte Session konstant bleiben, damit
Glanz-Reflexionen (z. B. ein Metall-Lineal), Fremdkörper (z. B. eine Hand) oder
Papier die Klassifikation nicht verfälschen können. Schusslöcher SHALL als
tisch-ähnlich gelten, da sie den gelernten Untergrund zeigen.

#### Scenario: Hintergrund wird eingefärbt
- **WHEN** ein Pixel dem gelernten Tisch-Untergrund entspricht und die Option aktiv ist
- **THEN** wird dieser Pixel mit der festen Tint-Farbe gerendert

#### Scenario: Loch wird eingefärbt
- **WHEN** ein Schussloch im Papier den gelernten Tisch-Untergrund sichtbar macht und die Option aktiv ist
- **THEN** wird die Lochfläche mit der festen Tint-Farbe gerendert

#### Scenario: Papier wird nicht eingefärbt
- **WHEN** die Papierfläche nicht dem gelernten Tisch-Untergrund entspricht und die Option aktiv ist
- **THEN** wird die Papierfläche unverändert dargestellt

#### Scenario: Glanz-Reflexion verfälscht die Klassifikation nicht
- **WHEN** ein Metall-Lineal Licht reflektiert (helle Glanz-Spots auf Lineal und angrenzendem Tisch) und die Option aktiv ist
- **THEN** bleiben die Glanz-Spots unverfärbt und die übrige Tischfläche wird weiterhin mit der Tint-Farbe gerendert

#### Scenario: Fremdkörper wird nicht eingefärbt
- **WHEN** ein Fremdkörper, der nicht Teil der gelernten Referenz ist, auf dem Tisch liegt und die Option aktiv ist
- **THEN** wird der Fremdkörper nicht mit der Tint-Farbe gerendert

#### Scenario: Hand wird nicht als Hintergrund klassifiziert
- **WHEN** eine Hand einen großen Teil der Szene verdeckt und die Option aktiv ist
- **THEN** wird die Hand nicht mit der Tint-Farbe gerendert

### Requirement: Maske wird periodisch nachgeführt
Das System SHALL die Tisch-Maske im Hintergrund periodisch — gedrosselt im
Render-Kreislauf (~0,3 s, `TINT_UPDATE_S`) — aus dem aktuellen, nur
LUT-korrigierten Kamera-Frame neu berechnen, solange die Option aktiv ist. Die
Berechnung SHALL in reduzierter (Referenz-)Auflösung laufen, damit sie den
Render-Loop nicht merklich belastet. Eine veraltete Maske SHALL dabei nicht die
Anzeige blockieren; ohne aktuelle Maske SHALL die Einfärbung deaktiviert sein,
bis eine neue Maske vorliegt.

#### Scenario: Maske aktualisiert sich
- **WHEN** die Option aktiv ist und die Kamera ein neues Bild mit veränderter Szene liefert
- **THEN** wird die Tisch-Maske innerhalb der Nachführ-Kadenz (~0,3 s) neu berechnet und die Anzeige entsprechend aktualisiert

#### Scenario: Keine Maske beim Einschalten
- **WHEN** die Option aktiviert wird und noch keine aktuelle Tisch-Maske berechnet wurde
- **THEN** wird das Bild ohne Einfärbung angezeigt, bis die erste Maske vorliegt

### Requirement: Messung und Erkennung unverfälscht
Das System SHALL die Hintergrund-Einfärbung ausschließlich auf die Anzeige wirken
lassen. Messwerte, Messpunkte, die Klick-Automation und die Gruppenerkennung SHALL
stets mit dem LUT-korrigierten, ungefärbten Bild arbeiten; eine Aktivierung oder
Deaktivierung der Option SHALL gesetzte Messpunkte oder Messergebnisse nicht
verändern.

#### Scenario: Einfärbung ändert keine Messung
- **WHEN** die Hintergrund-Einfärbung aktiv ist und der Nutzer einen Messpunkt setzt
- **THEN** wird der Messpunkt anhand des ungefärbten Bildes bestimmt, identisch zur Erkennung ohne Einfärbung

#### Scenario: Bestehende Punkte bleiben stabil
- **WHEN** während aktiver Messung die Hintergrund-Einfärbung umgeschaltet wird
- **THEN** bleiben alle bereits gesetzten Messpunkte an derselben Weltposition (Metrik-Werte unverändert)

### Requirement: Zustand über Sessions erhalten
Das System SHALL den eingestellten Zustand der Option (an/aus) beim Beenden der App
im Config-Verzeichnis speichern und beim nächsten Start wiederherstellen. Ein
gespeicherter Zustand mit fehlender Referenz (noch nicht gelernt) SHALL beim Start
ohne Einfärbung angewendet werden.

#### Scenario: Option nach Neustart erhalten
- **WHEN** der Nutzer die Option aktiviert, die App beendet und neu startet und eine Referenz vorliegt
- **THEN** ist die Option beim Start wieder aktiv und die Einfärbung wird angewendet

#### Scenario: Ungültiger gespeicherter Zustand
- **WHEN** der gespeicherte Zustand fehlt oder ungültige Werte enthält
- **THEN** wird die Option deaktiviert verwendet und das Bild ohne Einfärbung angezeigt