# GL / Rendering-Stack

Die App läuft auf dem **imgui-bundle**-Stack: Dear-ImGui mit gebündeltem **GLFW** und
**PyOpenGL**. Siehe auch [`architecture.md`](architecture.md) für den Datenfluss und
[`measurement.md`](measurement.md) für die LUT-Berechnung.

## Komponenten

- **`imgui-bundle`** (pip): Dear-ImGui + `imgui_bundle.python_backends.glfw_backend.GlfwRenderer`.
- **`glfw`** (pip): Fenster/Event-Backend.
- **`PyOpenGL`** (pip): `OpenGL.GL` für Viewport- und Lineal-Programme.
- **apt**: `python3-numpy`, `python3-scipy`, `python3-opencv`, `libglfw3`, `v4l-utils`,
  `gstreamer1.0-plugins-bad` (alle ohne pip; siehe [`README.md`](../README.md)).

## Plattformwahl vor dem Import (`gl_platform.py`)

**Wichtig:** PyOpenGL wählt seine Plattform (`glx`/`egl`) **beim Import** von
`OpenGL.GL` anhand von `PYOPENGL_PLATFORM`. GLFW entscheidet selbst, ob es GLX (X11)
oder EGL nutzt. Stimmen beide nicht überein, findet PyOpenGL den aktuellen GL-Kontext
nicht → Laufzeitfehler.

Deshalb wird `set_gl_platform()` **vor** dem Import von `OpenGL.GL` und vor
`glfw.init()`/`create_window()` aufgerufen (`app.py`-Modulimport-Gerüst):

- `resolve_gl_platform()`: explizite `PYOPENGL_PLATFORM` gewinnt; sonst `DISPLAY`
  vorhanden → `glx`; sonst `egl` (Wayland/headless).
- `set_glfw_platform()`: mit `DISPLAY` zwingt GLFW auf X11 (`PLATFORM_X11`-Hint),
  damit das Fenster unter X11/X-Forwarding sichtbar gemappt wird (unter Wayland/XWayland
  wählt GLFW sonst oft EGL → unsichtbares Fenster).

## Render-Pass-Reihenfolge (Single GL-Kontext)

In `BRSCanvas.render()`:

1. **Viewport**: Webcam-Frame → Textur (`webcam`), View-Matrix als Uniform, dann
   Webcam-Quad mit dem Fragment-Shader zeichnen, der die LUTs `lutr`/`lutg`/`lutb` per
   Textur-Lookup anwendet und danach die optionalen per-Pixel-**Anzeige-Filter**
   (Negativ, Graustufen, Kontrast, Gamma, Helligkeit, Sättigung) als letzten Schritt
   im Shader wirken lässt. Die Filter sind reine Anzeige (GPU-Uniforms), der
   Controller liefert pro Frame die effektiven Werte (`effective_uniforms()`);
   Neutralzustand bzw. deaktivierte Filter ergeben ein unverändertes Bild.
2. **Ruler**: `BRSRuler.draw()` — eigene GL-Programme für Messpunkte (gepunktete Ring-
   Shader) und Kaliber-Kreise (TRIANGLE_STRIP, mit `GL_BLEND`).
3. **ImGui**: `GlfwRenderer.process_inputs()` → `imgui.new_frame()` → `ui.draw()` →
   `imgui.render()` → `imgui_renderer.render(draw_data)`.

Beide Layers nutzen denselben GL-Kontext (PyOpenGL). Reihenfolge garantiert UI über dem
Video. Ruler/Overlays lesen die Webcam-Textur nicht → bleiben ungefiltert (krisp).

### Logo-Textur (Über-uns-Dialog)

`benchrestscore/data/logo.png` wird beim Start einmalig als eigene GL-Textur
(RGBA8, `GL_LINEAR`) hochgeladen und an ImGui als rohe Textur-ID übergeben
(`imgui.ImTextureRef`, `BRSCanvas.__init__`). Der „Über uns“-Dialog zeichnet
es via `imgui.image()` unter dem Urheberhinweis mit 50 % der
Dialog-Inhaltsbreite (`ui.about_logo_size()`, skaliert mit dem
Schrift-Präset; Full-Resolution-Upload, `GL_LINEAR` skaliert zur
Laufzeit). Fehlende/defekte Logodatei degradiert nur das Feature
(einmaliger Log, Dialog ohne Logo).

### Anzeige-Filter & Automation

Die Anzeige-Filter wirken **nur** auf das sichtbare Bild. Die automatische
Loch-Erkennung liest stets ein ungefiltertes (nur LUT-korrigiertes) Bild: Im Frame
mit ausstehendem Auto-Klick wird das Quad zwei Mal gezeichnet — einmal mit neutralem
Filter, der Buffer ausgelesen und an `_process_auto_point(pos, frame)` übergeben,
danach das Quad mit dem aktiven Filter für die tatsächliche Anzeige. So hängt das
Mess-/Erkennungsergebnis nie von der Filterwahl ab (auch nicht bei Negativ, das die
Polarität umkehren würde). Der CPU-Spiegel der Shader-Filteroperation ist
`filter_pixel()` in `controller.py` (maßgeblich für Tests).

