

import numpy as np
# suppress subnormal warnings from -ffast_math 
# https://stackoverflow.com/questions/70612364/numpy-warning-with-django-4-numpy-float64-type-is-zero
np.finfo(np.dtype("float32"))
np.finfo(np.dtype("float64"))

import scipy

# make sure it is installed >= 4.5.x
import cv2

from threading import Thread
from collections import deque

# Dual-Import: als Script und als Paket ladbar (vgl. controller.py).
try:
    from .i18n import tr
except ImportError:
    from i18n import tr
try:
    from .poly_warp import POLY3_N_PARAMS, poly3_features, poly3_features_jac, inv_distortion_poly
except ImportError:
    from poly_warp import POLY3_N_PARAMS, poly3_features, poly3_features_jac, inv_distortion_poly





class VMSChannel(Thread):
    def __init__(self, calib, channel, *args, **kwargs):
        super(VMSChannel, self).__init__(*args, **kwargs)
        self.daemon = False
        self.channel = channel
        self.calib = calib
        self.calibrated = False
        self.mean = 0
        self.sd = 0

    def run(self):
        pass


# papierkarte A 4.885mm --> raster=4.899
# pla 3d print raster=4.8
# Referenzmessungen (100 mm / 60 mm, Metalllineal) ergaben anisotrope Rastermasse,
# anschliessend um 0.6 % reduziert (Klick-Platzierungs-Bias-Korrektur).
RASTER_X_MM = 4.892
RASTER_Y_MM = 4.892
# Bewertungs-Bander fuer den mittleren Reprojektionsfehler (um); deckungsgleich
# mit bgr_accuracy in calibrate().
QUALITY_GOOD_UM = 50.0
QUALITY_OK_UM = 75.0
QUALITY_POOR_UM = 100.0


def calibration_quality(mean_um):
    """Klassifiziert den mittleren Reprojektionsfehler (µm).

    Rückgabe: "good" (<=50), "ok" (<=75), "poor" (<=100), "bad" (>100).
    Reine Logik, headless testbar.
    """
    if mean_um <= QUALITY_GOOD_UM:
        return "good"
    if mean_um <= QUALITY_OK_UM:
        return "ok"
    if mean_um <= QUALITY_POOR_UM:
        return "poor"
    return "bad"


def error_vs_radius(acc, ndc_grid, bins=8):
    """Fehler (µm) gemittelt in Radial-Bins um die Bildmitte.

    acc       per-Punkt-Fehlermatrix (mm), Shape (rows, cols).
    ndc_grid  (rows, cols, 2)-NDC-Koordinaten der Rasterpunkte (x in [-1,1],
              y symmetrisch); Radius relativ zur Bildmitte (0,0).
    Rückgabe: Liste von (Radius-Mitte, mean_µm); None, wenn ein Bin leer ist.
    """
    acc = np.asarray(acc, dtype=np.float64)
    ndc = np.asarray(ndc_grid, dtype=np.float64)
    r = np.linalg.norm(ndc[:, :, :2], axis=2)
    rmax = float(r.max())
    if rmax <= 0.0:
        return [(0.0, np.average(acc) * 1000 if acc.size else None)]
    edges = np.linspace(0.0, rmax, bins + 1)
    curve = []
    for i in range(bins):
        mask = (r >= edges[i]) & (r <= edges[i + 1])
        vals = acc[mask]
        mid = 0.5 * (edges[i] + edges[i + 1])
        curve.append((mid, np.average(vals) * 1000 if vals.size else None))
    return curve


def quadrant_breakdown(acc):
    """Fehler (µm) pro Bildquadrant.

    acc  per-Punkt-Fehlermatrix (mm); erste Achse = horizontale Richtung
         (Breite), zweite = vertikale (Höhe). Rückgabe-Dict TR/TL/BR/BL;
         eine Region ist None, wenn sie leer ist.
    """
    acc = np.asarray(acc, dtype=np.float64)
    rows, cols = acc.shape
    midx = rows // 2
    midy = cols // 2

    def _mean(mask):
        vals = acc[mask]
        return np.average(vals) * 1000 if vals.size else None

    return {
        "TL": _mean(np.ix_(np.arange(midx), np.arange(midy))),
        "TR": _mean(np.ix_(np.arange(midx, rows), np.arange(midy))),
        "BL": _mean(np.ix_(np.arange(midx), np.arange(midy, cols))),
        "BR": _mean(np.ix_(np.arange(midx, rows), np.arange(midy, cols))),
    }


