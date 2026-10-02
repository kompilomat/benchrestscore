# -*- coding: utf-8 -*-

import os
import sys
import time

import numpy as np
# suppress subnormal warnings from -ffast_math
# https://stackoverflow.com/questions/70612364/numpy-warning-with-django-4-numpy-float64-type-is-zero
np.finfo(np.dtype("float32"))
np.finfo(np.dtype("float64"))
import cv2

# GL-Plattform (glx/egl) muss VOR dem Import von OpenGL.GL stehen
from gl_platform import set_gl_platform
set_gl_platform()

import glfw
from OpenGL import GL as gl
import ctypes
from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

from camera import BRSCamera
from calibration import VMSCalibrate, undistort_frame
from view import BRSView
from measurement import BRSRuler, BRSMeasurementBox
from automation import find_center, metric_to_pixel, BRSAutomationIndicator
from controller import AppController, AppState, TINT_UPDATE_S
from ui import BRSAppUI
from fontconfig import compute_font_pixel_size, DEFAULT_FONT_SCALE_KEY, FONT_SCALES
from settings import default_config_path, default_config_dir
from brsmatch_api import (
    SCREENSHOT_WIDTH as _BRS_SHOT_W,
    SCREENSHOT_HEIGHT as _BRS_SHOT_H,
    encode_screenshot as _brs_encode_screenshot,
)


def _compile_shader(shader_type, source):
    shader = gl.glCreateShader(shader_type)
    gl.glShaderSource(shader, source)
    gl.glCompileShader(shader)
    if not gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS):
        log = gl.glGetShaderInfoLog(shader)
        raise RuntimeError(f"Shader compile error:\n{log}")
    return shader


def _link_program(vs, fs):
    prog = gl.glCreateProgram()
    gl.glAttachShader(prog, vs)
    gl.glAttachShader(prog, fs)
    gl.glBindAttribLocation(prog, 0, "a_position")
    gl.glBindAttribLocation(prog, 1, "a_texcoord")
    gl.glLinkProgram(prog)
    if not gl.glGetProgramiv(prog, gl.GL_LINK_STATUS):
        log = gl.glGetProgramInfoLog(prog)
        raise RuntimeError(f"Program link error:\n{log}")
    gl.glDeleteShader(vs)
    gl.glDeleteShader(fs)
    return prog


def _ease_in_out(t):
    """Smoothstep-Easing: t²·(3−2t) für weiche Animations-Übergänge."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


# Logo (Über-uns-Dialog): Pfad relativ zum Paket (unabhängig vom Startort).
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "logo.png")


def load_logo_image(path):
    """Logo-PNG laden und als `(rgba, aspect)` liefern.

    `rgba` ist ein uint8-Array (h, w, 4) in RGBA-Reihenfolge, `aspect` das
    Seitenverhältnis Breite/Höhe der Datei. Ohne Alphakanal wird ein
    voll-opaker Alphakanal ergänzt. Bei fehlender oder defekter Datei:
    ein Log-Eintrag und `None` (Feature-Degradation, kein Fehler)."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None or img.ndim != 3 or img.shape[2] not in (3, 4):
        print(f"[app] logo unreadable or missing: {path}", flush=True)
        return None
    if img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    h, w = img.shape[:2]
    return (rgba, float(w) / float(h))


