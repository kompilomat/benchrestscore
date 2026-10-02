# -*- coding: utf-8 -*-
"""Loss-of-Calibration-Erkennung über den Tisch-Untergrund.

Das Modul lernt markante Keypoints der freien Tischfläche nach der Kalibrierung
und prüft periodisch den aktuellen Kameraframe per Keypoint-Matching +
RANSAC-Homographie gegen dieses Modell. Die Homographie liefert den Status
`OK`/`SHIFTED`/`UNAVAILABLE` sowie die Verschiebung in Weltmetrik (mm).

Reine, headless testbare Kernlogik (analog `automation.py`); UI/Controller
übernehmen Zustand und Anzeige.
"""

import cv2
import threading

import numpy as np


# --- Konstanten (empirisch nachjustierbar, zentral) ---

# Kritische Verschiebung in mm (≈ 1 px @ 4K ≈ 0,04 mm)
DEVIATION_THRESHOLD_MM = 0.04
# Anteil der Inlier an allen guten Matches, ab dem der Untergrund als
# "sichtbar" gilt; darunter gilt die Fläche als belegt/nicht erkennbar.
MIN_INLIER_RATIO = 0.25
# Lowe-Ratio für das BFMatcher-Deskriptor-Matching. ORB-Descriptors sind kaum
# beleuchtungsinvariant: Bei Auto-Exposure-/Weißabgleich-Drifts spreizt sich die
# Hamming-Distanz-Verteilung, und eine zu strikte Ratio (0.75) verwirft alle
# Matches ("no_matches"). 0.9 lässt drift-betroffene Korrespondenzen durch;
# der RANSAC-Homographie-Inlier-Anteil ist der eigentliche Diskriminator gegen
# falsche (zufällige) Matches auf anderem Inhalt.
LOWE_RATIO = 0.9
# Mindestanzahl guter Matches, bevor überhaupt eine Homographie sinnvoll ist.
# Für 4 Freiheitsgrade reichen wenige konsistente Punkte; großzügig, damit
# Beleuchtungs-/Expositionsdrift des Webcams das Monitoring nicht auslöst.
MIN_MATCHES = 30
# Kadenz der periodischen Prüfung in Sekunden.
CHECK_CADENCE_S = 1.5
# Anzahl aufeinanderfolgender Schwellen-Überschreitungen, bevor `SHIFTED`
# gemeldet wird (Hysterese gegen Vibrieren/Flattern).
HYSTERESIS = 2
# Mindestanzahl Keypoints, die `learn()` für ein brauchbares Modell verlangt.
MIN_LEARN_KEYPOINTS = 30
# Downscale-Faktor der dichten Tisch-Referenz (RAM + Rechenkosten; die
# Segmentierung arbeitet auf ~1/16 der Pixel, `find_center` verfeinert voll).
REFERENCE_SCALE = 4
# EMA-Gewicht des Drift-Ausgleichs der Referenz (klein => langsame Nachführung).
REFERENCE_ALPHA = 0.1
# Nach wie vielen Nachführ-Ticks die ORB-Keypoints aus der Referenz neu
# abgeleitet werden (moderates Nachziehen bei Belichtungsdrift).
REFERENCE_UPDATE_EVERY = 10
# Anteil der kritischen Schwelle, unter dem die Verschiebung liegen muss,
# damit die Referenz nachgeführt wird (verhindert das Einbacken von Drift).
REFERENCE_UPDATE_DEVIATION_FACTOR = 0.5
# Obergrenze der gelernten Modell-Keypoints (`learn()`) und der je Check-Frame
# detektierten Keypoints. Rechenkosten von Matching (quadratisch) und RANSAC
# skalieren mit der Punktzahl; für eine robuste Homographie genügen wenige
# hundert gut verteilte Punkte deutlich.
MAX_LEARN_KEYPOINTS = 400
MAX_CHECK_KEYPOINTS = 400
# Obergrenze der an die Homographie übergebenen Matches (beste nach Distanz).
# Begrenzt die pro RANSAC-Iteration auszuwertende Punktmenge.
MAX_RANSAC_MATCHES = 200
# Explizite RANSAC-Grenzen für `findHomography`: Reprojektionsschwelle (px)
# und maximale Iterationszahl (Default wäre 2000).
RANSAC_REPROJ_THRESHOLD = 3.0
RANSAC_MAX_ITERS = 1000


