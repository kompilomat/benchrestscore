## Purpose

Stellt sicher, dass der Fullscreen-OpenGL-Viewport stets der aktuellen Framebuffer-
Größe folgt, sodass die Kamera-Textur den gesamten Viewport abdeckt und fremde
(wenn auch korrekte Letterbox-)Streifen auf unterschiedlichen Monitoren korrekt
positioniert sind — ohne weiße Ränder durch veraltete Viewport- oder Fenstergrößen.

## Requirements

### Requirement: Viewport-Größen-Synchronisierung
Das System SHALL die OpenGL-Viewport-Größe mit der aktuellen Framebuffer-Größe des
Fensters synchron halten. Ändert sich die Fenster- oder Framebuffer-Größe (z.B. beim
Erzeugen im Fullscreen, HiDPI-Skalierung oder Monitor-Wechsel), SHALL der Viewport
innerhalb desselben Render-Zyklus an die neue Größe angepasst werden, bevor neu
gezeichnet wird.

#### Scenario: Fenstergröße ändert sich nach dem Start
- **WHEN** die Framebuffer-Größe des Fensters sich nach der Initialisierung ändert
- **THEN** wird `glViewport` mit der neuen Größe gesetzt und die View-Matrix sowie
  alle abhängigen Overlays (Ruler, Messbox, Indikator) werden neu berechnet

#### Scenario: Initialisierung liefert eine vorläufige Größe
- **WHEN** nach dem ersten Event-Poll die endgültige Fenster-/Framebuffer-Größe vorliegt
- **THEN** wird der Viewport mit dieser finalen Größe einmalig neu gesetzt

#### Scenario: Größe ist null oder negativ
- **WHEN** eine gemeldete Fenstergröße null oder negativ ist (z.B. während der
  Minimierung/Initialisierung)
- **THEN** erfolgt keine Viewport-Änderung und die zuletzt gültige Größe bleibt aktiv

### Requirement: Fullscreen-Streaming-Viewport
Das System SHALL Webcam-Frames kontinuierlich in einen Fullscreen-GL-Viewport rendern,
wobei das aktuellste verfügbare Kamerabild ohne sichtbares Flackern angezeigt wird.

#### Scenario: Kamera liefert neue Frames
- **WHEN** ein neues Webcam-Frame verfügbar ist
- **THEN** wird es im Viewport als Textur gerendert und die Anzeige aktualisiert

#### Scenario: Kamera liefert noch kein Bild
- **WHEN** noch kein gültiges Webcam-Frame vorhanden ist
- **THEN** zeigt der Viewport den Warte-Bildschirm an

### Requirement: LUT-basiertes Korrektur-Rendering
Das System SHALL Lens-Distortion und Farbkanal-Korrektur über die Kalibrier-LUTs
(`lutr`/`lutg`/`lutb`) per GPU-Textur-Lookup im Fragment-Shader anwenden. In der
unkalibrierten Neutralzustand zeigen die LUTs eine unverzerrte Darstellung.

#### Scenario: Kalibrierung aktiv
- **WHEN** die Kalibrier-LUTs geladen sind
- **THEN** wird das Bild mit angewandter Korrektur gerendert

#### Scenario: keine Kalibrierung aktiv
- **WHEN** die neutralen LUTs aktiv sind
- **THEN** wird das Bild ohne Verzerrungskorrektur angezeigt

### Requirement: View-Transformation
Das System SHALL eine View-Matrix unterstützen, die Zoom (Faktor 1..18) und Drag über
das gerenderte Bild erlaubt, sodass Messpunkte metrisch korrekt positioniert bleiben.
Das Mausrad-Zoomen SHALL den Zoom nicht instantan springen lassen, sondern über die
Zeit kontinuierlich Richtung des akkumulierten Ziels glätten, wobei der Punkt unter
der Maus während der Bewegung festgehalten wird.

#### Scenario: Zoomen auf eine Position
- **WHEN** der Nutzer per Mausrad zoomt
- **THEN** wird das Ziel-Zoom um die Schrittweite (+1,5 pro Raste, geklemmt auf 1..18)
  akkumuliert und die View gleitet über mehrere Frames weich auf den akkumulierten
  Ziel-Zoom, wobei der Weltpunkt unter der Mausposition während der gesamten Bewegung
  an derselben Bildposition bleibt

#### Scenario: Schnelles Scrollen akkumuliert das Ziel
- **WHEN** der Nutzer mehrere Rasten in kurzer Folge scrollt, bevor das Smoothing das
  Ziel erreicht hat
- **THEN** wird das Ziel-Zoom um jede Raste weiter erhöht bzw. verringert (Schrittweite
  +1,5/Raste, geklemmt auf 1..18) und die View gleitet kontinuierlich auf das
  aktualisierte Ziel, ohne zwischen den Rasten zu springen

#### Scenario: Untergrenze Zoom 1 erreicht
- **WHEN** das Ziel-Zoom auf den Minimalwert 1 zurückgezoomt wird
- **THEN** fährt die View zusätzlich sanft auf die volle Kameraansicht (Translation
  Richtung (0,0)) aus, statt beim Erreichen von Zoom 1 zu springen

#### Scenario: Smoothing konvergiert
- **WHEN** die aktuelle View das Ziel-Zoom (innerhalb einer kleinen Toleranz) erreicht
  hat
- **THEN** wird exakt das Ziel gesetzt, der Smoothing-Zustand gelöscht und die View
  bleibt danach ruhig stehen

#### Scenario: Drag
- **WHEN** der Nutzer bei gedrückter Maustaste zieht
- **THEN** verschiebt die View-Matrix das Bild entsprechend und ein laufendes
  Scroll-Smoothing wird sofort abgebrochen

