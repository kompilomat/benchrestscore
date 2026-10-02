# I18n Specification

## Purpose

Die Benutzeroberfläche der Anwendung ist vollständig übersetzbar: Deutsch und Englisch
werden unterstützt, die Sprache ist über die Menüleiste wählbar und wird persistent
gespeichert. Weitere Sprachen lassen sich ohne strukturellen Umbau ergänzen.

## Requirements

### Requirement: Übersetzungssystem mit aktiver Sprache

Das System SHALL ein Übersetzungssystem bereitstellen, das jeden User-facing-String
der Anwendung über eine Nachrichtenkennung (Msg-ID) in der aktiven Sprache liefert.
Die aktive Sprache SHALL zu einem Zeitpunkt genau eine der unterstützten Sprachen
sein. Ist ein String für die aktive Sprache nicht hinterlegt, SHALL das System auf
die deutsche Übersetzung zurückfallen; ist auch die nicht vorhanden, SHALL das System
den Fehler deutlich signalisieren statt still einen unvollständigen String zu liefern.

#### Scenario: Übersetzung in der aktiven Sprache

- **WHEN** die aktive Sprache Englisch ist und ein bekannter String angefordert wird
- **THEN** liefert das System die englische Übersetzung des Strings

#### Scenario: Fallback auf Deutsch

- **WHEN** ein String für die aktive Sprache nicht hinterlegt ist
- **THEN** liefert das System die deutsche Übersetzung des Strings

#### Scenario: Fehlende Msg-ID

- **WHEN** eine Msg-ID angefordert wird, die in keiner Sprache hinterlegt ist
- **THEN** signalisiert das System einen Fehler (z.B. Exception oder deutliche Fehlermeldung)

### Requirement: Sprachwahl in der Menüleiste

Die Menüleiste SHALL ein Sprach-Untermenü enthalten, das alle unterstützten Sprachen
als auswählbare Einträge anbietet (angezeigt in der jeweiligen Endonym-Schreibweise,
z.B. "Deutsch" und "English"). Die Auswahl SHALL die aktive Sprache sofort für die
gesamte Oberfläche wirksam machen, ohne Neustart. Das Menü SHALL die aktuell aktive
Sprache markieren.

#### Scenario: Sprache über die Menüleiste wechseln

- **WHEN** der Nutzer im Sprach-Menü "English" wählt
- **THEN** ist die aktive Sprache sofort Englisch und alle Oberflächentexte erscheinen in Englisch

#### Scenario: Aktive Sprache ist markiert

- **WHEN** das Sprach-Menü geöffnet wird
- **THEN** ist der Eintrag der aktuell aktiven Sprache als ausgewählt markiert

### Requirement: Persistenz der Sprachwahl

Das System SHALL die zuletzt gewählte Sprache über App-Neustarts hinweg speichern und
beim Start wiederherstellen. Beim ersten Start ohne gespeicherte Sprache SHALL das
System die Sprache aus der System-Locale ableiten: deutsche Locales (Beginn mit `de`)
führen zu Deutsch, alle anderen zu Englisch.

#### Scenario: Gespeicherte Sprache wird wiederhergestellt

- **WHEN** die App mit einer zuvor gewählten und gespeicherten Sprache gestartet wird
- **THEN** ist diese Sprache beim Start aktiv

#### Scenario: Erster Start ohne gespeicherte Sprache

- **WHEN** die App erstmals startet und noch keine Sprachwahl gespeichert ist
- **THEN** wird die Sprache aus der System-Locale abgeleitet (deutsch bei `de_*`, sonst englisch)

### Requirement: Vollständige Übersetzung der Oberfläche

Alle User-facing-Strings der Anwendung SHALL über das Übersetzungssystem laufen:
Menüeinträge, Dialogtitel, Buttons, Checkboxen, Slider-Labels, Tooltips, der
Messwerttext (Mitte/Außen/Kaliber) und die Kalibrier-Fehlermeldungen. Es SHALL keine
unübersetzten User-facing-Strings im Code verbleiben. Die Oberfläche SHALL in jeder
unterstützten Sprache vollständig konsistent sein: Menübezeichnungen, Dialogtitel
und Statusanzeigen erscheinen einheitlich in der aktiven Sprache, ohne gemischte
Sprachebenen.

