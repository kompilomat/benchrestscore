# -*- coding: utf-8 -*-
"""Qualitätscheck von Kalibrierkarten (headless testbar).

Misst eine eingelegte Kalibrierkarte unter der **kalibrierten** Kamera und
vergleicht sie gegen die Referenzkarte — die gemessenen Rasterpunkte der Karte,
mit der die App kalibriert wurde (`grid_metric` im Kalibrier-Sidecar).

**Mess-Pipeline** (identisch für Referenz und Messung): Vollbild-Rastererkennung
(`findCirclesGrid`) im Roh-Frame → NDC (`get_target_grid`) → Inversion der
Linsen-Distortion mit den gemittelten Kanal-Parametern (`inv_distortion`) →
Weltmetrik über `mati`. Weil Referenz und Messung dieselbe Pipeline nutzen,
ergibt dieselbe Karte ≈ 0 Restfehler. Das Overlay (`pixel_grid`) verwendet die
**Roh-Pixelpositionen** der Blobs (keine Distortion-Inversion), weil es auf den
Roh-Frame gezeichnet und erst danach LUT-entzerrt angezeigt wird.

**Rauschreduktion**: Es werden `QC_SAMPLE_FRAMES` (3) aufeinanderfolgende
Frames erfasst; die NDC-Gitter werden über die Frames **gemittelt**, bevor die
Distortion-Inversion läuft. Das senkt das Detektionsrauschen (Blob-Jitter) um
≈ √N. Dasselbe Sampling nutzt die Kalibrierung (`VMSCalibrate.calibrate`), damit
Referenz und Messung konsistent bleiben.

**Ausgleichung**: Die gemessene Punktwolke wird per **Homographie** (DLT,
Least-Squares, alle Punkte) auf die Referenz abgebildet. Eine starre
Rotation+Translation genügt nicht: Das Metrik-Mapping hat ein positionsabhängiges
Fehlerfeld (Ø ~20 µm, max ~60 µm), das bei minimal anderer Einlage der Karte
verrauscht — die Homographie entfernt Einlage-Variation (Versatz, Drehung,
Skalierung/Perspektive) und lässt **lokale** Kartenfehler im Fehlermaß sichtbar.
Die Karte ist *in Spec*, wenn **jeder** Punkt nach der Ausgleichung innerhalb
`QC_TOLERANCE_MM` (±0,075 mm) liegt; Punkte bis ±0,05 mm sind grün, bis ±0,075
mm orange (beides in Spec), darüber rot/out of spec.

Reine Kernlogik; Controller/UI halten Zustand und Anzeige und lassen die
Erfassung in einem Hintergrund-Thread laufen (analog `automation.py`,
`calibration_recovery.py`).
"""

from collections import namedtuple
from datetime import datetime, timezone

import cv2
import numpy as np

# Dual-Import: als Script (`benchrestscore/` auf sys.path) und als Paket
# (`benchrestscore.calibration_card_qc` in Tests) ladbar.
try:
    from .calibration import VMSCalibrate
    from .calibration_recovery import (
        card_check_json_path,
        card_check_overlay_path,
        write_json,
    )
except ImportError:
    from calibration import VMSCalibrate
    from calibration_recovery import (
        card_check_json_path,
        card_check_overlay_path,
        write_json,
    )


# Anzahl der Frames, über die bei Messung (und Kalibrierung) gemittelt wird.
# Reduziert das Detektionsrauschen (Blob-Jitter) um ≈ √N.
QC_SAMPLE_FRAMES = 3

# Toleranz pro Punkt: Karte **out of spec**, wenn ein Punkt nach der
# Ausgleichung diese Grenze überschreitet. Punkte bis `QC_WARN_MM` gelten als
# unkritisch (grün), bis `QC_TOLERANCE_MM` als grenzwertig (orange) — beide noch
# in Spec; nur darüber ist die Karte rot/out of spec. Die Werte liegen bewusst
# über dem Einzelbild-Detektionsrauschen (~±40 µm max über 576 Punkte), damit
# eine gute Karte zuverlässig besteht und echte Druckfehler (> 75 µm)
# durchfallen.
QC_TOLERANCE_MM = 0.075  # > 75 µm -> rot / out of spec
QC_WARN_MM = 0.050       # > 50 µm -> orange (noch in Spec), darunter grün


