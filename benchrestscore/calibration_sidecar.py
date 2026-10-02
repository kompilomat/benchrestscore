# -*- coding: utf-8 -*-
"""Pydantic-Sidecar für Kalibrier-Ergebnisse (headless testbar).

Schreibt `CalibrationResult` als JSON neben `last_calibration.png` ins
Config-Verzeichnis. Enthält Qualität, Korrekturen, Matrizen, per-Punkt-Fehler
und die Diagnose-Auswertungen (Radius-Kurve, Quadranten).
"""
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

# Dual-Import: als Script und als Paket ladbar (vgl. controller.py).
try:
    from .calibration import calibration_quality, error_vs_radius, quadrant_breakdown
except ImportError:
    from calibration import calibration_quality, error_vs_radius, quadrant_breakdown


def _to_list(matrix):
    """NumPy-Array in verschachtelte Liste umwandeln (JSON-fähig)."""
    return np.asarray(matrix).tolist()


class CalibrationResult(BaseModel):
    """Strukturiertes Ergebnis eines Kalibrier-Versuchs (Erfolg oder Fehlschlag)."""

    timestamp: str
    ok: bool
    error: str | None = None

    # Kamera-Kontext (aus AppController; fehlt er, None)
    device: str | None = None
    preset_name: str | None = None
    rotate: int | None = None

    # Rahmenmetadaten der finalisierten Session (für die Wiederherstellung)
    width: int | None = None
    height: int | None = None
    has_background: bool = False

    # Qualität (µm)
    mean_um: float | None = None
    sd_um: float | None = None
    quality: str | None = None

    # Korrekturen
    A_correction: str | None = None
    B_correction: str | None = None

    # Matrizen und Kanal-Parameter (Listen)
    mat: list | None = None
    mati: list | None = None
    channel_params: list | None = None

    # Per-Punkt-Fehlermatrix (mm) und Diagnose (µm)
    acc: list | None = None
    radius_curve: list | None = None
    quadrants: dict | None = None

    # Referenz-Raster der Kalibrierkarte in Weltmetrik (mm), Shape
    # (rows, cols, 2) — Grundlage des Karten-Qualitätschecks. Optional:
    # alte Sidecars ohne dieses Feld bleiben ladbar.
    grid_metric: list | None = None

    @classmethod
    def from_calibration(cls, cal, frame, ok, error=None):
        """Ergebnis aus einem `VMSCalibrate`-Objekt bauen.

        Bei Erfolg werden Qualität/Matrizen/Diagnose gefüllt; bei Fehlschlag
        bleibt nur `ok=False` + Fehlertext (der Roh-Frame dient dem PNG).
        """
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result = cls(
            timestamp=ts,
            ok=bool(ok),
            error=error,
            device=getattr(cal, "device", None),
            preset_name=getattr(cal, "preset_name", None),
            rotate=getattr(cal, "rotate", None),
        )
        # Rahmenmetadaten aus dem Frame (für die Wiederherstellungs-Validierung)
        if frame is not None and getattr(frame, "shape", None) is not None:
            h, w = frame.shape[:2]
            result.width = int(w)
            result.height = int(h)
        if not ok or not getattr(cal, "calibrated", False):
            return result

        result.mean_um = getattr(cal, "mean", None)
        result.sd_um = getattr(cal, "sd", None)
        if result.mean_um is not None:
            result.quality = calibration_quality(result.mean_um)
        result.A_correction = getattr(cal, "A_correction", None)
        result.B_correction = getattr(cal, "B_correction", None)
        result.mat = _to_list(getattr(cal, "mat", None)) if getattr(cal, "mat", None) is not None else None
        result.mati = _to_list(getattr(cal, "mati", None)) if getattr(cal, "mati", None) is not None else None
        result.channel_params = _to_list(getattr(cal, "channel_params", None)) if getattr(cal, "channel_params", None) is not None else None
        acc = getattr(cal, "acc", None)
        if acc is not None:
            result.acc = _to_list(acc)
            pmodel = getattr(cal, "pmodel", None)
            if pmodel is not None:
                result.radius_curve = [
                    [mid, mean] for mid, mean in error_vs_radius(acc, pmodel[:, :, :2])
                ]
            result.quadrants = quadrant_breakdown(acc)
        metric_grid = getattr(cal, "metric_grid", None)
        if metric_grid is not None:
            result.grid_metric = _to_list(metric_grid)
        return result

    def to_json(self):
        """JSON-String (eingerückt) für die Sidecar-Datei."""
        return self.model_dump_json(indent=2)