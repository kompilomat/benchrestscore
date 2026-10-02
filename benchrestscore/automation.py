# -*- coding: utf-8 -*-
"""Automatische Schussloch-Erkennung (Klick-Automation).

Sucht nach einem Klick das Lochzentrum nahe dem Klickpunkt. Die Erkennung
basiert auf der ursprünglichen Variante (adaptive Schwelle + Varianz-
minimierung) und wird in zwei Schritten verfeinert:

1. Eine Ring-Kernel-Konvolution (zirkulärer Matched-Filter am bekannten
   Kaliberradius) lokalisiert das Lochzentrum robust gegen Scheibenaufdruck.
2. Eine schrumpfende Scheiben-Maske (1,2r → 1,05r → 0,95r) verfeinert das
   Zentrum unter harten Klick-Bounds; läuft der Fit ans Bound, schlägt die
   Erkennung explizit fehl (Fail-fast).

Reine, headless testbare Kernlogik; App/Controller übernehmen Zustand und
Anzeige.
"""

import cv2

import numpy as np

from scipy.optimize import minimize


# Konstanten für den Suchbereich (find_center und Flash-Overlay nutzen dieselbe
# Geometrie, damit Anzeige und Suche übereinstimmen).
SEARCH_EXCESS = 1.5
SEARCH_WIDTH = 300

# Grenzen des Fit-Zentrums (relativ zum Suchfenster). Der Klick ist laut Nutzer
# „ungefähr das Zentrum" (max ~25 px bzw. ~0,3 Kaliberradien entfernt); ein
# Zentrum, das weiter wandert, gehört zu einem Nachbarloch (Latch). Die engen
# Grenzen halten den Fit am angeklickten Loch, ohne die Verfeinerung
# einzuschränken. ±0,15r um die Fenstermitte (= Startzentrum).
CENTER_LO = 0.45
CENTER_HI = 0.55

# Ring-Kernel-Konvolution: Ein zirkulärer Matched-Filter am bekannten
# Kaliberradius unterscheidet die Lochkante vom Scheibenaufdruck (empirisch
# latche-frei, R=0,8r ist der Sweet-Spot; 0,85–0,9r erzeugt vereinzelte Latches).
RING_RADIUS_FRAC = 0.8   # Kern-Radius (Anteil des Kaliberradius)
RING_THICK_FRAC = 0.1   # Dicke des Annulus (Anteil des Kaliberradius)
RING_BOUND_FRAC = 0.15  # erlaubter Peak-Bereich um den Klick (± Anteil r)

# Schrumpfende Scheiben-Maske: Der Fit (adaptive Schwelle + Varianzminimierung)
# wird mehrstufig ausgeführt; die Maske liegt um das aktuelle Fit-Zentrum und
# schrumpft pro Stufe. Fenster und Bounds bleiben dabei fix (keine Latch-Gefahr).
MASK_SCALES = (1.2, 1.05, 0.95)

# Fail-fast: Liegt das verfeinerte Zentrum weiter als MAX_CENTER_OFFSET_R
# Kaliberradien vom Klick entfernt, war der Klick zu ungenau (oder ein
# Nachbarloch hat den Fit gezogen) -> expliziter Fehlschlag statt eines ungenauen
# Zentrums. Bei exaktem Klick liegt das Ergebnis empirisch < 0,25r entfernt
# (p90 ≈ 0,17r, max ≈ 0,22r); die Grenze 0,3r lässt normalen Klick-Versatz zu.
MAX_CENTER_OFFSET_R = 0.3


class AutoDetect(object):
    """Ergebnis der automatischen Schussloch-Erkennung.

    ok           True bei erfolgreicher Erkennung, sonst False.
    raw_metric   Roh-Klickpunkt in Weltmetrik (3,) ndarray.
    center_metric Platz des detektierten Zentrums in Weltmetrik (3,) ndarray,
                 None bei Fehlschlag.
    offset_mm    Betrag der Korrektur in mm, None bei Fehlschlag.
    radius_px    Projektion des Kaliberradius (Suchradius) in Pixeln; 0.0 wenn
                 keine Projektion möglich war.
    """

    def __init__(self, ok, raw_metric, center_metric, offset_mm, radius_px=0.0):
        self.ok = ok
        self.raw_metric = raw_metric
        self.center_metric = center_metric
        self.offset_mm = offset_mm
        self.radius_px = radius_px


