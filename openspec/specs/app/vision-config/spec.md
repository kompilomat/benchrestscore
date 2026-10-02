# Vision-Config Specification

## Purpose

Konfiguriert den OpenAI-kompatiblen Vision-Endpunkt, den die Gruppenerkennung für die
automatische Loch-Erkennung verwendet — persistent in den App-Settings und über eine
Konfigurationsmaske in der Anwendung bedienbar.

## Requirements

### Requirement: Vision-Endpunkt konfigurierbar
Das System SHALL einen OpenAI-kompatiblen Vision-Endpunkt über drei Einstellungen
konfigurierbar machen: Base-URL, Modell-Name und API-Key. Die Einstellungen SHALL
persistent in der App-Settings-Datei (`settings.json`, XDG-Konvention) gespeichert werden
und SHALL über Umgebungsvariablen (`BRS_VISION_BASE_URL`, `BRS_VISION_MODEL`,
`BRS_VISION_API_KEY`) übersteuerbar sein. Enthält die Settings-Datei keinen
`vision`-Block, SHALL die Vision-Erkennung als „nicht konfiguriert" gelten (neutrale,
leere Defaults ohne Anbieter- oder Modellnamen im ausgelieferten Code); die
Gruppenerkennung fällt dann auf den reinen CV-Pfad zurück. Ein explizit leerer
Base-URL-Wert (oder leeres Modell) im `vision`-Block SHALL ebenfalls als
„nicht konfiguriert" gelten.

#### Scenario: Konfiguration gespeichert
- **WHEN** der Nutzer Base-URL, Modell und API-Key einträgt und speichert
- **THEN** werden die Werte persistent in `settings.json` abgelegt und bei erneutem Start geladen

#### Scenario: Umgebungsvariablen überschreiben
- **WHEN** `BRS_VISION_BASE_URL` und `BRS_VISION_MODEL` gesetzt sind
- **THEN** haben diese gegenüber den gespeicherten Settings Vorrang

#### Scenario: Default ohne Settings
- **WHEN** die Settings-Datei keinen `vision`-Block enthält und keine
  Vision-Umgebungsvariablen gesetzt sind
- **THEN** gilt die Vision-Erkennung als nicht konfiguriert und die
  Gruppenerkennung nutzt den reinen CV-Pfad

#### Scenario: Explizit deaktiviert
- **WHEN** der `vision`-Block einen leeren Base-URL-Wert oder ein leeres Modell enthält
- **THEN** gilt die Vision-Erkennung als nicht konfiguriert und die Gruppenerkennung nutzt den reinen CV-Pfad

### Requirement: Konfigurationsmaske in der App
Das System SHALL im Einstellungen-Menü einen Eintrag „Vision-Konfiguration" anbieten,
der ein Fenster mit Feldern für Base-URL, Modell-Name und API-Key (maskierte Eingabe)
sowie Buttons „Speichern" und „Verbindung testen" öffnet. Die Labels SHALL links und
die Eingabefelder rechts stehen (einheitliche Label-Spalte). Das Fenster SHALL sich
automatisch an seinen Inhalt anpassen, sodass alle Bedienelemente — einschließlich
der Button-Reihe — bei jedem Schriftgrößen-Präset vollständig sichtbar sind, und
lange Base-URLs vollständig lesbar bleiben. Die Breite der Eingabefelder SHALL sich
an die Länge des jeweils eingegebenen Inhalts und das aktive Schriftgrößen-Präset
anpassen, sodass der eingegebene Text (insbesondere die Base-URL) bei jedem Präset
vollständig ohne horizontales Scrollen lesbar bleibt; alle Felder eines Dialogs
SHALL dieselbe Breite besitzen, und leere bzw. kurze Werte SHALL eine Mindestbreite
haben, die dem Standard-Aussehen entspricht. Die Gesamtbreite des Dialogs
(Label-Spalte, Felder, Fenster-Rahmen) SHALL auf 90 % der Viewport-Breite begrenzt
sein; ist der eingegebene Inhalt breiter, wird die Feldbreite auf die daraus
resultierende Obergrenze reduziert und der Text ist im Feld horizontal scrollbar.
Der Test-Button SHALL einen minimalen Anfrage-Call mit dem aktuellen Kamerabild an
den durch die **derzeit eingegebenen** Feldwerte angegebenen Endpunkt ausführen,
ohne diese zuvor persistent zu speichern, und das Ergebnis (Verbindung ok /
Fehlertyp) in einer prominenten Statuszeile anzeigen. Der Anfrage-Call SHALL
asynchron in einem Hintergrund-Thread laufen, ohne die Benutzeroberfläche zu
blockieren; während des Laufs SHALL der Test-Button deaktiviert sein und ein
Hinweis auf den laufenden Test angezeigt werden. Das Ergebnis wird nach Abschluss
angezeigt; Ergebnisse, die zu geänderten Eingaben nicht mehr gehören (Feld-Änderung
oder neuer Test während des Laufs), SHALL verworfen werden. Die Statuszeile und der
Hinweis SHALL gelöscht werden, sobald ein Feld im Dialog geändert wird.

