# BRSMatch API Specification

## Purpose

Anbindung der BRSMatch-Veranstaltungs-API in der Benchrestscore-App: Auflösung
der Etikett-Werte (Sch-Nr, Durchgang, Stand, Zeit) in Teilnehmer- und
Disziplin-Daten, Anzeige im Messung-Dialog und Übermittlung einer Wertung samt
Framebuffer-Screenshot über die Scoring-API.

## Requirements

### Requirement: Query-API-Lookup nach Etikett-Übernahme
Das System SHALL nach der Übernahme der Etikett-Werte (VLM-Scan oder manuelle
Eingabe) bei aktiviertem BRSMatch-Modus asynchron die konfigurierte Query-API
(`GET /{event_id}/api/lookup`) mit den vier Werten (sch_nr, dg, stand, zeit)
abfragen und das Ergebnis ablegen: Teilnehmer (Startnummer, Vorname, Nachname,
Verein, Kaliber), Disziplin (Klasse, Distanz, Matches, Schüsse), Durchgang und
die Anzahl bereits vorhandener Wertungen (`existing_scores`, Integer). Während
der Abfrage SHALL der Status als laufend erkennbar sein; das Ergebnis SHALL
nur übernommen werden, wenn die Etikett-Werte seit Auslösung unverändert sind
(veraltete Antworten verwerfen). Fehler SHALL mit einem Typ unterschieden
werden: keine Belegung (404), Konsistenzfehler (409), ungültiger Token (401)
und Netz-/Serverfehler.

#### Scenario: Erfolgreiche Auflösung
- **WHEN** die Etikett-Werte übernommen wurden und die Query-API einen Teilnehmer mit Disziplin und Durchgang liefert
- **THEN** speichert das System Teilnehmer, Disziplin, Durchgang und `existing_scores` und meldet den Lookup als erfolgreich

#### Scenario: Lookup läuft
- **WHEN** die Query-API-Abfrage gestartet, aber noch nicht beantwortet ist
- **THEN** zeigt das System den Lookup als laufend an

#### Scenario: Keine Belegung
- **WHEN** die Query-API mit 404 antwortet (keine Belegung für Stand/Zeit)
- **THEN** meldet das System einen Lookup-Fehler vom Typ „keine Belegung" und übernimmt keine Teilnehmerdaten

#### Scenario: Konsistenzfehler
- **WHEN** die Query-API mit 409 antwortet (Sch-Nr oder Durchgang passen nicht zur Belegung)
- **THEN** meldet das System einen Lookup-Fehler vom Typ „Konsistenz" und übernimmt keine Teilnehmerdaten

#### Scenario: Ungültiger Token
- **WHEN** die Query-API mit 401 antwortet
- **THEN** meldet das System einen Lookup-Fehler vom Typ „Token"

#### Scenario: Netz-/Serverfehler
- **WHEN** die Query-API nicht erreichbar ist oder mit einem Serverfehler antwortet
- **THEN** meldet das System einen Lookup-Fehler vom Typ „Netz/Server"

#### Scenario: Veraltete Antwort
- **WHEN** ein laufender Lookup beendet wird, nachdem der Nutzer andere Etikett-Werte übernommen hat
- **THEN** verwirft das System die Antwort und zeigt kein Teilnehmer-Ergebnis

### Requirement: Teilnehmer-Info im Messung-Dialog anzeigen
Das System SHALL nach erfolgreichem Lookup im Messung-Dialog den truncated
Nach- und Vornamen sowie das Kaliber des Teilnehmers anzeigen. Bei
`existing_scores == 0` SHALL die Anzeige grün erfolgen (kein Wertungsergebnis
vorhanden). Bei `existing_scores > 0` SHALL Nach- und Vorname sowie Kaliber
orange angezeigt werden (sofort erkennbar, dass ein Ergebnis vorliegt). Bei
Lookup-Fehler SHALL eine Fehlermeldung erscheinen; grüne Teilnehmer-Info und
Wertung-Aktion SHALL dann nicht verfügbar sein.

