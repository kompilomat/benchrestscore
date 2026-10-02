# Automation Specification

## Purpose

Definiert die Einbindung der automatischen Schussloch-Erkennung beim Klick in die
Mess-UI: zentrale Umschaltung, sichtbarer Status im Messung-Fenster, pro Punkt
angezeigte Korrektur, Fehler-Feedback und eine kurzfristige Visualisierung des
Suchradius im Viewport.

## Requirements

### Requirement: Zentrale Umschaltung der Automation
Das System SHALL die Automation über einen einzigen, zentralen Umschaltpfad an-
und ausschalten. Tastaturkürzel (M), Menüpunkt „Automatik (M)" im Reiter
„Messen" der Menüleiste und der UI-Schalter im Messung-Fenster SHALL auf
diesen Pfad zugreifen; der aktuelle Zustand SHALL dabei allen Bedienwegen
stets gemeinsam aktualisiert werden.

#### Scenario: Umschalten per Tastatur spiegelt sich in der UI
- **WHEN** der Nutzer die Taste M drückt und die Automation aktiviert
- **THEN** zeigen sowohl der Menüpunkt „Automatik (M)" als auch die
  Statusanzeige im Messung-Fenster den eingeschalteten Zustand

#### Scenario: Umschalten per Menü spiegelt sich im Messung-Fenster
- **WHEN** der Nutzer in der Menüleiste unter „Messen" den Eintrag
  „Automatik (M)" (um)schaltet
- **THEN** übernimmt das Messung-Fenster den neuen Zustand in seine
  Statusanzeige

### Requirement: Statusanzeige im Messung-Fenster
Das System SHALL im Messung-Fenster den Zustand der Automation anzeigen: Ist sie an,
erscheint eine grün hervorgehobene „Automatik: AN"-Anzeige samt Bedienelement zum
Ausschalten; ist sie aus, eine neutrale/graue Anzeige samt Bedienelement zum Einschalten.
Nur im App-Zustand MEASURING ist die Anzeige sichtbar.

#### Scenario: Automation eingeschaltet
- **WHEN** die Automation aktiv ist und das Messung-Fenster geöffnet ist
- **THEN** zeigen der Schalter und die Statuszeile den eingeschalteten Zustand an

#### Scenario: Automation ausgeschaltet
- **WHEN** die Automation inaktiv ist und das Messung-Fenster geöffnet ist
- **THEN** zeigen der Schalter und die Statuszeile den ausgeschalteten Zustand an

### Requirement: Pro-Punkt-Korrekturanzeige
Das System SHALL für jeden Messpunkt, der mit aktiver Automation gesetzt wurde, die
Korrektur des detektierten Zentrums gegenüber dem rohen Klickpunkt in der
Punktübersicht des Messung-Fensters anzeigen (dargestellt als Betrag in Millimetern).
Manuell gesetzte Punkte SHALL keine Korrekturangabe tragen; die Korrektur SHALL den
aktiven Punkt nach dem Verschieben/Löschen von Gegen- und Folgepunkten weiterhin korrekt
zugeordnet bleiben.

#### Scenario: Korrektur sichtbar
- **WHEN** der Nutzer mit aktiver Automation einen Punkt setzt und das detektierte
  Zentrum vom Klickpunkt abweicht
- **THEN** zeigt die Punktübersicht beim betroffenen Punkt die Korrektur z. B. als
  „auto +0,34 mm" an

#### Scenario: Manueller Punkt ohne Korrektur
- **WHEN** der Nutzer bei inaktiver Automation einen Punkt setzt
- **THEN** trägt der Punkt in der Punktübersicht keine Korrekturangabe

### Requirement: Fehler-Feedback bei erfolgloser Erkennung
Das System SHALL bei aktiver Automation und fehlgeschlagener Erkennung (kein Treffer im
Suchbereich) den Punkt an der rohen Klickposition setzen und im Messung-Fenster eine
rote Meldung „Auto-Erkennung fehlgeschlagen" anzeigen. Die Meldung SHALL nach spätestens
5 Sekunden automatisch ausgeblendet werden und SHALL zusätzlich verschwinden, sobald der
nächste Punkt gesetzt wird. Ein erneuter Fehlschlag innerhalb des 5-Sekunden-Fensters
SHALL das Fenster neu starten (die Meldung bleibt sichtbar).

#### Scenario: Erkennung schlägt fehl
- **WHEN** der Nutzer bei aktiver Automation auf eine Stelle klickt, in der die
  Erkennung kein Zentrum findet
- **THEN** wird der Punkt an der rohen Klickposition gesetzt und im Messung-Fenster
  erscheint die Fehlermeldung

#### Scenario: Fehler beim nächsten Punkt behoben
- **WHEN** nach einem Fehlschlag der nächste Punkt erfolgreich erkannt wird
- **THEN** ist die Fehlermeldung nicht mehr sichtbar

