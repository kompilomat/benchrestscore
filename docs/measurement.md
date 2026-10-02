# Vermessung, Kalibrierung & Genauigkeit

## Zentrale Konzepte

### Metrik vs. Pixel

Messungen laufen in **Weltmetrik (mm)**, nicht in Pixeln:

- Messpunkte werden beim Setzen (Klick) über `calib.mati` vom Bild (NDC) in die
  Weltmetrik überführt: `metric = ndc · mati`.
- Alle Abstände, Radii und Kaliber-Kreise werden in Metrik berechnet.
- Für die Anzeige werden sie über `calib.mat` zurück in NDC/GL-NDC projiziert.

`BRSView` koordiniert die Referenzsysteme: Pixel ↔ GL-NDC ↔ (NDC, geteilt durch
`aspect_ratio`). Zoom/Drag verändern nur die Anzeige-Matrix, nicht die Messwerte.

### LUT-Rendering (GPU)

Statt Bild-`remap` am CPU werden Lens-Distortion und die Farbkanal-Korrektur in
Texturen (`lutr`/`lutg`/`lutb`) ausgelagert und im Fragment-Shader per Textur-Lookup
angewandt:

- Jede LUT ist **4-kanalig** (RGBA) und kodiert die Ziel-Koordinate als zwei
  16-Bit-Werte (High/Low-Byte), also `(wh, wl, hh, hl)`.
- Der Shader rekonstruiert die Texturkoordinate (`r + g/256`, `b + a/256`), clampst auf
  `[0,1]` und samplt den Webcam-Textur-Kanal pro Farbkanal (Rot/Grün/Blau getrennt).
- `compute_lut_channels()` erzeugt die LUTs nach Kalibrierung; `default_lut_channels()`
  liefert die neutrale (unverzerrte) LUT. Der neutrale Zustand setzt `set_luts()` mit
  drei identischen LUTs.

Diese Auslagerung macht Echtzeit-Genauigkeit bis **0,01 mm** überhaupt möglich.

## Kalibrierung (`VMSCalibrate`)

OpenCV-basierter Workflow, läuft blockierend auf einem eingefrorenen Frame:

1. **Rasterpunkte erkennen**: `SimpleBlobDetector` + `findCirclesGrid`
   (symmetrisches 32×18-Raster, Rastermaß 4,899 mm; Karte als Kalibrierkarte).
2. **Projektion schätzen**: Homographie / Perspektiv-Projektion (`pre_estimate_projection`
   via `scipy.optimize`) → `mat` (NDC-Grid → Welt) und `mati` (Welt → NDC).
