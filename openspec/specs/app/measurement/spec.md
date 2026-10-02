# Measurement Specification

## Purpose

Definiert die Mehrpunkte-Vermessung in der Messphase: bis zu fünf Messpunkte können
gesetzt, verschoben, ausgewählt und gelöscht werden; der Messwert ist das Maximum
der paarweisen Distanzen aller Punkte, mit einem umgebenden Kaliber-Kreis um das
fernste Paar. Die Messpunkt-Marker werden als auflösungsunabhängiges Viertel-Kreuz
(Ø 2 mm) dargestellt und sind mit einem großzügigen, mit der Größe skalierten
Klick-/Drag-Bereich grabbar.

## Requirements

### Requirement: Messpunkte setzen
Das System SHALL nach erfolgreicher Kalibrierung (State `MEASURING`) einen neuen
Messpunkt anlegen, wenn der Nutzer mit der linken Maustaste auf freie Fläche klickt.
Es dürfen maximal fünf Messpunkte vorhanden sein; wird bei voller Belegung ein
weiterer Punkt gesetzt, hat das keinen Effekt (bestehende Punkte bleiben unverändert).

#### Scenario: Erster Punkt setzen
- **WHEN** der Nutzer mit der linken Maustaste auf freie Fläche klickt
- **THEN** wird an dieser Position ein neuer Messpunkt angelegt

#### Scenario: Fünfter Punkt erreicht
- **WHEN** bereits fünf Messpunkte vorhanden sind und der Nutzer erneut auf freie
  Fläche klickt
- **THEN** wird kein zusätzlicher Punkt angelegt und die fünf bestehenden Punkte
  bleiben unverändert

### Requirement: Messpunkt verschieben
Das System SHALL es erlauben, einen Messpunkt durch Ziehen (Drag) mit gedrückter
linker Maustaste auf seinem Punkt-Marker zu verschieben. Der Punkt folgt dabei der
Mausbewegung; die View wird dabei nicht verschoben.

#### Scenario: Drag auf dem Marker
- **WHEN** der Nutzer auf einen Punkt-Marker klickt und bei gedrückter linker
  Maustaste die Maus bewegt
- **THEN** wird dieser Messpunkt an die neue Position verschoben und die Messwerte
  aktualisieren sich

### Requirement: Aktiven Messpunkt wählen
Das System SHALL durch einen Klick der linken Maustaste auf einen Punkt-Marker diesen
als aktiven Messpunkt auswählen. Die Leertaste steppt den aktiven Messpunkt zyklisch
durch die vorhandenen Punkte durch.

#### Scenario: Punkt per Klick wählen
- **WHEN** der Nutzer mit der linken Maustaste auf einen Punkt-Marker klickt
- **THEN** wird dieser Punkt der aktive Messpunkt

#### Scenario: Leertaste steppt durch
- **WHEN** der Nutzer die Leertaste drückt und Messpunkte vorhanden sind
- **THEN** wechselt der aktive Messpunkt zum nächsten vorhandenen Punkt (zyklisch)

### Requirement: Messpunkt löschen
Das System SHALL einen Messpunkt löschen, wenn der Nutzer mit der rechten Maustaste
auf seinen Punkt-Marker klickt. Ein Rechtsklick auf freie Fläche hat keinen Effekt.

#### Scenario: Punkt per Rechtsklick löschen
- **WHEN** der Nutzer mit der rechten Maustaste auf einen Punkt-Marker klickt
- **THEN** wird dieser Messpunkt entfernt und die Messwerte aktualisieren sich

#### Scenario: Rechtsklick auf freie Fläche
- **WHEN** der Nutzer mit der rechten Maustaste auf freie Fläche klickt
- **THEN** wird kein Messpunkt entfernt

### Requirement: Messwert als max-paarweise Distanz
Das System SHALL den Messwert `Mitte` als Maximum der paarweisen Distanzen aller
Messpunkte in mm berechnen. Der Messwert ist nur definiert, wenn mindestens zwei
Messpunkte vorhanden sind. `Außen` ist der Messwert plus dem Kaliberdurchmesser.

#### Scenario: Mehrere Punkte messen
- **WHEN** mindestens zwei Messpunkte vorhanden sind
- **THEN** ist `Mitte` das Maximum aller paarweisen Distanzen der Messpunkte und
  `Außen` = `Mitte` + Kaliberdurchmesser