#### Scenario: Meldung verschwindet nach 5 Sekunden
- **WHEN** ein Fehlschlag aufgetreten ist und 5 Sekunden vergangen sind, ohne dass ein
  weiterer Punkt gesetzt wurde
- **THEN** ist die Fehlermeldung nicht mehr sichtbar

#### Scenario: Auffrischen bei erneutem Fehlschlag
- **WHEN** innerhalb des 5-Sekunden-Fensters erneut ein Fehlschlag auftritt
- **THEN** bleibt die Fehlermeldung sichtbar und das 5-Sekunden-Fenster startet neu

### Requirement: Suchradius- und Korrektur-Visualisierung im Viewport
Das System SHALL beim Setzen eines Messpunkts mit aktiver Automation für eine kurze Dauer
(etwa eine Sekunde) im Viewport den Suchradius als Kreis um den Klickpunkt sowie eine
Linie vom rohen Klickpunkt zum detektierten Zentrum anzeigen. Bei fehlgeschlagener
Erkennung SHALL diese Visualisierung als Fehlervariante (abweichende Farbe) für dieselbe
Dauer erscheinen.

#### Scenario: Erfolgreiche Erkennung visualisiert Korrektur
- **WHEN** der Nutzer mit aktiver Automation einen Punkt setzt und die Erkennung ein
  Zentrum findet
- **THEN** erscheinen kurzzeitig der Suchradius-Kreis um den Klickpunkt und eine Linie
  zum detektierten Zentrum

#### Scenario: Fehlgeschlagene Erkennung visualisiert Fehlschlag
- **WHEN** der Nutzer mit aktiver Automation einen Punkt setzt und die Erkennung
  fehlschlägt
- **THEN** erscheint kurzzeitig ein Suchradius-Kreis in der Fehlervariante um den
  Klickpunkt

### Requirement: Reine Framebuffer-Quelle der Erkennung
Das System SHALL die automatische Erkennung stets auf dem unverfälschten Kamera-/LUT-Bild
ausführen; gerenderte Marker, Kaliberkreise und Overlays SHALL zu keinem Zeitpunkt in den
Erkennungs-Input gelangen.

#### Scenario: Marker verfälschen die Erkennung nicht
- **WHEN** der Nutzer bei aktiver Automation einen Punkt setzt, nachdem bereits Messpunkte
  mit Markern sichtbar sind
- **THEN** enthält der Erkennungs-Input ausschließlich das Kamera-/LUT-Bild ohne Marker
  oder Overlays

### Requirement: Zentrumssuche über Ring-Kernel-Konvolution und Scheiben-Maske
Das System SHALL das Lochzentrum in zwei Schritten bestimmen, ohne eine
Tisch-Referenz vorauszusetzen:

1. **Ring-Kernel-Vorlokalisierung**: Auf dem adaptiv geschwellten Binaerbild
   SHALL ein zirkulaerer Matched-Filter (Annulus-Kernel) mit dem bekannten
   Kaliberradius angewendet werden. Ein Pixel SHALL genau dann aktiviert
   werden, wenn in seiner lokalen Nachbarschaft eine Kante mit annaehernd dem
   Kaliberradius verläuft. Der Peak der Antwort im erlaubten Bereich um den
   Klick SHALL als Startzentrum dienen. Damit unterscheidet die Suche die
   Lochkante vom Scheibenaufdruck, ohne auf eine gelernte Referenz
   angewiesen zu sein.
2. **Schrumpfende Scheiben-Maske**: Ausgehend vom Startzentrum SHALL die
   ursprüngliche Varianzminimierung (adaptive Schwelle + radialer Fit)
   mehrstufig ausgeführt werden; die Maske (Pixel-Auswahl um das aktuelle
   Fit-Zentrum) SHALL pro Stufe schrumpfen (z. B. 1,2r → 1,05r → 0,95r).
3. **Harte Klick-Bounds**: Das gesuchte Zentrum SHALL an den Klick gebunden
   bleiben (±0,15 Kaliberradien). Läuft der Fit an die Grenze, SHALL die
   Erkennung **explizit fehlschlagen** statt ein ungenaues Zentrum zu
   liefern — der Klick war dann zu ungenau, und der Nutzer positioniert den
   Punkt per Drag&Drop.

#### Scenario: Loch über Ring-Kernel gefunden
- **WHEN** der Nutzer mit aktiver Automation in ein Loch klickt und im
  Suchfenster eine Lochkante mit annähernd dem Kaliberradius verläuft
- **THEN** aktiviert der Ring-Kernel den Kandidaten und die schrumpfende
  Maske verfeinert das Zentrum auf die Lochmitte

#### Scenario: Scheibenaufdruck fließt nicht ein
- **WHEN** im Suchfenster Scheibenaufdruck oder Schmutz mit dunklen Pixeln
  vorliegt, aber keine Kante im Kaliberradius
