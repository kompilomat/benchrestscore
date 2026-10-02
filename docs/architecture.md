# Architektur

`benchrestscore/` ist eine OpenGL-basierte Anwendung (imgui-bundle/GLFW/PyOpenGL) zum
Vermessen von Schusslöchern an der Webcam in Echtzeit. Drei Säulen:

1. **Kamera-Thread** liefert Frames in eine geteilte Variable.
2. **Kalibrierung** (OpenCV) berechnet Verzerrungs-/LUT-Daten.
3. **UI + Messung** (ImGui + PyOpenGL-Shader) rendert das Bild und die Messdaten.

## Datenfluss (Übersicht)

```
Webcam (Thread) ──> BRSCamera.current_frame ──> on_timer ──> Textur (GPU) ──> Anzeige
     ▲                                                          │
     │                                                          │ LUT (Verzeichnis)
Kalibrierung (VMSCalibrate, OpenCV) ──> mat/mati + LUTs ────────┘
     ▲                                                            │
Klicks/Tasten (BRSCanvas) ──> BRSRuler / BRSMeasurementBox ──────> Messdaten (Metrik)
```

## Module (`benchrestscore/`)

- **`app.py` — `BRSCanvas`**: Glue-Layer und Event-Schleife. Erstellt GLFW-Fenster +
  GL-Kontext, verbindet Kamera-Thread, Kalibrierung, Lineal, Messbox, Controller und
  ImGui-Overlay; verarbeitet Tastatur (siehe unten) und Maus (Zoom/Drag, Messpunkte).
  Der Webcam-Quad wird als PyOpenGL-Program mit dem GLSL-Shader gerendert, der die
  Kalibrier-LUTs anwendet. Frame-Loop in `run()` (VSync aus, Frame-Limiter 60 fps).
   Für die BRSMatch-Wertung erfasst `request_wertung_capture()`/`_process_wertung_capture()`
   am Frame-Ende (nach dem ImGui-Render, vor `swap_buffers`) eine Framebuffer-Kopie
   des vollständigen Fensters (Menüleiste + Kamera-Bild + Messmarker +
   Messung-Dialog, kein Ausschnitt), skaliert sie kantengetreu (Lanczos) auf
   1280×720 und encodiert sie als JPEG, Qualität 90
   (`brsmatch_api.encode_screenshot`); der Upload läuft im Controller-Thread.