#### Scenario: Nur ein Punkt vorhanden
- **WHEN** höchstens ein Messpunkt vorhanden ist
- **THEN** wird kein Messwert angezeigt

### Requirement: Kreis um das fernste Paar
Das System SHALL den umgebenden Kaliber-Kreis um die zwei fernsten Messpunkte
zeichnen: Mittelpunkt = Mitte des Paares mit maximaler Distanz, Radius = maxDist/2 +
Kaliberradius. Zusätzlich wird um jeden Messpunkt ein Kaliber-Kreis gezeichnet.

#### Scenario: Fernstes Paar ermitteln
- **WHEN** mindestens zwei Messpunkte vorhanden sind
- **THEN** wird der umgebende Kreis um die beiden Punkte mit der maximalen Distanz
  gezeichnet und jeder einzelne Punkt erhält einen Kaliber-Kreis

### Requirement: Messpunkte zurücksetzen
Das System SHALL dem Nutzer erlauben, alle Messpunkte über einen Reset-Button im
Messung-Dialog oder über die Taste **R** zu löschen.

#### Scenario: Reset über den Dialog-Button
- **WHEN** der Nutzer im Messung-Dialog den Reset-Button wählt
- **THEN** werden alle Messpunkte entfernt und kein Messwert mehr angezeigt

#### Scenario: Reset über die Taste R
- **WHEN** der Nutzer die Taste **R** drückt
- **THEN** werden alle Messpunkte entfernt und kein Messwert mehr angezeigt

### Requirement: Messpunkte im Dialog auflisten
Der System SHALL im Messung-Dialog unter den Messdaten alle vorhandenen Messpunkte
auflisten, wobei der aktive Messpunkt gekennzeichnet ist und jeder Eintrag eine
Möglichkeit zum Löschen des jeweiligen Punkts bietet. Unter der Auflistung wird der
Reset-Button angezeigt.

#### Scenario: Punktliste anzeigen
- **WHEN** Messpunkte vorhanden sind
- **THEN** listet der Messung-Dialog alle Messpunkte mit Kennzeichnung des aktiven
  Punkts und einer Löschmöglichkeit pro Punkt sowie den Reset-Button auf

### Requirement: Auflösungsunabhängiger Messpunkt-Marker
Das System SHALL jeden Messpunkt als Kreis mit **2 mm Durchmesser** in Weltmetrik
rendern, bei dem die zwei gegenüberliegenden Viertel (Nordost und Südwest) gefüllt
sind und die beiden übrigen Viertel (Nordwest und Südost) leer bleiben. Die Größe
des Markers skaliert mit der View (Zoom); eine reine Pixel-Größe (z.B. OpenGL-Punkt)
wird nicht mehr verwendet. Der aktive Messpunkt wird in Orange, inaktive Punkte in
Rot dargestellt.

#### Scenario: Marker beim Setzen eines Punkts
- **WHEN** ein Messpunkt gesetzt wird
- **THEN** erscheint an der Punkt-Position ein Viertel-Kreuz-Marker (Ø 2 mm, NE+SW
  gefüllt) in der Farbe des jeweiligen Zustands (aktiv orange, sonst rot)

#### Scenario: Marker-Skalierung mit dem Zoom
- **WHEN** der Nutzer in die Ansicht hineinzoomt
- **THEN** skaliert die Marker-Größe mit dem Rest der Szene (metrisch konstant 2 mm)
  und es erscheinen keine Pixel-Artefakte als reine Bildschirmgröße

#### Scenario: Kein Center-Dot mehr
- **WHEN** Messpunkte sichtbar sind
- **THEN** wird kein zusätzlicher ausgefüllter Punkt (Center-Dot) mehr gezeichnet;
  die einzige Marker-Darstellung ist das Viertel-Kreuz

### Requirement: Grabbarkeit der Messpunkte
Das System SHALL den Klick-/Drag-Bereich eines Messpunkt-Markers so wählen, dass er
auf HiDPI-Displays zuverlässig getroffen werden kann. Der Trefferbereich SHALL
mindestens so groß sein wie der sichtbare Marker und zudem einen konstanten
Pixel-Mindestabstand abdecken.

