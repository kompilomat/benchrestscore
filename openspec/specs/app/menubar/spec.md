# Menubar Specification

## Purpose

Fasst die Menüleisten-Struktur der App zusammen: App-Reiter "Benchrestscore"
(Über uns/Beenden), "Kalibrierung" (Neu kalibrieren, Wiederherstellung,
Karten-Qualitätscheck), "Messen" (Automatik, Referenz-Modus), "Ansicht"
(Hintergrund einfärben, Crop Messung), "Einstellungen" (Kamera-Dialog,
Bildfilter, Vision-Konfiguration, Schriftgröße) und "Sprache", sowie den
rechtsbündigen Kalibrier-Status-Indikator. Weitere Menüleisten-Entwicklung folgt
als Folge-Changes unter dieser Capability.

## Requirements

### Requirement: Menüleisten-Reiter "Benchrestscore"
Das System SHALL die Menüleiste mit einem ersten Reiter "Benchrestscore" anzeigen,
der die Einträge "Über uns" und "Beenden (Q)" enthält.

#### Scenario: Menüleiste öffnen
- **WHEN** die Anwendung läuft
- **THEN** ist der Reiter "Benchrestscore" als erster in der Menüleiste sichtbar

#### Scenario: Beenden-Eintrag
- **WHEN** der Nutzer "Beenden (Q)" wählt
- **THEN** beendet die Anwendung das Programm (wie die Taste Q)

### Requirement: Über-uns-Dialog
Das System SHALL beim Klick auf "Über uns" ein modales Fenster öffnen, das
die Zeile `Version: <git-hash>`, den Hinweis `© Harald Lampesberger` und
darunter das Anwendungslogo anzeigt. Die Breite des Logos SHALL 50 % der
Dialog-Inhaltsbreite entsprechen, seine Höhe dem Seitenverhältnis der
Logodatei; die Größe SHALL mit dem aktiven Schrift-Präset skalieren. Der
Dialog SHALL unterhalb des Logos vertikalen Spielraum (mindestens eine
Schriftzeile) bereitstellen und SHALL seine Inhalte vollständig ohne
Scrollbar anzeigen (Fenstergröße folgt dem Inhalt). Ist die Logodatei
nicht verfügbar, SHALL der Dialog ohne Logo angezeigt werden, sonst
unverändert. Wird kein Git-Hash
ermittelt, zeigt die Version den Wert `unknown` an.

#### Scenario: Über uns öffnen
- **WHEN** der Nutzer den Menüleisten-Eintrag "Über uns" wählt und die Logodatei vorhanden ist
- **THEN** öffnet sich ein modales Fenster mit "Version: <hash>", "© Harald Lampesberger" und darunter dem Logo, mit Spielraum unter dem Logo

#### Scenario: Git-Hash nicht verfügbar
- **WHEN** kein Git-Hash ermittelbar ist
- **THEN** zeigt der Dialog `Version: unknown` und weiterhin Logo und Urheberhinweis

#### Scenario: Logodatei fehlt
- **WHEN** die Logodatei beim Start nicht vorhanden oder nicht lesbar ist
- **THEN** öffnet sich der Dialog ohne Logo, mit Version und Urheberhinweis, und die Ursache wird einmalig protokolliert

### Requirement: Reiter "Kalibrierung" mit Kalibrier-Aktionen
Das System SHALL den Reiter „Kalibrierung" in der Menüleiste anzeigen, der die
Einträge „Neu kalibrieren (K)", „Kalibrierung wiederherstellen" und
„Karten-Qualitätscheck" enthält. „Neu kalibrieren (K)" startet den
Kalibriervorgang (wie die Taste K), „Kalibrierung wiederherstellen" stellt die
letzte finalisierte Session wieder her und „Karten-Qualitätscheck" startet den
Karten-Qualitätscheck.

#### Scenario: Kalibrierung per Menü starten
- **WHEN** der Nutzer im Reiter „Kalibrierung" „Neu kalibrieren (K)" wählt
- **THEN** startet der Kalibriervorgang