class BRSAutomationIndicator(object):
    """Einfacher Zustandshalter für die Automation (Overlay übernimmt ImGui)."""

    def __init__(self, canvas):
        self.automation = False
        self.enabled = False

    def toggle(self):
        self.automation = not self.automation
        return self.automation

    def resize(self, canvas, vp_width, vp_height):
        pass

    def draw(self):
        pass


def pixel_to_metric(view, pixel, size, calibration):
    """Pixel-Klickposition -> Weltmetrik. Rückgabe (3,) ndarray (NDC-artig, w=1)."""
    glndc_pos = view.glndc_location(*pixel, *size)[:2]
    ndc = np.ones((1, 3))
    ndc[0][0] = glndc_pos[0]
    ndc[0][1] = glndc_pos[1] / view.aspect_ratio
    return np.matmul(ndc, calibration.mati)[0]


def metric_to_pixel(view, metric, size, calibration):
    """Weltmetrik (3,) -> Pixelposition (2,) ndarray (via aktuellem View)."""
    pos = np.asarray(metric, dtype=np.float64).reshape(3)
    pos[2] = 1.
    ndc_rad = np.matmul(pos.reshape(1, 3), calibration.mat)[0]
    glndc_rad = np.array([ndc_rad[0], ndc_rad[1] * view.aspect_ratio, 0., 1.])
    glndc_rad = np.matmul(glndc_rad, view.view)[:2]
    return np.array(view.glndc2pix(glndc_rad[0], glndc_rad[1], size[0], size[1]))


def _window_geom(pos, pix_radius):
    """Fenster-Geometrie um `pos` (Bildkoordinaten) für die Suche.

    Rückgabe: (x1, y1, x2, y2) oder None, wenn das Fenster aus dem Bild läuft.
    """
    x1, y1 = [int(p - SEARCH_EXCESS * pix_radius) for p in pos]
    x2, y2 = [int(p + SEARCH_EXCESS * pix_radius) for p in pos]
    if not (x1 > 0 and y1 > 0 and x2 > 0 and y2 > 0):
        return None
    return x1, y1, x2, y2


def _adaptive_binary(buf, pos, pix_radius):
    """Adaptiv geschwelltes Binaerbild (dunkle Pixel = Loch + Aufdruck) im
    Suchfenster um `pos`. Rückgabe (bw, geom) oder (None, None)."""
    geom = _window_geom(pos, pix_radius)
    if geom is None:
        return None, None
    x1, y1, x2, y2 = geom
    crop = cv2.cvtColor(cv2.resize(buf[y1:y2, x1:x2], (SEARCH_WIDTH, SEARCH_WIDTH)),
                        cv2.COLOR_BGR2GRAY)
    bw = cv2.adaptiveThreshold(crop, 255,
                               cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV,
                               21, 10)
    return bw.astype(np.float32), geom


def _ring_kernel(ksize, R, thick):
    """Annulus-Kernel: 1 für Pixel mit |dist - R| <= thick, sonst 0."""
    c = ksize // 2
    yy, xx = np.mgrid[0:ksize, 0:ksize]
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    return np.abs(r - R) <= thick