#### Scenario: Drag auf HiDPI trifft den Marker
- **WHEN** der Nutzer auf einem HiDPI-Display einen Messpunkt verschieben möchte und
  die Maus im Bereich des sichtbaren Markers (inkl. eines Mindest-Pixelabstands)
  platziert
- **THEN** wird der Messpunkt beim Ziehen gefasst und folgt der Mausbewegung

#### Scenario: Trefferbereich folgt der projizierten Größe
- **WHEN** der Marker durch Zoom größer oder kleiner dargestellt wird
- **THEN** wächst bzw. schrumpft der Trefferbereich mit dem projizierten Marker,
  fällt aber nie unter einen Mindest-Pixelwert

### Requirement: Feinjustierung mit Wiederholung
Das System SHALL die Feinjustierung des aktiven Messpunkts per Pfeiltaste sowohl bei
einmaligem Tastendruck als auch bei gedrückt gehaltener Taste ausführen
(OS-Key-Repeat). Andere globale Shortcuts SHALL bei Gedrückthalten nicht wiederholt
ausgelöst werden.

#### Scenario: Einmaliger Druck
- **WHEN** der Nutzer eine Pfeiltaste kurz drückt
- **THEN** wird der aktive Messpunkt einmal justiert

#### Scenario: Gedrückte Pfeiltaste
- **WHEN** der Nutzer eine Pfeiltaste gedrückt hält
- **THEN** wird der aktive Messpunkt wiederholt weiterjustiert

#### Scenario: Andere Shortcuts nicht wiederholen
- **WHEN** der Nutzer einen anderen globalen Shortcut (z.B. Q, C, Enter) gedrückt hält
- **THEN** wird dessen Aktion nicht wiederholt ausgelöst

