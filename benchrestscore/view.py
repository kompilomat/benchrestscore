import math
import numpy as np
# suppress subnormal warnings from -ffast_math 
# https://stackoverflow.com/questions/70612364/numpy-warning-with-django-4-numpy-float64-type-is-zero
np.finfo(np.dtype("float32"))
np.finfo(np.dtype("float64"))

def clamped_zoom_step(zoom, direction, max_zoom, step=0.5):
    """Zoom-Ziel nach einer Raste: `zoom + step·direction`, geklemmt auf [1, max_zoom]."""
    new_zoom = zoom + step * direction
    if new_zoom > max_zoom:
        new_zoom = max_zoom
    elif new_zoom < 1.0:
        new_zoom = 1.0
    return new_zoom

def focus_translation(x, y, ratio, tx0, ty0):
    """Translation, die den Weltpunkt unter (x, y) bei einem Zoom-Verhältnis festhält.

    Fokus-Formel: `tx = x − ratio·(x − tx0)`. Für `ratio = z_neu/z_alt` bleibt der
    Punkt unter dem Cursor während des Zoomens exakt an derselben Bildposition.
    """
    return x - ratio * (x - tx0), y - ratio * (y - ty0)

class BRSScrollZoom(object):
    """Kontinuierliches Ziel-Smoothing für das Mausrad-Zoomen.

    Rasten akkumulieren nur ein Ziel-Zoom + den Fokuspunkt; `step()` gleitet pro
    Frame exponentiell Richtung Ziel (framerate-unabhängig, `k = 1−exp(−λ·dt)`)
    und hält den Weltpunkt unter dem Fokus dabei fest. Bei Konvergenz wird exakt
    auf das Ziel gesnappt und das Smoothing deaktiviert. Ziel-Zoom 1 fährt die
    Translation zusätzlich exponentiell Richtung (0,0) aus.
    """
    RATE = 25.0            # Glättungsrate λ (1/s); größer = schneller
    MAX_DT = 0.25          # dt-Klemmung gegen Sprünge nach Frame-Stalls
    EPS = 0.001            # Zoom-Konvergenz-Toleranz (Abschluss)
    EPS_TRANSLATION = 1e-4  # NDC-Konvergenz der Translation bei Ziel == 1
    STEP = 1.5             # Zoom-Schrittweite pro Raste

    def __init__(self):
        self.target_zoom = 1.0
        self.focus_x = 0.0
        self.focus_y = 0.0
        self.active = False

    def on_scroll(self, direction, x, y, vp_width, vp_height,
                  current_zoom, max_zoom, step=None):
        """Eine Raste akkumulieren: Ziel-Zoom + Fokuspunkt (NDC) aktualisieren."""
        if step is None:
            step = self.STEP
        if not self.active:
            self.target_zoom = current_zoom
            self.active = True
        self.target_zoom = clamped_zoom_step(self.target_zoom, direction,
                                             max_zoom, step)
        self.focus_x = x / (vp_width / 2.) - 1.
        self.focus_y = 1.0 - y / (vp_height / 2.)
        return self.target_zoom

    def cancel(self):
        self.active = False

    def step(self, dt, zoom, tx, ty):
        """Einen exponentiellen Smoothing-Schritt ausführen.

        Rückgabe: `(z, tx, ty, done)`. `done` snappt exakt auf das Ziel und
        deaktiviert das Smoothing. Inaktiv -> unveränderte Eingabe, `done=True`.
        """
        if not self.active:
            return zoom, tx, ty, True
        target = self.target_zoom
        dt = min(max(dt, 0.0), self.MAX_DT)
        k = 1.0 - math.exp(-self.RATE * dt)
        z = zoom + k * (target - zoom)
        if target > 1.0:
            ratio = z / zoom if zoom > 0.0 else 1.0
            tx_new, ty_new = focus_translation(self.focus_x, self.focus_y,
                                               ratio, tx, ty)
            done = abs(target - z) < self.EPS
            if done:
                z = target
                ratio = target / zoom if zoom > 0.0 else 1.0
                tx_new, ty_new = focus_translation(self.focus_x, self.focus_y,
                                                   ratio, tx, ty)
            tx, ty = tx_new, ty_new
        else:
            # Ziel == 1: Translation exponentiell Richtung (0,0) ausfahren
            tx = tx + k * (0.0 - tx)
            ty = ty + k * (0.0 - ty)
            done = (abs(1.0 - z) < self.EPS
                    and abs(tx) < self.EPS_TRANSLATION
                    and abs(ty) < self.EPS_TRANSLATION)
            if done:
                z = 1.0
                tx = 0.0
                ty = 0.0
        if done:
            self.active = False
        return z, tx, ty, done


