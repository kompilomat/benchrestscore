# -*- coding: utf-8 -*-
"""Persistenz & Wiederherstellung der finalisierten Kalibrier-Session.

Die letzte Kalibrierung wird **nur als volles Set** persistiert: erst wenn der
Kalibrier-Workflow vollständig abgeschlossen ist (Ergebnis akzeptiert + Hintergrund
mit Keypoints gelernt + Messmodus erreicht) werden Kalibrierung und Hintergrund
zusammen ins XDG-Config-Verzeichnis geschrieben und über `last_session.json` als
wiederherstellbar markiert. `recover_calibration()` (Controller) stellt das volle
Set wieder her (Kalibrierung + Monitormodell, inkl. Auflösungs-Validierung).

Reine, headless testbare Kernlogik (analog `automation.py`); Controller/UI halten
Zustand und Anzeige.
"""

import json
import os
from datetime import datetime, timezone

import cv2
import numpy as np

# Dual-Import: als Script und als Paket ladbar (vgl. controller.py).
try:
    from .settings import default_config_dir
except ImportError:
    from settings import default_config_dir


# --- Pfade (Config-Verzeichnis) ---


def calibration_png_path():
    return os.path.join(default_config_dir(), "last_calibration.png")


def calibration_overlay_path():
    return os.path.join(default_config_dir(), "last_calibration_overlay.png")


def calibration_json_path():
    return os.path.join(default_config_dir(), "last_calibration.json")


def background_png_path():
    return os.path.join(default_config_dir(), "last_background.png")


def background_overlay_path():
    return os.path.join(default_config_dir(), "last_background_overlay.png")


def background_json_path():
    return os.path.join(default_config_dir(), "last_background.json")


def session_marker_path():
    return os.path.join(default_config_dir(), "last_session.json")


def card_check_json_path():
    return os.path.join(default_config_dir(), "last_card_check.json")


def card_check_overlay_path():
    return os.path.join(default_config_dir(), "last_card_check_overlay.png")


# --- JSON-Helfer (fehlertolerant) ---


def write_json(path, data):
    """Daten als JSON schreiben; legt das Config-Verzeichnis an.

    Fehler werden verschluckt und als False gemeldet, damit die Messung nie
    durch Persistenz blockiert wird.
    """
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:  # pragma: no cover - darf nie blockieren
        print(f"[recovery] write failed ({path}): {exc}", flush=True)
        return False