class MonitorStatus(object):
    OK = "ok"
    SHIFTED = "shifted"
    UNAVAILABLE = "unavailable"


class CheckResult(object):
    """Ergebnis eines Background-Checks.

    status        MonitorStatus (ok/shifted/unavailable).
    deviation_mm  Median-Verschiebung in mm; 0.0 bei unavailable.
    """

    __slots__ = ("status", "deviation_mm")

    def __init__(self, status, deviation_mm=0.0):
        self.status = status
        self.deviation_mm = float(deviation_mm)


def detect_keypoints(frame, nfeatures=2000):
    """ORB-Keypoints + Descriptoren eines Frames erkennen.

    frame     BGR- oder Graustufen-Bild.
    nfeatures Maximale Keypoint-Anzahl.

    Rückgabe: (keypoints, descriptors). Descriptoren sind None bei Fehlern.
    """
    if frame is None:
        return [], None
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    orb = cv2.ORB_create(nfeatures=nfeatures)
    kps, desc = orb.detectAndCompute(gray, None)
    return (list(kps) if kps is not None else []), desc


def similarity(reference, frame):
    """Tisch-Ähnlichkeits-Distanz (0 = identisch zur Referenz).

    reference  Downscaled Referenz (rh, rw, 3) float32.
    frame      Aktueller (LUT-entzerrter) Frame (h, w, 3) uint8.

    Rückgabe: (rh, rw) float32-Distanzkarte. Kombiniert die absolute
    Farbdistanz (Haupt-Diskriminator: Papier ≠ Tisch) mit der lokal
    mittelwert-subtrahierten Struktur-Distanz (robust gegen
    Beleuchtungsgradienten).
    """
    ref = np.asarray(reference, dtype=np.float32)
    rh, rw = ref.shape[:2]
    if frame.ndim == 2:
        small = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    else:
        small = frame
    if small.shape[:2] != (rh, rw):
        small = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_AREA)
    small = small.astype(np.float32)
    lim = min(rh, rw)
    k = int(lim * 0.06)
    k = max(3, min(21, k))
    if k % 2 == 0:
        k -= 1
    if k > lim - 1:
        k = max(1, lim - 1 if lim % 2 == 0 else lim)
    blur_small = cv2.GaussianBlur(small, (k, k), 0)
    blur_ref = cv2.GaussianBlur(ref, (k, k), 0)
    dev = (small - blur_small) - (ref - blur_ref)
    dev_dist = np.sqrt(np.mean(dev * dev, axis=2))
    abs_dist = np.sqrt(np.mean((small - ref) ** 2, axis=2))
    return abs_dist + 0.5 * dev_dist


def otsu_threshold(values, bins=200):
    """Otsu-Schwelle über die gegebenen Werte (databgeleitet).

    Maximiert die Varianz zwischen zwei Klassen des Histogramms. Liefert die
    Schwelle in derselben Skala wie `values`; 0.0 bei leerer/entarteter Menge.
    """
    values = np.asarray(values, dtype=np.float64).ravel()
    if values.size == 0:
        return 0.0
    hi = float(np.percentile(values, 99.5))
    if hi <= 1e-6:
        return 0.0
    hist, edges = np.histogram(values, bins=bins, range=(0.0, hi))
    bins_c = 0.5 * (edges[:-1] + edges[1:]).astype(np.float64)
    hist = hist.astype(np.float64)
    total = float(hist.sum())
    if total <= 0:
        return 0.0
    w = np.cumsum(hist)
    mu = np.cumsum(hist * bins_c) / total
    w_b = w / total
    w_f = 1.0 - w_b
    mu_b = mu / np.maximum(w_b, 1e-9)
    mu_f = (mu[-1] - mu) / np.maximum(w_f, 1e-9)
    var = w_b * w_f * (mu_b - mu_f) ** 2
    if not np.any(np.isfinite(var)):
        return 0.0
    return float(bins_c[int(np.nanargmax(var))])