### Requirement: Aktiven Messpunkt zentrieren
Das System SHALL beim Durchsteppen des aktiven Messpunkts per Leertaste
(`cycle_active_point`) die View so pannen, dass der neue aktive Punkt im Bildzentrum
liegt. Der Zoom-Faktor SHALL dabei unverändert bleiben. Der Übergang SHALL animiert
erfolgen (weiche Bewegung, ~0,25 s) und SHALL bei jeder Nutzer-Interaktion, die die
View direkt verändert (Drag, Mausrad-Zoom, View-Reset, Fenster-Resize, Kamera-Neustart),
sofort abgebrochen werden.

#### Scenario: Leertaste zentriert auf den aktiven Punkt
- **WHEN** der Nutzer im Messmodus mit mindestens einem Messpunkt die Leertaste drückt
- **THEN** wird die View so verschoben, dass der neue aktive Punkt im Bildzentrum liegt,
  und der Zoom-Faktor bleibt unverändert

#### Scenario: Keine Messpunkte vorhanden
- **WHEN** der Nutzer die Leertaste drückt, ohne dass ein Messpunkt gesetzt ist
- **THEN** ändert sich die View nicht

#### Scenario: Animation wird bei Drag abgebrochen
- **WHEN** während einer laufenden Zentrier-Animation der Nutzer einen View-Drag startet
  (oder das Mausrad dreht, die View per Mittelklick zurücksetzt, das Fenster die Größe
  ändert oder die Kamera neu gestartet wird)
- **THEN** stoppt die Animation sofort und die View folgt ab dem nächsten Frame allein
  der Nutzer-Interaktion

#### Scenario: Auswahl per Mausklick zentriert nicht
- **WHEN** der Nutzer einen Messpunkt per Mausklick auswählt (`select_point`)
- **THEN** bleibt die View unverändert (keine Zentrierung)

### Requirement: Animierter View-Reset
Das System SHALL beim Zurücksetzen der View per Mittelklick (bisher: sofortiges
Auszoomen auf das volle Kamerabild) die View animiert zurückführen: Zoom auf Faktor 1
und Translation auf (0,0) mit weicher Bewegung (~0,25 s, ease-in-out). Die Animation
SHALL bei jeder Nutzer-Interaktion, die die View direkt verändert (Drag, Mausrad-Zoom,
Fenster-Resize, Kamera-Neustart oder ein erneuter Mittelklick), sofort abgebrochen
werden.

#### Scenario: Mittelklick zoomt animiert aus
- **WHEN** der Nutzer bei einem Zoom > 1 per Mittelklick die View zurücksetzt
- **THEN** fährt die Kamera weich auf das volle Kamerabild (Zoom 1, Translation (0,0))
  zurück, statt sofort zu springen

#### Scenario: Reset-Animation wird bei Drag abgebrochen
- **WHEN** während der animierten Reset-Animation der Nutzer einen View-Drag startet
  (oder das Mausrad dreht, die Größe des Fensters ändert oder die Kamera neu startet)
- **THEN** stoppt die Animation sofort und die View folgt ab dem nächsten Frame allein
  der Nutzer-Interaktion

### Requirement: Messpunkte einpassen (Crop Messung)
Das System SHALL im Ansicht-Menü einen Eintrag „Crop Messung (X)" anbieten, wobei `X`
die Anzahl der aktuell gesetzten Messpunkte ist, und den Tastatur-Shortcut „C"
ausführen. Der Eintrag SHALL nur bei mindestens einer Messung aktiv sein. Wird er
gewählt, positioniert das System die View so, dass alle aktuellen Messpunkte UND der
große Messkreis (um die fernsten Punkte, inkl. Kaliberradius) vollständig sichtbar
sind, mit einem kleinen Rand (~5 %): Der Zoom wird passend skaliert (geklemmt auf die
bestehenden Grenzen 1..18) und das Zentrum des sichtbaren Bereichs ins Bildzentrum
verschoben. Der Übergang SHALL animiert erfolgen (~0,25 s, ease-in-out) und bei
Nutzer-Interaktion, die die View direkt verändert, sofort abgebrochen werden.

#### Scenario: Mehrere Messpunkte einpassen
- **WHEN** im Messmodus mehrere Messpunkte gesetzt sind und der Nutzer „Crop Messung"
  im Ansicht-Menü wählt (oder die Taste C drückt)
- **THEN** wird die View animiert so eingestellt, dass alle Messpunkte und der große
  Messkreis mit ~5 % Rand sichtbar sind und ihr Zentrum im Bildzentrum liegt

#### Scenario: Einzelner Messpunkt einpassen
- **WHEN** genau ein Messpunkt gesetzt ist und der Nutzer „Crop Messung" wählt
- **THEN** wird die View auf den einzelnen Punkt zentriert und der Zoom-Faktor bleibt
  unverändert (wie beim Leertaste-Zentrieren)

#### Scenario: Kein Messpunkt vorhanden
- **WHEN** keine Messung gesetzt ist
- **THEN** ist der Menüeintrag „Crop Messung" deaktiviert und löst nichts aus

#### Scenario: Crop-Animation wird bei Drag abgebrochen
- **WHEN** während der Crop-Animation der Nutzer einen View-Drag startet (oder das
  Mausrad dreht, die View per Mittelklick zurücksetzt, das Fenster die Größe ändert
  oder die Kamera neu gestartet wird)
- **THEN** stoppt die Animation sofort und die View folgt ab dem nächsten Frame allein
  der Nutzer-Interaktion