#### Scenario: Verbindung erfolgreich
- **WHEN** der Nutzer gültige Werte eingetragen und „Verbindung testen" betätigt
- **THEN** wird „Verbindung ok" angezeigt

#### Scenario: Verbindung fehlgeschlagen
- **WHEN** der Endpunkt nicht erreichbar ist oder einen Fehler liefert
- **THEN** wird eine Fehlermeldung mit dem Fehlertyp angezeigt (z.B. ungültige Antwort, Netzwerkfehler)

#### Scenario: Labels links, Felder rechts
- **WHEN** die Vision-Konfigurationsmaske geöffnet ist
- **THEN** stehen die Labels (Base-URL, Modell, API-Key) linksbündig und die Eingabefelder rechts davon ausgerichtet, breit genug für lange URLs

#### Scenario: Feldbreite wächst mit dem Inhalt
- **WHEN** der Nutzer einen Wert einträgt, dessen Textbreite die Standard-Feldbreite überschreitet
- **THEN** wächst die Breite aller Eingabefelder (und damit der Dialog) mit, bis der vollständige Text ohne horizontales Scrollen lesbar ist

#### Scenario: Feldbreite skaliert mit dem Schriftgrößen-Präset
- **WHEN** ein Wert eingegeben ist, der in der Standardgröße in die Feldbreite passt, und das Präset Large oder XLarge aktiviert wird
- **THEN** wächst die Feldbreite mit der Schriftgröße, sodass der vollständige Text auch in der größeren Schrift ohne horizontales Scrollen lesbar ist

#### Scenario: Feldbreite begrenzt an der Viewport-Breite
- **WHEN** der eingegebene Inhalt auch nach Anpassung breiter als die Obergrenze aus 90 % der Viewport-Breite (abzüglich Label-Spalte und Fenster-Rahmen) wäre
- **THEN** wächst der Dialog nicht über 90 % der Viewport-Breite hinaus und der Text bleibt im Feld horizontal scrollbar

#### Scenario: Button-Reihe bei großen Schriftgrößen vollständig sichtbar
- **WHEN** das Schriftgrößen-Präset Large oder XLarge aktiv ist und der Dialog geöffnet ist
- **THEN** sind alle Buttons der Button-Reihe (Speichern, Verbindung testen, Schließen) vollständig sichtbar und nicht abgeschnitten

#### Scenario: Test ohne vorheriges Speichern
- **WHEN** der Nutzer Base-URL und Modell eingegeben hat, aber noch nicht gespeichert hat
- **THEN** testet „Verbindung testen" den mit den eingegebenen Werten angegebenen Endpunkt und nicht die zuvor gespeicherte Konfiguration

#### Scenario: Veralteter Test-Status wird gelöscht
- **WHEN** der Nutzer ein Testergebnis angezeigt bekommen hat und danach ein Feld im Dialog ändert
- **THEN** verschwindet die Statuszeile, bis ein neuer Test läuft

#### Scenario: Test blockiert die Oberfläche nicht
- **WHEN** der Nutzer „Verbindung testen" betätigt und der Anfrage-Call mehrere Sekunden dauert
- **THEN** bleibt die Benutzeroberfläche reaktionsfähig (das Fenster „friert" nicht ein), der Test-Button ist währenddessen deaktiviert und ein Hinweis auf den laufenden Test ist sichtbar

#### Scenario: Feld-Änderung verwirft laufende Tests
- **WHEN** der Nutzer ein Feld im Dialog ändert, während ein Verbindungstest läuft
- **THEN** verschwinden Hinweis und Statuszeile und das Ergebnis des noch laufenden Tests wird nicht angezeigt