def table_mask(reference, frame, tight=False, threshold=None):
    """Binäre Tisch-Maske (Referenz-Skala) für Drift-Ausgleich/Tint-Anzeige.

    `tight` True liefert die konservative Kern-Maske der tisch-ähnlichsten
    Pixel (p10-Perzentil der Tisch-Klasse) für den Drift-Ausgleich; False die
    Tisch-Maske (Tisch vs. Papier). `threshold` setzt die Klassifikations-
    Schwelle explizit (z. B. einen statischen Wert für die Tint-Anzeige);
    `None` verwendet den datenabhängigen Otsu-Schnitt.
    """
    dist = similarity(reference, frame)
    thr = threshold if threshold is not None else otsu_threshold(dist)
    if tight:
        table_cls = dist[dist <= thr]
        thr_core = float(np.percentile(table_cls, 10.0)) \
            if table_cls.size > 0 else thr
        return dist <= thr_core
    return dist <= thr


def match_keypoints(desc_model, desc_current, min_matches=MIN_MATCHES,
                    max_matches=MAX_RANSAC_MATCHES, ratio=LOWE_RATIO):
    """Deskriptoren matchen (BFMatcher HAMMING + Lowe-Ratio).

    Rückgabe: (src_pts, dst_pts) als (N,2) float64-Pixelkoordinaten (Modell-Frame
    -> aktueller Frame). Leere Arrays (N=0), wenn zu wenige Matches oder kein
    Deskriptor vorliegt. Sind mehr als `max_matches` gute Matches vorhanden,
    werden nur die besten (kleinste Distanz) behalten — RANSAC skaliert mit der
    Match-Anzahl. `ratio` ist die Lowe-Ratio (`LOWE_RATIO`); bewusst großzügig,
    damit Belichtungs-/Weißabgleich-Drift Korrespondenzen nicht komplett
    verwirft — falsche Matches filtert der RANSAC-Inlier-Anteil.
    """
    empty = (np.zeros((0, 2)), np.zeros((0, 2)))
    if desc_model is None or desc_current is None:
        return empty
    if len(desc_model) < 2 or len(desc_current) < 2:
        return empty
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(desc_model, desc_current, k=2)
    good = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < ratio * n.distance:
                good.append(m)
    if len(good) < min_matches:
        return empty
    if max_matches is not None and len(good) > max_matches:
        good.sort(key=lambda m: m.distance)
        good = good[:max_matches]
    src = np.array([m.queryIdx for m in good], dtype=np.float64)
    dst = np.array([m.trainIdx for m in good], dtype=np.float64)
    return src, dst


class BackgroundMonitorThread(threading.Thread):
    """Periodischer Loss-of-Calibration-Check in einem eigenen Thread.

    Entkoppelt die ORB/Matching/RANSAC-Fracht (~50 ms pro Check) vom
    GL/Render-Thread. Der Thread schläft zwischen den Checks `cadence` Sekunden
    (abbrechbar über `stop()`) und ruft `check_cb()` auf — der Callback liefert
    ein `CheckResult` oder None (überspringen). Rückgaben/Exceptions des
    Callbacks verhindern den Lauf nicht; jeder Tick fängt sie isoliert.
    """

    def __init__(self, check_cb, cadence=CHECK_CADENCE_S):
        super(BackgroundMonitorThread, self).__init__()
        self.daemon = True
        self._check_cb = check_cb
        self._cadence = max(0.0, float(cadence))
        self._stop = threading.Event()

    def run(self):
        while not self._stop.wait(self._cadence):
            try:
                self._check_cb()
            except Exception as exc:
                # Ein Check-Tick darf den Thread nicht beenden; Fehler werden
                # gemeldet (letzter bekannt guter Status bleibt stehen).
                print(f"[monitor] check tick failed: {exc}", flush=True)

    def stop(self):
        """Check-Loop abbrechen (setzt das Stop-Event; weckt wait() sofort)."""
        self._stop.set()


