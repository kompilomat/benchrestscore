# -*- coding: utf-8 -*-
"""Referenz-Snapshots für realistische Tests gegen die manuelle Bewertung.

Erfasst im App-Betrieb (Referenz-Modus) die komplette Szene als selbst-
enthaltenes Sample: rohes + LUT-entzerrtes Bild, aktuelle Kalibrierung,
gelerntes Untergrund-Modell (Keypoints + dichte Referenz) und alle manuellen
Messpunkte in Weltmetrik. Damit lässt sich ein Erkennungs-Verfahren (z.B. die
Klick-Automation `find_center`) headless gegen die Bewertung eines Menschen
prüfen.

Ablage: ein nummerierter Ordner pro Referenzfall (`sample_01/`, `sample_02/`,
…) in der Dataset-Wurzel `BRS_REFERENCE_DATASET` (Default: Repo-`datasets/`).
Reine, headless testbare Kernlogik; Controller/UI halten Zustand und Anzeige.
"""

import json
import os

import cv2
import numpy as np

# Dual-Import: als Script (`benchrestscore/` auf sys.path) und als Paket
# (`benchrestscore.reference_eval` in Tests) ladbar (vgl. controller.py).
try:
    from .calibration_monitor import BackgroundModel
    from .view import BRSView
    from .automation import find_center, metric_to_pixel
except ImportError:
    from calibration_monitor import BackgroundModel
    from view import BRSView
    from automation import find_center, metric_to_pixel


# --- Datei-Namen eines Samples ---
CALIBRATION_JSON = "calibration.json"
CALIBRATION_PNG = "calibration.png"
CALIBRATION_OVERLAY_PNG = "calibration_overlay.png"
BACKGROUND_JSON = "background.json"
BACKGROUND_PNG = "background.png"
EVALUATION_PNG = "evaluation.png"
RAW_PNG = "raw.png"
METRICS_JSON = "metrics.json"

# Cache geladener Samples (key: absoluter sample_dir-Pfad). Die Samples sind
# pro Prozess-Lauf unveränderlich; der Cache spart wiederholtes 4K-Bild-Laden
# in Tests (`test_reference_dataset.py`) und Diagnose.
_REFERENCE_CACHE = {}


def clear_reference_cache():
    """Cache der geladenen Referenz-Samples leeren."""
    _REFERENCE_CACHE.clear()


