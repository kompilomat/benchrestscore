import numpy as np
# suppress subnormal warnings from -ffast_math
# https://stackoverflow.com/questions/70612364/numpy-warning-with-django-4-numpy-float64-type-is-zero
np.finfo(np.dtype("float32"))
np.finfo(np.dtype("float64"))

import time

from OpenGL import GL as gl
import ctypes

# german number format
import locale
locale.setlocale(locale.LC_ALL, locale.getlocale())

# Dual-Import: als Script und als Paket ladbar (vgl. controller.py).
try:
    from .i18n import tr
except ImportError:
    from i18n import tr


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
    gl.glLinkProgram(prog)
    if not gl.glGetProgramiv(prog, gl.GL_LINK_STATUS):
        log = gl.glGetProgramInfoLog(prog)
        raise RuntimeError(f"Program link error:\n{log}")
    gl.glDeleteShader(vs)
    gl.glDeleteShader(fs)
    return prog


def max_pairwise_distance(metrics):
    """Maximum paarweise Distanz über alle Punktpaare (headless testbar).

    metrics: (N, 2) oder (N, 3) ndarray in Metrik (mm).
    Rückgabe: (max_dist, (i, j)) mit i < j; -1 und (0, 1) bei < 2 Punkten.
    """
    n = len(metrics)
    best = -1.0
    pair = (0, 1)
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(metrics[i, :2] - metrics[j, :2])
            if d > best:
                best = d
                pair = (i, j)
    return best, pair


def fit_extent(positions, big_circle=None):
    """Weltkoordinaten (GLNDC) für das Einpassen: Punkte + großer Messkreis.

    Liefert (N,2) Punkte, deren Bounding-Box alles Sichtbare abdeckt: die
    Messpunkt-Weltkoordinaten (`positions`) und — falls vorhanden — den großen
    Messkreis um die fernsten Punkte (`big_circle`, GLNDC-Vertices). Ohne
    Messkreis (None oder leer) nur die Punkte. Reine Funktion (headless testbar).
    """
    pts = np.asarray(positions, dtype=np.float64).copy()
    if big_circle is not None and len(big_circle) > 0:
        bc = np.asarray(big_circle, dtype=np.float64)
        pts = np.vstack([pts, [[bc[:, 0].min(), bc[:, 1].min()],
                               [bc[:, 0].max(), bc[:, 1].max()]]])
    return pts


class BRSMeasurementBox(object):
    CALIBER = [
        (".177", 4.5),
        (".204", 5.2),
        (".224", 5.69),
        (".243/6 mm", 6.17),
        ("6.5 mm", 6.75),
        ("7 mm", 7.24),
        (".30", 7.82),
        (".338", 8.61),
        (".408", 10.4),
        (".454", 11.53),
        (".50", 13.00),
        (".58", 14.72),
    ]

    def __init__(self, canvas):
        self.enabled = False
        self.distance = -1.
        self.ind = 0
        self.cal = BRSMeasurementBox.CALIBER
        self.update()

    def set_index(self, ind):
        self.ind = ind

    def update(self, dist=None, dir=None):
        if dir is not None:
            if dir > 0:
                self.ind += 1
                if self.ind == len(self.cal):
                    self.ind = 0
            else:
                self.ind -= 1
                if self.ind == -1:
                    self.ind = len(self.cal) - 1

        if dist is not None:
            self.distance = dist

    def value_rows(self):
        """Messwert-Zeilen (Label, Wert) für den Messung-Dialog; leer ohne Distanz.

        Jede Zeile besteht aus einem linksbündigen Label („Mitte"/„Außen") und
        einem rechtsbündig auszurichtenden Wert (Zahl + „ mm"). Der Wert ist in
        beiden Zeilen gleich breit (`%10.2f`), sodass die Zahlenspalte sauber
        ausgerichtet wird — ohne Leerzeichen-Tricks im String.
        """
        if self.distance < 0:
            return []
        mid = locale.format_string("%10.2f", self.distance)
        outer = locale.format_string("%10.2f", self.distance + self.cal[self.ind][1])
        return [
            (tr("measurement.center_label"), f"{mid} mm"),
            (tr("measurement.outer_label"), f"{outer} mm"),
        ]

    def resize(self, canvas, vp_width, vp_height):
        pass

    def draw(self):
        pass

    def radius(self):
        return self.cal[self.ind][1] / 2.