3. **Pro-Kanal-Verzerrung**: Jeder Farbkanal (B, G, R) wird separat mit einem
   **linearen Grad-3-Polynom-Warp** gefittet (`g = F(x,y)·C`, 10 Terme je Koordinate:
   `1,x,y,x²,xy,y²,x³,x²y,xy²,y³` — gefittet per **geschlossenem `np.linalg.lstsq`**
   (QR, `channel_distortion_estimation`). Die pro-Kanal-Trennung korrigiert die
   chromatische Aberration der Linse (B-Kanal weicht ≈  40 µm ab`. Die Inversion
   erfolgt per **Newton-Iteration** auf dem Polynom (analytische Jacobian, ~2 Schritte`
   `inv_distortion()`.
4. **Kameraausrichtung**: A/B-Korrekturwerte (in Richtung `L`/`R`) via `solvePnP` +
   Rückprojektion der optischen Achse.
5. **LUTs**: `compute_lut_channels()` erzeugt für jeden Kanal die 4-Kanal-LUT
   (`sampling_step=2`, also 1080p-Dichte mit Interpolation).

Erfolg/Fehler: `calibrate(frame)` liefert `True`/`False`. Bei Erfolg zusätzlich
Genauigkeitswerte `mean`/`sd` (µm, AVG/VAR) pro Rasterpunkt und ein `visual`-Bild
über Kanälen.

### Einzelpose-Randbedingung (Montage)

Die Kamera ist **overhead fix montiert** und schaut — soweit mechanisch möglich — **orthogonal
auf den Tisch**. Daraus folgt eine harte Design-Constraint für die Kalibrierung:

- **Mehrere Posen sind nicht möglich**: Die Kalibrierkarte kann nicht gekippt oder verschoben
  werden, ohne die Messgeometrie zu verlassen. Damit ist die Mehrbild-Kalibrierung über
  `cv2.calibrateCamera` (5–20 Posen, unterschiedliche Ausrichtungen) konstruktionsbedingt
  ausgeschlossen.
- Die **eigene Single-Image-Implementierung** (Homographie + pro-Kanal-Verzerrungsfit,
  `VMSCalibrate`) ist deshalb eine bewusste Entscheidung: Eine planare Aufnahme liefert genau
  eine Homographie = 8 Freiheitsgrade; `fx`/`fy`, `cx`/`cy` und hochgradige `k2…k6` sind darin
  schwach/unterbestimmt bestimmt und neigen gerade in den Bildecken zu Oszillation.
- **Konsequenz für Verbesserungen**: Stabilitätsgewinn muss am Single-Image-Fit selbst kommen —
  Regularisierung auf `k4…k6`, Robust-Loss, Parameter-Skalierung für den Optimizer, optional ein
  `cx`/`cy`-Offset im eigenen Modell — **nicht** über eine Multi-Pose-Erweiterung.

> **Stand nach Change `calibration-polynomial-distortion`**: Diese k-basierten Hebel sind
> historisch. Das aktuelle Modell ist ein **lineares Grad-3-Polynom** pro Kanal (gefitett
> per `np.linalg.lstsq`, invertiert per Newton`, das die asymptrische Warp-Struktur (Sattel`
> abbildet und auf dem Fixture **mean ≈  17 µm, sd ≈  9 µm** erreicht.

### Diagnose & Persistenz (`last_calibration`)

Nach **jedem** Kalibrier-Versuch — Erfolg **und** Fehlschlag — schreibt `calibrate()` Dateien
ins Config-Verzeichnis (`~/.config/benchrestscore/`), überschreibend ohne Zeitstempel:

- **`last_calibration.png`**: Der **Roh-Frame** (ohne Overlay) — immer, auch bei Fehlschlag,
  damit ein unverfälschtes Beispiel fürs Debugging persistiert ist.
- **`last_calibration_overlay.png`**: Bei Erfolg das verarbeitete Kalibrier-Bild mit Raster-,
  per-Punkt-Fehler- und Diagnose-Overlay; bei Fehlschlag wird eine stale Overlay-Datei entfernt.
- **`last_calibration.json`**: Pydantic-Sidecar (`CalibrationResult`) mit Kamera-Kontext,
  `mean`/`sd`/`quality`, A/B-Korrektur, `mat`/`mati`, `channel_params`, `acc`-Matrix und den
  Diagnose-Auswertungen (`radius_curve`, `quadrants`).

Reine Diagnose-Funktionen (headless testbar):

- **`error_vs_radius(acc, ndc_grid)`**: Fehler (µm) in Radial-Bins um die Bildmitte.
  Monotones Ansteigen nach außen deutet auf Oszillation/hohe Distorsions-Ordnungen, Wellen
  auf ein `k4…k6`-Problem.
- **`quadrant_breakdown(acc)`**: Fehler (µm) pro Bildquadrant — Asymmetrie deutet auf eine
  dezentrierte Linse (`cx`/`cy`-Kandidat).

Der Regressionstest `tests/test_calibration_fixture.py` lädt die kommittierte Aufnahme
`data/calibration_card.png` (echte 4K, Karte füllt das Bild) und fährt die Kalibrierung
headless darüber — deterministische Basis für Modell-Änderungen (Phase 2).

#### Hintergrund-Snapshots (`last_background`)

Beim Abschließen der finalisierten Session (inkl. Hintergrund lernen) persistiert die App
neben den Kalibrier-Dateien:

- **`last_background.png`**: Der **LUT-entzerrte** Frame des freien Tischs — die per
  Farbkanal korrigierte Geometrie, die auch der Shader anzeigt. Über
  `undistort_frame()` (`calibration.py`, CPU-Spiegel des LUT-Shaders) wird die
  LUT-Korrektur (`compute_lut_channels()`) in Software angewandt.
- **`last_background_overlay.png`**: Die Keypoint-Visualisierung auf dem **entzerrten**
  Frame — die gezeichneten Keypoints erscheinen an der entzerrten Position.
- **`last_background.json`**: Die gelernten Keypoints inkl. ORB-Descriptors (Grundlage
  der Wiederherstellung).

Es wird nur die LUT-Geometrie angewandt — **keine** Anzeige-Filter (Kontrast/Gamma/
Negativ/Graustufen), konsistent zum „ungefilterten, nur LUT-korrigierten" Bild der
Automation. Ohne gültige LUTs (z. B. nicht kalibriert) wird der Roh-Frame geschrieben;
die Persistenz blockiert nie.

### Karten-Qualitätscheck (Kalibrierkarten-Varianz)

Kalibrierkarten werden mit einem Laser-Drucker gedruckt und haben mutmaßlich
Karten-zu-Karten-Varianz. Der **Karten-Qualitätscheck** (Kalibrierung-Reiter)
prüft eine
neu eingelegte Kalibrierkarte gegen die Karte, mit der die App kalibriert wurde:

- **Referenz**: Bei der Kalibrierung wird das gemessene Metrik-Raster der Karte
  (`cal.metric_grid`) über eine **identische Pipeline** wie die spätere Messung
  im Sidecar als `grid_metric` persistiert (Rohbild-`findCirclesGrid` +
  `inv_distortion` mit den gemittelten Kanal-Parametern + `mati`, jeweils mit
  **3-Frame-Sampling**). Die Referenz ist damit die **tatsächlich gemessene**
  Karte inkl. ihrer Abweichung vom Idealraster — ein Vergleich gegen das
  Nominalraster würde die Referenzkarte selbst durchfallen lassen.
- **Ablauf** (`run_card_qc`): Die Messung läuft in einem **Hintergrund-Thread**
  (die UI zeigt „Messe Kalibrierkarte…" mit Abbruch). Es werden **3
  aufeinanderfolgende Live-Frames** erfasst und das NDC-Gitter über die Frames
  **gemittelt** (`QC_SAMPLE_FRAMES`, Rauschreduktion √N — identisch zum
  Kalibrier-Sampling), Rastererkennung im Rohbild (`findCirclesGrid` +
  `get_target_grid`, identisch zur Kalibrierung) → NDC → `inv_distortion`
  (gemittelte Kanal-Parameter) → `mati` → Weltmetrik (`detect_grid_metric`).
  Zusammen ~0,5–1,0 s auf 4K.
- **Ausgleichung**: `homography_align` bildet das gemessene Raster per
  **Least-Squares-Homographie** (DLT, alle Punkte) auf die Referenz ab —
  Versatz, Drehung, Skalierung und Perspektive der Einlage werden
  herausgerechnet, **lokale** Kartenabweichungen bleiben im Fehlermaß
  sichtbar. (Eine reine Rotation+Translation genügt nicht: das Metrik-Mapping
  hat ein positionsabhängiges Fehlerfeld, das bei minimal anderer Einlage
  sonst als Schein-Abweichung erscheint.)
- **Bewertung**: `check_card` liefert pro Punkt die Abweichung (µm) sowie
  Max/Mean; die Karte ist **in Spec**, wenn **jeder** Punkt nach der
  Homographie-Ausgleichung innerhalb **±0,075 mm** liegt. Farbkodierung im
  Overlay: grün ≤ 50 µm, orange 50–75 µm (beides in Spec), rot > 75 µm
  (out of spec). Ergebnis + Overlay werden als `last_card_check.json` /
  `last_card_check_overlay.png` ins
  Config-Verzeichnis geschrieben (Schreibfehler blockieren den Betrieb nie).
  Das Overlay (`pixel_grid`) zeichnet die Punkte auf den **Rohbild-
  Pixelpositionen** der Blobs — der Marker liegt nach der LUT-Entzerrung
  genau auf dem Blob des angezeigten Bilds (keine zweite Distortion-Inversion,
  die die Marker sonst verbiegen würde).
- **Fehlerfälle**: ohne aktive Kalibrierung / ohne `grid_metric` im Sidecar
  (alte Sessions → „neu kalibrieren") / Raster nicht erkannt (mit Kreisanzahl).

### Experimentelle Befunde zur Kalibrier-Genauigkeit

> **Stand nach Change `calibration-polynomial-distortion`**: Die folgenden Befunde gelten für
> das **alte** Modell (`k1..k6`-Radial + Affine` und sind **historisch**. Das aktuelle Modell
> (lineares Grad-3-Polynom pro Kanal, per `lstsq` gefittet, per Newton invertiert) erreicht
> auf dem Fixture **mean ≈  17 µm, sd ≈  9 µm** — eine Halbierung. Das Radius-Profil
> ist flach (kein Sattel-/Eck-Anstieg mehr; die verbleibende Decke liegt im
> Blob-Detektions-Jitter (RMS ≈  12 µm` — nur mit besserer Zentroid-Schätzung
> (oder mehr Auflösung) weiter senkbar, nicht mit einem besseren Warp.

Eine Reihe von Modell-Experimenten wurde auf dem Fixture (`data/calibration_card.png`,
Ist-Zustand: **mean ≈  34,6 µm, sd ≈  18,5 µm**, äußerster Radius-Bin ≈  66 µm) gefahren.44
Alle getesteten Hebel führten zu **keiner** Verbesserung und wurden deshalb **nicht**
übernommen:

| Hebel | Ansatz | Ergebnis |
|---|---|---|
| Robust-Loss | Huber/Cauchy statt L2-Mittelwert im Fit | keine Änderung (kein Ausreißer-Einfluss) |
| Ordnungs-Reduktion | k6 → k5…k1 | keine Änderung |
| Tikhonov-Regularisierung | Gewicht auf k4…k6 | keine Änderung, ab λ=1e-3 schlechter |
| Isotropie | Radialterm im Pixel-proportionalen Raum (y·aspect) statt gestauchtem NDC | deutlich schlechter (≈157 µm) |

Zusätzliche Struktur-Analyse der Fehlermatrix `acc[x,y]`:

- Der Fehler wächst radial (Rand ≈ 52 µm vs. Zentrum ≈ 31 µm), ist aber **nicht** durch die
  Modellparameter erklärbar — sonst hätte mindestens einer der Hebel gegriffen.
- Die Fehlermatrix ist **rau**: Nachbarpunkte springen im Mittel um ≈ 12 µm bei einem globalen
  Mittel von ≈ 34,6 µm. Das spricht gegen ein glattes (radialsymmetrisches) Modelldefizit und
  für **per-Punkt-Zentrums-/Aufnahme-Rauschen** (leicht unebene Karte, Druckungenaugkeit,
  Beleuchtung).

**Schlussfolgerung / Empfehlung**: Der Ist-Zustand liegt auf dieser Aufnahme nahe der
praktischen Grenze (bei 4K entspricht ≈ 1 Pixel ≈ 0,04 mm ≈ 40 µm; die Karte füllt das Bild).
Eine weitere Genauigkeitssteigerung über den Distorsions-Fit selbst ist auf diesem Fixture
nicht absehbar. Das Diagnose-Tooling (`last_calibration.*`, `error_vs_radius`,
`quadrant_breakdown`, Fixture-Test) bleibt als Werkzeug erhalten, um neue Aufnahmen
(andere Karte, andere Beleuchtung, andere Montage) quantitativ zu bewerten, bevor an
Modell oder Detektion geschraubt wird.

#### Zweite Diagnose-Runde: Fehlerquelle eingrenzen

Eine weitergehende Diagnose (auf einer zweiten, frischen Aufnahme `data/calibration_card.png`,
Ist mean ≈ 34,6 µm) grenzt die Fehlerquelle weiter ein. Methoden und Befunde:

- **Fehler-Vektorfeld (radial vs. tangential)**: Der Fehler wächst radial (im Außenbereich
  rad ≈ 47 µm vs. tan ≈ 27 µm), ist aber im Zentrum erhöht (r<0.22 → ≈ 43 µm) statt monoton
  nach außen zu steigen — ein glattes, nicht-monotones Profil, das kein k1..k6-Modell abbildet.
- **`cx`/`cy`-Zentrums-Scan** (fixe Kanal-Parameter, Verschiebung des radialen Zentrums):
  Optimal `(0.020, 0.000)` ergibt **identisch** ≈ 34,6 µm → ein reiner Zentrums-Offset bringt
  nichts.
- **Leave-out-Kreuzvalidierung** (Fit auf geraden Spalten, messen auf allen): Test-mean
  ≈ 34,7–35,6 µm ≈ Train ≈ Ist → der Fit ist „ausgelernt", keine Überanpassung; die Decke
  liegt **außerhalb des Parameterraums**.
- **Kanal-Korrelation der Fehlervektoren** (B/G/R): Cosinus-Ähnlichkeit ≈ **+0.98…0.99** →
  der Fehler ist **gemeinsam/systematisch** über alle Kanäle, kein Kanal-/Blob-Rauschen.

**Rotations-A/B-Test (entscheidend):** Die Kalibrierkarte wurde unter der fixen Kamera um
exakt 180° gedreht und erneut kalibriert. Vergleich der Fehlermatrizen:
- Korrelation `acc_180` mit `acc_0` (**kamera-fest**): **+0.618** (Median-Differenz 9,9 µm)
- Korrelation `acc_180` mit `acc_0` rotiert (**karten-fest**): +0.402 (Median-Differenz 13,0 µm)

→ Der Fehler ist **kamera-/bild-fest** und rotiert **nicht** mit der Karte. Damit ist eine
**Karten-Druckungenauigkeit als Ursache ausgeschlossen**.

**Joint-Metrik-Fit (Fit „on what you measure"):** Versuch, statt des NDC-Vorwärtsfehlers direkt
die Reprojektionsmetrik `‖model − inv_distortion(target)·mati‖` (mm) mit geteilter Homographie
`mat` und pro Kanal nur k/p-Termen zu fitten. Sanity-Check (Ist-k + geteilte `mati`) reproduziert
die Produktions-Metrik **nicht** (≈ 1781 µm statt 35,6 µm): Die aktuelle Metrik hängt an der
**Kanal-Affine** (`channel_params[k][:8]`, Skala ≈ 1.037), die die kanal-spezifische
Raster-Erkennung kompensiert. Ein geteilter Metrik-Fit ohne Kanal-Affine ist eine **andere**
Metrik und funktioniert nicht; mit Kanal-Affine wären es zu viele Freiheitsgrade
(48+, unterbestimmt). → Kein Fit-Parameter-Experiment, sondern ein **Architektur-Eingriff**
nötig.

**Gesamtfazit (Stand):** Der verbleibende, systematische, kamera-feste Fehler (~35 µm, radial,
kanal-korreliert) liegt in der **gemeinsamen Projektion/Homographie `mat`** bzw. in einem Effekt,
den die Kanal-Affin-Struktur des Modells nicht abbildet. Eine Verbesserung erfordert einen
Architektur-Change (gemeinsame Homographie mit über alle Kanäle konsistenter Metrik), nicht
ein reines Fit-Experiment. Dieser Stand ist als Handover relevant: **Nicht** erneut die
bereits widerlegten Hebel testen (Robust-Loss, k-Ordnungen, Regularisierung, Isotropie,
`cx`/`cy`, Karten-Druck), sondern die gemeinsame Homographie/Projektion adressieren.


> **Stand nach Change `calibration-polynomial-distortion`**: Auch diese Runde gilt für das alte
> k-Modell und ist historisch. Der Architektur-Eingriff ist erfolgt — aber anders als damals
> vermutet: Statt die Homographie anzufassen, wurde die **per-Kanal-Distortion** durch ein
> **lineares Grad-3-Polynom** ersetzt (fit per `lstsq`, invers per Newton`, was das
> asymptrische Sattel-Warp abbildet und den mean von 34,6 auf ≈  17 µm senkt. Der
> Fehler lag also doch im Parameterraum des Distortion-Modells — nur nicht im radial-
> symmetrischen k1..k6-Raum. Die Hebel-Tabelle oben bleibt als historische Negativ-Liste
> nützlich (nicht wiederholen`. Die Doku zum Handover („nicht die widerlegten Hebel
> testen") bleibt sinngemäß gültig — der Gewinn kam aus der **neuen Modellklasse**, nicht
> aus einer Wiederholung der alten Hebel.

### Workflow: Kalibrieren → Untergrund lernen → Messen

Der Kalibrier-Workflow ist **verpflichtend** vierstufig (FSM `RESULT → LEARN_PROMPT →
LEARN_RESULT → MEASURING`). Die vier **sichtbaren Dialog-Stationen** tragen die
Schritt-Anzeige „Kalibrierung — Schritt `n/4`" im Titel:

1. **Ausrichten & Start** (`IDLE`, Schritt 1/4): Karte platzieren, `C`/Button startet
   die Kalibrierung. Diese läuft **blockierend** im GUI-Thread auf einem eingefrorenen
   Frame (`CALIBRATING`) — sie hat keinen eigenen sichtbaren Schritt/Dialog.
2. **Ergebnis** (`RESULT`, Schritt 2/4): `Enter` übernehmen oder `Esc` abbrechen.
3. **Untergrund lernen** (`LEARN_PROMPT`, Schritt 3/4): Infobox „Kalibrierkarte
   entfernen" + Button „Hintergrund lernen (Enter)" oder „Abbruch". Beim Lernen wird die
   Kamera eingefroren und der freie Tisch per ORB-Keypoints + Descriptoren gelernt
   (`calibration_monitor.py`). Zu strukturarme Fläche → Fehlertext, erneut versuchbar.
4. **Lern-Ergebnis** (`LEARN_RESULT`, Schritt 4/4): eingefrorener Frame mit
   eingezeichneten Keypoints (`draw_keypoints`) + Keypoint-Anzahl; „Abschließen (Enter)"
   → `MEASURING`.

Danach überwacht der **Loss-of-Calibration-Monitor** die Kamera periodisch (~1,5 s) im
Messbetrieb — in einem **eigenen Daemon-Thread** (`BackgroundMonitorThread`), damit die
ORB/Matching/RANSAC-Arbeit den Render-Thread nicht blockiert: Keypoint-Matching +
RANSAC-Homographie gegen das gelernte Modell liefert `OK` / `verschoben` (mm) / `n/a`.
Der Status erscheint in der Menüleiste rechtsbündig.
Reine Warnung — keine Auto-Korrektur; Modell wird bei
Re-Kalibrierung/Reset verworfen (Details `architecture.md`).

## Messung (`measurement.py`)

- **`BRSRuler`**: hält bis zu **fünf Messpunkte** (`MAX_POINTS`) in allen
  Referenzsystemen (GL-NDC, NDC, Metrisch) und zeichnet über GL-Programme die Punkte
  sowie die konzentrischen Kaliber-Kreise. Bei Änderung wird der Messwert berechnet
  und an die Messbox gemeldet.
  - Messpunkt-Marker als **Viertel-Kreuz** (Ø 2 mm in Weltmetrik, NE+SW gefüllt,
    Ring ~0,1 mm): auflösungsunabhängig und skaliert mit dem Zoom; der aktive
    Punkt ist orange, inaktive sind rot. Es gibt keinen OpenGL-Center-Dot mehr.
  - Der Klick-/Drag-Bereich ist an die projizierte Marker-Größe gekoppelt
    (`max(20 px, Marker-Radius + 10 px)`), damit Marker auch auf HiDPI-Displays
    zuverlässig getroffen werden.
  - `distance()` = **Maximum der paarweisen Distanzen** aller Messpunkte (mm),
    berechnet über die reine Funktion `max_pairwise_distance(metrics) -> (dist, (i,j))`.
  - `add_point`/`move_point`/`remove_point`/`set_active`/`cycle_active`/`reset_points`
    verwalten die Punkte; `hit_test(pixel, size)` ermittelt den Marker unter der Maus.
  - `adjust()` bewegt den aktiven Punkt in Metrik (0,05 mm-Schritt).
  - Der umgebende Kaliber-Kreis wird um die **zwei fernsten Punkte** gezeichnet
    (Mittelpunkt = Mitte des fernsten Paares, Radius = maxDist/2 + Kaliberradius);
    um jeden einzelnen Punkt liegt ein eigener Kaliber-Kreis. Zwei durchgehende Linien-
    segmente (je zwei Kaliberradien lang, nur außerhalb des umschließenden Kreises
    sichtbar) markieren, welches Paar den größten Abstand hat.
- **`BRSMeasurementBox`**: trägt die Kalibertabelle `CALIBER` (Name → Durchmesser mm,
  z.B. `.224` → 5,69). Liefert die Messwert-Zeilen (`value_rows()`, je Label links +
  rechtsbündiger Wert, in jeder Sprache sauber ausgerichtet):
  - `Mitte` = max-paarweise Distanz der Punkte (mm).
  - `Außen` = Mitte + Kaliberdurchmesser (mm).
  - `radius()` = halber Kaliberdurchmesser (für Kreise/Automation).
  - Die Kaliber-Auswahl erfolgt im Messung-Dialog (Dropdown mit Label) bzw. über die
    Tasten **1**/**2**; die frühere Kaliber-Anzeigezeile im Overlay-Text entfällt.

#### Interaktion (Messpunkte)

- Linke Maustaste auf freier Fläche **setzt** einen neuen Punkt (bis zu 5).
- Linke Maustaste auf einen Punkt-Marker **wählt** ihn als aktiven Punkt; Ziehen
  **verschiebt** ihn.
- Rechte Maustaste auf einen Punkt-Marker **löscht** ihn (Rechtsklick auf freie
  Fläche tut nichts).
- **Leertaste** steppt durch die Messpunkte; Pfeiltasten justieren den aktiven Punkt.
- **Taste R** (oder Reset-Button im Messung-Dialog) löscht alle Messpunkte.

### Kalibertabelle (`CALIBER`)

| Kaliber | ∅ mm |
|---------|------|
| .177 | 4,50 |
| .204 | 5,20 |
| .224 | 5,69 |
| .243 / 6 mm | 6,17 |
| 6.5 mm | 6,75 |
| 7 mm | 7,24 |
| .30 | 7,82 |
| .338 | 8,61 |
| .408 | 10,40 |
| .454 | 11,53 |
| .50 | 13,00 |
| .58 | 14,72 |

## Automation (`automation.py`)

`find_center(buf, view, pos, size, calibration, radius)` sucht das Schussloch-Zentrum
nahe dem Klickpunkt:

1. Klick in Metrik umrechnen, Suchradius (Kaliber) in Pixel projizieren.
2. Region ausschneiden (`SEARCH_EXCESS`=1,5-facher Kaliberradius, `SEARCH_WIDTH`=300),
   `adaptiveThreshold` (invertiert) → Pixelmaske.
3. `scipy.minimize` mit radialem Verlustmodell (Varianz + Radius-Term) → Zentrum.

Die Rückgabe ist ein `AutoDetect`-Ergebnis (`ok`, `raw_metric`, `center_metric`,
`offset_mm` in mm, `radius_px`) statt einer rohen Position; Fehlerfälle werden als
`ok=False` geliefert statt eine Exception zu werfen. Reine Helfer `pixel_to_metric`
und `metric_to_pixel` verbinden Pixel und Weltmetrik über den aktuellen View.

### UI-Einbindung

- **Umschaltung** läuft zentral über `controller.toggle_automation()` — erreichbar
  über die Taste M, den Messen-Reiter („Automatik (M)") und die Checkbox
  „Automatik (M)" im Messung-Fenster. Das Messung-Fenster zeigt zusätzlich eine Statuszeile
  („Automatik: AN" grün / „AUS" grau).
- **Pro-Punkt-Korrektur**: In der Punktübersicht trägt ein automatisiert gesetzter
  Punkt den Zusatz „auto +X,XX mm" (Korrektur des detektierten Zentrums gegenüber
  dem Rohklick, in Weltmetrik). Manuell gesetzte Punkte haben keinen Zusatz.
- **Fehl-Feedback**: Schlägt die Erkennung fehl, wird der Punkt am Rohklick gesetzt
  und eine rote Meldung „Auto-Erkennung fehlgeschlagen" im Messung-Fenster
  angezeigt; die nächste erfolgreiche Punkt-Setzung blendet sie aus. Die Meldung
  verschwindet außerdem automatisch nach 5 Sekunden (ein erneuter Fehlschlag
  frischt das Zeitfenster auf).
- **Flash-Overlay**: Für ~1 s erscheint im Viewport der Suchradius-Kreis um den
  Klickpunkt und die Korrekturlinie zum detektierten Zentrum (grün bei Erfolg, rot
  bei Fehlschlag).

Nur relevant, wenn die Automation aktiv ist; sonst setzt ein Klick den Punkt direkt.
Die Detektion läuft in `render()` direkt nach dem Webcam-Quad (vor Markern/Overlays)
und liest den Framebuffer, sodass gerenderte Marker/Overlays die Erkennung nie
verfälschen. Sie liest dabei **immer das ungefilterte** (nur LUT-korrigierte) Bild:
Im Auto-Klick-Frame wird das Quad einmal mit neutralem Filter gezeichnet, ausgelesen
und erst danach mit den aktiven Anzeige-Filtern neu gezeichnet. Anzeige-Filter
(Kontrast, Negativ, Graustufen, …) beeinflussen die Erkennung daher nie — auch
Negativ, das die Polarität umkehren würde, bleibt ohne Wirkung auf die Messung.

## Referenz-Snapshots (manuelle Bewertung für Tests)

Um ein Erkennungs-Verfahren (z.B. die Klick-Automation) gegen die Bewertung eines
Menschen zu prüfen, speichert die App im **Referenz-Modus** (Messen-Reiter) die
komplette Szene als selbst-enthaltenes Sample:

1. **Workflow**: Kalibrieren → Hintergrund lernen → Zielscheibe ablegen →
   **Referenz-Modus** (Messen-Reiter) einschalten → die Löcher manuell bepunkten →
   **„Referenz speichern"** im Messung-Fenster.
2. **Ablage**: Ein nummerierter Ordner pro Referenzfall —
   `datasets/sample_01/`, `sample_02/`, … in der Dataset-Wurzel
   (`BRS_REFERENCE_DATASET` übersteuert das Repo-`datasets/`). Ein Sample enthält:
   - `raw.png` + `evaluation.png` — rohes und LUT-entzerrtes Kamerabild.
   - `calibration.json`/`calibration.png`/`calibration_overlay.png` —
     Kalibrierung (Sidecar + Karten-Bilder).
   - `background.json`/`background.png` — gelerntes Untergrund-Modell
     (Keypoints + dichte Referenz in nativer Auflösung).
   - `metrics.json` — Breite/Höhe, Kaliber (Name + Radius in mm), die manuellen
     Messpunkte in Weltmetrik und die Kalibrier-Matrizen `mat`/`mati`.
3. **Headless-Auswertung**: `reference_eval.evaluate_automation(sample_dir)` lädt
   ein Sample, führt `find_center` pro manuellem Punkt aus (Identitäts-View) und
   liefert den Fehler (mm) des verfeinerten Zentrums gegen die manuelle Bewertung.

```bash
# In der App: kalibrieren -> Hintergrund lernen -> Scheibe ablegen ->
# Referenz-Modus -> Löcher bepunkten -> „Referenz speichern"
#   -> schreibt automatisch datasets/sample_NN/
.venv/bin/python -c "
import sys; sys.path.insert(0, 'benchrestscore')
from reference_eval import evaluate_automation
print(evaluate_automation('datasets/sample_01'))
"
```

## Genauigkeit & Determinismus

- Messwerte werden ausschließlich bei Tastatur/Maus-Events aktualisiert und in Metrik
  berechnet — Race-frei, deterministisch.
- Die Kalibrier-Genauigkeit wird direkt beim Kalibrieren als AVG/VAR in µm angezeigt.
- LUT-Rendering interpolieren (`GL_LINEAR`), Lookups sind deterministisch auf der GPU.