def read_json(path):
    """JSON-Dict lesen; bei fehlender/kaputter Datei None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# --- Volles Set: Kalibrierung + Hintergrund schreiben ---


def save_full_session(calibration, background_model, background_raw,
                      background_overlay):
    """Die vollständige, finalisierte Session als volles Set persistieren.

    Schreibt zusammen: `last_calibration.png`/`_overlay.png`/`.json`,
    `last_background.png`/`_overlay.png`/`.json` und `last_session.json`
    (Marker). Nur aufrufen, wenn der Workflow komplett abgeschlossen ist
    (Kalibrierung akzeptiert + Hintergrund gelernt). Einzelne Fehler werden
    geloggt, nie als Exception weitergereicht.
    """
    errors = []

    def _write(frame, path):
        try:
            if frame is not None and isinstance(frame, np.ndarray):
                cv2.imwrite(path, frame)
        except Exception as exc:  # pragma: no cover
            errors.append(f"{os.path.basename(path)}: {exc}")

    try:
        os.makedirs(default_config_dir(), exist_ok=True)
    except Exception as exc:  # pragma: no cover
        errors.append(f"mkdir: {exc}")

    # Kalibrierung (Roh-Frame der Karte + Visual)
    cal_frame = getattr(calibration, "frame", None)
    cal_visual = getattr(calibration, "visual", None)
    _write(cal_frame, calibration_png_path())
    _write(cal_visual, calibration_overlay_path())

    # Sidecar (inkl. width/height/has_background)
    try:
        try:
            from .calibration_sidecar import CalibrationResult
        except ImportError:  # pragma: no cover
            from calibration_sidecar import CalibrationResult
        result = CalibrationResult.from_calibration(calibration, cal_frame, ok=True)
        result.has_background = True
        if not write_json(calibration_json_path(), json.loads(result.to_json())):
            errors.append("calibration.json")
    except Exception as exc:  # pragma: no cover
        errors.append(f"calibration.json: {exc}")

    # Hintergrund (Roh-Frame + Keypoint-Visual + Keypoints)
    _write(background_raw, background_png_path())
    _write(background_overlay, background_overlay_path())
    try:
        bg_data = background_model.to_dict()
        h, w = background_model.shape
        bg_data["width"] = int(w)
        bg_data["height"] = int(h)
        bg_data["keypoint_count"] = int(background_model.keypoint_count)
        if not write_json(background_json_path(), bg_data):
            errors.append("background.json")
    except Exception as exc:  # pragma: no cover
        errors.append(f"background.json: {exc}")

    # Erfolgs-Marker (wiederherstellbar)
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not write_session_marker(
                int(background_model.shape[1]), int(background_model.shape[0]),
                int(background_model.keypoint_count), ts):
            errors.append("session.json")
    except Exception as exc:  # pragma: no cover
        errors.append(f"session.json: {exc}")

    if errors:  # pragma: no cover
        print(f"[recovery] save_full_session partial: {errors}", flush=True)


# --- Session-Marker-Lifecycle ---


def write_session_marker(width, height, keypoint_count, timestamp):
    """`last_session.json` schreiben (finalisierte Session)."""
    return write_json(session_marker_path(), {
        "width": width,
        "height": height,
        "keypoint_count": keypoint_count,
        "timestamp": timestamp,
    })


def remove_session_marker():
    """`last_session.json` löschen (Abbruch/Reset/Kamerawechsel)."""
    try:
        path = session_marker_path()
        if os.path.exists(path):
            os.unlink(path)
        return True
    except Exception as exc:  # pragma: no cover
        print(f"[recovery] remove marker failed: {exc}", flush=True)
        return False


def has_valid_session():
    """True, wenn eine wiederherstellbare finalisierte Session vorliegt.

    Prüft: Marker `last_session.json` vorhanden, Kalibrier-Sidecar `ok=true` und
    `last_background.json` (mit wiederherstellbaren Keypoints) vorhanden.
    """
    marker = read_json(session_marker_path())
    if marker is None:
        return False
    if marker.get("width") is None or marker.get("height") is None:
        return False
    sidecar = read_json(calibration_json_path())
    if sidecar is None or not sidecar.get("ok"):
        return False
    if read_json(background_json_path()) is None:
        return False
    return True


# --- Hintergrund laden (für die Wiederherstellung) ---


def load_background(path, background_model_cls=None, reference_path=None):
    """Hintergrund aus `last_background.json` wiederherstellen.

    Lädt zusätzlich die dichte (LUT-entzerrte) Tisch-Referenz aus
    `reference_path` (Default: `last_background.png`), falls vorhanden und
    lesbar — die Gruppenerkennung ist dann sofort verfügbar. Ein fehlendes
    oder kaputtes Bild ist kein Fehler (Session bleibt mit Keypoints gültig).

    Rückgabe: `BackgroundModel` (geleernt), wenn das JSON gültige Keypoints/
    Descriptoren enthält; sonst ein ungelerntes `BackgroundModel`.
    """
    try:
        from .calibration_monitor import BackgroundModel
    except ImportError:  # pragma: no cover
        from calibration_monitor import BackgroundModel
    cls = background_model_cls or BackgroundModel
    data = read_json(path)
    if data is None:
        return cls()
    if not data.get("keypoints") or not data.get("descriptors"):
        return cls()
    model = cls.restore(data)
    if model.learned:
        ref_path = reference_path if reference_path is not None \
            else background_png_path()
        _attach_background_reference(model, ref_path)
    return model


def _attach_background_reference(model, png_path):
    """Dichte Tisch-Referenz aus `last_background.png` ins Modell laden.

    Fehlende/kaputte Datei oder Shape-Mismatch sind keine Fehler — das Modell
    bleibt gelernt, nur `has_reference` kann False sein.
    """
    try:
        if not os.path.exists(png_path):
            return
        img = cv2.imread(png_path)  # BGR
    except Exception:  # pragma: no cover
        return
    if img is None:
        return
    try:
        if model.shape != (0, 0) and img.shape[:2] != model.shape:
            h, w = model.shape
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        model.set_reference(img)
    except Exception:  # pragma: no cover
        return