class BRSRuler(object):
    circle_vertex = """#version 330 core
        in vec2 a_position;
        uniform float activated;
        uniform mat4 view;
        out vec4 v_color;
        void main()
        {
            if (activated > 0)
                v_color = vec4(1.0, 0.549, 0.0, 0.45);
            else if (activated < 0)
                v_color = vec4(0., 0., 0., 0.5);
            else
                v_color = vec4(0.922, 0.0, 0.0, 0.45);
            gl_Position = view * vec4(a_position, 0.5, 1.0);
        }
    """

    circle_fragment = """#version 330 core
        in vec4 v_color;
        out vec4 frag_color;
        void main() {
            frag_color = v_color;
        }
    """

    MAX_POINTS = 5
    # Messpunkt-Marker: Viertel-Kreuz mit Ø 2 mm (Weltmetrik, auflösungsunabhängig)
    MARKER_RADIUS_MM = 1.0
    HIT_MIN_PX = 20.0
    # Sichtbarkeitsdauer der Fehlermeldung „Auto-Erkennung fehlgeschlagen"
    AUTO_ERROR_DURATION = 5.0

    def __init__(self, view_proj, calibration, mbox, segments=196, enabled=False):
        # State
        self.enabled = enabled
        self.view_proj = view_proj
        self.calib = calibration
        self.mbox = mbox
        self.segments = segments

        n = self.MAX_POINTS
        self.point_count = 0
        self.active_idx = 0
        self.positions = np.zeros((n, 2), dtype=np.float32)
        self.ndc = np.zeros((n, 2), dtype=np.float32)
        self.metric = np.zeros((n, 3), dtype=np.float32)
        self.active = np.zeros(n, dtype=np.float32)
        self.set_mask = np.zeros(n, dtype=bool)
        self.auto_offsets = [None] * n
        self.auto_error = False
        self.auto_error_at = None
        self._flash = None
        self.markers = [np.zeros((0, 2), dtype=np.float32) for _ in range(n)]
        self.point_circles = [np.zeros((self.segments * 2 + 2, 2), dtype=np.float32)
                              for _ in range(n)]
        self.big_circle = np.zeros((self.segments * 2 + 2, 2), dtype=np.float32)
        self.outer_line = np.zeros((0, 2), dtype=np.float32)

        self.circle_program = _link_program(
            _compile_shader(gl.GL_VERTEX_SHADER, BRSRuler.circle_vertex),
            _compile_shader(gl.GL_FRAGMENT_SHADER, BRSRuler.circle_fragment),
        )
        self.circle_vao = gl.glGenVertexArrays(1)
        self.circle_vbo = gl.glGenBuffers(1)
        self.circle_view_loc = gl.glGetUniformLocation(self.circle_program, "view")
        self.circle_activated_loc = gl.glGetUniformLocation(self.circle_program, "activated")

    def update(self, mbox=False, view=None, circles=False):
        # View-Matrix IMMER übernehmen (auch wenn Messung noch nicht aktiv),
        # sonst bleiben Kreise/Marker mit Identity-View = korrektes Seitenverhältnis fehlt.
        if view is not None:
            self.view_proj_view = view
        if self.enabled:
            if circles:
                self._recompute()

    def add_point(self, pixel, size, view=None, auto_offset_mm=None):
        """Neuen Messpunkt platzieren; None bei voller Belegung/deaktiviert.

        auto_offset_mm: Korrektur der Automation (mm); None = manuell."""
        if not self.enabled:
            return None
        if self.point_count >= self.MAX_POINTS:
            return None
        if view is not None:
            self.view_proj_view = view
        i = self.point_count
        self._place_point(i, pixel, size)
        self.auto_offsets[i] = auto_offset_mm
        self.auto_error = False
        self.auto_error_at = None
        self.point_count += 1
        self._set_active(i)
        self._recompute()
        return i

    def move_point(self, i, pixel, size, view=None):
        if not self.enabled or not (0 <= i < self.point_count):
            return
        if view is not None:
            self.view_proj_view = view
        self._place_point(i, pixel, size)
        self._recompute()

    def remove_point(self, i):
        if not self.enabled or not (0 <= i < self.point_count):
            return
        self.point_count -= 1
        for k in range(i, self.point_count):
            self.positions[k] = self.positions[k + 1]
            self.ndc[k] = self.ndc[k + 1]
            self.metric[k] = self.metric[k + 1]
            self.set_mask[k] = self.set_mask[k + 1]
            self.auto_offsets[k] = self.auto_offsets[k + 1]
            self.markers[k] = self.markers[k + 1]
            self.point_circles[k][:] = self.point_circles[k + 1]
        self.set_mask[self.point_count] = False
        self.auto_offsets[self.point_count] = None
        self.markers[self.point_count] = np.zeros((0, 2), dtype=np.float32)
        if self.point_count == 0:
            self.active_idx = 0
            self.active[:] = 0
            self.big_circle[:] = 0
        else:
            self.active_idx = min(self.active_idx, self.point_count - 1)
            self._set_active(self.active_idx)
        self._recompute()

    def set_active(self, i):
        if self.enabled and (0 <= i < self.point_count):
            self._set_active(i)

    def cycle_active(self):
        if self.point_count == 0:
            return
        self._set_active((self.active_idx + 1) % self.point_count)

    def reset_points(self):
        self.point_count = 0
        self.active_idx = 0
        self.active[:] = 0
        self.set_mask[:] = False
        self.auto_offsets[:] = [None] * self.MAX_POINTS
        self.auto_error = False
        self.auto_error_at = None
        for i in range(self.MAX_POINTS):
            self.markers[i] = np.zeros((0, 2), dtype=np.float32)
        self.big_circle[:] = 0
        self.outer_line = np.zeros((0, 2), dtype=np.float32)
        self.mbox.update(dist=-1)

    def fit_extent(self):
        """Weltkoordinaten für das Einpassen: Messpunkte + großer Messkreis.

        Liefert die Punkte (inkl. BBox-Eckpunkte des großen Messkreises), deren
        Bounding-Box alles Sichtbare abdeckt — Grundlage für `fit_target` beim
        „Crop Messung". Ohne Messkreis (weniger als 2 Punkte) nur die Punkte."""
        circle = None
        if self.point_count >= 2 and self.big_circle.shape[0] > 0:
            circle = self.big_circle
        return fit_extent(self.positions[:self.point_count], circle)

    def hit_test(self, pixel, size):
        """Tritt ein Marker? Klickradius an die projizierte Marker-Größe gekoppelt,
        mindestens HIT_MIN_PX."""
        px, py = pixel
        view = self._view
        marker_px = self._metric_px_radius(size)
        thr = max(self.HIT_MIN_PX, marker_px + 10.0)
        best_i, best_d = None, thr
        for i in range(self.point_count):
            gx, gy = self.positions[i]
            w = view.T @ np.array([gx, gy, 0.0, 1.0])
            mx, my = self.view_proj.glndc2pix(w[0], w[1], size[0], size[1])
            d = np.hypot(px - mx, py - my)
            if d <= best_d:
                best_d = d
                best_i = i
        return best_i

    # ---- transientes Auto-Erkennungs-Feedback (Flash) ----

    def flash_result(self, raw_px, center_px, search_radius_px=None, ok=True,
                     duration=1.0):
        """Kurzfristige Erfolgs-/Fehler-Visualisierung eines Auto-Erkennungs-Laufs.
        raw_px/center_px in Fenster-Pixeln (Screen-Space), search_radius_px in px."""
        self._flash = {
            "expire": time.monotonic() + duration,
            "raw_px": (float(raw_px[0]), float(raw_px[1])),
            "center_px": (float(center_px[0]), float(center_px[1])),
            "search_radius_px": search_radius_px,
            "ok": bool(ok),
        }

    def flash(self, now=None):
        """Aktuellen, nicht abgelaufenen Flash-Zustand; sonst None."""
        f = self._flash
        if f is None:
            return None
        if (now if now is not None else time.monotonic()) > f["expire"]:
            return None
        return f

    def auto_error_active(self, now=None):
        """Fehlermeldung „Auto-Erkennung fehlgeschlagen" noch sichtbar?

        Sichtbar, solange der Fehlschlag nicht älter als `AUTO_ERROR_DURATION`
        ist (`time.monotonic()`); `now` ist für Tests injizierbar."""
        if not self.auto_error or self.auto_error_at is None:
            return False
        now = time.monotonic() if now is None else now
        return now - self.auto_error_at < self.AUTO_ERROR_DURATION

    def _metric_px_radius(self, size):
        """Projizierten Marker-Radius in Pixeln liefern (mm->px via aktuellem View)."""
        p0 = self.metric_to_screen(np.array([0.0, 0.0]), size)
        p1 = self.metric_to_screen(np.array([self.MARKER_RADIUS_MM, 0.0]), size)
        mm_px = np.hypot(p1[0] - p0[0], p1[1] - p0[1])
        return mm_px

    def mm_to_px(self, mm, size):
        """Millimeter-Ausdehnung in Pixeln (aktuelle View-Zoom) zurückgeben."""
        p0 = self.metric_to_screen(np.array([0.0, 0.0]), size)
        p1 = self.metric_to_screen(np.array([mm, 0.0]), size)
        return np.hypot(p1[0] - p0[0], p1[1] - p0[1])

    def metric_to_screen(self, m, size):
        p = self._metric_to_glndc(np.asarray([m]))[0]
        w = self._view.T @ np.array([p[0], p[1], 0.0, 1.0])
        return np.array(self.view_proj.glndc2pix(w[0], w[1], size[0], size[1]))

    def _place_point(self, i, pixel, size):
        self.positions[i, :] = self.view_proj.glndc_location(*pixel, *size)[:2]
        self.ndc[i, 0] = self.positions[i, 0]
        self.ndc[i, 1] = self.positions[i, 1] / self.view_proj.aspect_ratio
        if self.calib.calibrated:
            self.metric[i, :] = np.matmul(np.array([[self.ndc[i, 0], self.ndc[i, 1], 1.]]),
                                          self.calib.mati)
        self.set_mask[i] = True

    def _set_active(self, i):
        self.active_idx = i
        self.active[:] = 0
        self.active[i] = 1.

    def _recompute(self):
        if not self.enabled:
            return
        self._recompute_markers()
        self._recompute_circles()
        dist, (i, j) = self._max_pair()
        if dist is not None:
            self.mbox.update(dist=dist)
            center = self.metric[i, :2] + 0.5 * (self.metric[j, :2] - self.metric[i, :2])
            radius = dist / 2 + self.mbox.radius()
            self.big_circle[:] = self.circle(center, radius=radius, thickness=0.1)
            self.outer_line = self._farthest_lines(i, j, dist)
        else:
            self.outer_line = np.zeros((0, 2), dtype=np.float32)
            self.big_circle[:] = 0
            self.mbox.update(dist=-1)

    def _recompute_markers(self):
        for i in range(self.point_count):
            if self.set_mask[i]:
                self.markers[i] = self._reticle(self.metric[i, :2])

    def _metric_to_glndc(self, pts):
        """(N,2) Punkte in Weltmetrik -> (N,2) GLNDC (calib.mat + y·aspect)."""
        pts = np.asarray(pts, dtype=np.float64)
        ones = np.hstack([pts, np.ones((pts.shape[0], 1))])
        gl = np.matmul(ones, self.calib.mat)[:, :2].astype(np.float32)
        gl[:, 1] *= self.view_proj.aspect_ratio
        return gl

    def _reticle(self, center):
        """Viertel-Kreuz (Ø 2 mm): nur gefüllte NE/SW-Sektoren als GL_TRIANGLES."""
        r = self.MARKER_RADIUS_MM

        def sector(a0, a1):
            arc_seg = 8
            angles = np.linspace(a0, a1, arc_seg + 1)
            arc = np.stack([np.cos(angles), np.sin(angles)], axis=1) * r
            tris = []
            c0 = np.zeros(2)
            for k in range(arc_seg):
                tris.append([c0, arc[k], arc[k + 1]])
            return np.concatenate(tris)

        verts = np.concatenate([sector(0.0, 0.5 * np.pi), sector(np.pi, 1.5 * np.pi)])
        verts = verts + center
        return self._metric_to_glndc(verts)

    def _farthest_lines(self, i, j, dist):
        """Zwei durchgehende Liniensegmente durch die zwei fernsten Punkte, nur
        außerhalb des umschließenden Messkreises (je ein Kaliberradius lang)."""
        pi = self.metric[i, :2]
        pj = self.metric[j, :2]
        u = (pj - pi) / dist
        cal_radius = self.mbox.radius()
        # Segment startet an der Kreisgrenze (pi/pj ± u*radius) und läuft zwei
        # Kaliberradien nach außen weiter -> nur sichtbar außerhalb des Kreises.
        l_i = self._line_quads(pi - u * cal_radius, pi - u * (3 * cal_radius))
        l_j = self._line_quads(pj + u * cal_radius, pj + u * (3 * cal_radius))
        parts = [p for p in (l_i, l_j) if p.shape[0] > 0]
        return np.vstack(parts) if parts else np.zeros((0, 2), dtype=np.float32)

    def _line_quads(self, p0, p1, thickness=0.5):
        """Durchgehendes Liniensegment p0->p1 (Metrik) als GL_TRIANGLES-Quads in
        GLNDC; Rückgabe (N,2) float32. Nur leeres Array bei Länge 0."""
        u = p1 - p0
        length = np.linalg.norm(u)
        if length <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        u = u / length
        perp = np.array([-u[1], u[0]]) * (thickness / 2.0)
        a = p0 - perp
        b = p0 + perp
        c = p1 + perp
        d = p1 - perp
        arr = np.array([a, b, c, a, c, d])
        ones = np.hstack([arr, np.ones((arr.shape[0], 1))])
        gl = np.matmul(ones, self.calib.mat)[:, :2]
        gl[:, 1] *= self.view_proj.aspect_ratio
        return gl.astype(np.float32)

    def _recompute_circles(self):
        for i in range(self.point_count):
            if self.set_mask[i]:
                self.point_circles[i][:] = self.circle(self.metric[i, :2])

    def _max_pair(self):
        if self.point_count >= 2:
            return max_pairwise_distance(self.metric[:self.point_count, :2])
        return None, (0, 1)

    def distance(self):
        dist, _ = self._max_pair()
        return dist

    def draw(self):
        if self.enabled:
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            for i in range(self.point_count):
                if self.set_mask[i]:
                    self._draw_marker(i)
                    self._draw_circle(self.point_circles[i], self.active[i])
            if self.point_count >= 2:
                self._draw_circle(self.big_circle, -1)
                if self.outer_line.shape[0] > 0:
                    self._draw_line(self.outer_line, -1)

    def _draw_marker(self, i):
        vertices = self.markers[i]
        if vertices.shape[0] == 0:
            return
        gl.glUseProgram(self.circle_program)
        gl.glUniform1f(self.circle_activated_loc, self.active[i])
        gl.glUniformMatrix4fv(self.circle_view_loc, 1, gl.GL_FALSE, self._view.flatten())
        gl.glBindVertexArray(self.circle_vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.circle_vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_DYNAMIC_DRAW)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, 8, ctypes.c_void_p(0))
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, len(vertices))
        gl.glBindVertexArray(0)

    def _draw_circle(self, circle, activated):
        gl.glUseProgram(self.circle_program)
        gl.glUniform1f(self.circle_activated_loc, activated)
        gl.glUniformMatrix4fv(self.circle_view_loc, 1, gl.GL_FALSE, self._view.flatten())
        gl.glBindVertexArray(self.circle_vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.circle_vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, circle.nbytes, circle, gl.GL_DYNAMIC_DRAW)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, 8, ctypes.c_void_p(0))
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, len(circle))
        gl.glBindVertexArray(0)

    def _draw_line(self, vertices, activated):
        if vertices.shape[0] == 0:
            return
        gl.glUseProgram(self.circle_program)
        gl.glUniform1f(self.circle_activated_loc, activated)
        gl.glUniformMatrix4fv(self.circle_view_loc, 1, gl.GL_FALSE, self._view.flatten())
        gl.glBindVertexArray(self.circle_vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.circle_vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_DYNAMIC_DRAW)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, 8, ctypes.c_void_p(0))
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, len(vertices))
        gl.glBindVertexArray(0)

    @property
    def _view(self):
        return getattr(self, "view_proj_view", np.eye(4))

    def adjust(self, key, step=0.05):
        if self.enabled and self.calib.calibrated and self.point_count > 0:
            i = self.active_idx
            lookup = {
                "Up":       np.array([[0., -step, 0.]]).astype(np.float32),
                "Down":     np.array([[0., +step, 0.]]).astype(np.float32),
                "Left":     np.array([[-step, 0., 0.]]).astype(np.float32),
                "Right":    np.array([[+step, 0., 0.]]).astype(np.float32),
            }
            self.metric[i] += lookup[key][0]
            self.ndc[i, :2] = np.matmul(self.metric[i], self.calib.mat)[:2]
            self.positions[i, 0] = self.ndc[i, 0]
            self.positions[i, 1] = self.ndc[i, 1] * self.view_proj.aspect_ratio
            self._recompute()

    def circle(self, center, radius=None, thickness=0.5):
        if radius is None:
            radius = self.mbox.radius()
        c = np.ones((self.segments * 2 + 2, 3))
        segments = np.linspace(0, 2 * np.pi, self.segments, endpoint=False)
        c[0:-2:2, 0] = radius * np.cos(segments)
        c[1:-2:2, 0] = (radius - thickness) * np.cos(segments)
        c[-2, 0] = c[0, 0]
        c[-1, 0] = c[1, 0]
        c[0:-2:2, 1] = radius * np.sin(segments)
        c[1:-2:2, 1] = (radius - thickness) * np.sin(segments)
        c[-2, 1] = c[0, 1]
        c[-1, 1] = c[1, 1]
        c[:, :2] += center
        glndc_c = np.matmul(c, self.calib.mat)[:, :2].astype(np.float32)
        glndc_c[:, 1] *= self.view_proj.aspect_ratio
        return glndc_c
