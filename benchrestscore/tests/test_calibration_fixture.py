# -*- coding: utf-8 -*-
"""Headless Regressionstest auf kommittierter Kalibrierkarten-Aufnahme.

Lädt `data/calibration_card.png` (echte 4K-Aufnahme, Karte füllt das Bild)
und fährt die volle Kalibrierung darüber. Dient als deterministische Basis
für spätere Modell-Änderungen: Bänder aus dem Polynom-Modell-Ist-Wert beim
Anlegen(mean≈17 µm, sd≈9 µm) mit Toleranz für Maschinenvarianz.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import cv2

from benchrestscore.calibration import (
    VMSCalibrate,
    error_vs_radius,
    quadrant_breakdown,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE_PATH = os.path.join(REPO_ROOT, "benchrestscore", "data",
                             "calibration_card.png")

# Genauigkeits-Bänder des Polynom-Modells (mean ≈ 17 µm, sd ≈ 9 µm).
MAX_MEAN_UM = 20.0
MAX_SD_UM = 12.0
# Flachheits-Grenze der Radius-Kurve (kein Sattel-/Eck-Anstieg mehr.
RADIUS_FLAT_DELTA_UM = 25.0


def _load_fixture():
    frame = cv2.imread(FIXTURE_PATH)
    assert frame is not None, f"Fixture fehlt: {FIXTURE_PATH}"
    return frame


def test_fixture_calibrates():
    frame = _load_fixture()
    cal = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal.calibrate(frame) is True, cal.error
    # Qualität in festen Bändern (Ist: mean 34.6, sd 18.5)
    assert 0 < cal.mean <= MAX_MEAN_UM, f"mean {cal.mean} außerhalb Band"
    assert 0 < cal.sd <= MAX_SD_UM, f"sd {cal.sd} außerhalb Band"


def test_fixture_acc_shape():
    frame = _load_fixture()
    cal = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal.calibrate(frame) is True
    assert np.asarray(cal.acc).shape == (32, 18)


def test_fixture_diagnostics_plausible():
    frame = _load_fixture()
    cal = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal.calibrate(frame) is True
    curve = error_vs_radius(cal.acc, cal.pmodel[:, :, :2])
    means = [m for _, m in curve if m is not None]
    assert len(means) == len(curve), "Radius-Bins dürfen nicht leer sein"
    assert all(m > 0 for m in means)
    # Radius-Profil ist flach: kein Sattel-/Eck-Anstieg mehr
    assert means[-1] < means[0] + RADIUS_FLAT_DELTA_UM
    q = quadrant_breakdown(cal.acc)
    assert all(v is not None and v > 0 for v in q.values())


def test_fixture_calibrate_writes_nothing_and_sidecar_buildable():
    save_env = os.environ.get("XDG_CONFIG_HOME")
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as td:
        os.environ["XDG_CONFIG_HOME"] = td
        try:
            frame = _load_fixture()
            cal = VMSCalibrate(frame.shape[1], frame.shape[0])
            assert cal.calibrate(frame) is True
            # Kalibrierung wird nur als volles Set (mit Hintergrund) persistiert:
            # ein blosser Kalibrier-Erfolg schreibt noch keine Dateien.
            cfg = os.path.join(td, "benchrestscore")
            names = os.listdir(cfg) if os.path.isdir(cfg) else []
            assert "last_calibration.png" not in names
            assert "last_calibration_overlay.png" not in names
            assert "last_calibration.json" not in names
            # Sidecar aus dem echten Kalibrier-Objekt ist weiterhin baubar und
            # trägt Qualität + Rahmenmetadaten (für das volle Set).
            from benchrestscore.calibration_sidecar import CalibrationResult
            res = CalibrationResult.from_calibration(cal, frame, ok=True)
            res.has_background = True
            assert res.ok is True
            assert abs(res.mean_um - float(cal.mean)) < 1e-6
            assert res.quality == "good"
            assert res.quadrants is not None
            assert set(res.quadrants) == {"TR", "TL", "BR", "BL"}
            assert res.width == frame.shape[1] and res.height == frame.shape[0]
            assert res.channel_params is not None
            assert [len(p) for p in res.channel_params] == [20, 20, 20]
        finally:
            if save_env is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = save_env



def test_legacy_16_channel_params_still_dispatch():
    frame = _load_fixture()
    cal = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal.calibrate(frame) is True
    pm = cal.pmodel.reshape(-1, 3)
    legacy = np.zeros(16)
    legacy[0] = 1.0
    legacy[4] = 1.0
    # Legacy (16er, Affine+k/p`: Vorwärts und Inversion laufen (≈ Identität
    out = cal.distortion(pm, legacy)
    assert np.all(np.isfinite(out))
    back = cal.inv_distortion(out, legacy)
    assert np.all(np.isfinite(back))
    # LUT-Berechnung ok mit Legacy-Format (Dispatch anhand Länge)
    cal.channel_params = np.tile(legacy, (3, 1))
    luts = cal.compute_lut_channels()
    assert luts is not None and len(luts) == 3
    # und mit neuem 20er-Format weiterhin ok
    cal2 = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal2.calibrate(frame) is True
    luts2 = cal2.compute_lut_channels()
    assert luts2 is not None and len(luts2) == 3

def test_fixture_poly_roundtrip_under_1um():
    frame = _load_fixture()
    cal = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal.calibrate(frame) is True
    pm = cal.pmodel.reshape(-1, 3)
    um_per_ndc = (frame.shape[1] / 2.0) * 41.74
    for params in cal.channel_params:
        back = cal.inv_distortion(cal.distortion(pm, params), params)
        err = np.linalg.norm(back[:, :2] - pm[:, :2], axis=1).mean()
        assert err * um_per_ndc < 1.0, f"roundtrip {err * um_per_ndc:.3f} um"

if __name__ == "__main__":
    for fn in (test_fixture_calibrates,
               test_fixture_acc_shape,
               test_fixture_diagnostics_plausible,
               test_fixture_calibrate_writes_nothing_and_sidecar_buildable,
               test_legacy_16_channel_params_still_dispatch,
               test_fixture_poly_roundtrip_under_1um):
        fn()
        print(f"PASS {fn.__name__}")
    print("All fixture tests passed")