- **`controller.py` — `AppController` + `AppState`**: UI-agnostische, explizite
  App-State-Maschine für den Kalibrier-Workflow. Zustände `IDLE`/`CALIBRATING`/
  `RESULT`/`LEARN_PROMPT`/`LEARN_RESULT`/`MEASURING`; Transitionen mit Guards und
  Side-Effects zentral gekapselt (`start_calibration`, `accept_calibration`,
  `learn_background`, `finish_background`, `cancel_calibration`, `reset`, …).
  Der Kalibrier-Workflow ist verpflichtend: `RESULT → accept → LEARN_PROMPT`
  („Kalibrierkarte entfernen") → `learn_background` → `LEARN_RESULT`
  (Keypoint-Visualisierung) → `finish_background` → `MEASURING`. Abbruch/
  `Esc` in den Learn-States → IDLE.
  Orthogonale Modell-Eigenschaften: `measuring_enabled`, `automation`,
  `caliber_index`, `language` (aus Settings geladen, via `set_language` wechselbar)
  sowie die Kamera-Einstellungen `camera_device`/`camera_preset`
  (persistiert in `settings.json`; 4K-Default wenn verfügbar).
  `apply_camera_settings()` wendet Änderungen sofort an (Kamera-Neustart;
  Geräte-/Auflösungswechsel setzen Kalibrierung und Messzustand auf IDLE zurück).
  Der Anzeige-Filterzustand (`filters`) wird beim Start aus Settings geladen und
  über `save_filters()`/`flush_filters_if_dirty()` (debounced) persistent gehalten.
  Für BRSMatch führt der Controller den Query-API-Lookup-Zustand (`lookup_status`/
  `lookup_result`/`lookup_error`, asynchron im Daemon-Thread mit Versions-Guard
  gegen veraltete Antworten) und den Wertung-Flow (`request_wertung`,
  `on_wertung_capture`, Bestätigungsdialog bei `existing_scores > 0`,
  `_reset_brsmatch_meta()` nach Erfolg — kein Doppel-Upload).

- **`ui.py` — `BRSAppUI`**: ImGui-Overlay. Zeichnet Menüleiste (Benchrestscore,
  Kalibrierung, Messen, Ansicht, Einstellungen, Sprache), Workflow-Dialoge pro
  `AppState` und das Kalibrier-Ergebnis (AVG/VAR, A/B-Korrektur). Der
  Einstellungen-Reiter bündelt die Einstellungs-Dialoge: „Kamera" (Gerät,
  Auflösung, Rotation als nicht-modaler Dialog; nur unterstützte Presets),
  „Bildfilter" (Anzeige-Panel), „Vision-Konfiguration" und das
  „Schriftgröße"-Untermenü (Präsete). Verdrahtet die
  FSM funktional; alle User-facing-Texte laufen über `tr()` aus `i18n.py`
  (Sprachwechsel wirkt sofort). In der Menüleiste zeigt rechtsbündig einen
  Loss-of-Calibration-Indikator (grün `ok` / orange
  `verschoben`+mm / neutral `n/a`) ab gelerntem Untergrund-Modell.
  Die Kaliber-Auswahl liegt im Messung-Dialog.
  Im Messung-Dialog zeigt der BRSMatch-Abschnitt nach der Etikett-Übernahme den
  Query-API-Lookup-Status und bei Erfolg den Teilnehmer (truncated Nach-/Vorname,
  Kaliber; grün bei `existing_scores == 0`, sonst Hinweis mit Anzahl), den
  „Wertung"-Button (nur bei Messwert) und Upload-Status. Bei vorhandenen Wertungen
  öffnet „Wertung" einen Bestätigungsdialog (Überschreiben) vor dem Upload; nach
  erfolgreichem Upload werden die BRSMatch-Metadaten zurückgesetzt.
  Persistiert die Positionen der Overlay-Fenster „Messung"/„Bildfilter"/
  „Kamera"/„Vision-Konfiguration" mit
  sprachunabhängigen Keys (`ui.window_pos.*` in `settings.json`, Restore per
  `Cond_.once` mit Off-Screen-Guard) sowie den Filterzustand (gedebounct,
  finaler Flush in `shutdown()`).

- **`camera.py` — `BRSCamera(Thread)`**: Endloser Daemon-Thread, liest via
  GStreamer-`appsink` (v4l2src, JPEG, feste `rotate-180`) Bilder und legt
  das aktuellste Frame in `current_frame` ab. Gerät, Auflösung und fps sind
  konfigurierbar (meist aus Settings geladen); der Pipeline-String wird von der
  reinen Funktion `gst_pipeline_string()` gebaut (headless testbar).
  `CAMERA_PRESETS` (1080p30/60, 4K30/60, Fallback 720p30) werden über
  `probe_supported_presets()` gefiltert: primär `v4l2-ctl --list-formats-ext`
  (MJPG, funktioniert auch bei belegtem Gerät), Fallback cv2-Pipeline-Probe;
  Ergebnisse werden pro Gerät gecacht. `list_camera_devices()` enumiert
  `/dev/video*` und blendet Nodes ohne nutzbare Capture-Formate aus
  (Metadata-/Control-Nodes). `pause()/unpause()` sperren das Bild für
  Kalibrierung/Mapping; der `confirmed`-Handshake wartet, bis ein Frame eingefroren ist.