class BRSCanvas(object):
    # Dauer der Zentrier-Animation (Leertaste) in Sekunden
    VIEW_ANIM_DURATION = 0.25

    vertex = """#version 330 core
        uniform mat4 view;
        in vec2 a_position;
        in vec2 a_texcoord;
        out vec2 v_texcoord;
        void main()
        {
            gl_Position = view * vec4(a_position, 0.5, 1.0);
            v_texcoord = a_texcoord;
        }
    """

    fragment = """#version 330 core
        uniform sampler2D webcam;
        uniform sampler2D lutr;
        uniform sampler2D lutg;
        uniform sampler2D lutb;
        uniform sampler2D tintmask;
        uniform float u_contrast;
        uniform float u_gamma;
        uniform float u_brightness;
        uniform float u_saturation;
        uniform float u_invert;
        uniform float u_gray;
        uniform float u_tint;
        uniform float u_tint_r;
        uniform float u_tint_g;
        uniform float u_tint_b;
        in vec2 v_texcoord;
        out vec4 frag_color;
        void main()
        {
            vec4 rawr = texture(lutr, v_texcoord.xy);
            vec2 uvr = clamp(vec2(rawr.r + rawr.g/256, rawr.b + rawr.a/256), 0., 1.);
            vec4 rawg = texture(lutg, v_texcoord.xy);
            vec2 uvg = clamp(vec2(rawg.r + rawg.g/256, rawg.b + rawg.a/256), 0., 1.);
            vec4 rawb = texture(lutb, v_texcoord.xy);
            vec2 uvb = clamp(vec2(rawb.r + rawb.g/256, rawb.b + rawb.a/256), 0., 1.);

            vec3 c = vec3(
                texture(webcam, uvr).b,
                texture(webcam, uvg).g,
                texture(webcam, uvb).r);

            // Hintergrund-Einfärbung (Tint) VOR den Anzeige-Filtern. Referenz
            // auf CPU: tint_pixel() in controller.py - identische Operation.
            // u_tint ist die Deckkraft (0 = aus, 1 = opak, <1 = semitransparent).
            float tm = texture(tintmask, v_texcoord.xy).r;
            c = mix(c, vec3(u_tint_r, u_tint_g, u_tint_b), clamp(u_tint * tm, 0., 1.));

            // Anzeige-Filter (per-Pixel, nach der LUT-Korrektur). Referenz
            // auf CPU: filter_pixel() in controller.py - identische
            // Operationen, nur diese Reihenfolge garantiert Gleichcharakter.
            float luma = dot(c, vec3(0.299, 0.587, 0.114));
            c = mix(vec3(luma), c, u_saturation);
            c = mix(c, 1.0 - c, u_invert);
            float k = mix(1.0, 0.0, u_gray);
            c = mix(vec3(dot(c, vec3(0.299, 0.587, 0.114))), c, k);
            c = (c - 0.5) * u_contrast + 0.5 + u_brightness;
            c = pow(clamp(c, 0.0, 1.0), vec3(u_gamma));

            frag_color = vec4(c, 1);
        }
    """

    def __init__(self, devmode=False):
        if not glfw.init():
            raise RuntimeError("Could not initialize OpenGL context")

        def _err(code, desc):
            print(f"[GLFW] error {code}: {desc}", flush=True)
        glfw.set_error_callback(_err)

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)

        monitor = glfw.get_primary_monitor()
        mode = glfw.get_video_mode(monitor)

        if devmode:
            size = mode.size.width // 2, mode.size.height // 2
            monitor = None
        else:
            size = mode.size.width, mode.size.height

        print(f"[app] creating window {size[0]}x{size[1]} "
              f"fullscreen={monitor is not None}", flush=True)
        self.window = glfw.create_window(int(size[0]), int(size[1]), "Benchrestscore",
                                         monitor, None)
        if not self.window:
            glfw.terminate()
            raise RuntimeError("Could not create window")
        glfw.show_window(self.window)

        glfw.make_context_current(self.window)
        # VSync über swap_interval(1) blockiert unter EGL/Fullscreen z.T.
        # unendlich; das Frame-Limiting in run() übernimmt die Taktung.
        glfw.swap_interval(0)

        self.size = size
        self.device_size = glfw.get_framebuffer_size(self.window)

        # ---- controller + ImGui ----
        imgui.create_context()
        # ImGui-Fenster-Persistenz (Position/Größe/Collapsed) ins Config-
        # Verzeichnis legen statt ins aktuelle Arbeitsverzeichnis: unabhängig
        # vom Startort und nicht von einem (gitignored) Repo-File überschattet.
        imgui.get_io().set_ini_filename(
            os.path.join(default_config_dir(), "imgui.ini"))
        self._load_font()
        # attach_callbacks=False: wir setzen eigene GLFW-Callbacks, die sowohl
        # die View-/App-Logik als auch ImGui-Events bedienen.
        self.imgui_renderer = GlfwRenderer(self.window, attach_callbacks=False)
        # Settings (Sprache + Kamera) vor dem ersten UI-Draw laden: der
        # Controller liest die persistierte Sprache/System-Locale sowie die
        # Kamera-Einstellungen (Gerät, Preset).
        self.controller = AppController(self, settings_path=default_config_path())
        # Gespeichertes Preset gegen das aktive Gerät normalisieren (Fallback
        # auf ein unterstütztes Preset, 4K bevorzugt), damit die Kamera korrekt
        # startet.
        self.controller.normalize_camera_preset()
        cam_device = self.controller.camera_device
        cam_preset = self.controller.camera_preset  # (name, w, h, fps)
        cam_w, cam_h, cam_fps = cam_preset[1], cam_preset[2], cam_preset[3]

        # ---- Viewport program (webcam quad + LUTs) ----
        self.view_proj = BRSView(cam_w, cam_h)
        self.program = _link_program(
            _compile_shader(gl.GL_VERTEX_SHADER, BRSCanvas.vertex),
            _compile_shader(gl.GL_FRAGMENT_SHADER, BRSCanvas.fragment),
        )
        self.view_loc = gl.glGetUniformLocation(self.program, "view")

        # full-screen quad (4 verts: pos + texcoord)
        quad = np.array([
            # pos xy, texcoord uv
            -1, -1,  0, 1,
            -1,  1,  0, 0,
            +1, -1,  1, 1,
            +1,  1,  1, 0,
        ], dtype=np.float32)
        self.vao = gl.glGenVertexArrays(1)
        self.vbo = gl.glGenBuffers(1)
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, quad.nbytes, quad, gl.GL_STATIC_DRAW)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, 16, ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 2, gl.GL_FLOAT, gl.GL_FALSE, 16, ctypes.c_void_p(8))
        gl.glBindVertexArray(0)

        self.webcam_tex = int(gl.glGenTextures(1))
        self.lutr_tex = int(gl.glGenTextures(1))
        self.lutg_tex = int(gl.glGenTextures(1))
        self.lutb_tex = int(gl.glGenTextures(1))
        # Tint-Masken-Textur (Anzeige-Hilfe): initial leer (1x1-Null), wird im
        # Render-Zyklus bei geändertem `tint_tick` neu geladen. `u_tint=0`
        # macht die leere/veraltete Maske zum No-op.
        self.tint_tex = int(gl.glGenTextures(1))
        self._upload_texture(self.tint_tex,
                             np.zeros((1, 1, 3), dtype=np.uint8), linear=True)
        self._last_tint_tick = None
        self._last_tint_update = None

        # camera + calibration + view (aus den geladenen Kamera-Einstellungen)
        self.capture_worker = BRSCamera(device=cam_device, width=cam_w,
                                        height=cam_h, fps=cam_fps,
                                        rotate=self.controller.camera_rotate)
        self.capture_worker.start()
        self.calibration = VMSCalibrate(cam_w, cam_h)
        self.mbox = BRSMeasurementBox(self)
        self.ruler = BRSRuler(self.view_proj, self.calibration, self.mbox)
        self.indicator = BRSAutomationIndicator(self)

        self.default_lut = self.calibration.default_lut_channels()
        self._upload_texture(self.lutr_tex, self.default_lut, internal=gl.GL_RGBA8)
        self._upload_texture(self.lutg_tex, self.default_lut, internal=gl.GL_RGBA8)
        self._upload_texture(self.lutb_tex, self.default_lut, internal=gl.GL_RGBA8)
        self._upload_texture(self.webcam_tex, self.capture_worker.waiting_screen)

        # ---- Logo (Über-uns-Dialog): eigene GL-Textur, an ImGui als rohe
        # Textur-ID übergeben (ImTextureRef). Full-Resolution-Upload;
        # GL_LINEAR skaliert zur Laufzeit (design.md D1). Fehlende Datei -> None.
        logo = load_logo_image(LOGO_PATH)
        if logo is not None:
            rgba, aspect = logo
            self.logo_tex = int(gl.glGenTextures(1))
            self._upload_texture(self.logo_tex, rgba, internal=gl.GL_RGBA8,
                                 linear=True)
            self._logo_ref = imgui.ImTextureRef(self.logo_tex)
            self._logo_aspect = aspect
        else:
            self._logo_ref = None
            self._logo_aspect = None

        # ---- controller wiring ----
        self.controller.calibration = self.calibration
        self.controller.capture_worker = self.capture_worker
        self.controller.ruler = self.ruler
        self.controller.mbox = self.mbox
        self.controller.indicator = self.indicator
        self.ui = BRSAppUI(self.controller)
        self._sync_font_to_ui()
        if self._logo_ref is not None:
            self.ui.set_logo(self._logo_ref, self._logo_aspect)

        # Loss-of-Calibration-Monitor: periodische Checks laufen in einem eigenen
        # Thread (`BackgroundMonitorThread`), damit ORB/Matching/RANSAC den
        # Render-Thread nicht blockieren. Ergebnis wird über
        # `controller.last_background_check` von der UI gelesen.
        self.controller.start_background_monitor()

        self.wants_exit = False
        self.is_drag = False
        self.point_drag = None
        self.drag_start = np.array([0, 0]).astype(int)
        self.drag_xy = np.array([0, 0]).astype(int)
        self._last_cursor = [0, 0]
        self._pending_auto_point = None
        self._pending_wertung_capture = False
        self._wertung_capture_next = False
        self._view_anim = None
        self._last_scroll_step_t = 0.0

        glfw.set_key_callback(self.window, self._on_key)
        glfw.set_char_callback(self.window, self._on_char)
        glfw.set_mouse_button_callback(self.window, self._on_mouse_button)
        glfw.set_cursor_pos_callback(self.window, self._on_mouse_move)
        glfw.set_scroll_callback(self.window, self._on_scroll)
        glfw.set_framebuffer_size_callback(self.window, self._on_framebuffer_resize)

        self.on_resize(self.device_size)

    # ---------- input callbacks (wired to controller + view) ----------

    ARROW_KEYS = frozenset((glfw.KEY_UP, glfw.KEY_DOWN, glfw.KEY_LEFT, glfw.KEY_RIGHT))

    def _on_framebuffer_resize(self, window, width, height):
        self.on_resize((width, height))

    def _on_char(self, window, char):
        # Zeichen-Eingabe für ImGui (InputText-Felder): `keyboard_callback`
        # liefert nur Key-Events, keine Text-Zeichen — ohne diese Weiterleitung
        # lassen sich Textfelder nicht befüllen.
        self.imgui_renderer.char_callback(window, char)

    def _on_key(self, window, key, scancode, action, mods):
        # ImGui immer die Key-Events geben (UI-Interaktion)
        if action == glfw.PRESS or action == glfw.RELEASE:
            self.imgui_renderer.keyboard_callback(window, key, scancode, action, mods)
        # Text-Eingabe (InputText/InputInt/...) aktiv -> App-Shortcuts unterdrücken.
        # ImGui erhält den Key weiterhin (s.o.); nur die Shortcut-Dispatch-Kette
        # wird übersprungen, damit K/C/Q/... beim Tippen nicht auslösen.
        # Ausnahme: Escape schließt den manuellen Etikett-Eingabe-Dialog (nur
        # PRESS, damit Gedrückthalten nicht erneut auslöst).
        if self.imgui_renderer.io.want_text_input:
            if key == glfw.KEY_ESCAPE and action == glfw.PRESS \
                    and self.controller.manual_dialog_open:
                self.controller.close_manual_dialog()
            return
        # App-Kürzel NICHT von ImGui verschlucken lassen: diese sind globale
        # Shortcuts (Q/K/C/1/2/M/Pfeiltasten). Nur wenn ImGui eine Text-Eingabe
        # aktiv hat, weichen wir (dort gibt es ohnehin keine solchen Kürzel).
        # REPEAT nur für Pfeiltasten zulassen (Gedrückthalten = weiterjustieren),
        # damit andere Shortcuts nicht wiederholt auslösen.
        if action == glfw.REPEAT and key not in BRSCanvas.ARROW_KEYS:
            return
        if action != glfw.PRESS and action != glfw.REPEAT:
            return
        ctrl = self.controller
        if key == glfw.KEY_Q:
            ctrl.quit()
        elif key == glfw.KEY_K:
            ctrl.request_calibration()
        elif key == glfw.KEY_C:
            self.start_fit_measurements()
        elif key == glfw.KEY_ENTER:
            # Kontextabhängig: Ergebnis akzeptieren -> Lern-Schritt ->
            # Lern-Ergebnis abschließen -> Messmodus
            if ctrl.state is AppState.RESULT:
                ctrl.accept_calibration()
            elif ctrl.state is AppState.LEARN_PROMPT:
                ctrl.learn_background()
            elif ctrl.state is AppState.LEARN_RESULT:
                ctrl.finish_background()
        elif key == glfw.KEY_ESCAPE:
            # Offener manueller Etikett-Eingabe-Dialog hat Vorrang: Escape
            # bricht die Eingabe ab (wirft ab, keine Übernahme); andernfalls
            # das bestehende Kalibrier-Abbruch-Verhalten.
            if ctrl.manual_dialog_open:
                ctrl.close_manual_dialog()
            else:
                ctrl.cancel_calibration()
        elif key == glfw.KEY_SPACE:
            ctrl.cycle_active_point()
            self._start_center_anim()
        elif key == glfw.KEY_R:
            ctrl.reset_points()
        elif key == glfw.KEY_1:
            ctrl.increment_caliber(-1)
        elif key == glfw.KEY_2:
            ctrl.increment_caliber(+1)
        elif key == glfw.KEY_UP:
            ctrl.adjust_point("Up")
        elif key == glfw.KEY_DOWN:
            ctrl.adjust_point("Down")
        elif key == glfw.KEY_LEFT:
            ctrl.adjust_point("Left")
        elif key == glfw.KEY_RIGHT:
            ctrl.adjust_point("Right")
        elif key == glfw.KEY_M:
            ctrl.toggle_automation()
        elif key == glfw.KEY_F:
            ctrl.toggle_filters_active()
        elif key == glfw.KEY_E:
            ctrl.scan_sticker()

    def _on_mouse_button(self, window, button, action, mods):
        # ImGui-Events immer bedienen
        self.imgui_renderer.mouse_button_callback(window, button, action, mods)
        if self.imgui_renderer.io.want_capture_mouse:
            # Klick gehört ImGui (Menü/Panel/Dialog): keine App-eigene Drag-/
            # Klick-Logik starten. Einen ggf. laufenden Drag-Zustand aber immer
            # räumen, damit er nicht als View-Pan hängen bleibt (z.B. Release
            # im Menü öffnet Popup -> want_capture_mouse wird erst danach wahr).
            if action == glfw.RELEASE and button == glfw.MOUSE_BUTTON_LEFT:
                self.is_drag = False
                self.point_drag = None
            return
        # letzte bekannte Cursorposition verwenden (kein get_cursor_pos im
        # Callback-Kontext -> blockiert auf diesem Display)
        x, y = self._last_cursor
        if action == glfw.PRESS:
            if button == glfw.MOUSE_BUTTON_LEFT:
                self.is_drag = True
                self.drag_start[:] = [x, y]
                self.drag_xy[:] = [x, y]
                # Marker-Hit entscheidet: Punkt verschieben statt View pannen
                self.point_drag = self._hit_point((x, y))
                # Gegriffener Punkt wird sofort aktiv
                if self.point_drag is not None:
                    self.controller.select_point(self.point_drag)
        elif action == glfw.RELEASE:
            if button == glfw.MOUSE_BUTTON_LEFT:
                self.is_drag = False
                moved = np.linalg.norm(np.array([x, y]) - self.drag_start) >= 4
                if self.point_drag is not None:
                    if not moved:
                        # Klick auf Marker -> aktiven Punkt wählen
                        self.controller.select_point(self.point_drag)
                else:
                    if not moved:
                        # Klick statt Drag -> neuen Messpunkt setzen
                        if self.controller.automation:
                            # Automatische Detektion erfolgt in render() auf
                            # sauberem Framebuffer (ohne Marker/Overlays).
                            self._pending_auto_point = (x, y)
                        else:
                            self._set_measurement_point((x, y))
                self.point_drag = None
            elif button == glfw.MOUSE_BUTTON_RIGHT:
                hit = self._hit_point((x, y))
                if hit is not None:
                    self.controller.remove_point(hit)
            elif button == glfw.MOUSE_BUTTON_MIDDLE:
                self._cancel_view_anim()
                self._start_reset_anim()

    def _hit_point(self, pos):
        """Punkt-Marker unter der Maus ermitteln (nur im Messmodus), sonst None."""
        ctrl = self.controller
        if ctrl.state is not AppState.MEASURING or not self.ruler.enabled:
            return None
        return self.ruler.hit_test(pos, self.size)

    def _start_center_anim(self):
        """Zentrier-Animation auf den aktiven Messpunkt starten (Leertaste).

        Kein Op bei fehlenden Punkten. Start = aktuelle View-Translation, Ziel =
        Zentrierung von `ruler.positions[active_idx]` (Weltkoordinaten). Zoom bleibt
        unverändert. Die Animation wird in `render()` ausgeführt."""
        if getattr(self, "ruler", None) is None or self.ruler.point_count == 0:
            return
        wx, wy = self.ruler.positions[self.ruler.active_idx]
        tx1, ty1 = self.view_proj.center_translation(wx, wy)
        # Zoom unverändert: Start == Ziel (nur pan)
        z = self.view_proj.current_zoom
        self._begin_view_anim(z1=z, tx1=tx1, ty1=ty1)

    def _start_reset_anim(self):
        """Animierter View-Reset (Mittelklick): Zoom -> 1, Translation -> (0,0).

        Fährt weich auf das volle Kamerabild statt instantan zu springen. Die
        Animation wird in `render()` ausgeführt; Abbruch über `_cancel_view_anim()`."""
        self._begin_view_anim(z1=1.0, tx1=0.0, ty1=0.0)

    def start_fit_measurements(self):
        """Animiertes Einpassen aller Messpunkte (Ansicht -> „Crop Messung").

        Ohne Messpunkte wird die Ansicht auf das volle Kamerabild zurückgesetzt
        (Zoom -> 1, Translation -> 0; wie Mittelklick). Bei degenerierter
        Bounding-Box (ein einzelner Punkt) wird nur zentriert (Zoom unverändert,
        wie Leertaste); sonst passt die View Zoom+Pan so an, dass alle Messpunkte
        UND der große Messkreis mit ~5 % Rand im Bild liegen.
        """
        if getattr(self, "ruler", None) is None or self.ruler.point_count == 0:
            self._start_reset_anim()
            return
        target = self.view_proj.fit_target(
            self.ruler.fit_extent(),
            self.size[0], self.size[1], margin=0.25)
        if target is None:
            # Degeneriert (ein Punkt): nur zentrieren, Zoom unverändert
            self._start_center_anim()
            return
        z1, tx1, ty1 = target
        self._begin_view_anim(z1=z1, tx1=tx1, ty1=ty1)

    def _begin_view_anim(self, z1, tx1, ty1):
        """Gemeinsame View-Animation (Zoom + Translation) aufsetzen.

        Start = aktuelle View (Zoom und Translation), Ziel = übergebener Zustand.
        `sx`/`sy` (Basis-Skala) und `z0` werden zum Startzeitpunkt eingefroren;
        `render()` interpoliert Zoom und Translation mit ease-in-out."""
        self.view_proj.scroll_zoom.cancel()
        sx, sy = self.view_proj.aspect_scale(self.size[0], self.size[1])
        self._view_anim = {
            "t0": time.monotonic(),
            "dur": BRSCanvas.VIEW_ANIM_DURATION,
            "z0": self.view_proj.current_zoom,
            "z1": float(z1),
            "sx": sx,
            "sy": sy,
            "tx0": self.view_proj.view[3, 0],
            "ty0": self.view_proj.view[3, 1],
            "tx1": float(tx1),
            "ty1": float(ty1),
        }

    def _cancel_view_anim(self):
        """Laufende View-Animation und Scroll-Smoothing abbrechen (Nutzer übernimmt die View)."""
        self.view_proj.scroll_zoom.cancel()
        self._view_anim = None

    def _set_measurement_point(self, pos):
        """Messpunkt manuell setzen (keine Automation; nur nach Kalibrierung)."""
        ctrl = self.controller
        if ctrl.state is not AppState.MEASURING or not self.ruler.enabled:
            return
        self.ruler.add_point(pos, self.size, view=self.view_proj.view)

    def _process_auto_point(self, pos, frame=None):
        """Vorgemerkten Klick mit Automation im Render-Zyklus verarbeiten.

        Muss nach dem Webcam-Quad, aber VOR ruler.draw()/ImGui laufen: der
        Framebuffer enthält dann nur das Kamera-/LUT-Bild, nie Marker/Overlays.
        `frame` ist das BGR-Bild, das der Aufrufer bereits aus dem (ungefilterten)
        Render-Pass gelesen hat (standardmäßig wird es hier per _grab_frame
        nachgezogen, wenn der Aufrufer es nicht liefert)."""
        ctrl = self.controller
        if ctrl.state is not AppState.MEASURING or not self.ruler.enabled:
            return
        res = None
        try:
            if frame is None:
                frame = self._grab_frame()
            radius = self.mbox.radius()
            res = find_center(frame, self.view_proj, list(pos), self.size,
                              self.calibration, radius)
        except Exception as _e:
            print(f"[app] automation find_center failed: {_e}", flush=True)
        if res is not None and res.ok:
            center_px = metric_to_pixel(self.view_proj, res.center_metric,
                                        self.size, self.calibration)
            self.ruler.add_point((float(center_px[0]), float(center_px[1])),
                                 self.size, view=self.view_proj.view,
                                 auto_offset_mm=res.offset_mm)
            self.ruler.flash_result(raw_px=pos,
                                    center_px=(float(center_px[0]),
                                               float(center_px[1])),
                                    search_radius_px=res.radius_px, ok=True)
        else:
            self.ruler.add_point(pos, self.size, view=self.view_proj.view)
            self.ruler.auto_error = True
            self.ruler.auto_error_at = time.monotonic()
            self.ruler.flash_result(raw_px=pos, center_px=pos,
                                    search_radius_px=res.radius_px if res else None,
                                    ok=False)

    def _grab_frame(self):
        """Aktuellen Framebuffer als BGR-Bild (für Automation) auslesen."""
        w, h = self.device_size
        gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)
        buf = gl.glReadPixels(0, 0, w, h, gl.GL_RGB, gl.GL_UNSIGNED_BYTE)
        img = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
        img = np.flipud(img)          # OpenGL: Zeile 0 unten -> spiegeln
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def request_wertung_capture(self):
        """Framebuffer-Kopie für die BRSMatch-Wertung im übernächsten Frame anfordern.

        Der Render-Loop erfasst am Frame-Ende (nach dem ImGui-Pass, vor
        `swap_buffers`) den vollständigen Framebuffer — komplettes Fenster
        inkl. Menüleiste: Kamera-/LUT-Bild, Messmarker und Messung-Dialog —
        skaliert ihn auf 1280×720 und encodiert ihn als JPEG (Qualität 90).
        Die Erfassung wird um einen Frame verzögert,
        damit ein im
        selben Frame geschlossener Dialog (Überschreib-Bestätigung) nicht mehr
        im Bild ist. Die Bytes gehen an `controller.on_wertung_capture`.
        """
        self._pending_wertung_capture = True

    def _process_wertung_capture(self):
        """Framebuffer-Kopie erfassen, skalieren, encodieren und übergeben.

        Läuft im UI-/Video-Thread direkt nach dem ImGui-Render (das Overlay
        liegt zu diesem Zeitpunkt bereits im Framebuffer, wurde aber noch nicht
        geswappt). Der Screenshot zeigt das vollständige Fenster inkl.
        Menüleiste — kein Ausschnitt. Der eigentliche HTTP-Upload läuft im
        Controller-Thread.
        """
        self._pending_wertung_capture = False
        img = self._grab_frame()
        # Auf 16:9-Zielauflösung skalieren + JPEG encodieren (reine Funktion).
        jpg = _brs_encode_screenshot(img, _BRS_SHOT_W, _BRS_SHOT_H)
        self.controller.on_wertung_capture(jpg)

    def _on_mouse_move(self, window, x, y):
        self._last_cursor = [x, y]
        # ImGui io direkt setzen. Keine GLFW-Abfragen im Callback-Kontext
        # (get_window_attrib/get_cursor_pos schlagen auf diesem Display fehl
        # und blockieren die Loop).
        self.imgui_renderer.io.add_mouse_pos_event(x, y)
        if self.imgui_renderer.io.want_capture_mouse:
            # ImGui (Menü/Panel) hält die Maus: laufenden View-Drag sofort
            # beenden, statt den Zustand bis zum Release hängen zu lassen.
            self.is_drag = False
            self.point_drag = None
            return
        if self.is_drag:
            dx, dy = x - self.drag_xy[0], y - self.drag_xy[1]
            if self.point_drag is not None:
                # Marker-Drag: Messpunkt der Maus folgen lassen
                self.ruler.move_point(self.point_drag, (x, y), self.size)
            else:
                # View-Drag: laufende Zentrier-Animation abbrechen
                self._cancel_view_anim()
                v = self.view_proj.drag(dx, dy, *self.size)
                self.ruler.update(view=v)
            self.drag_xy[:] = [x, y]

    def _on_scroll(self, window, xoff, yoff):
        self.imgui_renderer.scroll_callback(window, xoff, yoff)
        if self.imgui_renderer.io.want_capture_mouse:
            return
        # Ziel-Zoom an der letztbekannten Mausposition akkumulieren (kein
        # get_cursor_pos im Callback -> blockiert auf diesem Display). Das
        # eigentliche Gleiten passiert im Render-Loop (Scroll-Smoothing).
        x, y = self._last_cursor
        self._cancel_view_anim()
        self.view_proj.scroll_zoom.on_scroll(
            yoff, x, y, *self.size,
            current_zoom=self.view_proj.current_zoom,
            max_zoom=self.view_proj.max_zoom)
        self._last_scroll_step_t = time.monotonic()

    # ---------- helpers ----------

    def _bind_texture(self, unit, tex_id):
        gl.glActiveTexture(gl.GL_TEXTURE0 + unit)
        gl.glBindTexture(gl.GL_TEXTURE_2D, int(tex_id))

    def _upload_texture(self, tex_id, data, internal=gl.GL_RGB8,
                        linear=False):
        h, w = data.shape[:2]
        gl.glBindTexture(gl.GL_TEXTURE_2D, int(tex_id))
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, internal, w, h, 0,
                        gl.GL_RGB if data.shape[2] == 3 else gl.GL_RGBA,
                        gl.GL_UNSIGNED_BYTE, data)
        filt = gl.GL_LINEAR if linear else gl.GL_NEAREST
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, filt)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, filt)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

    def set_luts(self, luts):
        """luts: list of 3 four-channel LUTs (BGR order from compute_lut_channels)."""
        # compute_lut_channels returns [b, g, r]; shader expects lutr=red, lutg=green, lutb=blue
        for i, lut in enumerate((luts[2], luts[1], luts[0])):
            self._upload_texture((self.lutr_tex, self.lutg_tex, self.lutb_tex)[i], lut, internal=gl.GL_RGBA8, linear=True)

    def restart_camera(self, device, width, height, fps, rotate=180,
                       rebuild_calibration=True):
        """Kamera-Thread mit neuen Einstellungen neu starten.

        Läuft im GUI-Thread (GL-Textur-Uploads). `rebuild_calibration=True`
        baut `VMSCalibrate` und die neutralen LUTs neu (Auflösungs-/Geräte-/
        Rotations-Wechsel); False behält die bestehende Kalibrierung. Der
        Ruler teilt die Kalibrier-Referenz und wird deshalb mitgeführt.
        """
        self._cancel_view_anim()
        old = self.capture_worker
        if old is not None:
            old.stop()
            old.join(timeout=2)
        worker = BRSCamera(device=device, width=width, height=height, fps=fps,
                           rotate=rotate)
        worker.start()
        self.capture_worker = worker
        if rebuild_calibration or self.calibration is None:
            self.calibration = VMSCalibrate(width, height)
            self.default_lut = self.calibration.default_lut_channels()
            self._upload_texture(self.lutr_tex, self.default_lut,
                                 internal=gl.GL_RGBA8)
            self._upload_texture(self.lutg_tex, self.default_lut,
                                 internal=gl.GL_RGBA8)
            self._upload_texture(self.lutb_tex, self.default_lut,
                                 internal=gl.GL_RGBA8)
            self.ruler.calib = self.calibration
        self.view_proj.set_dimensions(width, height, *self.size)
        self._upload_texture(self.webcam_tex, worker.waiting_screen)
        self._last_frame = None
        self.controller.calibration = self.calibration
        self.controller.capture_worker = self.capture_worker

    def _draw_viewport(self, filt=None, tint=None):
        """Webcam-Quad mit dem View/Filter-Programm zeichnen.

        `filt` sind die 6 Filter-Uniform-Werte (contrast, gamma, brightness,
        saturation, invert, gray); None -> effective_uniforms() des Controllers
        (Neutralzustand => identisches Bild). `tint` ist das 4-Tupel
        (u_tint, r, g, b) der Hintergrund-Einfärbung; None -> effective_tint().
        Die LUTs bestimmen die verzerrte Abtastung; der Filter ist der letzte
        Schritt im Fragment-Shader. Der Auto-Erkennungs-Pass übergibt explizit
        `tint=(0,0,0,0)`, damit das gelesene Bild ungefärbt ist."""
        if filt is None:
            filt = self.controller.effective_uniforms()
        if tint is None:
            tint = self.controller.effective_tint()
        gl.glUseProgram(self.program)
        gl.glBindVertexArray(self.vao)
        gl.glUniformMatrix4fv(self.view_loc, 1, gl.GL_FALSE, self.view_proj.view.flatten())
        # Sampler- und Filter-Uniform-Locations einmalig abfragen
        if getattr(self, "_samplers_set", None) is None:
            gl.glUniform1i(gl.glGetUniformLocation(self.program, "webcam"), 0)
            gl.glUniform1i(gl.glGetUniformLocation(self.program, "lutr"), 1)
            gl.glUniform1i(gl.glGetUniformLocation(self.program, "lutg"), 2)
            gl.glUniform1i(gl.glGetUniformLocation(self.program, "lutb"), 3)
            gl.glUniform1i(gl.glGetUniformLocation(self.program, "tintmask"), 4)
            self._filter_locs = tuple(
                gl.glGetUniformLocation(self.program, n)
                for n in ("u_contrast", "u_gamma", "u_brightness",
                          "u_saturation", "u_invert", "u_gray"))
            self._tint_locs = tuple(
                gl.glGetUniformLocation(self.program, n)
                for n in ("u_tint", "u_tint_r", "u_tint_g", "u_tint_b"))
            self._samplers_set = True
        for loc, value in zip(self._filter_locs, filt):
            gl.glUniform1f(loc, value)
        for loc, value in zip(self._tint_locs, tint):
            gl.glUniform1f(loc, value)
        self._bind_texture(0, self.webcam_tex)
        self._bind_texture(1, self.lutr_tex)
        self._bind_texture(2, self.lutg_tex)
        self._bind_texture(3, self.lutb_tex)
        self._bind_texture(4, self.tint_tex)
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        gl.glBindVertexArray(0)

    # ---------- Font ----------

    FONT_CANDIDATES = [
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono[wght].ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoMono-Regular.ttf",
    ]

    # Faktor der großen Messwert-Variante relativ zur Basis
    _LARGE_FACTOR = 1.35

    def _load_font(self):
        """Font-Präsete initialisieren: Präset "normal" aktiv, Basis- und
        Large-Font einmalig backen. Die Größen-Umschaltung passiert zur
        Laufzeit über `imgui.push_font(font, size)` in der UI — ein
        Runtime-Re-Rastern des Atlas wird dadurch nicht benötigt."""
        self._font_scale_key = DEFAULT_FONT_SCALE_KEY
        self._bake_fonts()
        self._sync_font_to_ui()

    def _find_font_path(self):
        """Ersten vorhandenen Font-Kandidaten (Ubuntu Mono bevorzugt) liefern."""
        import os as _os
        return next((p for p in BRSCanvas.FONT_CANDIDATES if _os.path.exists(p)), None)

    def _current_font_pixel_size(self):
        """Basis-Pixelgröße für das aktive Präset und die aktuelle Fensterhöhe."""
        return compute_font_pixel_size(self.device_size[1], self._font_scale_key)

    def _sync_font_to_ui(self):
        """Aktuelle Font-Metrik an die UI durchreichen (Dialoggrößen)."""
        if getattr(self, "ui", None) is None:
            return
        self.ui.set_font_pixel_size(getattr(self, "_font_pixel_size", 13.0))
        self.ui.set_large_font(getattr(self, "font_large", None))

    def _bake_fonts(self):
        """Basis- und Large-Font einmalig backen (Referenz: Normal-Präset).

        imgui-bundle 1.92 kann den Font-Atlas zur Laufzeit nicht zuverlässig
        neu rastern (`clear_fonts()` + `add_font_from_file_ttf` behält alte
        Glyphen-Metriken, siehe design.md D2). Deshalb wird einmalig gebacken
        und die Präset-Größe per `push_font(font, size)` angewendet — das
        Backing skaliert lazy und ist für Messung UND Rendering korrekt.

        Ist kein externer Font ladbar (kein Kandidat vorhanden oder TTF-Fehler),
        fällt die App auf die skalierbare ImGui-Default-Vektor-Font zurück —
        die Präsete bleiben damit auf jedem System sichtbar wirksam.
        """
        fb_h = self.device_size[1]  # DPI- (Framebuffer-) Höhe
        ref = compute_font_pixel_size(fb_h, "normal")
        font_path = self._find_font_path()

        io = imgui.get_io()
        io.fonts.clear_fonts()
        try:
            if font_path is None:
                raise RuntimeError("no font candidate found")
            cfg = imgui.ImFontConfig()
            cfg.oversample_h = 2
            cfg.oversample_v = 2
            self.font = io.fonts.add_font_from_file_ttf(font_path, float(ref), cfg)
            # Größere Variante für Messwerte (~1.35x der Basis)
            cfg2 = imgui.ImFontConfig()
            cfg2.oversample_h = 2
            cfg2.oversample_v = 2
            self.font_large = io.fonts.add_font_from_file_ttf(
                font_path, float(ref * BRSCanvas._LARGE_FACTOR), cfg2)
        except Exception as _e:
            # Fallback: skalierbare Default-Vektor-Font in Referenz-Größe
            print(f"[app] font fallback to default (ref={ref}): {_e}", flush=True)
            cfg = imgui.ImFontConfig()
            cfg.size_pixels = float(ref)
            self.font = io.fonts.add_font_default_vector(cfg)
            cfg2 = imgui.ImFontConfig()
            cfg2.size_pixels = float(ref * BRSCanvas._LARGE_FACTOR)
            self.font_large = io.fonts.add_font_default_vector(cfg2)
        io.font_default = self.font
        self._font_pixel_size = self._current_font_pixel_size()
        print(f"[app] font src={font_path or 'default'} ref={ref} "
              f"scale={self._font_scale_key} size={self._font_pixel_size}",
              flush=True)

    def request_font_scale(self, key):
        """Präset-Größe sofort wechseln (wirkt ab dem nächsten Frame).

        Kein Re-Rastern nötig: `BRSAppUI.draw()` pusht die Fonts pro Frame mit
        der aktiven Größe. Ungültige Keys werfen einen ValueError; ein Wechsel
        auf das bereits aktive Präset ist ein No-op."""
        if key not in FONT_SCALES:
            raise ValueError(
                f"unknown font scale key {key!r}; expected one of {sorted(FONT_SCALES)}")
        if key == self._font_scale_key:
            return
        self._font_scale_key = key
        self._font_pixel_size = self._current_font_pixel_size()
        self._sync_font_to_ui()

    # ---------- frame loop ----------

    def render(self):
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        # webcam frame -> texture, nur wenn ein neues Frame vorliegt
        new_frame = self.capture_worker.current_frame
        if new_frame is not None and new_frame is not getattr(self, "_last_frame", None):
            self._upload_texture(self.webcam_tex, new_frame)
            self._last_frame = new_frame

        # Anzeige-Tint-Maske -> Textur (nur bei Änderung; Muster `_last_frame`).
        # Die Maske wird im Render-Loop gedrosselt nachgeführt (Referenz-Skala,
        # ~18 ms @4K statt 640 ms Voll-Auflösung) und im selben Pass hochgeladen
        # — race-frei, ohne Monitor-Thread-Flaschenhals. Ohne Maske bleibt die
        # leere 1x1-Textur (No-op, u_tint=0 bzw. tm=0).
        now = time.monotonic()
        if (self._last_tint_update is None
                or now - self._last_tint_update >= TINT_UPDATE_S):
            self._last_tint_update = now
            self.controller.update_tint_mask()
        model = self.controller.background_model
        if (model.tint_mask is not None
                and model.tint_tick != self._last_tint_tick):
            m = np.dstack((model.tint_mask * 255, model.tint_mask * 255,
                           model.tint_mask * 255)).astype(np.uint8)
            self._upload_texture(self.tint_tex, m, linear=True)
            self._last_tint_tick = model.tint_tick

        # View-Animation (Leertaste/Mittelklick/Crop): zeitbasierte Interpolation
        # von Translation UND Zoom mit ease-in-out; am Ende exakt das Ziel setzen.
        if self._view_anim is not None:
            a = self._view_anim
            t = (now - a["t0"]) / a["dur"]
            if t >= 1.0:
                self.view_proj.view[0, 0] = a["z1"] * a["sx"]
                self.view_proj.view[1, 1] = a["z1"] * a["sy"]
                self.view_proj.view[3, 0] = a["tx1"]
                self.view_proj.view[3, 1] = a["ty1"]
                self.view_proj.current_zoom = a["z1"]
                self._view_anim = None
            else:
                e = _ease_in_out(t)
                z = a["z0"] + e * (a["z1"] - a["z0"])
                self.view_proj.view[0, 0] = z * a["sx"]
                self.view_proj.view[1, 1] = z * a["sy"]
                self.view_proj.view[3, 0] = a["tx0"] + e * (a["tx1"] - a["tx0"])
                self.view_proj.view[3, 1] = a["ty0"] + e * (a["ty1"] - a["ty0"])
                self.view_proj.current_zoom = z
            self.ruler.update(view=self.view_proj.view)

        # Scroll-Zoom-Smoothing (Mausrad): exponentielles Ziel-Smoothing.
        # Abgebrochen durch jede View-übernehmende Interaktion (Drag, Resize,
        # Kamera-Neustart, Leertaste/Mittelklick/Crop — siehe
        # _cancel_view_anim/_begin_view_anim), also nie parallel zur
        # View-Animation aktiv.
        if self.view_proj.scroll_zoom.active:
            z0 = self.view_proj.current_zoom
            if z0 > 0.0:
                sx = self.view_proj.view[0, 0] / z0
                sy = self.view_proj.view[1, 1] / z0
            else:
                sx = sy = 1.0
            dt = now - self._last_scroll_step_t
            self._last_scroll_step_t = now
            z, tx, ty, _done = self.view_proj.scroll_zoom.step(
                dt, z0, self.view_proj.view[3, 0], self.view_proj.view[3, 1])
            self.view_proj.view[0, 0] = z * sx
            self.view_proj.view[1, 1] = z * sy
            self.view_proj.view[3, 0] = tx
            self.view_proj.view[3, 1] = ty
            self.view_proj.current_zoom = z
            self.ruler.update(view=self.view_proj.view)

        # Automatische Punkt-Erkennung: Framebuffer enthält hier ausschließlich
        # das Kamera-/LUT-Bild (Markers/Overlays werden erst danach gezeichnet).
        if self._pending_auto_point is not None:
            # Automation liest ein UNGEFILTERTES (nur LUT-korrigiertes) Bild,
            # damit Filterwahl UND Hintergrund-Einfärbung das Messergebnis nie
            # beeinflussen. Dazu wird das Quad zwei Mal gezeichnet: einmal mit
            # neutralem Filter + ohne Tint, Buffer lesen, dann die eigentliche
            # Anzeige mit aktivem Filter/Tint.
            self._draw_viewport(filt=(1.0, 1.0, 0.0, 1.0, 0.0, 0.0),
                                tint=(0.0, 0.0, 0.0, 0.0))
            auto_frame = self._grab_frame()
            self._draw_viewport()
            self._process_auto_point(self._pending_auto_point, frame=auto_frame)
            self._pending_auto_point = None
        else:
            self._draw_viewport()

        # ruler
        self.ruler.draw()

        # ImGui
        self.imgui_renderer.process_inputs()
        imgui.new_frame()
        self.ui.draw()
        imgui.render()
        self.imgui_renderer.render(imgui.get_draw_data())

        # BRSMatch-Wertung: Framebuffer-Kopie erst jetzt (nach ImGui-Render),
        # damit das Messung-Dialog-Overlay im Bild ist; vor swap_buffers, damit
        # glReadPixels den gerade gerenderten Inhalt liest. Die Erfassung wird
        # um einen Frame verzögert, damit ein im selben Frame geschlossener
        # Dialog (z.B. die Überschreib-Bestätigung) nicht mehr gezeichnet ist.
        if self._pending_wertung_capture:
            self._pending_wertung_capture = False
            self._wertung_capture_next = True
        elif self._wertung_capture_next:
            self._wertung_capture_next = False
            self._process_wertung_capture()

        glfw.swap_buffers(self.window)

    def run(self):
        import time as _time
        target_period = 1.0 / 60.0
        startup_synced = False
        while not glfw.window_should_close(self.window):
            _t0 = _time.time()
            glfw.poll_events()
            if not startup_synced:
                startup_synced = True
                self.on_resize(glfw.get_framebuffer_size(self.window))
            self.render()
            if self.wants_exit:
                glfw.set_window_should_close(self.window, True)
            # Frame-Limiter: VSync greift unter EGL/Software nicht immer,
            # sonst dreht die Loop bei 100% CPU.
            _dt = _time.time() - _t0
            if _dt < target_period:
                _time.sleep(target_period - _dt)
        self.shutdown()

    def on_resize(self, size):
        width, height = size
        if width <= 0 or height <= 0:
            return
        self._cancel_view_anim()
        self.device_size = glfw.get_framebuffer_size(self.window)
        self.size = glfw.get_window_size(self.window)
        gl.glViewport(0, 0, width, height)
        v = self.view_proj.resize(width, height)
        self.ruler.update(view=v)
        self.mbox.resize(self, width, height)
        self.indicator.resize(self, width, height)

    def shutdown(self):
        # Verbleibende UI-Persistenz (Filter/Fensterpositionen) sofort schreiben,
        # bevor der ImGui-Kontext heruntergefahren wird.
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        if getattr(self, "ui", None) is not None:
            self.ui.flush_ui_state()
        self.controller.stop_background_monitor()
        if self.capture_worker:
            self.capture_worker.stop()
            self.capture_worker.join()
        self.imgui_renderer.shutdown()
        glfw.terminate()


if __name__ == "__main__":
    import signal
    import sys
    # --windowed / --dev: windowed Fenster (für Debugging und X11/X-Forwarding)
    windowed = ("--windowed" in sys.argv) or ("--dev" in sys.argv)
    c = BRSCanvas(devmode=windowed)

    # SIGINT (Strg+C) / SIGTERM: geordneter Shutdown über den bestehenden
    # Exit-Pfad (wants_exit -> Loop-Ende -> shutdown()) statt hartem Abbruch.
    def _request_exit(signum, frame):
        c.wants_exit = True

    signal.signal(signal.SIGINT, _request_exit)
    signal.signal(signal.SIGTERM, _request_exit)

    try:
        c.run()
    except KeyboardInterrupt:
        # Fallback, falls ein Interrupt doch als Exception ankommt: sauber
        # herunterfahren statt den Prozess hart abbrechen zu lassen.
        c.shutdown()