def draw_keypoints(frame, keypoints):
    """Keypoints in einen Frame einzeichnen (fürs Lern-Ergebnis).

    frame      BGR- oder Graustufen-Frame.
    keypoints  Liste von cv2.KeyPoint (oder KeyPoint-fähige Objekte mit `pt`).

    Rückgabe: BGR-Bild mit eingezeichneten Keypoints (Kreisen mit Orientierung).
    """
    if frame is None:
        return None
    if keypoints is None:
        keypoints = []
    img = frame.copy()
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return cv2.drawKeypoints(img, list(keypoints), None,
                             flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)


def _pixels_to_metric(calib, points, shape):
    """Pixel-Koordinaten -> Weltmetrik (x, y) über die Kalibrierung.

    calib    Objekt mit `mati` (NDC -> Weltmetrik).
    points   (N,2) Pixel-Koordinaten.
    shape    Frame-Form (h, w, ...) für die NDC-Normalisierung.
    """
    h, w = shape[:2]
    aspect = w / h
    ndc = np.zeros(points.shape, dtype=np.float64)
    ndc[:, 0] = points[:, 0] * 2.0 / w - 1.0
    ndc[:, 1] = (1.0 - points[:, 1] * 2.0 / h) / aspect
    ones = np.ones((len(ndc), 3), dtype=np.float64)
    ones[:, :2] = ndc
    metric = np.matmul(ones, calib.mati)[:, :2]
    return metric


def _homography_deviation_mm(calib, H, ref_points, shape):
    """Median-Verschiebung (mm), die H auf die Referenzpunkte ausübt.

    ref_points (N,2) Pixel im Modell-Frame. Projiziert durch H und mit der
    Kalibrierung in Metrik umgerechnet; Rückgabe: Median über die euklidischen
    Abstände in mm.
    """
    ref = np.asarray(ref_points, dtype=np.float64).reshape(-1, 2)
    if len(ref) == 0:
        return 0.0
    ones = np.ones((len(ref), 3), dtype=np.float64)
    ones[:, :2] = ref
    proj = np.matmul(ones, H.T)
    proj = proj[:, :2] / proj[:, 2:3]
    metric_src = _pixels_to_metric(calib, ref, shape)
    metric_dst = _pixels_to_metric(calib, proj, shape)
    dists = np.linalg.norm(metric_dst - metric_src, axis=1)
    return float(np.median(dists))