- **`calibration.py` — `VMSCalibrate`**: OpenCV-basiert. Findet die Rasterpunkte der
  Kalibrierkarte (Blob-Detektor + `findCirclesGrid`, Muster 32×18, Raster 4.899 mm),
  schätzt die Projektion/Verzerrung pro Farbkanal (`mat`/`mati` = Welt↔NDC) und erzeugt
  die vierkanaligen LUTs für die GPU (`compute_lut_channels()`).
  `default_lut_channels()` liefert die neutrale, unverzerrte LUT. Berechnet außerdem die
  A/B-Korrekturwerte für die Kameraausrichtung und folgt der aktiven Kalibrierkarte.
  **Single-Pose-Constraint**: Die Kamera ist overhead fix montiert und schaut orthogonal
  auf den Tisch — eine Multi-Pose-Kalibrierung (z.B. `cv2.calibrateCamera`) ist daher
  ausgeschlossen (Details: `measurement.md`, Abschnitt Einzelpose-Randbedingung).
  Nach jedem Versuch werden `last_calibration.png` + `.json` ins Config-Verzeichnis
  geschrieben (Diagnose/Persistenz, Details: `measurement.md`).
- **`calibration_sidecar.py` — `CalibrationResult`**: Pydantic-Modell für das Kalibrier-
  Sidecar (`last_calibration.json`): Qualität, Korrekturen, Matrizen, `acc` und
  Diagnose (`radius_curve`, `quadrants`) sowie das Referenz-Raster der Kalibrierkarte
  in Weltmetrik (`grid_metric`, Grundlage des Karten-Qualitätschecks); Factory
  `from_calibration()`. Das Feld ist optional — alte Sidecars bleiben ladbar.
- **`calibration_card_qc.py` — Karten-Qualitätscheck**: Reine, headless testbare
  Kernlogik (analog `automation.py`). Erkennt das Raster einer eingelegten
  Kalibrierkarte unter der kalibrierten Kamera (identische Pipeline wie die
  Kalibrierung: `findCirclesGrid` → `get_target_grid` → `inv_distortion` →
  `mati`; **3-Frame-Sampling** mit NDC-Mittelung, `QC_SAMPLE_FRAMES`), vermisst
  sie in Weltmetrik (`detect_grid_metric`), gleicht die Einlage per
  **Least-Squares-Homographie** (DLT, alle Punkte — `homography_align`, entfernt
  Versatz/Drehung/Skala/Perspektive, lässt lokale Kartenfehler sichtbar) aus
  und bewertet ±0,075 mm pro Punkt (`check_card`; grün ≤ 50 µm, orange bis
  75 µm — in Spec, rot darüber — out of spec). `pixel_grid` liegt in
  **Rohbild-Pixelkoordinaten** der Blobs (das Overlay wird auf den Roh-Frame
  gezeichnet und erst danach LUT-entzerrt angezeigt — keine zweite
  Distortion-Inversion, sonst verbiegen die Marker). Ergebnis + Overlay werden als
  `last_card_check.json` / `last_card_check_overlay.png` ins Config-Verzeichnis
  persistiert (`save_result`). Controller/UI halten Zustand und Anzeige
  (`run_card_qc` im Kalibrierung-Reiter).

- **`view.py` — `BRSView`**: Koordinaten-/Zoom-Modell. Verwaltet die OpenGL-View-Matrix
  (Zoom 1..18, Drag) und Konvertierungen Pixel ↔ GL-NDC ↔ NDC (geteilt durch
  `aspect_ratio`), die Basis für die metrische Umrechnung. Das Mausrad-Zoomen läuft
  über `BRSScrollZoom` (kontinuierliches Ziel-Smoothing): Jede Raste akkumuliert nur
  ein Ziel-Zoom (+1,5 pro Raste, geklemmt auf 1..18) plus den Maus-Fokuspunkt; der Render-Loop
  gleitet den Zoom pro Frame exponentiell Richtung Ziel (`k = 1−exp(−λ·dt)`, `λ = 25/s`,
  `dt` geklemmt auf 0,25 s) und hält den Punkt unter dem Cursor dabei fest
  (Fokus-Formel `tx = x − ratio·(x − tx0)`, als pure Helfer
  `clamped_zoom_step`/`focus_translation` extrahiert). Ziel-Zoom 1 fährt die
  Translation zusätzlich exponentiell Richtung (0,0) aus; bei Konvergenz
  (`EPS = 0,001` / `EPS_TRANSLATION = 1e−4`) wird exakt auf das Ziel gesnappt und das
  Smoothing deaktiviert. Der alte instante `zoom()` bleibt als Wrapper erhalten.

