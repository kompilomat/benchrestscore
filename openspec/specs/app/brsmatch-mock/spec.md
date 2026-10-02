# BRSMatch Mock Specification

## Purpose

BRSMatch-Mock für Benchrestscore: Verbindungskonfiguration zu einem
BRSMatch-Ranglistensystem (Base-URL, API-Key, Aktivieren), das Auslesen der
Etikett-Metadaten (Durchgang, Schützennummer, Schießstand, Startzeit) per
VLM-Erkennung aus dem Kamerabild und deren Anzeige im Mess-Dialog. Die echte
BRSMatch-API-Interaktion ist ein separates, späteres Proposal.

## Requirements

### Requirement: BRSMatch-Verbindungskonfiguration persistieren
Das System SHALL eine BRSMatch-Verbindungskonfiguration mit Base-URL, API-Key,
Event-ID und einem Aktivieren-Schalter (bool) verwalten und persistent in den
App-Settings (`brsmatch`-Block) speichern. Die Konfiguration SHALL beim Start
aus den Settings geladen werden; beim ersten Start ohne gespeicherten Block
SHALL der Aktivieren-Schalter deaktiviert sein. Die Event-ID SHALL eine
Ganzzahl sein und bezeichnet die BRSMatch-Veranstaltung, gegen die sich alle
API-Anfragen richten.

#### Scenario: Konfiguration speichern
- **WHEN** der Nutzer Base-URL, API-Key, Event-ID und den Aktivieren-Schalter setzt
- **THEN** wird der `brsmatch`-Block in den App-Settings gespeichert

#### Scenario: Konfiguration beim Start laden
- **WHEN** die App startet und ein gespeicherter `brsmatch`-Block vorhanden ist
- **THEN** werden Base-URL, API-Key, Event-ID und Aktivieren-Zustand daraus geladen

#### Scenario: Erster Start ohne Konfiguration
- **WHEN** die App erstmals startet und kein `brsmatch`-Block gespeichert ist
- **THEN** ist der Aktivieren-Schalter deaktiviert

#### Scenario: Ungültige Event-ID
- **WHEN** im `brsmatch`-Block eine fehlende oder ungültige Event-ID gespeichert ist
- **THEN** lädt das System den Block mit leerer Event-ID und der Lookup kann nicht ausgeführt werden

### Requirement: BRSMatch-Modus-Aktivierung
Das System SHALL den BRSMatch-Modus nur bei gesetztem Aktivieren-Schalter als
aktiv betrachten. Nur im aktiven BRSMatch-Modus SHALL der Etikett-Scan im
Mess-Dialog verfügbar sein.

#### Scenario: Aktiviert
- **WHEN** der Aktivieren-Schalter gesetzt ist
- **THEN** ist der BRSMatch-Modus aktiv und der Etikett-Scan verfügbar

#### Scenario: Deaktiviert
- **WHEN** der Aktivieren-Schalter nicht gesetzt ist
- **THEN** ist der BRSMatch-Modus inaktiv und der Etikett-Scan nicht verfügbar

### Requirement: Etikett-Scan über VLM
Das System SHALL beim Auslösen des Etikett-Scans das aktuelle Kamerabild an den
konfigurierten VLM-Endpunkt senden und daraus die Etikett-Werte `zeit`, `stand`,
`dg` und `sch_nr` extrahieren. `zeit` SHALL eine Uhrzeit im Format `HH:MM` sein;
`stand`, `dg` und `sch_nr` SHALL Ganzzahlen sein. Die Erkennung SHALL
`response_format` (JSON-Schema) verwenden und die Werte strukturiert liefern.

#### Scenario: Erfolgreicher Scan
- **WHEN** der Nutzer den Etikett-Scan auslöst und der Sticker lesbar ist
- **THEN** liefert das System `zeit`, `stand`, `dg` und `sch_nr` mit korrekten
  Typen (Uhrzeit-String, Ganzzahlen)

#### Scenario: Scan ohne Kamerabild
- **WHEN** der Etikett-Scan ausgelöst wird und kein Kamerabild verfügbar ist
- **THEN** meldet das System einen Scan-Fehler und liefert keine Metadaten

#### Scenario: Scan mit leerer Modell-Antwort
- **WHEN** der VLM-Endpunkt eine leere oder ungültige Antwort liefert
- **THEN** meldet das System einen Scan-Fehler und zeigt keine Metadaten an

### Requirement: Scan-Ergebnis anzeigen
Das System SHALL das Ergebnis des letzten Etikett-Scans oder der letzten
manuellen Etikett-Eingabe im Mess-Dialog im Abschnitt „Metadaten" anzeigen: die
vier Werte (Zeit, Stand, DG, Sch-Nr) und bei einem Fehlschlag eine Fehlermeldung.
Der Scan-Status SHALL einen laufenden, erfolgreichen oder fehlgeschlagenen Scan
unterscheidbar machen.

#### Scenario: Werte anzeigen
- **WHEN** ein Etikett-Scan oder eine manuelle Eingabe erfolgreich war
- **THEN** zeigt der Mess-Dialog die vier gelesenen bzw. eingegebenen Werte an

