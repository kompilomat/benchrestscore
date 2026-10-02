# Font Scale Specification

## Purpose

Definiert die Schriftgrößen-Präsete der ImGui-Oberfläche (Normal / Large / XLarge),
die der Nutzer über den Einstellungen-Reiter (Untermenü „Schriftgröße") zur
Laufzeit wählen kann.



## Requirements

### Requirement: Schriftgrößen-Präsete
Das System SHALL drei vordefinierte Schriftgrößen-Präsete anbieten: **Normal**,
**Large** und **XLarge**. Die basis-Pixelgröße wird proportional zur
Framebuffer-Höhe bestimmt (Referenz 28 px bei 2160 px Fensterhöhe, Untergrenze
16 px) und mit einem Präset-Faktor skaliert: Normal = ×1.0, Large = ×1.25,
XLarge = ×1.5. Die Untergrenze SHALL mit dem Präset-Faktor skalieren
(`16×scale`), damit die Stufen bei jeder Fensterhöhe sichtbar unterscheidbar
bleiben. Das zuletzt gewählte Präset SHALL über die Anwendungs-Neustarts
hinweg persistiert bleiben. Beim Start SHALL das persistierte Präset aktiv
sein; fehlt der Eintrag oder ist er ungültig, SHALL das Präset "Normal" aktiv
sein. Die Wahl eines Präsets SHALL unmittelbar persistiert werden.

#### Scenario: Startwert Normal
- **WHEN** die Anwendung startet und kein gültiges persistiertes Präset vorliegt
- **THEN** ist das Präset Schriftgröße "Normal" aktiv

#### Scenario: Persistiertes Präset beim Start
- **WHEN** die Anwendung startet und zuletzt das Präset "XLarge" persistiert wurde
- **THEN** ist das Präset Schriftgröße "XLarge" aktiv

#### Scenario: Ungültiges persistiertes Präset
- **WHEN** der persistierte Wert kein bekanntes Präset ist (z.B. "huge")
- **THEN** ist das Präset Schriftgröße "Normal" aktiv

#### Scenario: Präset-Faktoren
- **WHEN** das Fenster eine gegebene Framebuffer-Höhe hat
- **THEN** ergeben sich für Normal, Large und XLarge streng aufsteigende
  Basis-Pixelgrößen im Verhältnis ×1.0 / ×1.25 / ×1.5 (Untergrenze
  `16×scale` eingerechnet)

#### Scenario: Sichtbar unterscheidbar bei kleinen Fenstern
- **WHEN** die Framebuffer-Höhe 1080 px oder kleiner ist
- **THEN** ergeben die drei Präsete klar unterscheidbare Pixelgrößen
  (z.B. 1080 px: 16/20/24 statt 16/16/16)

#### Scenario: Präset-Wahl wird persistiert
- **WHEN** der Nutzer im Einstellungen-Menü ein anderes Präset wählt
- **THEN** wirkt die Wahl unmittelbar und wird sofort persistiert, sodass sie
  einem Neustart der Anwendung erhalten bleibt

### Requirement: Persistente Speicherung der Präset-Wahl
Das System SHALL den aktuell gewählten Schriftgrößen-Präset-Key in denselben
Settings speichern, die auch Sprache und Kamera-Einstellungen persistieren
(`settings.json`). Ein Wechsel des Präsets SHALL sofort gespeichert werden (ohne
explizites Speichern oder Neustart).





#### Scenario: Wechsel wird gespeichert
- **WHEN** der Nutzer das Präset von "Normal" auf "Large" wechselt
- **THEN** enthält die Settings-Datei den Wert "large" für den Schriftgrößen-Key
  (analog zu "language"/"camera_*")



### Requirement: Umschaltung über den Einstellungen-Reiter
Das System SHALL die drei Präsete Normal / Large / XLarge im Untermenü
„Schriftgröße" des Menüleisten-Reiters „Einstellungen" anzeigen, mit dem
aktuell aktiven Präset markiert. Die Auswahl eines Präsets wirkt unmittelbar
zur Laufzeit, ohne Neustart der Anwendung.

#### Scenario: Präset im Einstellungen-Menü wechseln
- **WHEN** der Nutzer im Untermenü „Schriftgröße" des Reiters „Einstellungen"
  ein anderes Präset wählt
- **THEN** wird die Schriftgröße der gesamten Oberfläche (Menüleiste, Dialoge,
  Messwerte und die große Messwert-Variante) mit dem Präset-Faktor gerastert,
  und das gewählte Präset ist als aktiv markiert

#### Scenario: Aktives Präset markiert
- **WHEN** der Nutzer das Untermenü „Schriftgröße" öffnet
- **THEN** ist das aktuell aktive Präset erkennbar markiert (Häkchen/Radio)

### Requirement: Dialoggrößen passen zur Schrift
Das System SHALL sicherstellen, dass alle Dialoge bei jedem Präset so dimensioniert
sind, dass Inhalte vollständig sichtbar bleiben (kein abgeschnittener Text).



#### Scenario: Ergebnisdialog bei XLarge
- **WHEN** das Präset XLarge aktiv ist und der Kalibrier-Ergebnis-Dialog angezeigt wird
- **THEN** sind alle Texte und Schaltflächen vollständig sichtbar



### Requirement: Keine Rückwirkung auf Kamerabild-Overlays
Das System SHALL die Schriftgrößen-Präsete ausschließlich auf die ImGui-Oberfläche
anwenden. Texte, die direkt in das Kamerabild gerendert werden (z.B. "Warte auf
Kamera …", Kalibrier-µm-Werte), SHALL von den Präseten unverändert bleiben.



#### Scenario: Kamerabild-Overlays unverändert
- **WHEN** ein Präset gewechselt wird
- **THEN** bleiben die direkt ins Kamerabild gerenderten Texte unverändert