### Requirement: Kaliber im Messung-Dialog wählen
Das System SHALL die Kaliber-Auswahl im Messung-Dialog anbieten: ein Dropdown mit
sichtbarem Label („Kaliber"/„Caliber") ersetzt die reine Kaliber-Anzeigezeile über
den Messwerten. Die Auswahl SHALL sofort wirksam sein (Kaliber-Kreise, `Außen`-Wert
und Automation verwenden das gewählte Kaliber). Die Tasten **1**/**2** SHALL das
Kaliber weiterhin zyklisch wechseln; die Auswahl im Dialog und die Tasten wirken
dabei auf denselben Kaliber-Zustand.

#### Scenario: Kaliber im Dialog wählen
- **WHEN** der Nutzer im Messung-Dialog im Kaliber-Dropdown ein anderes Kaliber wählt
- **THEN** wird dieses Kaliber aktiv, `Außen` und die Kaliber-Kreise aktualisieren sich
  und der Auswahlzustand bleibt mit den Tasten 1/2 synchron

#### Scenario: Tasten 1/2 wirken auf denselben Zustand
- **WHEN** der Nutzer im Messbetrieb die Taste 1 oder 2 drückt
- **THEN** wechselt das Kaliber zyklisch und der Messung-Dialog zeigt das neue Kaliber
  im Dropdown an

### Requirement: Messwertzeilen rechtsbündig ausrichten
Das System SHALL die beiden Messwertzeilen (`Mitte` und `Außen`) im Messung-Dialog so
ausrichten, dass die Zahlenspalte in beiden Zeilen an derselben Position beginnt —
in allen unterstützten Sprachen (Deutsch und Englisch). Die Werte SHALL in beiden
Zeilen auf gleiche Breite formatiert sein.

#### Scenario: Ausrichtung in Englisch
- **WHEN** die aktive Sprache Englisch ist und zwei Messpunkte gesetzt sind
- **THEN** beginnen die Werte von `Center` und `Outside` in derselben Spalte
  (rechtsbündig), unabhängig von der unterschiedlichen Label-Länge

#### Scenario: Ausrichtung in Deutsch
- **WHEN** die aktive Sprache Deutsch ist und zwei Messpunkte gesetzt sind
- **THEN** beginnen die Werte von `Mitte` und `Außen` in derselben Spalte
### Requirement: Metadaten-Abschnitt im Messung-Dialog
Das System SHALL im Messung-Dialog unterhalb des Messpunkte-Reset-Buttons einen
Abschnitt „Metadaten" anzeigen, wenn der BRSMatch-Modus aktiviert ist. Der Abschnitt
SHALL einen Button „Etikett-Scan (E)" enthalten, der den Etikett-Scan auslöst, sowie
die Anzeige des letzten Scan-Ergebnisses (DG, Sch-Nr, Stand, Zeit) bzw. einer
Fehlermeldung bei Fehlschlag.

#### Scenario: Metadaten-Abschnitt bei aktivem BRSMatch
- **WHEN** der BRSMatch-Modus aktiviert ist und der Messung-Dialog geöffnet ist
- **THEN** wird unterhalb des Reset-Buttons der Abschnitt „Metadaten" mit dem Button „Etikett-Scan (E)" angezeigt

#### Scenario: Metadaten-Abschnitt bei inaktivem BRSMatch
- **WHEN** der BRSMatch-Modus nicht aktiviert ist und der Messung-Dialog geöffnet ist
- **THEN** wird kein Abschnitt „Metadaten" angezeigt

#### Scenario: Scan-Ergebnis anzeigen
- **WHEN** ein Etikett-Scan erfolgreich war und der Messung-Dialog geöffnet ist
- **THEN** zeigt der Metadaten-Abschnitt die vier gelesenen Werte (DG, Sch-Nr, Stand, Zeit) an

#### Scenario: Scan-Fehler anzeigen
- **WHEN** ein Etikett-Scan fehlgeschlagen ist und der Messung-Dialog geöffnet ist
- **THEN** zeigt der Metadaten-Abschnitt eine Fehlermeldung an

### Requirement: Stabile Breite des Messung-Dialogs
Das System SHALL die Breite des Messung-Dialogs aus seinen stabilen
Inhaltszeilen ableiten: Kaliber-Zeile (Label und Dropdown), Messwert-Zeilen
(`Mitte`/`Außen`), Messpunkt-Liste inklusive Lösch-Buttons, Reset-Button und —
wenn der BRSMatch-Modus aktiviert ist — die Zeilen des Metadaten-Abschnitts
(Scan-Buttons, gelesene Etikett-Werte, Teilnehmer-Info und Wertung-Aktion).
Diese Breite ist die definierte Dialog-Breite; sie SHALL sich mit dem Inhalt
(anliegende Messpunkte, vorhandene Metadaten, aktive Sprache, Schriftgrößen-
Präset) skalieren und SHALL nicht an der aktuellen Fensterbreite festgemacht
sein. Status- und Fehlermeldungen (Scan, Lookup, Wertung, Referenz-Modus,
Auto-Detektion) sind keine stabilen Inhaltszeilen: Sie SHALL die definierte
Dialog-Breite nicht bestimmen.

#### Scenario: Breite ist durch stabile Zeilen definiert
- **WHEN** der Messung-Dialog geöffnet ist und keine breitere Status- oder
  Fehlermeldung angezeigt wird
- **THEN** entspricht die Dialog-Breite der Breite seiner stabilen
  Inhaltszeilen und ändert sich nur, wenn sich deren Inhalt ändert (z. B.
  Anzahl der Messpunkte, gelesene Etikett-Werte)

#### Scenario: Breitere Meldung vergrößert nur während der Anzeige
- **WHEN** eine Status- oder Fehlermeldung (z. B. der Lookup-Fehler „Sch-Nr
  oder Durchgang passt nicht zur Belegung") angezeigt wird, deren Zeile breiter
  ist als die definierte Dialog-Breite
- **THEN** wird der Dialog während der Anzeige dieser Zeile breiter, damit die
  Meldung vollständig lesbar bleibt

#### Scenario: Rückkehr zur definierten Breite
- **WHEN** die breitere Status- oder Fehlermeldung nicht mehr angezeigt wird
  (z. B. nachdem der Nutzer ein neues Etikett gescannt hat)
- **THEN** kehrt der Messung-Dialog von selbst in seine definierte Breite
  zurück, ohne dass der Nutzer eingreifen muss; eine einmalige Vergrößerung
  durch eine kurze Meldung bleibt nicht dauerhaft bestehen

#### Scenario: Rechtsbündiges Layout bleibt erhalten
- **WHEN** der Messung-Dialog mit Kaliber-Auswahl und Messwerten gezeichnet
  wird und keine breitere Status-/Fehlermeldung angezeigt wird
- **THEN** stehen das Kaliber-Dropdown und die Messwerte rechtsbündig am
  rechten Rand der definierten Dialog-Breite, wie vor der Änderung