#### Scenario: Fehler anzeigen
- **WHEN** ein Etikett-Scan fehlgeschlagen ist
- **THEN** zeigt der Mess-Dialog eine Fehlermeldung an

### Requirement: Manuelle Etikett-Eingabe
Das System SHALL eine manuelle Erfassung der Etikett-Werte als Fallback zum
VLM-Scan anbieten. Im Metadaten-Abschnitt des Mess-Dialogs SHALL neben dem
automatischen Etikett-Scan eine manuelle Eingabe verfügbar sein. Die manuelle
Eingabe SHALL einen Dialog mit Eingabefeldern für Sch-Nr, DG, Stand und Zeit
öffnen sowie eine Speichern- und eine Schließen-Funktion bieten. Zeit SHALL eine
Uhrzeit im Format `HH:MM` sein; Stand, DG und Sch-Nr SHALL Ganzzahlen sein. Beim
Speichern SHALL das System die Werte strikt validieren; bei ungültigen Werten
SHALL das System einen Fehlerhinweis anzeigen und keine Werte übernehmen.

Der Dialog SHALL vollständig per Tastatur bedienbar sein: Beim Öffnen SHALL der
Eingabefokus automatisch im ersten Feld liegen. Mit Tab SHALL der Nutzer den
Fokus zwischen den vier Feldern und den Buttons des Dialogs wechseln. Enter
innerhalb eines Eingabefelds SHALL denselben Speichern-Pfad auslösen wie der
Speichern-Button, inklusive strikter Validierung; bei ungültigen Werten SHALL
der Dialog geöffnet bleiben und den Fehlerhinweis anzeigen. Escape SHALL den
Dialog ohne Übernahme der Werte schließen (Regel siehe Capability `app/input`).

#### Scenario: Manuelle Eingabe übernehmen
- **WHEN** der Nutzer gültige Werte eingegeben und Speichern betätigt
- **THEN** übernimmt das System die Werte wie nach einem erfolgreichen Etikett-Scan

#### Scenario: Manuelle Eingabe mit ungültigen Werten
- **WHEN** der Nutzer ungültige Werte eingibt (Zeit nicht `HH:MM` oder Werte
  nicht ganzzahlig) und Speichern betätigt
- **THEN** zeigt das System einen Fehlerhinweis und übernimmt keine Werte

#### Scenario: Dialog schließen ohne Speichern
- **WHEN** der Nutzer den Dialog über Schließen verlässt
- **THEN** übernimmt das System keine Werte

#### Scenario: Manuelle Eingabe im inaktiven BRSMatch-Modus
- **WHEN** der BRSMatch-Modus nicht aktiviert ist
- **THEN** ist die manuelle Etikett-Eingabe nicht verfügbar

#### Scenario: Auto-Fokus im ersten Feld
- **WHEN** der Nutzer den Dialog öffnet
- **THEN** liegt der Eingabefokus automatisch im ersten Feld (DG), ohne dass der
  Nutzer klicken muss

#### Scenario: Tab-Wechsel zwischen den Feldern
- **WHEN** der Dialog offen ist und der Nutzer Tab drückt
- **THEN** wechselt der Eingabefokus zum nächsten Feld bzw. Button des Dialogs,
  sodass alle vier Felder nacheinander per Tab erreicht werden

#### Scenario: Enter speichert
- **WHEN** der Dialog offen ist, gültige Werte eingegeben sind und der Nutzer
  Enter innerhalb eines Eingabefelds drückt
- **THEN** übernimmt das System die Werte wie nach einem erfolgreichen Etikett-Scan
  (gleicher Pfad wie der Speichern-Button)

#### Scenario: Enter mit ungültigen Werten
- **WHEN** der Dialog offen ist, ungültige Werte eingegeben sind und der Nutzer
  Enter innerhalb eines Eingabefelds drückt
- **THEN** zeigt das System einen Fehlerhinweis, der Dialog bleibt geöffnet und
  es werden keine Werte übernommen

### Requirement: Gemeinsame Übernahme der Etikett-Werte
Das System SHALL die Etikett-Werte aus VLM-Scan und manueller Eingabe über einen
gemeinsamen Übernahme-Schritt in das Ergebnis-Objekt übernehmen. Dieser
Übernahme-Schritt SHALL der Integrationspunkt für eine spätere BRSMatch-
Veranstaltungs-API sein (Anfrage mit den übernommenen Werten; Ergänzung des
Ergebnisses z.B. um Teilnehmerdaten). Solange die API nicht angebunden ist,
bleibt das übernommene Ergebnis auf die vier Etikett-Werte beschränkt.

#### Scenario: Scan und manuelle Eingabe nutzen denselben Übernahme-Schritt
- **WHEN** ein VLM-Scan oder eine manuelle Eingabe erfolgreich abgeschlossen ist
- **THEN** übernimmt das System die Werte über denselben Übernahme-Schritt in das
  Ergebnis-Objekt