#### Scenario: Wiederherstellung per Menü
- **WHEN** der Nutzer im Reiter „Kalibrierung" „Kalibrierung wiederherstellen" wählt
- **THEN** wird die Wiederherstellung der letzten finalisierten Session ausgelöst

#### Scenario: Karten-Qualitätscheck per Menü
- **WHEN** der Nutzer im Reiter „Kalibrierung" „Karten-Qualitätscheck" wählt
- **THEN** startet der Karten-Qualitätscheck

### Requirement: Reiter "Messen" mit Mess-Aktionen
Das System SHALL den Reiter „Messen" in der Menüleiste anzeigen, der die
Einträge „Automatik (M)" und „Referenz-Modus" enthält. „Automatik (M)" schaltet
die Automation um; „Referenz-Modus" schaltet den Referenz-Modus um und SHALL
nur im Messbetrieb (MEASURING) auswählbar sein.

#### Scenario: Automation umschalten
- **WHEN** der Nutzer im Reiter „Messen" „Automatik (M)" (um)schaltet
- **THEN** wechselt die Automation zwischen an und aus

#### Scenario: Referenz-Modus nur im Messbetrieb
- **WHEN** sich die App nicht im Messbetrieb befindet
- **THEN** ist der Eintrag „Referenz-Modus" nicht auswählbar

### Requirement: Reiter "Einstellungen" mit Einstellungs-Dialogen
Das System SHALL den Reiter „Einstellungen" in der Menüleiste anzeigen, der
folgende Einträge enthält:
- „Kamera" öffnet den Kamera-Einstellungs-Dialog (Gerät, Auflösung, Rotation).
- „Bildfilter" (um)schaltet das Bildfilter-Panel und ist wie eine Checkbox
  markiert, wenn das Panel offen ist; der Shortcut F bleibt erhalten.
- „Vision-Konfiguration" (um)schaltet den Vision-Konfigurations-Dialog und ist
  wie eine Checkbox markiert, wenn der Dialog offen ist.
- Das Untermenü „Schriftgröße" führt die Präsete Normal / Groß / Sehr groß mit
  dem jeweils aktiven Präset markiert.

Der Kamera-Einstellungs-Dialog, das Bildfilter-Panel und der
Vision-Konfigurations-Dialog SHALL jeweils einen „Schließen"-Button enthalten;
dessen Betätigung SHALL den jeweiligen Dialog ausblenden (gleiche Wirkung wie
das Abhaken des Menüeintrags).

#### Scenario: Kamera-Dialog öffnen
- **WHEN** der Nutzer im Reiter „Einstellungen" „Kamera" wählt
- **THEN** öffnet sich der Kamera-Einstellungs-Dialog mit den Auswahlen für
  Gerät, Auflösung und Rotation

#### Scenario: Bildfilter-Panel umschalten
- **WHEN** der Nutzer im Reiter „Einstellungen" „Bildfilter" (um)schaltet
- **THEN** wird das Bildfilter-Panel eingeblendet bzw. ausgeblendet (wie die Taste F)

#### Scenario: Vision-Dialog umschalten
- **WHEN** der Nutzer im Reiter „Einstellungen" „Vision-Konfiguration" (um)schaltet
- **THEN** wird der Vision-Konfigurations-Dialog eingeblendet bzw. ausgeblendet
  und der Menüeintrag zeigt den geöffneten Zustand als Checkbox

#### Scenario: Schriftgröße als Untermenü
- **WHEN** der Nutzer im Reiter „Einstellungen" das Untermenü „Schriftgröße" öffnet
- **THEN** sind die Präsete Normal, Groß und Sehr groß sichtbar und das aktive
  Präset ist markiert

#### Scenario: Dialog per Button schließen
- **WHEN** der Nutzer in einem der Einstellungs-Dialoge (Kamera, Bildfilter
  oder Vision-Konfiguration) den „Schließen"-Button betätigt
- **THEN** wird der Dialog ausgeblendet und der zugehörige Menüeintrag ist
  nicht mehr markiert