- **THEN** zählt dieser Aufdruck nicht zur Ring-Antwort und verzerrt das
  Zentrum nicht

#### Scenario: Klick zu ungenau -> Fail-fast
- **WHEN** der Fit das Zentrum an die harte Klick-Bound drückt (Klick sitzt
  zu weit außerhalb)
- **THEN** schlägt die Erkennung explizit fehl (`ok=False`), statt ein
  ungenaues Zentrum zu liefern

### Requirement: Reale Dataset-Akzeptanz der Zentrumssuche
Das System SHALL die automatische Zentrumssuche gegen reale Referenz-Samples
(`datasets/sample_*` bzw. `BRS_REFERENCE_DATASET`) headless prüfen lassen, sodass
die Qualität der Zentrumsverfeinerung gegenüber der manuellen Bewertung eines
Menschen reproduzierbar messbar ist. Die Suche SHALL dabei folgende
Akzeptanz-Grenzen erreichen: bei exaktem Klick in das gedachte Zentrum wird für
jeden manuellen Punkt ein Zentrum gefunden (kein Fehlschlag), der Fehler des
detektierten Zentrums gegenüber der manuellen Weltmetrik liegt pro Punkt unter
1,0 mm und pro Sample im Mittel unter 1,0 mm. Ist das Ziel noch nicht erreicht,
SHALL der Test als explizit erwarteter Fehlschlag (`xfail`) ausgewiesen werden,
bis die Grenzen erfüllt sind.

#### Scenario: Sub-mm-Genauigkeit gegen reale Samples
- **WHEN** die Automation gegen alle realen Referenz-Samples mit exaktem Klick
  in das gedachte Zentrum ausgeführt wird
- **THEN** wird für jeden manuellen Punkt ein Zentrum gefunden und der Fehler
  liegt pro Punkt unter 1,0 mm sowie pro Sample im Mittel unter 1,0 mm

#### Scenario: Erwarteter Fehlschlag solange Ziel offen
- **WHEN** die Sub-mm-Grenzen aktuell nicht erfüllt sind und die Tests laufen
- **THEN** schlagen die Ziel-Assertions als explizit erwartete Fehlschläge
  (`xfail`) fehl, ohne die übrige Suite rot zu färben

### Requirement: Kein Latch auf ein Nachbarloch
Das System SHALL beim automatischen Punktesetzen das Zentrum dem angeklickten
Loch zuordnen: das detektierte Zentrum SHALL näher an der manuellen Position des
angeklickten Lochs liegen als an jeder anderen manuellen Lochposition desselben
Samples (kleine Toleranz erlaubt). Ein Verstoß (Latch-Ereignis) SHALL in der
headless Auswertung pro Punkt markierbar sein; solange Latches auftreten, SHALL
der zugehörige Test als erwarteter Fehlschlag (`xfail`) laufen.

#### Scenario: Kein Latch in engen Lochgruppen
- **WHEN** die Automation gegen Samples mit eng benachbarten manuellen Punkten
  ausgeführt wird
- **THEN** liegt das detektierte Zentrum jedes Punkts näher an der manuellen
  Position des angeklickten Lochs als an jeder anderen Lochposition (kein Latch)

#### Scenario: Latch als erwarteter Fehlschlag
- **WHEN** ein Punkt auf ein Nachbarloch latchen würde
- **THEN** ist der Latch in der Auswertung markiert und der Latch-Test schlägt
  als erwarteter Fehlschlag (`xfail`) fehl

### Requirement: Robustheit gegen realistische Klick-Versatz
Das System SHALL die automatische Zentrumssuche auch dann zuverlässig ausführen,
wenn der Klick bis etwa 25 Pixel vom gedachten Zentrum abweicht (realistischer
Hand-Klick). Bei Versätzen bis 10 Pixel SHALL der Fehler des detektierten
Zentrums gegen die manuelle Weltmetrik pro Punkt unter 1,0 mm bleiben; bei
Versätzen bis 25 Pixel SHALL er pro Punkt unter 2,0 mm bleiben (ein Versatz von
25 px entspricht bei den realen Kalibern bereits rund 1 mm, Löcher mit
teilweise schwachem Lochrand sind darüber hinaus nicht weiter korrigierbar).
Solange diese Grenzen nicht erreicht sind, SHALL der zugehörige Test als
erwarteter Fehlschlag (`xfail`) laufen.

#### Scenario: Klick-Versatz bis 25 px
- **WHEN** die Automation pro manuellem Punkt mit zufälligem Klick-Versatz von
  0, 10 und 25 Pixeln ausgeführt wird
- **THEN** bleibt der Fehler des detektierten Zentrums pro Punkt unter 1,0 mm
  bei 0/10 px und unter 2,0 mm bei 25 px