## GL-Details

- GL-Kontext: OpenGL **3.3 Core** (`CONTEXT_VERSION_MAJOR/MINOR`, `OPENGL_CORE_PROFILE`,
  `OPENGL_FORWARD_COMPAT`).
- VSync: `swap_interval(0)` — Frame-Limiting macht `BRSCanvas.run()` (Ziel ~60 fps,
  `time.sleep`-Pause), da VSync unter EGL/Fullscreen teils endlos blockiert.
- Texturen: Webcam (RGB8, `GL_NEAREST`) + LUTs (RGBA8, `GL_LINEAR`);
  `GL_CLAMP_TO_EDGE`; `GL_UNPACK_ALIGNMENT 1`.
- Shader: `_compile_shader`/`_link_program`-Helper in `app.py` und `measurement.py`;
  Fehler werfen `RuntimeError` mit Log.
- ImGui-Font: Ubuntu-Mono (DPI-proportionale Pixelgröße relativ zur Framebuffer-Höhe),
  große Variante für Messwerte (~1.35×); Fallback auf die Standard-Font.

### Schriftgrößen-Präsete (Einstellungen-Reiter)

Die Basis-Pixelgröße wird über `fontconfig.compute_font_pixel_size(fb_h, key)` berechnet
(`max(16*scale, int(fb_h * 28/2160 * scale))`, Referenz 28 px @ 2160p). Die Untergrenze
**skaliert mit dem Präset-Faktor**, damit die Stufen bei jeder Fensterhöhe sichtbar
unterscheidbar bleiben (z.B. 720p/1080p: 16/20/24 statt 16/16/16). Der
Reiter **"View"** in der Menüleiste wählt zwischen drei Präseten (Faktoren aus
`FONT_SCALES`):

- **Normal** (×1.0, Startwert) → 16 px @ 1080p / 28 px @ 2160p
- **Large** (×1.25) → 20 px @ 1080p / 35 px @ 2160p
- **XLarge** (×1.5) → 24 px @ 1080p / 42 px @ 2160p

Der Wechsel wirkt zur Laufzeit ohne Neustart — **ohne** Re-Rastern des Atlas.
`BRSCanvas._bake_fonts()` backt beim Start einmalig Basis- und Large-Font in der
Referenzgröße (Normal-Präset). `request_font_scale(key)` validiert gegen
`FONT_SCALES`, aktualisiert `_font_scale_key`/`_font_pixel_size` und reicht die
Metrik an die UI durch. `BRSAppUI.draw()` pusht den Basis-Font mit
`push_font(font, _font_pixel_size)` um die gesamte UI und die Messwert-Variante mit
`push_font(large, size*1.35)`. imgui-bundle 1.92 skaliert über `push_font` korrekt
für Messung **und** Rendering. Die Präset-Wahl wird in `settings.json` persistiert
und beim Start wieder angewendet (`AppController.set_font_scale` / `_load_font_scale`,
analog zu Sprache und Kamera-Einstellungen).

**Warum kein `clear_fonts()`-Runtime-Rebuild:** Empirisch behält imgui-bundle 1.92
nach `clear_fonts()` + `add_font_from_file_ttf` die alten Glyphen-Metriken bei (der
Atlas wird nur als `want_updates` markiert, nie neu gerastert), selbst mit
`io.font_default`-Umstellung. `push_font(font, size)` ist die dafür vorgesehene API.

Präsete wirken **nur** auf die ImGui-Oberfläche; die direkt ins Kamerabild
gerenderten cv2-Texte ("Warte auf Kamera …", Kalibrier-µm) bleiben unverändert.
Dialoggrößen skalieren font-proportional (`ui._next_window_size`) bzw. nutzen
`always_auto_resize`; die Kaliber-Combo in der Menüleiste positioniert sich
schriftskaliert.

## ImGui-Events

`GlfwRenderer(..., attach_callbacks=False)` — `BRSCanvas` setzt **eigene** GLFW-Callbacks
(Tastatur/Maus/Scroll), die sowohl die App-/View-Logik als auch ImGui bedienen:

- ImGui-Events werden immer an `imgui_renderer.*_callback` weitergegeben.
- App-Kürzel (`Q`, `C`, `Enter`, `Esc`, `1/2`, Pfeiltasten, `Space`, `M`) gehen an den
  Controller, wenn ImGui keine Text-Eingabe braucht.
- Maus-Drag/Clicks und Scroll bedienen erst ImGui (`want_capture_mouse`), sonst
  `BRSView` (Zoom/Drag) bzw. `BRSRuler` (Messpunkt).

## Headless-Betrieb

`set_gl_platform()` wählt ohne `DISPLAY` ein `egl`; die App braucht aber einen
GL-Kontext und läuft nicht headless als Bildserver. Für Tests ohne Fenster gibt es die
Controller-FSM-Tests (kein GL) — siehe [`workflow.md`](workflow.md).