- **`measurement.py` — `BRSRuler` + `BRSMeasurementBox`**: Vermessung. Der Lineal
  zeichnet bis zu fünf Messpunkte als Viertel-Kreuz-Marker (Ø 2 mm, NE+SW gefüllt)
  und die konzentrischen Kaliber-Kreise über eigene GL-Programme (Kreis-Shader);
  die Messbox hält die Kalibertabelle (`CALIBER`) und liefert den Overlay-Text
  `Mitte`/`Außen` in mm (Mitte = max-paarweise Distanz aller Punkte).

- **`automation.py` — `BRSAutomationIndicator` + `find_center`**: Automation. Dünner
  Zustandshalter (`BRSAutomationIndicator`); `find_center` sucht mit `scipy.minimize`
  das Zentrum des Schusslochs im Klick-Umfeld (adaptive Threshold + radiales Verlustmodell).

- **`brsmatch_api.py` — BRSMatch-API-Client**: Headless testbarer httpx-Client für die
  BRSMatch-Veranstaltungs-API. `lookup()` löst die Etikett-Werte (Sch-Nr, Durchgang,
  Stand, Zeit) gegen `GET /{event_id}/api/lookup` in Teilnehmer/Disziplin/Durchgang
   samt `existing_scores` auf; `submit_measurement()` übermittelt eine Wertung samt
   Screenshot (1280×720-JPEG, Qualität 90) über `POST /{event_id}/api/measurements`.
   Fehler sind `BrsmatchError` mit `kind` (nicht konfiguriert/Auth/keine
   Belegung/Konsistenz/Validierung/HTTP/Netz); der Transport ist injizierbar
   (Tests). `encode_screenshot()` skaliert ein BGR-Bild mit kantengetreuer
   Interpolation (Lanczos) auf 1280×720 und encodiert es als JPEG (Qualität 90).
  Controller/UI halten Zustand und Anzeige; die Lookup-/Upload-Aufrufe laufen in
  Daemon-Threads, damit der GL-/Video-Thread nie blockiert.

- **`calibration_monitor.py` — `BackgroundModel`**: Loss-of-Calibration-Erkennung.
  Lernt im Kalibrier-Workflow (Schritt `LEARN_PROMPT`) den freien Tisch-Untergrund
  (ORB-Keypoints + Descriptoren) und prüft periodisch den Kameraframe per
  Keypoint-Matching + RANSAC-Homographie (Status `ok`/`shifted`/`unavailable` mit
  mm-Abweichung, Hysterese). `draw_keypoints()` visualisiert das Lern-Ergebnis im
  eingefrorenen Frame (`LEARN_RESULT`). Reine headless testbare Kernlogik;
  Controller/UI halten Zustand und Anzeige.

- **`gl_platform.py`**: Wählt die GL-Plattform (`glx`/`egl`) für PyOpenGL **und** GLFW
  **vor** dem Import von `OpenGL.GL` und `glfw.init()`. Details siehe
  [`gl-stack.md`](gl-stack.md).

- **`i18n.py`**: Leichtgewichtiges Übersetzungssystem (GL-frei, headless testbar).
  `tr(msg_id, **kwargs)` liefert den String für die aktive Sprache aus
  `TRANSLATIONS` (Msg-ID → `{de, en, …}`), fällt auf Deutsch zurück und wirft bei
  unbekannter Msg-ID einen `KeyError`. `set_language`/`set_locale`/
  `language_from_locale`; neue Sprachen ergänzen sich rein über Daten
  (`SUPPORTED_LANGUAGES` + `TRANSLATIONS`).

