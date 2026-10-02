# Overlay Specification

## Purpose

Bietet die Bedienoberfläche der App als Dear-ImGui-Overlay im selben Fullscreen-GL-Kontext
wie der Video-Viewport, inklusive Menü, Buttons, Kaliber-Dropdown und Kalibrier-Workflow-Dialog.

## Requirements

### Requirement: ImGui-Overlay im Viewport-Kontext
Das System SHALL die Benutzeroberfläche als Overlay im selben GL-Kontext über dem
Video-Viewport darstellen, ohne ein separates Fenster oder einen verkleinerten Viewport.

#### Scenario: Overlay wird angezeigt
- **WHEN** die Anwendung läuft
- **THEN** werden UI-Elemente (Menü, Buttons) über dem Fullscreen-Video gezeichnet

#### Scenario: Overlay-Eingabe
- **WHEN** der Nutzer ein UI-Element per Maus bedient
- **THEN** wird das Ereignis an die Oberfläche weitergeleitet und nicht als Mess-/Zoom-Aktion interpretiert

### Requirement: Kaliber-Auswahl per Dropdown
Das System SHALL die Kaliber-Auswahl über ein Dropdown anbieten, das die Kalibertabelle
der App (z.B. `.177`, `.224`, `.30`) auflistet. Die Auswahl steuert den aktiven Kaliber
für Messung und Kreise.

#### Scenario: Kaliber wechseln
- **WHEN** der Nutzer im Dropdown einen anderen Kaliber wählt
- **THEN** wird der aktive Kaliber gewechselt und alle Kaliberkreise entsprechend neu berechnet

### Requirement: Menü und Buttons für Aktionen
Das System SHALL einen Menü-/Button-Zugang zu den App-Aktionen bereitstellen, darunter
Kalibrierung starten, Kalibrierung übernehmen und Automation umschalten, ohne dass
diese Aktionen eine Tastatureingabe erfordern.

#### Scenario: Kalibrierung per UI starten
- **WHEN** der Nutzer über das Menü "Kalibrieren" wählt
- **THEN** startet der Kalibriervorgang

#### Scenario: Automation umschalten
- **WHEN** der Nutzer die Automation per Button/Toggle umschaltet
- **THEN** wechselt die Automation zwischen an und aus

### Requirement: Kalibrier-Workflow-Dialog
Das System SHALL den Kalibrier-Workflow (init/compute/mapping/result) als Dialog darstellen
und Status, Fehlerwerte (AVG/VAR) sowie die A/B-Korrekturen anzeigen.

#### Scenario: Kalibrierung erfolgreich
- **WHEN** die Kalibrierung abgeschlossen ist
- **THEN** zeigt der Dialog Ergebnis, AVG/VAR und A/B-Korrekturen

#### Scenario: Kalibrierung fehlgeschlagen
- **WHEN** die Kalibrierkarte nicht erkannt wird
- **THEN** zeigt der Dialog eine Fehlermeldung und der Vorgang kann neu gestartet werden

### Requirement: Tastatur-/Maus-Fallback für bestehende Kürzel
Das System SHALL die bisherigen Tastaturkürzel (z.B. `Q` Beenden, `Space` aktiven Punkt
wechseln) weiterhin unterstützen, während sie zusätzlich über die UI erreichbar sind.

#### Scenario: Tastaturkürzel
- **WHEN** der Nutzer ein bestehendes Tastaturkürzel drückt
- **THEN** wird die entsprechende Aktion ausgeführt