def undistort_frame(frame, luts):
    """LUT-Korrektur in Software auf einen Frame anwenden (Shader-Spiegel).

    Rekonstruiert für jeden Farbkanal die Ziel-Texturkoordinate aus der
    4-Kanal-LUT (`(wh, wl, hh, hl)` = High-/Low-Byte der 16-Bit-x/y-Koordinate)
    exakt wie der GL-Fragment-Shader (`BRSCanvas.fragment` in app.py) und remapt
    den Kanal mit `cv2.remap` (bilinear, Replicate-Rand ≈ GL clamp-to-edge).
    Nur die Geometrie (Lens-Distortion) — keine Anzeige-Filter.

    frame  BGR-Frame (h, w, 3), uint8.
    luts   drei LUTs in BGR-Reihenfolge aus `compute_lut_channels()` — je
           (h, w, 4) uint8; None bei nicht-kalibrierter Kamera.

    Rückgabe: entzerrter BGR-Frame; ohne gültige LUTs (None, Länge ≠ 3, falsche
    Shape) unverändert `frame` — Persistenz blockiert nie.
    """
    if frame is None or luts is None:
        return frame
    if not isinstance(luts, (list, tuple, np.ndarray)) or len(luts) != 3:
        return frame
    try:
        h, w = frame.shape[:2]
    except Exception:  # pragma: no cover
        return frame
    # Graustufen-Frames (2D) haben keine pro-Kanal-LUT-Mappung → unverändert
    if frame.ndim != 3 or frame.shape[2] != 3:
        return frame
    for lut in luts:
        lut = np.asarray(lut)
        if lut.ndim != 3 or lut.shape[2] != 4:
            return frame
        if lut.shape[0] != h or lut.shape[1] != w:
            return frame
    out = np.empty_like(frame)
    for c, lut in enumerate(luts):
        lut = np.asarray(lut, dtype=np.float32)
        # Shader: u = raw.r + raw.g/256 (GL normalisiert uint8 -> /255)
        u = lut[..., 0] * (1.0 / 255.0) + lut[..., 1] * (1.0 / (255.0 * 256.0))
        v = lut[..., 2] * (1.0 / 255.0) + lut[..., 3] * (1.0 / (255.0 * 256.0))
        u = np.clip(u, 0.0, 1.0)
        v = np.clip(v, 0.0, 1.0)
        map_x = (u * w).astype(np.float32)
        map_y = (v * h).astype(np.float32)
        out[..., c] = cv2.remap(frame[..., c], map_x, map_y,
                                cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REPLICATE)
    return out


def downscale_luts(luts, rh, rw):
    """4-Kanal-LUTs (Vollauflösung) auf eine Ziel-Auflösung herunterskalieren.

    Die LUTs kodieren Ziel-Texturkoordinaten als 16-Bit-Werte (High-/Low-Byte
    je Achse). Naives Byte-Downscaling würde die Bytepaare zerlegen; deshalb
    werden die Koordinatenfelder dekodiert, als glatte Float-Karten per
    INTER_AREA skaliert und wieder in das 4-Kanal-Format kodiert.

    luts  Drei LUTs in BGR-Reihenfolge aus `compute_lut_channels()` (h, w, 4).
    rh/rw Ziel-Höhe/-Breite.

    Rückgabe: Liste aus drei downscaled LUTs (rh, rw, 4) uint8; None bei
    ungültigem Input (dann bleibt `undistort_frame` ein No-op).
    """
    if luts is None:
        return None
    if not isinstance(luts, (list, tuple, np.ndarray)) or len(luts) != 3:
        return None
    out = []
    for lut in luts:
        lut = np.asarray(lut)
        if lut.ndim != 3 or lut.shape[2] != 4:
            return None
        u = lut[..., 0] / 255.0 + lut[..., 1] / (255.0 * 256.0)
        v = lut[..., 2] / 255.0 + lut[..., 3] / (255.0 * 256.0)
        u = cv2.resize(u, (rw, rh), interpolation=cv2.INTER_AREA)
        v = cv2.resize(v, (rw, rh), interpolation=cv2.INTER_AREA)
        u16 = np.clip(np.round(u * 65280.0), 0, 65535).astype(np.int64)
        v16 = np.clip(np.round(v * 65280.0), 0, 65535).astype(np.int64)
        out.append(np.dstack([
            ((u16 >> 8) & 255).astype(np.uint8),
            (u16 & 255).astype(np.uint8),
            ((v16 >> 8) & 255).astype(np.uint8),
            (v16 & 255).astype(np.uint8),
        ]))
    return out


def _as_frame_list(frames):
    """Eingabe normalisieren: einzelnes Frame oder Liste -> Liste von Frames."""
    if isinstance(frames, np.ndarray) and frames.ndim == 4:
        return [np.asarray(fr) for fr in frames]
    if isinstance(frames, (list, tuple)):
        return [np.asarray(fr) for fr in frames if fr is not None]
    return [np.asarray(frames)] if frames is not None else []