class BackgroundModel(object):
    """Gelerntes Untergrund-Modell mit periodischer Verschiebungs-Prüfung.

    Neben den ORB-Keypoints hält das Modell eine **dichte Tisch-Referenz**
    (LUT-entzerrter Lern-Frame, downscaled) — Grundlage des Drift-Ausgleichs
    und der Tint-Anzeige: Bei Status `OK` (Phasen zwischen Messungen) wird die
    Referenz per EMA in Richtung des aktuellen Frames nachgeführt und
    periodisch die ORB-Keypoints aus der nachgeführten Roh-Referenz neu
    abgeleitet.
    """

    def __init__(self):
        self.learned = False
        self._kps = []
        self._desc = None
        self._shape = None
        self._consecutive_shifted = 0
        self.last_status = MonitorStatus.UNAVAILABLE
        self.last_check_info = {"reason": "no_model"}
        # Dichte Referenz: `reference` (LUT-entzerrt, Drift-Ausgleich/Tint),
        # `reference_raw` (Roh-Darstellung, für die ORB-Neuableitung). Beide
        # downscaled float32 (BGR); `reference_shape` = Voll-Auflösung.
        self.reference = None
        self.reference_raw = None
        self.reference_shape = (0, 0)
        self.reference_ticks = 0
        # Anzeige-Tint-Maske (Tisch vs. Papier, halbe Referenz-Skala, uint8) samt
        # Monotonie-Zähler: vom Render-Loop gedrosselt berechnet, vom selben
        # Pass als Textur hochgeladen (nur Anzeige-Hilfe).
        self.tint_mask = None
        self.tint_tick = 0

    def _downscale_reference(self, img):
        """Bild auf die Referenz-Skala bringen (BGR float32).

        Zielgröße aus der Voll-Auflösung (`_shape` bzw. Bildgröße) abgeleitet;
        2D-Graustufen werden zu BGR konvertiert. None bei ungültigem Input.
        """
        if img is None:
            return None
        h, w = img.shape[:2]
        if self._shape is not None:
            h, w = self._shape
        if h <= 0 or w <= 0:
            h, w = img.shape[:2]
        rh = max(1, h // REFERENCE_SCALE)
        rw = max(1, w // REFERENCE_SCALE)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        small = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_AREA)
        return np.asarray(small, dtype=np.float32)

    @property
    def has_reference(self):
        """True, wenn eine dichte (LUT-entzerrte) Referenz vorliegt."""
        return self.reference is not None

    def learn(self, frame, reference=None):
        """Tisch-Untergrund aus einem Frame lernen.

        `reference` (optional): LUT-entzerrter Frame für die dichte Referenz
        (Roh-Referenz wird aus `frame` selbst abgeleitet). Ohne Referenz bleibt
        `has_reference` False — die Keypoint-Logik läuft unverändert.

        Rückgabe: True bei Erfolg. Zu strukturarme Bilder (wenige Keypoints)
        lehnt `learn()` ab und lässt das Modell ungelernt.
        """
        kps, desc = detect_keypoints(frame, nfeatures=MAX_LEARN_KEYPOINTS)
        if len(kps) < MIN_LEARN_KEYPOINTS or desc is None:
            self.learned = False
            self._kps = []
            self._desc = None
            self._shape = None
            self._consecutive_shifted = 0
            self.reference = None
            self.reference_raw = None
            self.reference_shape = (0, 0)
            self.reference_ticks = 0
            self.tint_mask = None
            self.tint_tick = 0
            self.last_status = MonitorStatus.UNAVAILABLE
            return False
        self._kps = kps
        self._desc = desc
        self._shape = tuple(frame.shape[:2])
        self._consecutive_shifted = 0
        self.learned = True
        self.last_status = MonitorStatus.OK
        self.last_check_info = {"reason": "ok", "frame_keypoints": len(kps),
                                "matches": 0, "inlier_ratio": None}
        self._set_references(frame, reference)
        return True

    def _set_references(self, frame_raw, frame_undist):
        """Dichte Referenzen aus den Lern-Frames ableiten (downscaled)."""
        self.reference_raw = self._downscale_reference(frame_raw)
        self.reference = self._downscale_reference(frame_undist)
        if frame_raw is not None:
            self.reference_shape = (frame_raw.shape[0], frame_raw.shape[1])
        else:
            self.reference_shape = (0, 0)
        self.reference_ticks = 0
        # Neue Referenz => veraltete Tint-Maske verwerfen (wird im nächsten
        # Monitor-Tick neu berechnet).
        self.tint_mask = None
        self.tint_tick = 0

    def set_reference(self, undistorted):
        """LUT-entzerrte Tisch-Referenz extern setzen (Wiederherstellung).

        Erwartet das volle Bild (BGR); gespeichert wird downscaled. Ohne
        gültiges Bild bleibt die Referenz ungelernt. Die Roh-Referenz wird
        erst durch die nächste Nachführung befüllt.
        """
        if undistorted is None:
            return
        ref = self._downscale_reference(undistorted)
        if ref is None:
            return
        self.reference = ref
        if self.reference_shape == (0, 0):
            self.reference_shape = (undistorted.shape[0],
                                    undistorted.shape[1])
        # Veraltete Tint-Maske verwerfen (wird im nächsten Monitor-Tick neu
        # berechnet).
        self.tint_mask = None
        self.tint_tick = 0

    def update_reference(self, frame_raw, frame_undist, mask,
                         alpha=REFERENCE_ALPHA):
        """Dichte Referenz per EMA in Richtung des aktuellen Frames nachführen.

        `frame_raw`/`frame_undist` sind die (vollen) Kamera-Frames in Roh- bzw.
        LUT-entzerrter Darstellung; `mask` (Referenz-Skala, bool) begrenzt die
        Nachführung auf sichere Tisch-Pixel. Fehlende Referenz oder
        Shape-Mismatch sind No-ops.
        """
        if self.reference is None:
            return
        raw = self._downscale_reference(frame_raw)
        und = self._downscale_reference(frame_undist)
        if raw is None or und is None:
            return
        if raw.shape != self.reference.shape or und.shape != self.reference.shape:
            return
        m = np.asarray(mask, dtype=bool)
        rh, rw = self.reference.shape[:2]
        if m.shape != (rh, rw):
            m = (cv2.resize(m.astype(np.uint8), (rw, rh),
                            interpolation=cv2.INTER_NEAREST) > 0)
        if not np.any(m):
            return
        a = float(alpha)
        self.reference[m] = (1.0 - a) * self.reference[m] + a * und[m]
        if self.reference_raw is None:
            self.reference_raw = raw.copy()
        else:
            self.reference_raw[m] = (1.0 - a) * self.reference_raw[m] + a * raw[m]

    def relearn_from_reference(self):
        """ORB-Keypoints/Descriptors aus der nachgeführten Roh-Referenz ableiten.

        Nutzt `reference_raw` hochskaliert auf die Voll-Auflösung. Ohne
        Roh-Referenz oder bei zu wenigen Keypoints bleibt das Modell
        unverändert (weiterhin gelernt).
        """
        if self.reference_raw is None:
            return
        h, w = self.reference_shape
        if h <= 0 or w <= 0:
            return
        full = cv2.resize(self.reference_raw, (w, h),
                          interpolation=cv2.INTER_LINEAR)
        full = np.clip(full, 0, 255).astype(np.uint8)
        kps, desc = detect_keypoints(full, nfeatures=MAX_LEARN_KEYPOINTS)
        if len(kps) < MIN_LEARN_KEYPOINTS or desc is None:
            return
        self._kps = kps
        self._desc = desc
        self.reference_ticks = 0

    @property
    def keypoint_count(self):
        return len(self._kps)

    @property
    def keypoints(self):
        """Gelernte Keypoints (für Visualisierungen); leere Liste wenn ungelernt."""
        return list(self._kps)

    @property
    def shape(self):
        """Lern-Frame-Form (h, w) als Tupel; (0, 0) wenn ungelernt."""
        return self._shape if self._shape is not None else (0, 0)

    def to_dict(self):
        """Seriellisierbare Repräsentation (JSON-tauglich) der gelernten Punkte.

        Enthält `keypoints` (je pt/size/angle/response/octave/class_id) und
        `descriptors` (je 32 Werte, aus uint8). Ohne gelerntes Modell leere
        Listen.
        """
        kps = []
        for kp in self._kps:
            kps.append({
                "x": float(kp.pt[0]),
                "y": float(kp.pt[1]),
                "size": float(kp.size),
                "angle": float(kp.angle),
                "response": float(kp.response),
                "octave": int(kp.octave),
                "class_id": int(kp.class_id),
            })
        desc = []
        if self._desc is not None:
            desc = self._desc.astype(np.uint8).tolist()
        return {"keypoints": kps, "descriptors": desc}

    @classmethod
    def restore(cls, data):
        """Modell aus einem `to_dict()`-Dict wiederherstellen.

        `data`  Dict mit `keypoints` und `descriptors` (Listen). Ohne gültige
                Daten (oder zu wenige Punkte) bleibt das Modell ungelernt.

        Rückgabe: `BackgroundModel`-Instanz. Der `_shape` wird aus
        `width`/`height` der Daten gesetzt (vom Persistenz-Helfer ergänzt).
        """
        model = cls()
        kps_raw = data.get("keypoints") or []
        desc_raw = data.get("descriptors") or []
        if len(kps_raw) < MIN_LEARN_KEYPOINTS or not desc_raw:
            return model
        kps = []
        for k in kps_raw:
            kps.append(cv2.KeyPoint(
                x=float(k["x"]), y=float(k["y"]),
                size=float(k.get("size", 31.0)),
                angle=float(k.get("angle", -1.0)),
                response=float(k.get("response", 0.0)),
                octave=int(k.get("octave", 0)),
                class_id=int(k.get("class_id", -1)),
            ))
        desc = np.asarray(desc_raw, dtype=np.uint8)
        if desc.ndim != 2 or desc.shape[0] != len(kps):
            return model
        model._kps = kps
        model._desc = desc
        model._shape = (int(data.get("height", 0) or 0),
                        int(data.get("width", 0) or 0))
        model._consecutive_shifted = 0
        model.learned = True
        model.last_status = MonitorStatus.OK
        model.last_check_info = {"reason": "ok", "frame_keypoints": len(kps),
                                 "matches": 0, "inlier_ratio": None}
        return model

    def check(self, frame, calib):
        """Aktuellen Frame gegen das Modell prüfen.

        calib Kalibrierung mit `mati` (NDC -> Weltmetrik) für die mm-Umrechnung.

        Rückgabe: CheckResult. Ohne gelerntes Modell oder bei unbrauchbarem
        Frame -> UNAVAILABLE (Abweichung 0.0). Bei UNAVAILABLE wird `last_check_info`
        mit einer Diagnose (`reason`, Frame-Keypoints, Matches, Inlier-Ratio)
        gefüllt, damit die Ursache (kein Tisch / Tisch mismatch) sichtbar ist.
        """
        na = CheckResult(MonitorStatus.UNAVAILABLE, 0.0)

        def _na(reason, frame_kps=0, matches=0, inlier_ratio=None):
            self.last_check_info = {
                "reason": reason,
                "frame_keypoints": int(frame_kps),
                "matches": int(matches),
                "inlier_ratio": (round(float(inlier_ratio), 3)
                                 if inlier_ratio is not None else None),
            }
            self._consecutive_shifted = 0
            self.last_status = na.status
            return na

        if not self.learned or self._desc is None:
            return _na("no_model")
        if frame is None:
            return _na("no_frame")

        kps, desc = detect_keypoints(frame, nfeatures=MAX_CHECK_KEYPOINTS)
        if len(kps) == 0 or desc is None:
            return _na("no_frame_keypoints", frame_kps=len(kps))

        src_idx, dst_idx = match_keypoints(self._desc, desc)
        if len(src_idx) == 0:
            return _na("no_matches", frame_kps=len(kps))

        src = np.array([self._kps[int(i)].pt for i in src_idx], dtype=np.float64)
        dst = np.array([kps[int(i)].pt for i in dst_idx], dtype=np.float64)

        H, mask = cv2.findHomography(
            src, dst, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD,
            maxIters=RANSAC_MAX_ITERS)
        if H is None or mask is None:
            return _na("no_homography", frame_kps=len(kps),
                       matches=len(src_idx))

        inliers = mask.ravel().astype(bool)
        ratio = float(inliers.sum()) / float(len(inliers))
        if ratio < MIN_INLIER_RATIO:
            # Fläche belegt / zu wenig Übereinstimmung -> kein Check möglich
            return _na("low_inlier_ratio", frame_kps=len(kps),
                       matches=len(src_idx), inlier_ratio=ratio)

        self.last_check_info = {
            "reason": "ok",
            "frame_keypoints": int(len(kps)),
            "matches": int(len(src_idx)),
            "inlier_ratio": round(float(ratio), 3),
        }
        ref = src[inliers]
        dev_mm = _homography_deviation_mm(calib, H, ref, self._shape)

        if dev_mm >= DEVIATION_THRESHOLD_MM:
            self._consecutive_shifted += 1
            if self._consecutive_shifted >= HYSTERESIS:
                result = CheckResult(MonitorStatus.SHIFTED, dev_mm)
            else:
                result = CheckResult(MonitorStatus.OK, dev_mm)
        else:
            self._consecutive_shifted = 0
            result = CheckResult(MonitorStatus.OK, dev_mm)
        self.last_status = result.status
        return result