#### Scenario: Kein vorhandenes Wertungsergebnis
- **WHEN** der Lookup erfolgreich ist und `existing_scores == 0`
- **THEN** zeigt das System Nach- und Vorname (truncated) sowie Kaliber in grün an

#### Scenario: Vorhandene Wertungsergebnisse
- **WHEN** der Lookup erfolgreich ist und `existing_scores > 0`
- **THEN** zeigt das System Nach- und Vorname sowie Kaliber in orange an

#### Scenario: Lookup-Fehler
- **WHEN** der Lookup fehlgeschlagen ist
- **THEN** zeigt das System eine Fehlermeldung und weder grüne Teilnehmer-Info noch eine Wertung-Aktion

### Requirement: Wertung mit Screenshot übermitteln
Das System SHALL über einen „Wertung"-Button eine Wertung über die Scoring-API
(`POST /{event_id}/api/measurements`) übermitteln. Der Button SHALL nur
erscheinen, wenn der Lookup erfolgreich ist und ein Messwert vorliegt
(`Mitte` ≥ 0). Ein Klick SHALL eine vollständige, unbeschnittene Kopie des
Framebuffers (Kamera-/LUT-Bild, Messmarker, Messung-Dialog und die
Menüleiste) erstellen: Das Bild wird Seitenverhältnis erhaltend mit einer
kantengetreuen Interpolation (Lanczos) auf 1280×720 skaliert (bei
abweichendem Seitenverhältnis zentriert auf schwarzer Leinwand), als JPEG mit
Qualität 90 encodiert und zusammen mit den Etikett-Werten und dem Gruppenmaß
asynchron hochgeladen (Multipart-Feld `screenshot`, Content-Type
`image/jpeg`). Ein Ausschnitt (z. B. der Menüleiste) SHALL am Screenshot nicht
erfolgen. Während des Uploads SHALL die UI bedienbar bleiben; ein laufender
Upload SHALL einen zweiten Upload verhindern. Erfolg und Fehlschlag SHALL
angezeigt werden.

#### Scenario: Erfolgreicher Upload mit Screenshot
- **WHEN** der Nutzer bei aufgelöstem Etikett und vorhandenem Messwert „Wertung" betätigt und die Scoring-API die Messung annimmt
- **THEN** wird ein 1280×720-JPEG (Qualität 90; komplettes Fenster inkl. Menüleiste, Kamera-Bild, Messmarker, Messung-Dialog) samt Gruppenmaß und Etikett-Werten übermittelt und das System meldet den Erfolg

#### Scenario: Screenshot zeigt das vollständige Fenster
- **WHEN** eine Wertung mit Screenshot übermittelt wird
- **THEN** enthält das JPEG den oberen Rand des Framebuffers ohne Ausschnitt (Menüleiste vollständig sichtbar, kein beschnittener Streifen)

#### Scenario: Kein Messwert
- **WHEN** kein Messwert vorliegt
- **THEN** erscheint der „Wertung"-Button nicht

#### Scenario: Laufender Upload
- **WHEN** ein Upload läuft
- **THEN** verhindert das System einen zweiten Upload derselben Etikett-Werte

#### Scenario: Fehlgeschlagener Upload
- **WHEN** die Scoring-API die Übermittlung ablehnt oder nicht erreichbar ist
- **THEN** meldet das System einen Upload-Fehler und die Metadaten bleiben für einen erneuten Versuch erhalten

### Requirement: Überschreiben nur nach Bestätigung
Das System SHALL bei `existing_scores > 0` vor dem Upload einen
Bestätigungsdialog öffnen, der Vor- und Nachname, Durchgang, Stand und Uhrzeit
zeigt und den Nutzer bestätigen lässt, dass das vorhandene Wertungsergebnis
überschrieben wird. Erst nach Bestätigung SHALL der Upload ausgelöst werden;
bei Abbruch SHALL kein Upload erfolgen.