class VMSCalibrate(object):
    def __init__(self, width, height, pattern=(32, 18), raster=4.899,

                 raster_x=None, raster_y=None):
        self.width = width
        self.height = height
        self.pattern = pattern
        self.raster = raster
        self.raster_x = raster_x if raster_x is not None else RASTER_X_MM
        self.raster_y = raster_y if raster_y is not None else RASTER_Y_MM
        self.calibrated = False
        self.result = None
        self.default_lut = None
        self.A_correction = ""
        self.B_correction = ""
        self.error = None

        self.mat = None
        self.mati = None
        # Referenz-Raster der Kalibrierkarte in Weltmetrik (Karten-QC).
        self.metric_grid = None


        ## shared parameters for blob detector
        blob_params = cv2.SimpleBlobDetector_Params()

        # Change thresholds 40, 190
        blob_params.minThreshold = 80
        blob_params.maxThreshold = 240

        # Set Area filtering parameters 
        blob_params.filterByArea = True
        blob_params.minArea = 80
        
        # Set Circularity filtering parameters 
        blob_params.filterByCircularity = True 
        blob_params.minCircularity = 0.65
        
        # Set Convexity filtering parameters 
        blob_params.filterByConvexity = True
        blob_params.minConvexity = 0.95
            
        # Set inertia filtering parameters 
        blob_params.filterByInertia = True
        blob_params.minInertiaRatio = 0.4

        self.blob_detector = cv2.SimpleBlobDetector_create(blob_params)

        self.rgb_blob_params = dict()
        self.rgb_blob_detector = dict()

        self.rgb_blob_params["r"] = cv2.SimpleBlobDetector_Params()

        # Change thresholds 40, 190
        self.rgb_blob_params["r"].minThreshold = 80
        self.rgb_blob_params["r"].maxThreshold = 240

        # Set Area filtering parameters 
        self.rgb_blob_params["r"].filterByArea = True
        self.rgb_blob_params["r"].minArea = 80
        
        # Set Circularity filtering parameters 
        self.rgb_blob_params["r"].filterByCircularity = True 
        self.rgb_blob_params["r"].minCircularity = 0.65
        
        # Set Convexity filtering parameters 
        self.rgb_blob_params["r"].filterByConvexity = True
        self.rgb_blob_params["r"].minConvexity = 0.95
            
        # Set inertia filtering parameters 
        self.rgb_blob_params["r"].filterByInertia = True
        self.rgb_blob_params["r"].minInertiaRatio = 0.4

        self.rgb_blob_detector["r"] = cv2.SimpleBlobDetector_create(self.rgb_blob_params["r"])

        self.rgb_blob_params["g"] = cv2.SimpleBlobDetector_Params()

        # Change thresholds 40, 190
        self.rgb_blob_params["g"].minThreshold = 80
        self.rgb_blob_params["g"].maxThreshold = 240

        # Set Area filtering parameters 
        self.rgb_blob_params["g"].filterByArea = True
        self.rgb_blob_params["g"].minArea = 80
        
        # Set Circularity filtering parameters 
        self.rgb_blob_params["g"].filterByCircularity = True 
        self.rgb_blob_params["g"].minCircularity = 0.65
        
        # Set Convexity filtering parameters 
        self.rgb_blob_params["g"].filterByConvexity = True
        self.rgb_blob_params["g"].minConvexity = 0.95
            
        # Set inertia filtering parameters 
        self.rgb_blob_params["g"].filterByInertia = True
        self.rgb_blob_params["g"].minInertiaRatio = 0.4

        self.rgb_blob_detector["g"] = cv2.SimpleBlobDetector_create(self.rgb_blob_params["g"])

        self.rgb_blob_params["b"] = cv2.SimpleBlobDetector_Params()

        # Change thresholds 40, 190
        self.rgb_blob_params["b"].minThreshold = 80
        self.rgb_blob_params["b"].maxThreshold = 240

        # Set Area filtering parameters 
        self.rgb_blob_params["b"].filterByArea = True
        self.rgb_blob_params["b"].minArea = 80
        
        # Set Circularity filtering parameters 
        self.rgb_blob_params["b"].filterByCircularity = True 
        self.rgb_blob_params["b"].minCircularity = 0.65
        
        # Set Convexity filtering parameters 
        self.rgb_blob_params["b"].filterByConvexity = True
        self.rgb_blob_params["b"].minConvexity = 0.95
            
        # Set inertia filtering parameters 
        self.rgb_blob_params["b"].filterByInertia = True
        self.rgb_blob_params["b"].minInertiaRatio = 0.4

        self.rgb_blob_detector["b"] = cv2.SimpleBlobDetector_create(self.rgb_blob_params["b"])




        # construct model of calibration plate
        self.model = np.ones((pattern[0], pattern[1], 3))
        for i in range(pattern[0]):
            for j in range(pattern[1]):
                self.model[i, j, 0] = i * self.raster_x
                self.model[i, j, 1] = j * self.raster_y


    def calibrate(self, frames):
        """Kalibrierung aus einem Frame oder mehreren Frames.

        `frames`: einzelnes BGR-Frame oder Liste von Frames (gleiche
        Auflösung). Bei mehreren Frames wird das NDC-Gitter über die Frames
        gemittelt (Rauschreduktion √N — identisch zur Messung im
        Karten-Qualitätscheck `calibration_card_qc.detect_grid_metric`).
        """
        frame_list = _as_frame_list(frames)
        if not frame_list:
            self.error = tr("calibration.card_not_found", count=0)
            return False
        self.frame = frame_list[-1]
        self.error = None

        # Vollbild-Rastererkennung pro Frame; NDC-Gitter mitteln.
        target_grids = []
        for fr in frame_list:
            circles_found, centers = self.find_circles(fr, self.blob_detector)
            if not circles_found:
                self.error = tr("calibration.card_not_found",
                                count=len(self.keypoints))
                return False
            target_grids.append(self.get_target_grid(centers))
        target_grid = np.mean(np.asarray(target_grids, dtype=np.float64),
                              axis=0)

        # debug visualization
        # detected_grid = target_grid[:, :, :2]
        # shp = detected_grid.shape
        # detected_grid = self.ndc2pix(detected_grid.reshape(-1, 2)).reshape(shp)

        projection_params = self.pre_estimate_projection(target_grid)
        a, b, c, d, e, f, g, h = projection_params
        self.mat = np.array([[a, d, g], [b, e, h], [c, f, 1.]])
        self.mati = np.linalg.inv(self.mat)

        # check camera orthogonality
        # oculus = position of the camera
        # Sources:
        # "Determining camera parameters from the perspective projection of a rectangle" (1989)
        # "Whiteboard scanning and image enhancement" (probably relevant)
        # https://stackoverflow.com/a/1222855
        # simple linear heuristic instead....
        wtop = target_grid[-1, 0] - target_grid[0, 0]
        wbot = target_grid[-1, -1] - target_grid[0, -1]
        hleft = target_grid[0, -1] - target_grid[0, 0]
        hright = target_grid[-1, -1] - target_grid[-1, 0]
        
        # TODO: estimate? parameter?
        wratio = 1 - np.linalg.norm(wtop) / np.linalg.norm(wbot)
        hratio = 1 - np.linalg.norm(hleft) / np.linalg.norm(hright)

        # from testing, related by aspect_ratio
        wslope = 0.00166428646726112
        hslope = 0.00322459818834792

        # angles
        A_degrees = hratio / hslope
        B_degrees = wratio / wslope
        self.A_correction = f'{abs(round(A_degrees * 5) / 5):.1f}{"L" if A_degrees > 0 else "R"}'
        self.B_correction = f'{abs(round(B_degrees * 5) / 5):.1f}{"L" if B_degrees > 0 else "R"}'
        #print(f"A: {self.A_correction}")
        #print(f"B: {self.B_correction}")

        # camera orthogonality using opencv solvepnp
        pattern_3d_points = np.array([
            self.model[0, 0],
            self.model[-1, 0],
            self.model[-1, -1],
            self.model[0, -1]
        ])
        pattern_3d_points[:, 2] = 0
        img_2d_points = np.array([
            target_grid[0, 0, :2],
            target_grid[-1, 0, :2],
            target_grid[-1, -1, :2],
            target_grid[0, -1, :2]
        ])
        dist_coeffs = np.zeros((4, 1))

        fx = 600 / (self.model[-1, 0, 0] / 2)
        cam_mat = np.array([[fx, 0., 0.],
                            [0., fx, 0.],
                            [0., 0., 1.],])

        succ, rot, trans = cv2.solvePnP(pattern_3d_points, img_2d_points, cam_mat, dist_coeffs, flags=0)
        optical_axis = np.matmul(np.array([0., 0., 1.]), self.mati)
        optical_axis[2] = 100.

        # get point in NDC
        endpoint, _ = cv2.projectPoints(optical_axis, rot, trans, cam_mat, dist_coeffs)

        # project back into world
        world_endpoint = np.ones(3)
        world_endpoint[:2] = endpoint[0][0]
        world_endpoint = np.matmul(world_endpoint, self.mati)

        # compute world angle
        dxdy = (world_endpoint - optical_axis)[:2]
        A_degrees = np.rad2deg(np.arctan2(dxdy[0], optical_axis[2]))
        B_degrees = np.rad2deg(np.arctan2(dxdy[1], optical_axis[2]))
        self.A_correction = f'{abs(round(A_degrees * 5) / 5):.1f}{"R" if A_degrees > 0 else "L"}'
        self.B_correction = f'{abs(round(B_degrees * 5) / 5):.1f}{"R" if B_degrees > 0 else "L"}'
        # endpoint = self.ndc2pix(np.clip(endpoint[0], -1, 1))
        # centerpoint = self.ndc2pix(np.array([[0., 0.]]))


        # debug visualization 
        #t = np.matmul(self.model, np.array([[a, d, g], [b, e, h], [c, f, 1.]]))
        #true_projected = t[:, :, :2]
        #shp = true_projected.shape
        #true_projected = self.ndc2pix(true_projected.reshape(-1, 2)).reshape(shp)

        self.pmodel = np.matmul(self.model, self.mat)

        # process channels independently, averaged over all frames
        # order BGR
        channel_target_grids = {code: [] for code in "bgr"}
        for fr in frame_list:
            channels = cv2.split(fr)
            for channel, code in zip(channels, "bgr"):
                blob_detector = self.rgb_blob_detector[code]
                # if code == "b":
                #     self.visualize_blob_detector(channel, blob_detector, self.rgb_blob_params[code])
                circles_found, centers = self.find_circles(channel, blob_detector)
                if not circles_found:
                    self.error = tr("calibration.channel_not_found",
                                    channel=code.upper(), count=len(self.keypoints))
                    return False
                channel_target_grids[code].append(
                    self.get_target_grid(centers))
        print("ALL CHANNELS FOUND")
        channel_target_grid = [
            np.mean(np.asarray(channel_target_grids[code], dtype=np.float64),
                    axis=0)
            for code in "bgr"]
        channel_params = [self.channel_distortion_estimation(cgrid, self.pmodel) for cgrid in channel_target_grid]

        acc, self.mean, self.sd = self.channel_reprojection_error(channel_target_grid, channel_params)
        self.acc = acc

        # Referenz-Raster der Kalibrierkarte in Weltmetrik (Grundlage des
        # Karten-Qualitätschecks). WICHTIG: dieselbe Pipeline wie die QC-Messung
        # (`calibration_card_qc.detect_grid_metric`) — Vollbild-Rastererkennung +
        # Inversion mit den gemittelten Kanal-Parametern + `mati` — damit
        # Referenz und Messung konsistent sind (sonst gilt die eigene Karte als
        # „out of spec"). Shape (pattern[0], pattern[1], 2), mm.
        avg_params = np.mean(np.asarray(channel_params, dtype=np.float64), axis=0)
        pts = self.inv_distortion(target_grid.reshape(-1, 3), avg_params)
        self.metric_grid = (pts @ self.mati)[:, :2].reshape(
            self.pattern[0], self.pattern[1], 2)


        pm = self.pmodel.reshape(-1, 3)
        est_grids = [self.distortion(pm, params).reshape(self.pattern[0], self.pattern[1], 3) for \
                     params in channel_params]
        true_projected = np.average(est_grids, axis=0)[:, :, :2]
        shp = true_projected.shape
        true_projected = self.ndc2pix(true_projected.reshape(-1, 2)).reshape(shp)


        ### legacy working solution
        # total_params = self.distortion_estimation(target_grid, projection_params)

        # store results
        # self.total_params = total_params
        # a, b, c, d, e, f, g, h, k1, k2, k3, k4, k5, k6, p1, p2 = total_params
        # self.mat = np.array([[a, d, g],
        #                     [b, e, h],
        #                     [c, f, 1.]])
        # self.mati = np.linalg.inv(self.mat)
        self.channel_params = channel_params
        self.calibrated = True

        # visualization output
        #estimated_grid = self.distortion(self.model.reshape(-1, 3), total_params).reshape(self.pattern[0], self.pattern[1], 3)
        #true_projected = estimated_grid[:, :, :2]
        #shp = true_projected.shape
        #true_projected = self.ndc2pix(true_projected.reshape(-1, 2)).reshape(shp)


        # acc, mean, sd = self.reprojection_error(target_grid, total_params)
        # print(f"ACC MEAN {self.mean:.0f}um  SD {self.sd:.0f}um")

        def bgr_accuracy(a):
            if a <= 0.05:
                return (0., 255., 0.)
            elif a <= 0.075:
                return (0., 255., 255.)
            elif a <= 0.1:
                return (0., 150., 255.)
            else:
                return (0., 0., 255.)

        self.visual = self.frame.copy()
        if self.keypoints:
            blank = np.zeros((1, 1))
            self.visual = cv2.drawKeypoints(self.visual, self.keypoints, blank,
                                      (0, 0, 255), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

        # cv2.arrowedLine(self.visual, np.rint(centerpoint[0]).astype(int), np.rint(endpoint[0]).astype(int), (144, 140, 0), 2)

        true = np.rint(true_projected).astype(int)
        for x in range(self.pattern[0]): # rows
            for y in range(self.pattern[1]):  # cols
                if x < self.pattern[0] - 1:
                    # draw line to the left
                    cv2.line(self.visual, true[x, y], true[x+1, y], (0, 140, 255), 2)
                if y < self.pattern[1] - 1:
                    cv2.line(self.visual, true[x, y], true[x, y+1], (0, 140, 255), 2)

                col = bgr_accuracy(acc[x, y])

                cv2.putText(self.visual, f"{acc[x, y]*1000:.0f}",
                            (int(true[x, y, 0]) + 5, int(true[x, y, 1]) + 40),
                            cv2.FONT_HERSHEY_DUPLEX, 1.1, col, 2)

        # Diagnose-Overlay: Radius-Befund (innerster->äußerster Bin) und
        # Quadranten-Fehler (µm) — oben links im Ergebnis-Bild.
        self.radius_curve = error_vs_radius(acc, self.pmodel[:, :, :2])
        self.quadrants = quadrant_breakdown(acc)
        rc = [m for _, m in self.radius_curve if m is not None]
        radius_text = "R " + ("->".join(f"{v:.0f}" for v in (rc[0], rc[-1]))) if rc else "R -"
        q = self.quadrants
        quad_text = "Q TR:{:.0f} TL:{:.0f} BR:{:.0f} BL:{:.0f}".format(
            q["TR"] or 0, q["TL"] or 0, q["BR"] or 0, q["BL"] or 0)
        org = (20, 60)
        for line in (radius_text, quad_text):
            cv2.putText(self.visual, line, org,
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3,
                        cv2.LINE_AA)
            cv2.putText(self.visual, line, org,
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 1,
                        cv2.LINE_AA)
            org = (org[0], org[1] + 45)


        return True

    def channel_distortion_estimation(self, target_grid,  pmodel):
        # Grad-3-Polynom-Fit (linear, geschlossen per lstsq)
        pmodel = pmodel.reshape(-1,  3)
        target_grid = target_grid.reshape(-1,  3)
        F = poly3_features(pmodel[:, :2])
        C, _, _, _ = np.linalg.lstsq(F, target_grid[:, :2], rcond=None)
        return C.ravel()
    

    # NOT USED
    def compute_mappings(self):
        if self.calibrated:
            wpix = np.arange(self.frame.shape[1])  # x
            hpix = np.arange(self.frame.shape[0])  # y
            xx, yy = np.meshgrid(wpix, hpix)
            pixels = np.column_stack((xx.ravel(), yy.ravel()))
            ndc_pixels = self.pix2ndc(pixels)

            ndc_dist = self.distort_only(ndc_pixels, self.total_params)

            px = self.ndc2pix(ndc_dist)
            mx = px[:, 0].reshape(self.frame.shape[:2]).astype("float32")
            my = px[:, 1].reshape(self.frame.shape[:2]).astype("float32")
            return cv2.convertMaps(mx, my, cv2.CV_16SC2)
        else:
            return None, None

    def compute_lut_channels(self):
        # set to 1 for full 4K LUT Map
        # sampling_step = 2 is effectively 1080p and interpolation in between
        sampling_step = 2
        if self.calibrated:
            wpix = np.arange(self.frame.shape[1], step=sampling_step)  # x
            hpix = np.arange(self.frame.shape[0], step=sampling_step)  # y
            xx, yy = np.meshgrid(wpix, hpix)
            pixels = np.column_stack((xx.ravel(), yy.ravel()))
            ndc_pixels = self.pix2ndc(pixels)

            ndc_pixels = np.hstack([ndc_pixels, np.ones((ndc_pixels.shape[0], 1))])

            res = []

            h, w, _ = self.frame.shape
            aspect_ratio = w / h

            for params in self.channel_params:
                # costly operation
                ndc_dist = self.distortion(ndc_pixels, params)[:, :2]

                # normalize xy from [-1,1] into [0, 1] for texture coordinates
                ndc_dist[:, 0] = (ndc_dist[:, 0] + 1) / 2
                ndc_dist[:, 1] = (1 - ndc_dist[:, 1] * aspect_ratio) / 2

                # reshape into frame aspect ratio
                ndc_dist = ndc_dist.reshape(self.frame.shape[0] // sampling_step,
                                            self.frame.shape[1] // sampling_step,
                                            -1)

                # unpool and average interpolated values
                if sampling_step == 2:
                    ndc_dist = np.repeat(ndc_dist, sampling_step, axis=0)
                    ndc_dist[1:-2:2, :] += (ndc_dist[2::2, :] - ndc_dist[:-2:2, :]) / 2
                    ndc_dist = np.repeat(ndc_dist, sampling_step, axis=1)
                    ndc_dist[:, 1:-2:2] += (ndc_dist[:, 2::2] - ndc_dist[:, :-2:2]) / 2

                # split up information in low and high byte
                ndc16 = np.clip(ndc_dist * 65536, 0, 65535)
                wh = np.floor(ndc16[:, :, 0] / 256).astype(np.uint8)
                wl = np.mod(ndc16[:, :, 0], 256).astype(np.uint8)
                hh = np.floor(ndc16[:, :, 1] / 256).astype(np.uint8)
                hl = np.mod(ndc16[:, :, 1], 256).astype(np.uint8)

                lut = np.dstack([wh, wl, hh, hl])
                res.append(lut)

            # cv2.namedWindow("lol", cv2.WINDOW_NORMAL)
            # cv2.resizeWindow("lol", (self.width, self.height))
            # cv2.imshow("lol", res[0])
            # cv2.waitKey(0)
            # cv2.destroyWindow("lol")
            return res
        else:
            return None

    def default_lut_channels(self):
        if self.default_lut is None:
            # http://luohanjie.com/2023-01-29/use-opengl-shader-to-realize-opencv-remap-function.html
            # https://community.khronos.org/t/lookup-tables-in-glsl/65216/5
            w16 = np.linspace(0, 1, self.width, False) * 65536
            wpix_high = np.floor(w16 / 256).astype(np.uint8)
            wpix_low = np.mod(w16, 256).astype(np.uint8)
            h16 = np.linspace(0, 1, self.height, False) * 65536
            hpix_high = np.floor(h16 / 256).astype(np.uint8)
            hpix_low = np.mod(h16, 256).astype(np.uint8)
            wh, hh = np.meshgrid(wpix_high, hpix_high)
            wl, hl = np.meshgrid(wpix_low, hpix_low)
            self.default_lut = np.dstack([wh, wl, hh, hl])
        return self.default_lut

    def compute_lut(self):
        if self.calibrated:
            wpix = np.arange(self.frame.shape[1])  # x
            hpix = np.arange(self.frame.shape[0])  # y
            xx, yy = np.meshgrid(wpix, hpix)
            pixels = np.column_stack((xx.ravel(), yy.ravel()))

            ndc_pixels = self.pix2ndc(pixels)
            ndc_dist = self.distort_only(ndc_pixels, self.total_params)
            px = self.ndc2pix(ndc_dist).reshape(*self.frame.shape[:2], -1)

            wh = np.floor(px[:, :, 0] / 256).astype(np.uint8)
            wl = np.mod(px[:, :, 0], 256).astype(np.uint8)
            hh = np.floor(px[:, :, 1] / 256).astype(np.uint8)
            hl = np.mod(px[:, :, 1], 256).astype(np.uint8)

            lut = np.dstack([wh, wl, hh, hl])
            return lut
        else:
            return None

    def pix2ndc(self, points):
        h, w, _ = self.frame.shape
        aspect_ratio = w / h
        ret = np.zeros(points.shape)
        # x .. width
        ret[:, 0] = points[:, 0] * 2. / w - 1.
        # y .. height, div by w to keep aspect ratio
        ret[:, 1] = (1. - points[:, 1] * 2. / h) / aspect_ratio

        return ret

    def ndc2pix(self, points):
        h, w, _ = self.frame.shape
        aspect_ratio = w / h
        ret = np.zeros(points.shape)
        ret[:, 0] = (points[:, 0] + 1.) * w * 0.5
        ret[:, 1] = (1. - points[:, 1] * aspect_ratio) * h * 0.5
        return ret

    def find_circles(self, frame, blob_detector):
        self.keypoints = blob_detector.detect(frame)
        circles_found, centers = cv2.findCirclesGrid(frame, self.pattern, None,
                                            flags=(cv2.CALIB_CB_SYMMETRIC_GRID | cv2.CALIB_CB_CLUSTERING),
                                            blobDetector=blob_detector)
        return circles_found, centers

    def get_target_grid(self, centers):
        # coordinates are normalized
        # X axis -1 to +1 (width)
        # Y axis -(1 / aspect ratio) to +(1 / aspect ratio) (height)
        h, w, _ = self.frame.shape
        aspect_ratio = w / h
        
        # centers is shape (num_circles, 1, 2)
        normed = self.pix2ndc(centers.reshape((-1, 2)))
        centers = deque(normed)
        
        grid = np.ones((self.pattern[0], self.pattern[1], 3))

        # find point closest to origin 0, 0
        # progress top down, line by line
        for x in range(self.pattern[0]):
            for y in range(self.pattern[1]):
                if y == 0:
                    # special case, first element in col
                    if x == 0:
                        # special case, first row
                        # ndc of top left corner of img
                        prev_point = np.array([-1., 1. / aspect_ratio])
                    else:
                        prev_point = grid[x-1, y, :2]
                    vec = np.array(centers) - prev_point
                    dist = np.linalg.norm(vec, axis=1)
                    min_idx = np.argmin(dist)
                    
                    grid[x, y, :2] = centers[min_idx]
                    del centers[min_idx]

                else:
                    # regular case: find nearest neighbor below
                    prev_point = grid[x, y-1, :2]
                    vec = np.array(centers) - prev_point
                    dist = np.linalg.norm(vec, axis=1)
                    
                    if x == self.pattern[0] - 1:
                        # special case, last col
                        min_idx = np.argmin(dist)
                    else:
                        nn1_idx = np.argmin(dist)
                        dist[nn1_idx] = np.inf
                        nn2_idx = np.argmin(dist)
                        min_idx = nn2_idx
                        # choose nn below 
                        if vec[nn1_idx, 1] < vec[nn2_idx, 1]:
                            min_idx = nn1_idx
                    grid[x, y, :2] = centers[min_idx]
                    del centers[min_idx]
        return grid

    def pre_estimate_projection(self, target_grid):
        def grid_error(params):
            a, b, c, d, e, f, g, h = params
            mat = np.array([[a, d, g],
                            [b, e, h],
                            [c, f, 1.]])
            proj_model = np.matmul(self.model, mat)
            # errors = np.sum(np.square(target_grid - proj_model), axis=2)
            # only consider corner points for projection
            errors = np.square(target_grid[0, 0] - proj_model[0, 0]) + \
                     np.square(target_grid[0, -1] - proj_model[0, -1]) + \
                     np.square(target_grid[-1, 0] - proj_model[-1, 0]) + \
                     np.square(target_grid[-1, -1] - proj_model[-1, -1])
            return np.average(errors)

        affine_pre_estimation = [1., 0., 0., 0., 1., 0., 0., 0.]
        res = scipy.optimize.minimize(grid_error, affine_pre_estimation, method="BFGS", tol=1e-7)
        # print("PRE RES", res)
        return res.x

    def distortion(self, hpoints, params):
        if len(params) == POLY3_N_PARAMS:
            out = np.copy(hpoints)
            out[:, :2] = poly3_features(hpoints[:, :2]) @ params.reshape(10,  2)
            return out
        a, b, c, d, e, f, g, h, k1, k2, k3, k4, k5, k6, p1, p2 = params

        mat = np.array([[a, d, g],
                        [b, e, h],
                        [c, f, 1.]])

        hpoints_proj = np.matmul(hpoints, mat)
        
        # precompute x2 + y2 term
        r2 = np.sum(np.square(hpoints_proj[:, :2]), axis=1)
        y2 = np.square(hpoints_proj[:, 1])
        x2 = np.square(hpoints_proj[:, 0])
        xy = hpoints_proj[:, 0] * hpoints_proj[:, 1]

        distort_factor_x = (1 + \
                            k1 * r2 + \
                            k2 * np.square(r2) + \
                            k3 * np.power(r2, 3) + \
                            k4 * np.power(r2, 4) + \
                            k5 * np.power(r2, 5) + \
                            k6 * np.power(r2, 6) + \
                            2 * p1 * xy + \
                            p2 * (r2 + 2*x2)) 
        distort_factor_y = (1 + \
                            k1 * r2 + \
                            k2 * np.square(r2) + \
                            k3 * np.power(r2, 3) + \
                            k4 * np.power(r2, 4) + \
                            k5 * np.power(r2, 5) + \
                            k6 * np.power(r2, 6) + \
                            p1 * (r2 + 2*y2) + \
                            2 * p2 * xy)
        hpoints_proj[:, 0] *= distort_factor_x
        hpoints_proj[:, 1] *= distort_factor_y

        return hpoints_proj

    def inv_distortion(self, hpoints, params):
        if len(params) == POLY3_N_PARAMS:
            return inv_distortion_poly(hpoints,  params)
        # based on https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4934233/
        a, b, c, d, e, f, g, h, k1, k2, k3, k4, k5, k6, p1, p2 = params
        mat = np.array([[a, d, g],
                        [b, e, h],
                        [c, f, 1.]])
        mati = np.linalg.inv(mat)

        # homogeneous point list of the grid
        points_c = np.copy(hpoints)
        points_cprev = np.zeros(points_c.shape)

        err = np.sum(np.square(points_c - points_cprev))

        while err > 1e-15:

            r2 = np.sum(np.square(points_c[:, :2]), axis=1)
            y2 = np.square(points_c[:, 1])
            x2 = np.square(points_c[:, 0])
            xy = points_c[:, 0] * points_c[:, 1]

            # undistort
            distort_factor_x = (1 + \
                            k1 * r2 + \
                            k2 * np.square(r2) + \
                            k3 * np.power(r2, 3) + \
                            k4 * np.power(r2, 4) + \
                            k5 * np.power(r2, 5) + \
                            k6 * np.power(r2, 6) + \
                            2 * p1 * xy + \
                            p2 * (r2 + 2*x2))
            distort_factor_y = (1 + \
                            k1 * r2 + \
                            k2 * np.square(r2) + \
                            k3 * np.power(r2, 3) + \
                            k4 * np.power(r2, 4) + \
                            k5 * np.power(r2, 5) + \
                            k6 * np.power(r2, 6) + \
                            p1 * (r2 + 2*y2) + \
                            2 * p2 * xy)
            points_cprev = np.copy(points_c)
            points_c[:, 0] = hpoints[:, 0] / distort_factor_x
            points_c[:, 1] = hpoints[:, 1] / distort_factor_y
            err = np.sum(np.square(points_c - points_cprev))
            
        # project into undistorted space and return
        return np.matmul(points_c, mati)

    def distortion_estimation(self, target_grid, pre_params):      
        def distortion_error(params):
            model_proj = self.distortion(self.model.reshape(-1, 3), params).reshape(self.pattern[0], self.pattern[1], 3)
            errors = np.sum(np.square(target_grid - model_proj), axis=2)
            #weight = 2. - np.sum(np.square(target_grid[:, :, :2]), axis=2)
            #weight *= 10
            weight = 1. / np.power(2., np.linalg.norm(target_grid[:, :, :2], axis=2))
            return np.average(errors * weight)
            #return np.average(errors * weight) + 0.001 * np.sum(np.square(params[8:]))

        total_params =  list(pre_params) + [0., 0., 0., 0., 0., 0., 0., 0.]
        self.result = scipy.optimize.minimize(distortion_error, total_params, method="BFGS", tol=1e-5)
        return self.result.x

    
    def reprojection_error(self, target_grid, params):
        real_points = self.inv_distortion(target_grid.reshape(-1, 3), params)[:, :2]
        diff = np.linalg.norm(self.model.reshape(-1, 3)[:, :2] - real_points, axis=1)
        shp = target_grid.shape
        acc = diff.reshape(shp[:2])
        return acc, np.average(acc)*1000, np.sqrt(np.var(acc))*1000


    def channel_reprojection_error(self, channel_target_grid, channel_params):

        metric_points = [np.matmul(self.inv_distortion(t.reshape(-1, 3), p), self.mati)[:, :2] \
                         for t, p in zip(channel_target_grid, channel_params)]

        metric_points = np.average(metric_points, axis=0)
        diff = np.linalg.norm(self.model.reshape(-1, 3)[:, :2] - metric_points, axis=1)
        shp = channel_target_grid[0].shape
        acc = diff.reshape(shp[:2])

        return acc, np.average(acc)*1000, np.sqrt(np.var(acc))*1000




    def distort_only(self, points, params):
        a, b, c, d, e, f, g, h, k1, k2, k3, k4, k5, k6, p1, p2 = params

        ret = np.zeros(points.shape)

        # precompute x2 + y2 term
        r2 = np.sum(np.square(points[:, :2]), axis=1)
        y2 = np.square(points[:, 1])
        x2 = np.square(points[:, 0])
        xy = points[:, 0] * points[:, 1]

        distort_factor_x = (1 + \
                            k1 * r2 + \
                            k2 * np.square(r2) + \
                            k3 * np.power(r2, 3) + \
                            k4 * np.power(r2, 4) + \
                            k5 * np.power(r2, 5) + \
                            k6 * np.power(r2, 6) + \
                            2 * p1 * xy + \
                            p2 * (r2 + 2*x2)) 
        distort_factor_y = (1 + \
                            k1 * r2 + \
                            k2 * np.square(r2) + \
                            k3 * np.power(r2, 3) + \
                            k4 * np.power(r2, 4) + \
                            k5 * np.power(r2, 5) + \
                            k6 * np.power(r2, 6) + \
                            p1 * (r2 + 2*y2) + \
                            2 * p2 * xy)
        ret[:, 0] = points[:, 0] * distort_factor_x
        ret[:, 1] = points[:, 1] * distort_factor_y

        return ret

    def visualize_blob_detector(self, img, blob_detector, blob_params):
        keypoints = blob_detector.detect(img)
        #_, img = cv2.threshold(img, blob_params.minThreshold, blob_params.maxThreshold, cv2.THRESH_BINARY)

        im_with_keypoints = cv2.drawKeypoints(img, keypoints, np.array([]), (0,0,255), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
        cv2.namedWindow("lol", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("lol", (self.width, self.height))
        cv2.imshow("lol", im_with_keypoints)
        cv2.waitKey(0)
        cv2.destroyWindow("lol")