### Requirement: Reiter "Ansicht" mit Anzeige-Optionen
Das System SHALL den Reiter „Ansicht" in der Menüleiste anzeigen, der die
Einträge „Hintergrund einfärben" und „Crop Messung (C)" enthält und keine
Einstellungs-Dialoge. „Hintergrund einfärben" SHALL nur auswählbar sein, wenn
eine dichte Tisch-Referenz (gelernt oder wiederhergestellt) vorliegt;
„Crop Messung (C)" SHALL nur auswählbar sein, wenn mindestens ein Messpunkt
gesetzt ist.

#### Scenario: Hintergrund einfärben nur mit Referenz
- **WHEN** keine dichte Tisch-Referenz vorliegt
- **THEN** ist der Eintrag „Hintergrund einfärben" nicht auswählbar

#### Scenario: Crop Messung nur mit Messpunkten
- **WHEN** keine Messpunkte gesetzt sind
- **THEN** ist der Eintrag „Crop Messung (C)" nicht auswählbar

#### Scenario: Ansicht enthält keine Einstellungen
- **WHEN** der Nutzer den Reiter „Ansicht" öffnet
- **THEN** enthält er nur „Hintergrund einfärben" und „Crop Messung (C)"
  (keine Kamera-, Bildfilter-, Schriftgrößen- oder Vision-Einträge)

### Requirement: Kein eigener Kamera-Reiter in der Menüleiste
Das System SHALL in der Menüleiste keinen eigenen Reiter „Kamera" mehr anzeigen;
die Kamera-Einstellungen sind ausschließlich über den Reiter „Einstellungen"
(Eintrag „Kamera") erreichbar.

#### Scenario: Kamera-Reiter fehlt
- **WHEN** die Menüleiste angezeigt wird
- **THEN** enthält sie keinen Reiter „Kamera"
### Requirement: Reiter "BRSMatch" mit Verbindungs-Dialog
Das System SHALL den Reiter „BRSMatch" in der Menüleiste anzeigen, der den Eintrag
„Verbindung" enthält. Der Eintrag (um)schaltet den BRSMatch-Verbindungs-Dialog und
ist wie eine Checkbox markiert, wenn der Dialog offen ist. Der Dialog SHALL Felder
für Base-URL und API-Key sowie eine Checkbox „Aktivieren" enthalten; ein
„Schließen"-Button blendet den Dialog aus (gleiche Wirkung wie das Abhaken des
Menüeintrags). Die Breite der Eingabefelder des Dialogs SHALL sich — wie in der
Vision-Konfigurationsmaske — an die Länge des eingegebenen Inhalts und das aktive
Schriftgrößen-Präset anpassen, sodass eine eingegebene Base-URL vollständig ohne
horizontales Scrollen lesbar bleibt; die Gesamtbreite des Dialogs SHALL auf 90 %
der Viewport-Breite begrenzt sein.

#### Scenario: BRSMatch-Dialog öffnen
- **WHEN** der Nutzer im Reiter „BRSMatch" „Verbindung" wählt
- **THEN** öffnet sich der BRSMatch-Verbindungs-Dialog mit Base-URL, API-Key und Aktivieren-Checkbox

#### Scenario: BRSMatch-Dialog umschalten
- **WHEN** der Nutzer im Reiter „BRSMatch" „Verbindung" (um)schaltet
- **THEN** wird der Dialog eingeblendet bzw. ausgeblendet und der Menüeintrag zeigt den geöffneten Zustand als Checkbox

#### Scenario: Dialog per Button schließen
- **WHEN** der Nutzer im BRSMatch-Verbindungs-Dialog den „Schließen"-Button betätigt
- **THEN** wird der Dialog ausgeblendet und der Menüeintrag ist nicht mehr markiert

#### Scenario: Lange Base-URL im BRSMatch-Dialog lesbar
- **WHEN** der Nutzer im BRSMatch-Dialog eine lange Base-URL einträgt
- **THEN** wächst die Feldbreite mit dem Inhalt (skaliert mit dem aktiven Schriftgrößen-Präset), bis die vollständige URL ohne horizontales Scrollen lesbar ist, und der Dialog wächst dabei nicht über 90 % der Viewport-Breite hinaus
