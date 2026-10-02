# Camera Specification

## Purpose

Ermöglicht die Konfiguration der Videoquelle (Gerät, Auflösungs-Preset, Bildrotation)
über den „Kamera"-Dialog unter dem Menüleisten-Reiter „Einstellungen". Änderungen
werden sofort zur Laufzeit angewandt (Kamera-Neustart) und persistent gespeichert.

## Requirements

### Requirement: Kamera-Dialog mit Geräte- und Auflösungs-Auswahl
Das System SHALL die Kamera-Einstellungen in einem „Kamera"-Dialog anbieten,
der über den Menüleisten-Reiter „Einstellungen" (Eintrag „Kamera") geöffnet
wird. Der Dialog SHALL die aktuell angeschlossenen Video-Capture-Geräte
(z.B. `/dev/video0`, `/dev/video1`) zur Auswahl anbieten und ein
Auflösungs-Preset auswählbar machen. Geräte-Nodes ohne nutzbare
Capture-Formate (z.B. reine Metadata-/Control-Nodes einer USB-Kamera) SHALL
nicht in der Auswahl erscheinen. Ist kein Video-Gerät auffindbar, SHALL der
Dialog dennoch geöffnet werden können und das zuletzt gewählte Gerät als
Eintrag führen. Der Dialog SHALL ein nicht-modales Overlay-Fenster sein, dessen
Position persistent gespeichert und wiederhergestellt wird.

#### Scenario: Kamera-Dialog öffnen
- **WHEN** der Nutzer im Reiter „Einstellungen" den Eintrag „Kamera" wählt
- **THEN** öffnet sich der Kamera-Dialog und die Geräte-Auswahl sowie die
  Auflösungs-Auswahl sind sichtbar

#### Scenario: Metadata-Node wird ausgeblendet
- **WHEN** ein `/dev/video*`-Node keine nutzbaren Capture-Formate bietet (Metadata-/Control-Node)
- **THEN** erscheint dieser Node nicht in der Geräte-Auswahl

#### Scenario: Kein Gerät gefunden
- **WHEN** unter `/dev/` keine Video-Geräte auffindbar sind
- **THEN** zeigt die Geräte-Auswahl ausschließlich das zuletzt konfigurierte
  Gerät und der Dialog bleibt bedienbar

#### Scenario: Dialog-Position bleibt erhalten
- **WHEN** der Nutzer den Kamera-Dialog verschiebt und die App beendet
- **THEN** erscheint der Dialog beim nächsten Start an der zuletzt gespeicherten
  Position

### Requirement: Auflösung nur über unterstützte Presets wählbar
Das System SHALL die Auflösungs-Auswahl auf Presets beschränken, die das gewählte
Gerät tatsächlich unterstützt. Kandidaten-Presets SHALL mindestens umfassen
`1080p30`, `1080p60`, `4K30` und `4K60`; zusätzlich SHALL ein `720p30`-Fallback-
Preset angeboten werden, wenn das Gerät keines der höheren Presets unterstützt.
Nicht unterstützte Presets SHALL in der Auswahl nicht erscheinen; die Auswahl
SHALL nie leer sein.

#### Scenario: Gerät unterstützt 4K30 und 1080p30
- **WHEN** das gewählte Gerät 4K30 und 1080p30, aber nicht 4K60 oder 1080p60 unterstützt
- **THEN** zeigt die Auflösungs-Auswahl nur die Presets 4K30 und 1080p30

#### Scenario: Gerät ohne höhere Auflösungen
- **WHEN** das gewählte Gerät weder 1080p noch 4K unterstützt
- **THEN** zeigt die Auflösungs-Auswahl mindestens das Preset 720p30

#### Scenario: Nicht unterstütztes gespeichertes Preset
- **WHEN** ein gespeichertes Preset am aktuell gewählten Gerät nicht unterstützt wird
- **THEN** wird ein unterstütztes Preset als aktiv gesetzt und angezeigt

### Requirement: 4K-Default wenn verfügbar
Das System SHALL ohne gespeicherte Auflösungs-Wahl ein 4K-Preset als Standard
verwenden, sofern das aktive Gerät 4K unterstützt. Steht kein 4K-Preset zur
Verfügung, SHALL das erste unterstützte Preset als Default dienen. Wird ein
nicht unterstütztes Preset angewandt oder nachgeladen, SHALL ebenfalls ein
unterstützter Default (4K bevorzugt) gewählt werden.

#### Scenario: Erststart wählt 4K
- **WHEN** keine Auflösung gespeichert ist und das Gerät 4K unterstützt
- **THEN** wird ein 4K-Preset als aktiv gesetzt und angezeigt

#### Scenario: Kein 4K am Gerät
- **WHEN** keine Auflösung gespeichert ist und das Gerät kein 4K unterstützt
- **THEN** wird das erste unterstützte Preset als aktiv gesetzt und angezeigt