class BRSView(object):
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.aspect_ratio = width / height
        self.view = np.eye(4)
        self.current_zoom = 1.
        self.max_zoom = 18.
        self.scroll_zoom = BRSScrollZoom()        

    def aspect_scale(self, vp_width, vp_height):
        vp_aspect_ratio = vp_width / vp_height
        ratio = self.aspect_ratio / vp_aspect_ratio
        if ratio < 1.0:
            return ratio, 1.0
        else:
            return 1.0, 1.0 / ratio
        
    def reset(self, vp_width, vp_height):
        sx, sy = self.aspect_scale(vp_width, vp_height)
        self.view = np.eye(4)
        self.view[0, 0] = sx
        self.view[1, 1] = sy
        self.current_zoom = 1.
        return self.view
    
    def drag(self, dx, dy, vp_width, vp_height):
        # memory organization is in column order for OpenGL [col, row]
        # translate matrix
        # ┌          ┐
        # │ 1 0 0 tx │
        # │ 0 1 0 ty │
        # │ 0 0 1 tz │
        # │ 0 0 0 1  │
        # └          ┘   
        self.view[3, 0] += 2*dx/vp_width
        self.view[3, 1] -= 2*dy/vp_height
        return self.view

    def zoom(self, x, y, direction, vp_width, vp_height):
        # memory organization is in column order for OpenGL [col, row]
        # scale matrix
        # ┌            ┐
        # │ sx 0  0  0 │
        # │ 0  sy 0  0 │
        # │ 0  0  sz 0 │
        # │ 0  0  0  1 │
        # └            ┘ 
        x = x/(vp_width/2.) - 1.
        y = 1.0 - y/(vp_height/2.)

        sx, sy = self.aspect_scale(vp_width, vp_height)

        new_zoom = clamped_zoom_step(self.current_zoom, direction, self.max_zoom)
        ratio = new_zoom / self.current_zoom
        self.current_zoom = new_zoom

        self.view[0, 0] = self.current_zoom * sx
        self.view[1, 1] = self.current_zoom * sy

        if direction > 0:
            # zoom in, focus on mouse point
            tx, ty = focus_translation(x, y, ratio,
                                       self.view[3, 0], self.view[3, 1])
            self.view[3, 0] = tx
            self.view[3, 1] = ty
        else:
            # zoom out, move towards center
            if self.current_zoom == 1.:
                self.view[3, 0] = 0.
                self.view[3, 1] = 0.
            else:
                tx, ty = focus_translation(x, y, ratio,
                                           self.view[3, 0], self.view[3, 1])
                self.view[3, 0] = tx
                self.view[3, 1] = ty
        
        return self.view


    def set_dimensions(self, width, height, vp_width=None, vp_height=None):
        """Kamera-Auflösung setzen (width/height/aspect_ratio folgen).

        Optional View sofort zurücksetzen (`reset(vp_width, vp_height)`),
        wenn die Viewport-Größe bekannt ist. Wird ein anderer Aspect, z.B.
        16:9 vs. 4:3, vorausgesetzt, bleibt der Rest des Zustands unverändert.
        """
        self.width = width
        self.height = height
        self.aspect_ratio = width / height
        if vp_width is not None and vp_height is not None:
            return self.reset(vp_width, vp_height)
        self.current_zoom = 1.
        self.view = np.eye(4)
        return self.view

    def resize(self, vp_width, vp_height):
        sx, sy = self.aspect_scale(vp_width, vp_height)
        self.view[0, 0] = self.current_zoom * sx
        self.view[1, 1] = self.current_zoom * sy
        return self.view

    def pix2glndc(self, x, y, width, height):
        x = x /(width/2.) - 1.
        y = 1.0 - y/(height/2.)
        return x, y
    
    def glndc2pix(self, x, y, width, height):
        x = (x + 1.) / 2 * width
        y = (1. - y) / 2 * height
        return x, y

    def glndc_location(self, x, y, vp_width, vp_height):
        inv_view = np.linalg.inv(self.view)
        x, y = self.pix2glndc(x, y, vp_width, vp_height)
        return np.dot(np.array([x, y, 0., 1.]), inv_view)

    def center_translation(self, wx, wy):
        """Translation (tx, ty) für die Zentrierung eines Weltpunkts im Bildzentrum.

        Der Punkt liegt nach Anwenden der Translation in Screen-NDC bei (0,0):
        `0 = sx·wx + tx` bzw. `0 = sy·wy + ty`. Zoom/Scale bleibt unverändert;
        die View wird hier NICHT verändert (der Aufrufer wendet das Ziel an).
        """
        return -self.view[0, 0] * wx, -self.view[1, 1] * wy

    def fit_target(self, positions, vp_width, vp_height, margin=0.1):
        """Ziel (zoom, tx, ty) zum Einpassen von Weltpunkten in den Viewport.

        `positions`: (N,2) Punkte in Quad-/Weltkoordinaten (GLNDC vor View-
        Transformation, z.B. `ruler.positions`). Das Ziel bringt alle Punkte
        inklusive Rand (`margin`, ~10 %) ins Bild: Die Punkte füllen den Anteil
        `1−margin` der Bild-Halbbreite/-höhe, ihr BBox-Zentrum liegt in Screen-
        NDC (0,0). Der Zoom wird auf `[1.0, max_zoom]` geklemmt. Die View wird
        hier NICHT verändert; der Aufrufer wendet das Ziel an (`view[0,0]=zoom·sx`,
        `view[1,1]=zoom·sy`, `view[3,0]=tx`, `view[3,1]=ty`).
        Rückgabe: `None` bei degenerierter Bounding-Box (≤ 1 Punkt oder alle
        Punkte identisch) — der Aufrufer kann dann nur zentrieren.
        """
        pts = np.asarray(positions, dtype=np.float64)
        if pts.shape[0] < 2:
            return None
        x0, y0 = pts[:, 0].min(), pts[:, 1].min()
        x1, y1 = pts[:, 0].max(), pts[:, 1].max()
        hx = x1 - x0
        hy = y1 - y0
        if hx <= 0.0 and hy <= 0.0:
            return None
        sx, sy = self.aspect_scale(vp_width, vp_height)
        frac = 1.0 - margin
        zoom = 2.0 * frac / max(sx * hx, sy * hy)
        zoom = min(max(zoom, 1.0), self.max_zoom)
        cx = x0 + hx / 2.0
        cy = y0 + hy / 2.0
        return zoom, -zoom * sx * cx, -zoom * sy * cy
        

    def ndc_location(self, x, y, vp_width, vp_height):
        ndc = self.glndc_location(x, y, vp_width, vp_height)
        return ndc[0], ndc[1] / self.aspect_ratio

    def pixel_location(self, x, y, vp_width, vp_height):
        ndc = self.glndc_location(x, y, vp_width, vp_height)
        pix = self.glndc2pix(ndc[0], ndc[1], self.width, self.height)
        return pix