def repo_dataset_root():
    """Repo-`datasets/`-Verzeichnis (Standard-Ablage der Samples)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "datasets")


def dataset_root():
    """Dataset-Wurzel; `BRS_REFERENCE_DATASET` übersteuert Repo-`datasets/`."""
    env = os.environ.get("BRS_REFERENCE_DATASET")
    if env:
        return env
    return repo_dataset_root()


def list_reference_samples(root=None):
    """Vorhandene Sample-Verzeichnisse (`sample_*`), aufsteigend sortiert."""
    root = root or dataset_root()
    if not os.path.isdir(root):
        return []
    names = [n for n in sorted(os.listdir(root)) if n.startswith("sample_")]
    return [os.path.join(root, n) for n in names]


def next_sample_dir(root=None):
    """Nächstes freies Sample-Verzeichnis (`sample_NN`, fortlaufend)."""
    root = root or dataset_root()
    highest = 0
    for path in list_reference_samples(root):
        name = os.path.basename(path)
        try:
            num = int(name.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        highest = max(highest, num)
    return os.path.join(root, "sample_%02d" % (highest + 1))


def save_sample(sample_dir, calibration, background_model, frame_undist,
                metrics, cal_frame=None, cal_visual=None, frame_raw=None):
    """Ein vollständiges Sample schreiben (fehlertolerant).

    sample_dir          Zielordner (wird angelegt; `sample_NN`).
    calibration         Kalibrierung (mat/mati, frame/visual für PNGs).
    background_model    Gelerntes Untergrund-Modell (Keypoints + Referenz).
    frame_undist        LUT-entzerrter Kamera-Frame (`evaluation.png`).
    metrics             Dict: width/height, caliber_name/caliber_radius_mm,
                        points (Weltmetrik), mat/mati, timestamp.
    cal_frame/visual    Kalibrierkarten-Bilder (optional).
    frame_raw           Roh-Kameraframe (`raw.png`, optional).

    Rückgabe: True, wenn alle Pflicht-Dateien geschrieben wurden.
    """
    try:
        os.makedirs(sample_dir, exist_ok=True)
    except OSError:
        return False

    ok = True

    def _write_image(frame, name):
        nonlocal ok
        if frame is None:
            return
        try:
            if cv2.imwrite(os.path.join(sample_dir, name), frame) is False:
                ok = False
        except Exception:  # pragma: no cover
            ok = False

    _write_image(frame_undist, EVALUATION_PNG)
    _write_image(frame_raw, RAW_PNG)
    _write_image(cal_frame, CALIBRATION_PNG)
    _write_image(cal_visual, CALIBRATION_OVERLAY_PNG)

    # Dichte Referenz in nativer (downscaled) Auflösung — exakt der RAM-Stand.
    ref = getattr(background_model, "reference", None)
    if ref is not None:
        _write_image(np.asarray(ref, dtype=np.uint8), BACKGROUND_PNG)

    # Kalibrierung als Sidecar (identische Struktur wie die Session-Persistenz).
    try:
        from .calibration_sidecar import CalibrationResult
    except ImportError:  # pragma: no cover
        from calibration_sidecar import CalibrationResult
    try:
        result = CalibrationResult.from_calibration(calibration, cal_frame, ok=True)
        with open(os.path.join(sample_dir, CALIBRATION_JSON), "w",
                  encoding="utf-8") as f:
            f.write(result.to_json())
    except Exception:  # pragma: no cover
        ok = False

    # Untergrund: Keypoints + Descriptoren + Kontext.
    try:
        bg = background_model.to_dict()
        h, w = background_model.shape
        bg["width"] = int(w)
        bg["height"] = int(h)
        bg["keypoint_count"] = int(background_model.keypoint_count)
        with open(os.path.join(sample_dir, BACKGROUND_JSON), "w",
                  encoding="utf-8") as f:
            json.dump(bg, f, indent=2)
    except Exception:  # pragma: no cover
        ok = False

    # Metriken (selbst-enthalten für den headless Test-Lauf).
    try:
        with open(os.path.join(sample_dir, METRICS_JSON), "w",
                  encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
    except Exception:  # pragma: no cover
        ok = False
    return ok


class ReferenceData(object):
    """Geladene Metriken eines Samples (self-contained für den Test-Lauf)."""

    def __init__(self, width, height, caliber_name, caliber_radius_mm,
                 points, mat, mati):
        self.width = int(width)
        self.height = int(height)
        self.caliber_name = caliber_name
        self.caliber_radius_mm = float(caliber_radius_mm)
        self.points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        self.mat = np.asarray(mat, dtype=np.float64)
        self.mati = np.asarray(mati, dtype=np.float64)


def load_reference(json_path):
    """`metrics.json` laden; None bei fehlender/ungültiger Datei."""
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def load_reference_sample(sample_dir):
    """Sample laden → (ReferenceData, frame_undist, BackgroundModel).

    `frame` ist der LUT-entzerrte Frame (`evaluation.png`), `model` das
    wiederhergestellte Untergrund-Modell inkl. dichter Referenz in nativer
    Auflösung. Rückgabe (None, None, None), wenn `metrics.json` fehlt.

    Geladene Samples werden pro Prozess-Lauf zwischengespeichert
    (`clear_reference_cache()` leert den Cache).
    """
    key = os.path.abspath(sample_dir)
    if key in _REFERENCE_CACHE:
        return _REFERENCE_CACHE[key]
    metrics = load_reference(os.path.join(sample_dir, METRICS_JSON))
    if metrics is None:
        return None, None, None
    raw_points = metrics.get("points", [])
    points_xy = [(float(p["x"]), float(p["y"])) if isinstance(p, dict) else p
                 for p in raw_points]
    data = ReferenceData(
        metrics.get("width", 0), metrics.get("height", 0),
        metrics.get("caliber_name", ""), metrics.get("caliber_radius_mm", 0.0),
        points_xy,
        metrics.get("mat", np.eye(3)), metrics.get("mati", np.eye(3)))

    model = BackgroundModel()
    bg_path = os.path.join(sample_dir, BACKGROUND_JSON)
    if os.path.exists(bg_path):
        try:
            with open(bg_path, "r", encoding="utf-8") as f:
                model = BackgroundModel.restore(json.load(f))
        except (OSError, ValueError):  # pragma: no cover
            pass
    ref_path = os.path.join(sample_dir, BACKGROUND_PNG)
    if os.path.exists(ref_path):
        ref = cv2.imread(ref_path)
        if ref is not None:
            model.reference = ref.astype(np.float32)
            model.reference_shape = (data.height, data.width)
            model.reference_raw = model.reference

    frame = cv2.imread(os.path.join(sample_dir, EVALUATION_PNG))
    if frame is not None:
        _REFERENCE_CACHE[key] = (data, frame, model)
    return data, frame, model


LATCH_TOLERANCE_MM = 0.2


def evaluate_automation(sample_dir, click_jitter_px=0.0, seed=0):
    """Klick-Automation gegen die manuelle Bewertung prüfen (realistischer Test).

    Pro manuellem Punkt wird `find_center` nahe dem projizierten Punkt
    ausgeführt (Identitäts-View auf `frame_size`) und der Fehler des
    verfeinerten Zentrums gegen die manuelle Weltmetrik gemessen. `ok=False`
    der Automation wird als Fehler eines nicht gefundenen Lochs gewertet.

    Zusätzlich wird pro Punkt klassifiziert, ob das detektierte Zentrum auf ein
    **anderes** manuelles Loch „gelatcht" ist (näher an einer anderen manuellen
    Position als an der des angeklickten Lochs, Toleranz `LATCH_TOLERANCE_MM`).

    Rückgabe: Dict mit `n_manual`, `errors_mm` (je Punkt; None, wenn die
    Automation fehlschlug), `mean_error_mm`, `max_error_mm`, `latched`
    (je Punkt: True/False bzw. None bei Fehlschlag) und `n_latched`.
    """
    data, frame, model = load_reference_sample(sample_dir)
    if data is None or frame is None:
        return None
    fh, fw = frame.shape[:2]
    view = BRSView(fw, fh)
    view.set_dimensions(fw, fh)
    size = (fw, fh)
    rng = np.random.default_rng(seed)
    errors = []
    latched = []
    for i, m in enumerate(data.points):
        m3 = np.append(m, 1.0)
        px = metric_to_pixel(view, m3, size, data)
        if click_jitter_px > 0:
            px = px + rng.uniform(-click_jitter_px, click_jitter_px, 2)
        res = find_center(frame, view, (float(px[0]), float(px[1])), size,
                          data, data.caliber_radius_mm)
        if res.ok and res.center_metric is not None:
            c = res.center_metric[:2]
            err = float(np.linalg.norm(c - m[:2]))
            errors.append(err)
            d_click = float(np.linalg.norm(c - m[:2]))
            d_other = min((float(np.linalg.norm(c - o[:2]))
                           for j, o in enumerate(data.points) if j != i),
                          default=float("inf"))
            latched.append(bool(d_other + LATCH_TOLERANCE_MM < d_click))
        else:
            errors.append(None)
            latched.append(None)
    valid = [e for e in errors if e is not None]
    return {
        "n_manual": len(data.points),
        "errors_mm": errors,
        "mean_error_mm": float(np.mean(valid)) if valid else None,
        "max_error_mm": float(np.max(valid)) if valid else None,
        "latched": latched,
        "n_latched": sum(1 for l in latched if l),
    }


def evaluate_automation_dataset(sample_dirs, click_jitter_px=0.0, seed=0):
    """Klick-Automation gegen eine Menge von Samples prüfen (Aggregat).

    Führt `evaluate_automation` pro Sample aus und sammelt die Ergebnisse samt
    Sample-Name. Nicht ladbare Samples werden übersprungen; ohne gültige Samples
    liefert die Funktion ein leeres Aggregat statt zu scheitern.

    Rückgabe: Dict mit `samples` (je Eintrag `name`, `n_manual`, `n_found`,
    `n_latched`, `errors_mm`, `mean_error_mm`, `max_error_mm`), `total_points`,
    `total_found`, `total_latched`, `mean_error_mm`, `max_error_mm`.
    """
    results = []
    for sample_dir in sample_dirs:
        res = evaluate_automation(sample_dir, click_jitter_px=click_jitter_px,
                                  seed=seed)
        if res is None:
            continue
        valid = [e for e in res["errors_mm"] if e is not None]
        results.append({
            "name": os.path.basename(sample_dir),
            "n_manual": res["n_manual"],
            "n_found": len(valid),
            "n_latched": res["n_latched"],
            "errors_mm": res["errors_mm"],
            "mean_error_mm": res["mean_error_mm"],
            "max_error_mm": res["max_error_mm"],
        })
    found = [e for r in results for e in r["errors_mm"] if e is not None]
    return {
        "samples": results,
        "total_points": sum(r["n_manual"] for r in results),
        "total_found": len(found),
        "total_latched": sum(r["n_latched"] for r in results),
        "mean_error_mm": float(np.mean(found)) if found else None,
        "max_error_mm": float(np.max(found)) if found else None,
    }