def _ring_start(bw, geom, pix_radius):
    """Ring-Kernel-Vorlokalisierung: Peak der Annulus-Antwort als Startzentrum.

    Der Annulus-Kernel (Radius RING_RADIUS_FRAC*r, Dicke RING_THICK_FRAC*r)
    wird auf dem Binaerbild gefaltet. Ein Pixel wird genau dann aktiviert, wenn
    in seiner Nachbarschaft eine Kante mit annähernd dem Kaliberradius verläuft
    — das unterscheidet die Lochkante vom Scheibenaufdruck. Der Peak im
    erlaubten Bereich um den Klick (RING_BOUND_FRAC*r) dient als Startzentrum.

    Rückgabe: Zentrum in Bildkoordinaten (px) oder None.
    """
    x1, y1, x2, y2 = geom
    rel_pix_radius = pix_radius / (x2 - x1) * SEARCH_WIDTH
    R = RING_RADIUS_FRAC * rel_pix_radius
    thick = RING_THICK_FRAC * rel_pix_radius
    ksize = int(2 * (R + thick)) + 3
    if ksize > SEARCH_WIDTH:
        return None
    kernel = _ring_kernel(ksize, R, thick)
    resp = cv2.filter2D(bw, -1, kernel.astype(np.float32))
    c = SEARCH_WIDTH // 2
    yy, xx = np.mgrid[0:SEARCH_WIDTH, 0:SEARCH_WIDTH]
    rmap = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    lim = RING_BOUND_FRAC * rel_pix_radius
    mask = rmap <= lim
    if not mask.any():
        return None
    resp_masked = resp.copy()
    resp_masked[~mask] = -1
    if resp.max() <= 1e-6:
        return None
    idx = np.unravel_index(np.argmax(resp_masked), resp_masked.shape)
    return np.array([x1 + idx[1] / SEARCH_WIDTH * (x2 - x1),
                     y1 + idx[0] / SEARCH_WIDTH * (y2 - y1)])


def _radial_fit(pixels, geom, center_px, scale, pix_radius):
    """Varianzminimierung auf den dunklen Pixelkoordinaten.

    pixels     (N, 2) dunkle Pixel im Binaerbild (Fensterkoordinaten).
    geom       (x1, y1, x2, y2) des Suchfensters.
    center_px  aktuelles Zentrum (Bildkoordinaten), Startpunkt des Fits.
    scale      Scheiben-Radius (Anteil des Kaliberradius) für die Pixel-Auswahl.
    pix_radius Kaliberradius in Pixeln.

    Bounds sind FIX relativ zum Fenster (CENTER_LO/HI = 0,45/0,55): das
    Zentrum darf nur ±0,15r um die Fenstermitte (= Startzentrum) wandern. Der
    Fit startet bei `center_px`, die Bounds wandern nicht mit (sonst würde das
    Weglatchen aufs Nachbarloch wieder möglich).

    Rückgabe: Zentrum in Bildkoordinaten oder None.
    """
    x1, y1, x2, y2 = geom
    width = SEARCH_WIDTH
    if pixels.shape[0] < 10:
        return None
    rel_pix_radius = scale * pix_radius / (x2 - x1) * width

    def _loss(params):
        cx, cy = params
        dists = np.sqrt((pixels[:, 0] - cx * width)**2 +
                        (pixels[:, 1] - cy * width)**2)
        mask = dists < (1.02 * rel_pix_radius)
        if np.sum(mask) < 10:
            return 1e6  # strafe
        dists = dists[mask]
        rm = np.median(dists)
        return np.var(dists) + \
            0.05 * (rm - rel_pix_radius)**2 + \
            0.5 * ((cx - 0.5)**2 + (cy - 0.5)**2)

    # Startpunkt des Fits = aktuelles Zentrum (Bildkoordinaten -> Fensterkoord.)
    x0 = (center_px[0] - x1) / (x2 - x1)
    y0 = (center_px[1] - y1) / (y2 - y1)
    x0 = min(max(x0, CENTER_LO), CENTER_HI)
    y0 = min(max(y0, CENTER_LO), CENTER_HI)
    result = minimize(_loss, np.array([x0, y0]),
                      bounds=[(CENTER_LO, CENTER_HI), (CENTER_LO, CENTER_HI)],
                      tol=1e-8)
    if result is None:
        return None
    rel = result.x
    return np.array([rel[0] * (x2 - x1) + x1, rel[1] * (y2 - y1) + y1])


