# UI State Specification

## Purpose

Persistiert den UI-Zustand der Overlay-Fenster (Positionen von Messung,
Bildfilter, Kamera und Vision-Konfiguration) sowie die Ablage der
ImGui-Fenster-Persistenz im Config-Verzeichnis, damit das Layout über Sessions
und Sprachwechsel hinweg stabil bleibt.

## Requirements

### Requirement: Fensterpositionen persistent speichern
Das System SHALL die Positionen der Overlay-Fenster „Messung", „Bildfilter",
„Kamera" und „Vision-Konfiguration" mit sprachunabhängigen Schlüsseln im
Config-Verzeichnis speichern und beim nächsten App-Start beim ersten Anzeigen
des jeweiligen Fensters wiederherstellen.

#### Scenario: Position nach Neustart wiederhergestellt
- **WHEN** der Nutzer das Messung-Fenster verschiebt und die App beendet
- **THEN** erscheint das Messung-Fenster beim nächsten Start an der zuletzt
  gespeicherten Position

#### Scenario: Kamera-Dialog-Position wird persistiert
- **WHEN** der Nutzer den Kamera-Dialog verschiebt und die App beendet
- **THEN** erscheint der Kamera-Dialog beim nächsten Start an der zuletzt
  gespeicherten Position

#### Scenario: Sprache wechselt, Position bleibt
- **WHEN** die UI-Sprache gewechselt wird und eine Fenster-Position gespeichert ist
- **THEN** bleibt das Fenster an der gespeicherten Position (unabhängig vom
  geänderten Fenstertitel)

#### Scenario: Nicht mehr sichtbare Position wird verworfen
- **WHEN** die gespeicherte Position außerhalb des sichtbaren Arbeitsbereichs
  liegt (z.B. nach Bildschirmwechsel)
- **THEN** wird die gespeicherte Position nicht angewendet und das Fenster
  erscheint an einer sichtbaren Standardposition

### Requirement: Fenster-Persistenz im Config-Verzeichnis
Das System SHALL die ImGui-Fenster-Persistenz (Position, Größe, Collapsed-Zustand)
im Config-Verzeichnis ablegen statt im aktuellen Arbeitsverzeichnis.

#### Scenario: INI-Datei im Config-Verzeichnis
- **WHEN** die App gestartet wird und der Nutzer ein Fenster verschiebt oder in die Leiste legt
- **THEN** wird die Persistenz-Datei im Config-Verzeichnis der App geschrieben und beim nächsten Start daraus gelesen