### Requirement: Sofortige Anwendung der Kamera-Einstellungen
Das System SHALL Änderungen an Gerät oder Auflösung sofort zur Laufzeit
anwenden: die Kamera wird mit den neuen Einstellungen neu gestartet, ohne dass ein
App-Neustart oder ein Bestätigungsdialog nötig ist.

#### Scenario: Auflösung während der Messung ändern
- **WHEN** der Nutzer das Auflösungs-Preset ändert
- **THEN** zeigt der Viewport ab dem nächsten Frame das Bild in der neuen Auflösung

#### Scenario: Gerätewechsel
- **WHEN** der Nutzer ein anderes Video-Gerät auswählt
- **THEN** wird das Bild der neuen Videoquelle angezeigt

### Requirement: Kalibrierung und Messzustand bei Kamera-Wechsel zurücksetzen
Das System SHALL beim Wechsel von Gerät oder Auflösung den App-Zustand auf den
Ausgangszustand (IDLE) zurücksetzen und eine bestehende Kalibrierung sowie alle
Messpunkte verwerfen, da die Kalibrierung an die Auflösung der Videoquelle
gebunden ist.

#### Scenario: Auflösungswechsel verwirft Messpunkte
- **WHEN** während aktiver Messung das Auflösungs-Preset geändert wird
- **THEN** sind alle Messpunkte entfernt und der App-Zustand ist IDLE

#### Scenario: Gleiche Einstellungen erneut angewandt
- **WHEN** Gerät und Auflösung unverändert erneut angewandt werden
- **THEN** bleiben Kalibrierung und Messzustand erhalten

### Requirement: Persistenz der Kamera-Einstellungen
Das System SHALL die gewählten Kamera-Einstellungen (Gerät, Auflösungs-Preset)
persistent speichern und beim nächsten App-Start wiederherstellen.

#### Scenario: Einstellungen bleiben nach Neustart erhalten
- **WHEN** der Nutzer Gerät und Preset wählt und die App danach neu startet
- **THEN** startet die Kamera mit den zuletzt gewählten Einstellungen

### Requirement: Bildrotation einstellbar (0°/180°)
Das System SHALL die Bildrotation der Kamera im Kamera-Dialog (Reiter
„Einstellungen") auf 0° oder 180° einstellbar machen. Die Rotation SHALL den
GStreamer-`videoflip` der Pipeline steuern (rotate-0 bzw. rotate-180). Ohne
gespeicherte Wahl SHALL die Rotation 180° betragen (bisheriges Verhalten,
Kamera hängt auf dem Kopf).

#### Scenario: Rotation im Kamera-Dialog wählbar
- **WHEN** der Nutzer den Kamera-Dialog (Reiter „Einstellungen") öffnet
- **THEN** ist die Rotation als Auswahl mit den Optionen 0° und 180° sichtbar
  und zeigt den aktuell aktiven Wert

#### Scenario: Rotation wirkt sofort
- **WHEN** der Nutzer die Rotation von 180° auf 0° (oder umgekehrt) umstellt
- **THEN** wird die Kamera mit der neuen Rotation neu gestartet und der Viewport
  zeigt das Bild ab dem nächsten Frame korrekt ausgerichtet

#### Scenario: Default bei Erststart
- **WHEN** keine Rotation gespeichert ist und die App startet
- **THEN** ist die Rotation 180° aktiv

### Requirement: Rotation-Änderung setzt Messzustand zurück
Das System SHALL beim Wechsel der Bildrotation den App-Zustand auf IDLE
zurücksetzen und eine bestehende Kalibrierung sowie alle Messpunkte verwerfen,
da die Kalibrierung an die Bildorientierung gebunden ist (Raster-Sortierung ab
der Top-Left-Ecke). Unveränderte Einstellungen erneut angewandt SHALL den
Messzustand erhalten.

#### Scenario: Rotationswechsel verwirft Messpunkte
- **WHEN** während aktiver Messung die Rotation von 180° auf 0° geändert wird
- **THEN** sind alle Messpunkte entfernt und der App-Zustand ist IDLE

#### Scenario: Gleiche Rotation erneut angewandt
- **WHEN** die aktive Rotation unverändert erneut angewandt wird
- **THEN** bleiben Kalibrierung und Messzustand erhalten

### Requirement: Persistenz der Rotation
Das System SHALL die gewählte Bildrotation persistent speichern und beim nächsten
App-Start wiederherstellen. Fehlt der Wert in den gespeicherten Einstellungen,
SHALL 180° als Default gelten.

#### Scenario: Rotation bleibt nach Neustart erhalten
- **WHEN** der Nutzer die Rotation auf 0° stellt und die App danach neu startet
- **THEN** startet die Kamera mit Rotation 0°

#### Scenario: Alte Settings ohne Rotations-Key
- **WHEN** eine bestehende `settings.json` ohne Rotations-Wert geladen wird
- **THEN** wird die Rotation 180° verwendet und bestehende Kalibrierung/Messzustand
  bleiben unangetastet