def _shrink_mask(buf, start_px, pix_radius, scales=MASK_SCALES):
    """Schrumpfende Scheiben-Maske unter harten Bounds (Fix am Startzentrum).

    Mehrstufige Varianzminimierung; die Maske (Pixel-Auswahl um das aktuelle
    Fit-Zentrum) schrumpft pro Stufe. Fenster und Bounds bleiben am Startzentrum
    fix (±0,15r) — das verhindert das Weglatchen aufs Nachbarloch.

    Rückgabe: Zentrum in Bildkoordinaten oder None.
    """
    bw, geom = _adaptive_binary(buf, start_px, pix_radius)
    if bw is None:
        return None
    x1, y1, x2, y2 = geom
    ys, xs = np.nonzero(bw)
    pixels = np.vstack((xs, ys)).T
    cur = np.asarray(start_px, dtype=np.float64).copy()
    for scale in scales:
        c = _radial_fit(pixels, geom, cur, scale, pix_radius)
        if c is None:
            return None
        cur = c
    return cur


def find_center(buf, view, pos, size, calibration, radius):
    """Schussloch-Zentrum nahe dem Klickpunkt suchen.

    buf         BGR-Kamerabild.
    view        BRSView (Pixel <-> GL-NDC).
    pos         Klickposition in Pixeln (window coords).
    size        Fenstergröße (width, height).
    calibration Kalibrierung (mat/mati).
    radius      Kaliberradius in mm.

    Die Erkennung lokalisiert das Lochzentrum über eine Ring-Kernel-Konvolution
    am bekannten Kaliberradius (robust gegen Scheibenaufdruck) und verfeinert es
    mit einer schrumpfenden Scheiben-Maske unter harten Bounds. Läuft der Fit an
    die Bound (Klick zu ungenau), schlägt die Erkennung explizit fehl statt ein
    ungenaues Zentrum zu liefern.

    Rückgabe: AutoDetect. Statt Exceptions im Fehlerfall ok=False.
    """
    try:
        raw_metric = pixel_to_metric(view, pos, size, calibration)
    except Exception:
        _empty = np.zeros(3)
        return AutoDetect(False, _empty, None, None, 0.0)

    # Suchradius (Kaliber) in Pixel projizieren
    try:
        rad_pos = raw_metric.copy()
        rad_pos[0] += radius
        pix_rad = metric_to_pixel(view, rad_pos, size, calibration)
    except Exception:
        return AutoDetect(False, raw_metric, None, None, 0.0)

    px0 = np.asarray(pos, dtype=np.float64)
    pix_radius = float(np.linalg.norm(pix_rad - px0))
    if pix_radius <= 0:
        return AutoDetect(False, raw_metric, None, None, 0.0)

    # 1) Ring-Kernel-Vorlokalisierung (Startzentrum).
    bw, geom = _adaptive_binary(buf, px0, pix_radius)
    if bw is not None:
        start = _ring_start(bw, geom, pix_radius)
    else:
        start = None

    # 2) Schrumpfende Scheiben-Maske unter harten Bounds.
    center_px = _shrink_mask(buf, start if start is not None else px0, pix_radius)

    if center_px is None:
        return AutoDetect(False, raw_metric, None, None, pix_radius)

    # 3) Fail-fast: Liegt das Zentrum weiter als MAX_CENTER_OFFSET_R vom Klick
    #    entfernt, war der Klick zu ungenau (oder ein Nachbarloch hat den Fit
    #    gezogen) -> expliziter Fehlschlag statt eines ungenauen Zentrums.
    #    Bei exaktem Klick liegt das Ergebnis empirisch < 0,25r entfernt.
    center_offset_r = float(np.linalg.norm(center_px - px0)) / pix_radius
    if center_offset_r > MAX_CENTER_OFFSET_R:
        return AutoDetect(False, raw_metric, None, None, pix_radius)

    try:
        center_metric = pixel_to_metric(view, center_px, size, calibration)
    except Exception:
        return AutoDetect(False, raw_metric, None, None, pix_radius)

    offset_mm = float(np.linalg.norm(center_metric[:2] - raw_metric[:2]))
    return AutoDetect(True, raw_metric, center_metric, offset_mm, pix_radius)