- **`settings.py`**: Persistente App-Settings als JSON im XDG-Config-Verzeichnis
  (`~/.config/benchrestscore/settings.json`). `load()`/`save(patch)`; der Pfad ist
  injizierbar (Tests). Speichert u.a. die gewählte `language`, die
Kamera-Einstellungen (`camera_device`, `camera_preset`) sowie den UI-Zustand:
   Anzeige-Filter (`filters`) und Fensterpositionen der Dialoge
   Messung/Bildfilter/Kamera/Vision-Konfiguration
   (`ui.window_pos.*`). Der `brsmatch`-Block speichert Base-URL, API-Key,
   Event-ID und den Aktivieren-Zustand. Auch die ImGui-Fenster-Persistenz (`imgui.ini`) liegt im
   Config-Verzeichnis (`app.py`, `set_ini_filename` nach `create_context()`).

- **`data/`**: Assets (z.B. `logo.png`). **`tests/`**: Headless FSM-Tests für den
  Controller (siehe [`workflow.md`](workflow.md)).

## Tastatur-Kürzel

| Kürzel | Aktion |
|--------|--------|
| `Q` | Beenden |
| `C` | Kalibrieren starten / bestehende zurücksetzen |
| `Enter` | Kalibrierung übernehmen → `MEASURING` |
| `Esc` | Kalibrierung abbrechen |
| `Space` | aktiven Messpunkt wechseln (durchsteppen) |
| `R` | alle Messpunkte löschen (Reset) |
| `1` / `2` | Kaliber zyklisch wechseln |
| Pfeiltasten | aktiven Messpunkt feinjustieren (`adjust_point`, Schritt 0,05 mm) |
| `M` | Automatik (Autocenter) togglen |

## Thread-Modell

- **Kamera-Thread** (`BRSCamera`): Daemon-Thread, **nur** schreibt `current_frame`.
  Der GL-`Timer`/die Frame-Loop (`render()`) übernimmt das Bild in die GPU-Textur.
  Keine direkte Interaktion mit UI-Objekten; die Frame-Loop erkennt neue Frames über
  Objektidentität (`new_frame is not self._last_frame`).
- **Loss-of-Calibration-Monitor** (`BackgroundMonitorThread`): Daemon-Thread, getaktet mit
  `CHECK_CADENCE_S` im `render()`-Kreislauf entkoppelt. Jeder Tick ruft
  `controller.check_background()` auf (gelerntes Modell + `MEASURING` + Roh-Frame aus
  `current_frame`); ORB/Matching/RANSAC läuft damit **nicht** im GUI-Thread. Ergebnis
  landet über `last_background_check` (atomic gesetzt) für die UI. Modell-
  Invalidierung im UI-Thread tauscht `background_model` aus; der Thread schreibt nur
  zurück, wenn Modell/Zustand unverändert sind (`self.background_model is model`).
  Gestartet nach dem Controller-Wiring, gestoppt in `shutdown()`.
- **Kalibrierung**: Blockierend im GUI-Thread auf einem eingefrorenen Frame (nach
  `pause()`); Ergebnis (`mat`, `mati`, LUTs, `calibrated`) wird nach Abschluss übergeben.
- **Messlogik**: rein UI-Thread, synchron zu den Eingabe-Events. Messwerte (`distance`,
  `radius`) werden ausschließlich bei Tastatur/Maus-Events aktualisiert ⇒ deterministisch,
  kein Race zwischen Threads.

## UI- / Rendering-Aufteilung

- `app.py` (BRSCanvas) = Fenster, GL-Kontext, Event-Callbacks → delegiert an Controller.
- `controller.py` = State-Machine + Modell-Aktionen (UI-agnostisch).
- `ui.py` (BRSAppUI) = ImGui-Overlay/Menüs/Dialoge, ruft nur Controller-Methoden.

## Start

```bash
.venv/bin/python benchrestscore/app.py            # Fullscreen
.venv/bin/python benchrestscore/app.py --windowed # Fenster (Debug/X-Forwarding)
```