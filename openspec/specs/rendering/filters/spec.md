# Filters Specification

## Purpose

Stellt dem Nutzer einstellbare, rein anzeigebezogene per-Pixel-Bildfilter für die
Webcam-Ansicht bereit, damit Bilddetails (Schusslöcher, Kalibrierkarte) besser
beurteilt werden können, während Messung und automatische Erkennung ungefiltert
und damit unverfälscht bleiben.

## Requirements

### Requirement: Anzeige-Filter anwendbar
Das System SHALL per-Pixel-Bildfilter auf die Webcam-Ansicht anwenden, die nach der
LUT-Verzerrungskorrektur im Fragment-Shader wirken. Unterstützte Filter SHALL
mindestens umfassen: Negativ, Graustufen, Kontrast, Gamma, Helligkeit und
Sättigung. Kontrast, Gamma und Helligkeit SHALL einen neutralen Zustand haben, in
dem das Bild unverändert dargestellt wird, und über kontinuierliche Parameter
einstellbar sein (nur anzeigebezogen).

#### Scenario: Kontrast neutral wirkt nicht
- **WHEN** Kontrast auf den neutralen Wert gesetzt ist und alle übrigen Filter deaktiviert sind
- **THEN** wird das Webcam-Bild identisch zur Darstellung ohne Filter angezeigt

#### Scenario: Filter kombinierbar
- **WHEN** mehrere Filter gleichzeitig aktiv sind (z.B. Graustufen und Kontrast)
- **THEN** werden alle aktiven Filter gemeinsam auf denselben Render-Pass angewandt

### Requirement: Automation und Kalibrierung ungefiltert
Das System SHALL die automatische Schussloch-Erkennung und die Kalibrierung stets
mit dem LUT-korrigierten, ungefilterten Bild versorgen. Eine Änderung der
Anzeige-Filter SHALL das Ergebnis einer Messung oder die ermittelten Messpunkte
nicht verändern.

#### Scenario: Negativ ändert keine Messung
- **WHEN** der Negativ-Filter aktiv ist und der Nutzer einen Messpunkt per Auto-Erkennung setzt
- **THEN** wird das Schussloch-Zentrum anhand des ungefilterten Bildes bestimmt, identisch zur Erkennung ohne Filter

#### Scenario: Filter ändern bestehende Messpunkte nicht
- **WHEN** während aktiver Messung ein Anzeige-Filter geändert wird
- **THEN** bleiben alle bereits gesetzten Messpunkte an derselben Weltposition (Metrik-Werte unverändert)

### Requirement: Filterzustand orthogonal zur App-State-Maschine
Das System SHALL den Filterzustand unabhängig vom App-Zustand (IDLE, CALIBRATING,
RESULT, MEASURING) führen. Der Filter SHALL in jedem App-Zustand schalt- und
anpassbar sein, ohne den App-Zustand zu wechseln.

#### Scenario: Filter im IDLE-Zustand aktiv
- **WHEN** sich die App im IDLE-Zustand befindet (Kalibrierung ausstehend)
- **THEN** kann der Anzeige-Filter aktiviert und eingestellt werden, und die Einstellung wirkt auf die sichtbare Kalibrieransicht

### Requirement: Filter unterscheidbar zurückzusetzen
Das System SHALL einen vordefinierten Ausgangszustand („Filter aus") anbieten, der
alle Filter deaktiviert und alle Parameter auf ihre neutralen Werte setzt.

#### Scenario: Zurücksetzen auf Ausgangszustand
- **WHEN** der Nutzer die Aktion „Zurücksetzen" auslöst
- **THEN** wird das Bild ungefiltert angezeigt und der Filterzustand entspricht dem Ausgangszustand

### Requirement: Filter ein-/ausblendbar über Taste
Das System SHALL den Filterkombinationseffekt über eine Einzeltaste (F) global
umschalten; beim erneuten Aktivieren SHALL der zuletzt eingestellte Filterzustand
wiederhergestellt werden.

#### Scenario: Taste schaltet Filter um
- **WHEN** ein Filterzustand eingestellt und die Taste F gedrückt wird
- **THEN** wird die Webcam-Ansicht ungefiltert angezeigt
- **WHEN** die Taste F erneut gedrückt wird
- **THEN** wird die zuletzt eingestellte Filterkombination wieder angewandt

### Requirement: Filterzustand über Sessions erhalten
Das System SHALL die eingestellten Filterparameter (Kontrast, Gamma, Helligkeit,
Sättigung, Negativ, Graustufen) sowie die Option „Hintergrund einfärben" beim
Beenden der App im Config-Verzeichnis speichern und beim nächsten Start
wiederherstellen. Der Aktiv-Schalter der Bildfilter (`active`) und der der
Option „Hintergrund einfärben" (`tint`) SHALL beim Start der App generell
deaktiviert sein, unabhängig vom Zustand beim Beenden.

#### Scenario: Filtereinstellungen nach Neustart erhalten
- **WHEN** der Nutzer einen Filterzustand einstellt, die Filter aktiv lässt und die App beendet und neu startet
- **THEN** sind dieselben Filterparameter wiederhergestellt
- **AND** sind Bildfilter und „Hintergrund einfärben" deaktiviert, sodass das Webcam-Bild ungefiltert angezeigt wird

#### Scenario: Ungültiger gespeicherter Zustand fällt auf Neutral zurück
- **WHEN** der gespeicherte Filterzustand fehlt oder ungültige Werte enthält
- **THEN** wird der neutrale Ausgangszustand verwendet und das Bild ungefiltert angezeigt

#### Scenario: Zurücksetzen wirkt auch persistent
- **WHEN** der Nutzer die Aktion „Zurücksetzen" auslöst
- **THEN** wird der neutrale Filterzustand angewandt und auch persistent gespeichert