class GridResult(namedtuple("GridResult", ["metric_grid", "pixel_grid",
                                           "circle_count"])):
    """Ergebnis einer Raster-Detektion.

    Erfolg: `metric_grid` (Weltmetrik) und `pixel_grid` (**Rohbild**-
    Pixelpositionen des Blobs, shape (rows, cols, 2)) gefüllt; Fehlschlag:
    beide None, `circle_count` = Anzahl der im Gesamtbild gefundenen Kreise
    (für die Fehlermeldung). `pixel_grid` in Roh-Koordinaten ist bewusst: Das
    Overlay wird auf den Roh-Frame gezeichnet, der danach LUT-entzerrt wird;
    ein Marker an der Roh-Position des Blobs erscheint auf dem Display genau
    auf dem Blob (eine vorherige Distortion-Inversion würde die Entzerrung
    doppelt anwenden).
    """


def detect_grid_metric(frames, calibration):
    """Raster in einem (oder mehreren) Frames erkennen und vermessen.

    Akzeptiert ein einzelnes BGR-Frame **oder** eine Liste von Frames. Bei
    mehreren Frames wird das NDC-Gitter über die Frames **gemittelt**
    (Rauschreduktion, `QC_SAMPLE_FRAMES`), bevor `inv_distortion` + `mati`
    laufen. Dieselbe Pipeline wie die Referenz (`calibration.metric_grid`),
    damit dieselbe Karte ≈ 0 Restfehler ergibt. `pixel_grid` stammt aus dem
    gemittelten NDC-Gitter (Roh-Pixelpositionen der Blobs).

    frames      BGR-Frame oder Liste von BGR-Frames (gleiche Auflösung).
    calibration aktives Kalibrier-Objekt mit `mati` + `channel_params`.

    Rückgabe: `GridResult`.
    """
    if frames is None:
        return GridResult(None, None, 0)
    if isinstance(frames, np.ndarray) and frames.ndim == 4:
        frame_list = [np.asarray(fr) for fr in frames]
    elif isinstance(frames, (list, tuple)):
        frame_list = [np.asarray(fr) for fr in frames if fr is not None]
    else:
        frame_list = [frames]
    if not frame_list or frame_list[0] is None:
        return GridResult(None, None, 0)
    h, w = frame_list[0].shape[:2]
    mati = np.asarray(getattr(calibration, "mati", None), dtype=np.float64)
    channel_params = getattr(calibration, "channel_params", None)
    # Der Vergleich braucht die aktive Metrik (Homographie) und die
    # Linsen-Distortion — ohne Kalibrierung geht es nicht.
    if mati is None or channel_params is None:
        return GridResult(None, None, 0)

    work = VMSCalibrate(w, h)
    target_grids = []
    circle_count = 0
    for fr in frame_list:
        work.frame = fr
        # Nur `findCirclesGrid` (nicht zusätzlich `blob_detector.detect` — das
        # ist eine zweite Vollbild-Detektion, nur für die Kreiszahl gebraucht).
        circles_found, centers = cv2.findCirclesGrid(
            fr, work.pattern, None,
            flags=(cv2.CALIB_CB_SYMMETRIC_GRID | cv2.CALIB_CB_CLUSTERING),
            blobDetector=work.blob_detector)
        if not circles_found:
            kps = work.blob_detector.detect(fr)
            circle_count = len(kps) if kps is not None else 0
            continue
        target_grids.append(work.get_target_grid(centers))
    if not target_grids:
        return GridResult(None, None, circle_count)

    # NDC-Gitter über die Frames mitteln (Rauschreduktion √N).
    target_grid = np.mean(np.asarray(target_grids, dtype=np.float64), axis=0)
    avg_params = np.mean(np.asarray(channel_params, dtype=np.float64), axis=0)

    # Weltmetrik (identische Pipeline wie die Referenz).
    points = work.inv_distortion(target_grid.reshape(-1, 3), avg_params)
    metric_grid = (points @ mati)[:, :2].reshape(
        work.pattern[0], work.pattern[1], 2)

    # Overlay-Pixelpositionen in **Rohbild-Koordinaten**: Das Overlay wird auf
    # den Roh-Frame gezeichnet und der gesamte Frame danach durch den
    # LUT-Shader (bzw. `undistort_frame`) entzerrt. Ein Marker an der
    # **Roh-Pixelposition** des Blobs landet nach der Entzerrung exakt dort,
    # wo der Blob auf dem Display erscheint (empirisch verifiziert: ~1–4 px).
    # Eine Inversion der Distortion hier würde die Entzerrung doppelt
    # anwenden und die Marker auf dem Display verbiegen.
    # `ndc2pix` erwartet flache (n, 2)-Punkte (bei 3D-Input greift `points[:, 0]`
    # auf die falsche Achse zu -> bis zu mehrere tausend Pixel daneben).
    raw_pix = work.ndc2pix(target_grid[:, :, :2].reshape(-1, 2))
    pixel_grid = np.asarray(raw_pix, dtype=np.float64).reshape(
        work.pattern[0], work.pattern[1], 2)
    return GridResult(metric_grid, pixel_grid, circle_count)