#### Scenario: Messwerttext ist übersetzt

- **WHEN** die aktive Sprache Englisch ist und Messwerte angezeigt werden
- **THEN** erscheinen die Beschriftungen (Mitte/Außen/Kaliber) auf Englisch

#### Scenario: Kalibrier-Fehler ist übersetzt

- **WHEN** die aktive Sprache Englisch ist und eine Kalibrierung fehlschlägt
- **THEN** erscheint die Fehlermeldung auf Englisch

#### Scenario: Menübegriffe sind konsistent übersetzt

- **WHEN** die aktive Sprache Englisch ist
- **THEN** erscheinen die Menübezeichnungen als englische Entsprechungen
  (z.B. "Calibration", "Measure", "Settings" statt "Kalibrierung", "Messen",
  "Einstellungen")

### Requirement: Erweiterbarkeit um weitere Sprachen

Das System SHALL so strukturiert sein, dass eine weitere Sprache ohne Änderung der
Aufrufstruktur ergänzt werden kann: Die vollständige Übersetzung einer neuen Sprache
SHALL ausschließlich durch Hinzufügen der zugehörigen Übersetzungsdaten erfolgen.

#### Scenario: Neue Sprache wird ergänzt

- **WHEN** die Übersetzungsdaten für eine dritte Sprache vollständig hinterlegt werden
- **THEN** ist diese Sprache im Sprach-Menü wählbar und alle Strings erscheinen in ihr, ohne Code-Änderungen an Aufrufstellen

### Requirement: Übersetzung des Crop-Messung-Menüeintrags

Das System SHALL den Menüeintrag „Crop Messung" des Ansicht-Menüs über das
Übersetzungssystem liefern, einschließlich der Anzahl der aktuell gesetzten
Messpunkte als Platzhalter `{n}`. Der Eintrag SHALL in Deutsch und Englisch hinterlegt
sein und den Tastatur-Shortcut „C" anzeigen.

#### Scenario: Deutscher Menüeintrag

- **WHEN** die aktive Sprache Deutsch ist und der Übersetzungsschlüssel mit
  Punktanzahl abgerufen wird
- **THEN** liefert das System den deutschen Text einschließlich der eingefügten
  Punktanzahl

#### Scenario: Englischer Menüeintrag

- **WHEN** die aktive Sprache Englisch ist und der Übersetzungsschlüssel mit
  Punktanzahl abgerufen wird
- **THEN** liefert das System den englischen Text einschließlich der eingefügten
  Punktanzahl

### Requirement: Kalibrier-Shortcut als K

Das System SHALL den Tastatur-Shortcut zum Starten der Kalibrierung von „C" auf „K"
umstellen und die zugehörigen Menü-/Dialogtexte („Neu kalibrieren", „Kalibrieren",
Ausricht-Hinweis) entsprechend auf „K" umschreiben. Der Shortcut „C" ist dadurch für
das Einpassen der Messpunkte (Crop Messung) frei.

#### Scenario: Kalibriertexte zeigen K

- **WHEN** die aktive Sprache Deutsch oder Englisch ist
- **THEN** zeigen „Neu kalibrieren", „Kalibrieren" und der Ausricht-Hinweis den
  Shortcut „K" statt „C"
### Requirement: Übersetzung der BRSMatch-Oberfläche
Das System SHALL alle neuen User-facing-Strings des BRSMatch-Mocks über das
Übersetzungssystem liefern, in Deutsch und Englisch: den Menü-Reiter „BRSMatch",
den Verbindungs-Dialog (Titel, Base-URL, API-Key, Aktivieren, Schließen), den
Metadaten-Abschnitt im Messung-Dialog (Titel, Button „Etikett-Scan (E)") sowie die
Scan-Status-Texte (laufend, erfolgreich, fehlgeschlagen).

#### Scenario: Deutscher Menü-Reiter
- **WHEN** die aktive Sprache Deutsch ist
- **THEN** erscheint der Menü-Reiter als „BRSMatch" und die Dialog-Texte auf Deutsch

#### Scenario: Englischer Menü-Reiter
- **WHEN** die aktive Sprache Englisch ist
- **THEN** erscheinen die BRSMatch-Strings auf Englisch