#### Scenario: Bestätigung
- **WHEN** `existing_scores > 0` ist und der Nutzer die Überschreibung im Dialog bestätigt
- **THEN** wird die Wertung mit Screenshot übermittelt

#### Scenario: Abbruch
- **WHEN** `existing_scores > 0` ist und der Nutzer den Bestätigungsdialog abbricht
- **THEN** wird kein Upload ausgelöst

### Requirement: Metadaten nach erfolgreichem Upload zurücksetzen
Das System SHALL nach erfolgreichem Upload die BRSMatch-Metadaten im
Messung-Dialog zurücksetzen (Etikett-Werte, Lookup-Ergebnis und -Status,
Wertung-Status), damit nicht irrtümlich eine zweite Wertung für dieselben
Etikett-Werte hochgeladen wird. Eine erneute Wertung SHALL erst nach einer
neuen Etikett-Übernahme möglich sein.

#### Scenario: Erfolg setzt Metadaten zurück
- **WHEN** ein Upload erfolgreich abgeschlossen ist
- **THEN** sind Etikett-Werte, Lookup-Ergebnis und Wertung-Status zurückgesetzt und der „Wertung"-Button verschwindet

#### Scenario: Erneute Wertung erfordert neue Übernahme
- **WHEN** die Metadaten zurückgesetzt sind
- **THEN** ist eine weitere Wertung erst nach einer neuen Etikett-Übernahme (Scan oder manuell) möglich

### Requirement: Zeit-Wert in kanonischer HH:MM-Form an die API senden
Das System SHALL den Zeit-Wert (`zeit`) der Etikett-Werte vor jedem Call der
BRSMatch-Veranstaltungs-API (Query-API-Lookup und Scoring-API-Übermittlung)
auf die kanonische, null-gestützte `HH:MM`-Form mit Leading Zero normalisieren
(z. B. `9:05` → `09:05`) und diesen normalisierten Wert an die API senden.
Beide Quellen der Etikett-Werte (manuelle Eingabe und VLM-Scan) SHALL über
dieselbe Normalisierung laufen. Die Anzeige, Validierung und Übernahme der
Etikett-Werte in der App bleiben von der Normalisierung unberührt (es wird
weiterhin der übernommene Wert angezeigt). Zeit-Werte, die nicht als
`H:MM`-Uhrzeit interpretierbar sind (z. B. fehlende Minute, Stunden- oder
Minutenwert außerhalb gültiger Bereiche), SHALL clientseitig als Fehler
verworfen werden und SHALL keine Anfrage an die API senden.

#### Scenario: Manuelle Eingabe ohne Leading Zero
- **WHEN** der Nutzer ein Etikett mit der Zeit `9:05` übernimmt und BRSMatch aktiv ist
- **THEN** fragt das System die Query-API mit `zeit=09:05` ab und löst die Belegung auf

#### Scenario: VLM-Scan ohne Leading Zero
- **WHEN** der Etikett-Scan die Zeit `7:30` liefert
- **THEN** fragt das System die Query-API mit `zeit=07:30` ab

#### Scenario: Null-gestützter Wert bleibt unverändert
- **WHEN** der Zeit-Wert des Etiketts bereits `19:00` ist
- **THEN** sendet das System `zeit=19:00` unverändert an die API

#### Scenario: Wertung mit normalisierter Zeit
- **WHEN** der Nutzer eine Wertung übermittelt, deren Etikett die Zeit `8:15` trägt
- **THEN** enthält die Scoring-API-Anfrage das Feld `zeit=08:15`

#### Scenario: Nicht interpretierbarer Zeit-Wert
- **WHEN** ein Zeit-Wert, der nicht als gültige `H:MM`-Uhrzeit interpretierbar ist (z. B. `9:75`), den API-Client erreicht
- **THEN** meldet das System einen clientseitigen Fehler und sendet keine Anfrage an die API