def rigid_align(source, target):
    """Least-Squares-**Rotation + Translation** (constraint), Skala = 1.

    Umeyama mit fixem Skala=1: verschiebt/rotiert `source` so nah wie möglich zu
    `target`. Die Ebene bleibt gleich (fix montierte Kamera, planees Einlegen),
    deshalb nur dieser 3 Freiheitsgrade — Skalierung/perspektive bleiben im
    Fehlermaß, das die eigentliche Karten-Abweichung misst.

    source/target: (n, 2) oder (rows, cols, 2) in derselben Einheit (mm).
    Rückgabe: transformiertes `source`-Array (gleiche Shape, mm).
    """
    s = np.asarray(source, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    shape = s.shape
    s_f = s.reshape(-1, 2)
    t_f = t.reshape(-1, 2)
    cs = s_f.mean(axis=0)
    ct = t_f.mean(axis=0)
    sm = s_f - cs
    tm = t_f - ct
    cov = sm.T @ tm
    u, _, vt = np.linalg.svd(cov)
    rot = vt.T @ u.T
    if np.linalg.det(rot) < 0:
        vt[-1] *= -1.0
        rot = vt.T @ u.T
    aligned = sm @ rot.T + ct
    return aligned.reshape(shape)


def homography_align(source, target):
    """Least-Squares-**Homographie** (DLT, alle Punkte) zwischen Punktwolken.

    Bilde `source` projektiv so nah wie möglich auf `target` ab (8
    Freiheitsgrade, inkl. Skalierung/Perspektive). Grund: Das Metrik-Mapping
    (`inv_distortion @ mati`) hat ein positionsabhängiges Fehlerfeld — eine
    starre Rotation+Translation reicht nicht, um die Einlage-Variation einer
    identischen Karte zu entfernen. Die Homographie gleicht die globale
    Einlage (Versatz, Drehung, Skala, Tilt) aus; **lokale** Kartenfehler
    bleiben im Fehlermaß sichtbar. Numerisch stabil über normalisierte
    Koordinaten.

    source/target: (n, 2) oder (rows, cols, 2) in derselben Einheit (mm).
    Rückgabe: transformiertes `source`-Array (gleiche Shape, mm).
    """
    s = np.asarray(source, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    shape = s.shape
    s_f = s.reshape(-1, 2)
    t_f = t.reshape(-1, 2)
    if len(s_f) < 4:
        return s.reshape(shape)

    # Normalisieren (verbessert die Kondition der DLT-Normalgleichung).
    ms, ss = s_f.mean(axis=0), s_f.std(axis=0)
    mt, st = t_f.mean(axis=0), t_f.std(axis=0)
    ss = np.where(ss == 0, 1.0, ss)
    st = np.where(st == 0, 1.0, st)
    sn = (s_f - ms) / ss
    tn = (t_f - mt) / st

    a = np.column_stack([
        sn[:, 0], sn[:, 1], np.ones(len(sn)),
        np.zeros(len(sn)), np.zeros(len(sn)), np.zeros(len(sn)),
        -tn[:, 0] * sn[:, 0], -tn[:, 0] * sn[:, 1],
    ])
    b0 = np.column_stack([
        np.zeros(len(sn)), np.zeros(len(sn)), np.zeros(len(sn)),
        sn[:, 0], sn[:, 1], np.ones(len(sn)),
        -tn[:, 1] * sn[:, 0], -tn[:, 1] * sn[:, 1],
    ])
    A = np.vstack([a, b0])
    B = np.concatenate([tn[:, 0], tn[:, 1]])
    h = np.linalg.lstsq(A, B, rcond=None)[0]
    Hn = np.array([[h[0], h[1], h[2]],
                   [h[3], h[4], h[5]],
                   [h[6], h[7], 1.0]])
    # Rücktransformation in originale Koordinaten.
    T1 = np.array([[1 / ss[0], 0, -ms[0] / ss[0]],
                   [0, 1 / ss[1], -ms[1] / ss[1]],
                   [0, 0, 1]])
    T2 = np.array([[st[0], 0, mt[0]],
                   [0, st[1], mt[1]],
                   [0, 0, 1]])
    H = T2 @ Hn @ T1

    pts = np.ones((len(s_f), 3))
    pts[:, :2] = s_f
    p = pts @ H.T
    aligned = p[:, :2] / p[:, 2:3]
    return aligned.reshape(shape)


def check_card(reference, measured, tolerance_mm=QC_TOLERANCE_MM):
    """Punktweise Abweichung der gemessenen von der Referenzkarte (µm).

    Wendet die **Homographie**-Ausgleichung (DLT, alle Punkte) an, bevor die
    ±-Toleranz evaluiert wird. Abweichungen in µm (per Punkt), Max/Mean und
    `pass` (alle innerhalb der Toleranz) — `None` bei Shape-Mismatch.

    reference/measured: (rows, cols, 2) oder (n, 2) Weltmetrikdaten (mm).
    Rückgabe: dict `{pass, max_um, mean_um, over_um, count,
    deviations_um}`.
    """
    ref = np.asarray(reference, dtype=np.float64)
    meas = np.asarray(measured, dtype=np.float64)
    if ref.shape != meas.shape or meas.ndim not in (2, 3) \
            or meas.shape[-1] != 2:
        return None
    aligned = homography_align(meas, ref)
    dist = np.linalg.norm(aligned.reshape(-1, 2) - ref.reshape(-1, 2), axis=1)
    deviations = dist * 1000.0  # µm
    return {
        "pass": bool(np.all(dist <= tolerance_mm)),
        "max_um": float(np.max(deviations)),
        "mean_um": float(np.mean(deviations)),
        "over_count": int(np.sum(dist > tolerance_mm)),
        "count": int(dist.size),
        "deviations_um": deviations.reshape(meas.shape[:-1]),
    }


def _over_count(deviations_um, tolerance_mm=QC_TOLERANCE_MM):
    return int(np.sum(np.asarray(deviations_um) > tolerance_mm * 1000.0))


def render_overlay(frame, pixel_grid, deviations_um, passed):
    """Overlay für das Ergebnisbild: Punkte + per-Punkt-Abweichung (µm).

    `pixel_grid` enthält **Rohbild-Pixelpositionen** der Blobs (aus
    `detect_grid_metric`): Das Overlay wird auf `frame` (Roh-Frame) gezeichnet
    und der komplette Frame wird danach LUT-entzerrt angezeigt, sodass die
    Marker genau auf den Blobs des angezeigten Bilds liegen. Farbkodierung je
    Punkt: grün = ≤ 50 µm, orange = 50–75 µm (beides in Spec), rot = > 75 µm
    (out of spec). Rückgabe: BGR-Kopie mit Overlay.
    """
    out = frame.copy()
    tol_um = QC_TOLERANCE_MM * 1000.0
    warn_um = QC_WARN_MM * 1000.0
    pix = np.asarray(pixel_grid, dtype=np.float64)
    devs = np.asarray(deviations_um, dtype=np.float64)
    for i in range(devs.shape[0]):
        for j in range(devs.shape[1]):
            x, y = int(round(pix[i, j, 0])), int(round(pix[i, j, 1]))
            dev = float(devs[i, j])
            if dev > tol_um:
                color = (60, 60, 255)
            elif dev > warn_um:
                color = (60, 180, 255)
            else:
                color = (60, 255, 60)
            cv2.circle(out, (x, y), 16, color, 3)
            cv2.putText(out, f"{dev:.0f}", (x + 22, y + 8),
                        cv2.FONT_HERSHEY_DUPLEX, 1.35, color, 2)
    summary = "IN SPEC" if passed else \
        f"OUT OF SPEC ({_over_count(devs)})"
    cv2.putText(out, summary, (24, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(out, summary, (24, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                (60, 255, 60) if passed else (60, 60, 255), 1, cv2.LINE_AA)
    return out


def save_result(payload, overlay=None):
    """Ergebnis-JSON + Overlay-PNG ins Config-Verzeichnis schreiben.

    `last_card_check.json` (JSON-fähiges dict) und optional
    `last_card_check_overlay.png`. Schreibfehler werden geschluckt und als
    False gemeldet — Persistenz blockiert nie.
    """
    ok_json = write_json(card_check_json_path(), payload)
    ok_png = True
    if overlay is not None:
        try:
            ok_png = bool(cv2.imwrite(card_check_overlay_path(), overlay))
        except Exception as exc:  # pragma: no cover — darf nie blockieren
            print(f"[card_qc] overlay write failed: {exc}", flush=True)
            ok_png = False
    return bool(ok_json and ok_png)


def build_payload(reference, measured, check_result):
    """JSON-fähiges Ergebnis-Dict bauen (für `save_result`)."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pass": bool(check_result["pass"]),
        "max_um": float(check_result["max_um"]),
        "mean_um": float(check_result["mean_um"]),
        "over_count": int(check_result["over_count"]),
        "count": int(check_result["count"]),
        "tolerance_mm": QC_TOLERANCE_MM,
        "reference_grid": np.asarray(reference, dtype=np.float64).tolist(),
        "measured_grid": np.asarray(measured, dtype=np.float64).tolist(),
        "deviations_um": np.asarray(
            check_result["deviations_um"], dtype=np.float64).tolist(),
    }