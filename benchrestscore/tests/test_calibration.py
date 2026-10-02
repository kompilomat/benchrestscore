# -*- coding: utf-8 -*-
"""Headless unit tests for the calibration quality logic (no GL/OpenCV)."""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

from benchrestscore.calibration import (
    calibration_quality,
    error_vs_radius,
    quadrant_breakdown,
    undistort_frame,
    downscale_luts,
    VMSCalibrate,
)
from benchrestscore.calibration_sidecar import CalibrationResult
from benchrestscore.i18n import current_language, set_language, tr


def test_good_at_zero():
    assert calibration_quality(0.0) == "good"


def test_good_at_threshold():
    assert calibration_quality(50.0) == "good"


def test_ok_above_good():
    assert calibration_quality(50.01) == "ok"
    assert calibration_quality(75.0) == "ok"


def test_poor_above_ok():
    assert calibration_quality(75.01) == "poor"
    assert calibration_quality(100.0) == "poor"


def test_bad_above_poor():
    assert calibration_quality(100.01) == "bad"
    assert calibration_quality(200.0) == "bad"


def test_negative_clamps_to_good_band():
    # negative Werte (theoretisch) nicht vorkommend, aber konsistent zur
    # <=-Logik: kleiner/gleich 50 -> good
    assert calibration_quality(-1.0) == "good"


def test_error_vs_radius_increases_outward():
    xx, yy = np.meshgrid(np.linspace(-1, 1, 9), np.linspace(-1, 1, 9))
    ndc = np.stack([xx, yy, np.ones_like(xx)], axis=-1)
    # Fehler wächst mit dem Radius (mm) -> äußere Bins müssen höher liegen
    acc = np.linalg.norm(ndc[:, :, :2], axis=2)
    curve = error_vs_radius(acc, ndc, bins=4)
    means = [m for _, m in curve]
    assert all(m is not None for m in means)
    assert means[-1] > means[0]


def test_error_vs_radius_units_micrometers():
    acc = np.full((4, 4), 0.001)  # 1 µm überall
    xx, yy = np.meshgrid(np.linspace(-1, 1, 4), np.linspace(-1, 1, 4))
    ndc = np.stack([xx, yy, np.ones_like(xx)], axis=-1)
    curve = error_vs_radius(acc, ndc, bins=2)
    for _, m in curve:
        assert m is not None
        assert abs(m - 1.0) < 1e-9


def test_quadrant_breakdown_separates_corners():
    acc = np.zeros((8, 8))
    acc[0, 0] = 0.20       # TL (x klein, y klein)
    acc[6:8, 6:8] = 0.05   # BR
    acc[1:-1, 1:-1] = 0.01
    res = quadrant_breakdown(acc)
    assert res["TL"] > res["BR"]
    assert res["TL"] > res["TR"]
    assert res["TL"] > res["BL"]


def test_quadrant_breakdown_symmetric():
    acc = np.ones((8, 8)) * 0.001
    res = quadrant_breakdown(acc)
    for k, v in res.items():
        assert v is not None
        assert abs(v - 1.0) < 1e-9


class _FakeCal(object):
    def __init__(self):
        self.device = "/dev/video0"
        self.preset_name = "4K30"
        self.rotate = 180
        self.mean = 40.0
        self.sd = 12.0
        self.A_correction = "1.5L"
        self.B_correction = "0.0R"
        self.mat = np.eye(3)
        self.mati = np.eye(3)
        self.channel_params = np.zeros((3, 16))
        self.acc = np.full((4, 4), 0.002)
        self.pmodel = np.zeros((4, 4, 3))
        xx, yy = np.meshgrid(np.linspace(-1, 1, 4), np.linspace(-1, 1, 4))
        self.pmodel[:, :, 0] = xx
        self.pmodel[:, :, 1] = yy
        self.pmodel[:, :, 2] = 1.0
        self.calibrated = True


def test_sidecar_success_populates_fields():
    cal = _FakeCal()
    res = CalibrationResult.from_calibration(cal, None, ok=True)
    assert res.ok is True
    assert res.error is None
    assert res.device == "/dev/video0"
    assert res.preset_name == "4K30"
    assert res.rotate == 180
    assert res.mean_um == 40.0
    assert res.sd_um == 12.0
    assert res.quality == "good"
    assert res.mat == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert len(res.channel_params) == 3
    assert res.radius_curve is not None and len(res.radius_curve) > 0
    assert res.quadrants is not None
    assert set(res.quadrants) == {"TR", "TL", "BR", "BL"}


def test_sidecar_failure_keeps_context():
    cal = _FakeCal()
    res = CalibrationResult.from_calibration(cal, None, ok=False,
                                             error="Kalibrierkarte nicht erkannt")
    assert res.ok is False
    assert res.error == "Kalibrierkarte nicht erkannt"
    assert res.mean_um is None
    assert res.acc is None
    assert res.device == "/dev/video0"


def test_sidecar_serializes_json():
    cal = _FakeCal()
    res = CalibrationResult.from_calibration(cal, None, ok=True)
    js = res.to_json()
    import json
    data = json.loads(js)
    assert data["ok"] is True
    assert data["mean_um"] == 40.0
    assert "quadrants" in data


def test_failed_calibration_writes_nothing():
    save_env = os.environ.get("XDG_CONFIG_HOME")
    with tempfile.TemporaryDirectory() as td:
        os.environ["XDG_CONFIG_HOME"] = td
        try:
            cal = VMSCalibrate(320, 240, pattern=(4, 4), raster=4.899)
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            assert cal.calibrate(frame) is False
            # Kalibrierung wird nur als volles Set (mit Hintergrund) persistiert;
            # ein fehlgeschlagener Versuch schreibt keine last_calibration-Dateien.
            cfg = os.path.join(td, "benchrestscore")
            all_files = []
            if os.path.isdir(cfg):
                for name in os.listdir(cfg):
                    all_files.append(name)
            assert "last_calibration.png" not in all_files
            assert "last_calibration.json" not in all_files
        finally:
            if save_env is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = save_env


def _lut_from_uv(u, v):
    """4-Kanal-LUT aus Ziel-Texturkoordinaten (Shader-Dekodierung).

    u, v   (h, w) float32 in [0, 1] — die Zielkoordinate, die `undistort_frame`
           (wie der Shader) aus der LUT rekonstruieren soll.
    Kodierung kompensiert den Dekodier-Faktor `t/65280` (Shader:
    `r + g/256` mit uint8 -> /255) und clippt auf den 16-Bit-Bereich der
    echten LUT-Erzeugung (`compute_lut_channels`: `clip(ndc*65536, 0, 65535)`).
    """
    u16 = np.clip(np.round(u * 65280), 0, 65535).astype(np.int64)
    v16 = np.clip(np.round(v * 65280), 0, 65535).astype(np.int64)
    wh = (u16 // 256).astype(np.uint8)
    wl = (u16 % 256).astype(np.uint8)
    hh = (v16 // 256).astype(np.uint8)
    hl = (v16 % 256).astype(np.uint8)
    return np.dstack([wh, wl, hh, hl])


def _identity_luts(h, w):
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    lut = _lut_from_uv(xx.astype(np.float32) / w,
                       yy.astype(np.float32) / h)
    return [lut, lut, lut]


def test_downscale_luts_identity_at_same_res():
    # Downscale auf die gleiche Auflösung ist (bis auf Rundung) ein No-op.
    h, w = 60, 80
    luts = _identity_luts(h, w)
    out = downscale_luts(luts, h, w)
    assert out is not None and len(out) == 3
    for a, b in zip(luts, out):
        assert b.shape == (h, w, 4)
        assert b.dtype == np.uint8
        assert np.allclose(a, b, atol=1)


def test_downscale_luts_half_keeps_coordinate_field():
    # Halbierung: die Ziel-Koordinate an (y, x) muss der ursprünglichen an
    # (2y, 2x) entsprechen (INTER_AREA einer glatten Koordinatenrampe).
    h, w = 60, 80
    luts = _identity_luts(h, w)
    out = downscale_luts(luts, h // 2, w // 2)
    assert out is not None
    lut = out[0]
    assert lut.shape == (h // 2, w // 2, 4)
    # Dekodierung identisch zu undistort_frame
    u = lut[..., 0] / 255.0 + lut[..., 1] / (255.0 * 256.0)
    v = lut[..., 2] / 255.0 + lut[..., 3] / (255.0 * 256.0)
    y, x = 20, 30
    # Original an (2y, 2x): u = x/w, v = y/h
    assert abs(u[y, x] - (2 * x) / float(w)) < 0.02
    assert abs(v[y, x] - (2 * y) / float(h)) < 0.02


def test_downscale_luts_invalid_inputs_none():
    assert downscale_luts(None, 10, 10) is None
    assert downscale_luts([], 10, 10) is None
    assert downscale_luts([None, None, None], 10, 10) is None
    assert downscale_luts([np.zeros((4, 4, 3), dtype=np.uint8)] * 3,
                          10, 10) is None


def test_undistort_identity_luts_approx_identity():
    h, w = 240, 320
    cal = VMSCalibrate(w, h)
    luts = [cal.default_lut_channels()] * 3
    frame = np.dstack([
        np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1)),
        np.tile(np.linspace(0, 255, h, dtype=np.uint8)[:, None], (1, w)),
        np.full((h, w), 128, dtype=np.uint8),
    ])
    out = undistort_frame(frame, luts)
    # Identitäts-LUT: Geometrie unverändert (Bilinear-Toleranz)
    assert out.shape == frame.shape and out.dtype == frame.dtype
    assert np.allclose(out, frame, atol=3)


def test_undistort_invalid_luts_passthrough():
    h, w = 60, 80
    frame = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    assert undistort_frame(frame, None) is frame
    assert undistort_frame(None, []) is None
    # Länge != 3
    assert np.array_equal(undistort_frame(frame, _identity_luts(h, w)[:2]), frame)
    # falsche Shape
    bad = [np.zeros((h, w, 4), dtype=np.uint8)] * 3
    bad[0] = np.zeros((h + 1, w, 4), dtype=np.uint8)
    assert np.array_equal(undistort_frame(frame, bad), frame)
    # nicht-4-Kanal
    not4 = [np.zeros((h, w, 3), dtype=np.uint8)] * 3
    assert np.array_equal(undistort_frame(frame, not4), frame)


def test_undistort_shift_maps_frame():
    h, w = 60, 80
    frame = np.dstack([
        np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1)),
        np.tile(np.linspace(0, 255, h, dtype=np.uint8)[:, None], (1, w)),
        np.full((h, w), 128, dtype=np.uint8),
    ])
    dx = 3
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    lut = _lut_from_uv((xx + dx).astype(np.float32) / w,
                       yy.astype(np.float32) / h)
    out = undistort_frame(frame, [lut, lut, lut])
    # um +dx nach links verschieben; rechter Rand repliziert (BORDER_REPLICATE)
    exp = np.empty_like(frame)
    for c in range(3):
        s = np.zeros((h, w), dtype=np.uint8)
        s[:, :w - dx] = frame[:, dx:, c]
        s[:, w - dx:] = frame[:, -1, c][:, None]
        exp[..., c] = s
    assert np.array_equal(out, exp)


def test_undistort_channel_separation():
    h, w = 60, 80
    frame = np.dstack([
        np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1)),
        np.tile(np.linspace(0, 255, h, dtype=np.uint8)[:, None], (1, w)),
        np.full((h, w), 128, dtype=np.uint8),
    ])
    dx = 3
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    shift = _lut_from_uv((xx + dx).astype(np.float32) / w,
                         yy.astype(np.float32) / h)
    ident = _identity_luts(h, w)[0]
    # nur Kanal 0 (Blau) wird verschoben; Grün/Rot unverändert
    out = undistort_frame(frame, [shift, ident, ident])
    assert np.array_equal(out[..., 1], frame[..., 1])
    assert np.array_equal(out[..., 2], frame[..., 2])
    shifted = np.zeros((h, w), dtype=np.uint8)
    shifted[:, :w - dx] = frame[:, dx:, 0]
    shifted[:, w - dx:] = frame[:, -1, 0][:, None]
    assert np.array_equal(out[..., 0], shifted)


def test_calibration_error_keys_translate():
    save = current_language()
    try:
        set_language("de")
        assert "Kalibrierkarte" in tr("calibration.card_not_found", count=5)
        assert "Kanal R" in tr("calibration.channel_not_found", channel="R", count=5)
        set_language("en")
        assert "Calibration card" in tr("calibration.card_not_found", count=5)
        assert "Channel R" in tr("calibration.channel_not_found", channel="R", count=5)
    finally:
        set_language(save)


if __name__ == "__main__":
    for fn in (test_good_at_zero, test_good_at_threshold, test_ok_above_good,
               test_poor_above_ok, test_bad_above_poor, test_negative_clamps_to_good_band,
               test_error_vs_radius_increases_outward,
               test_error_vs_radius_units_micrometers,
               test_quadrant_breakdown_separates_corners,
               test_quadrant_breakdown_symmetric,
               test_sidecar_success_populates_fields,
               test_sidecar_failure_keeps_context,
               test_sidecar_serializes_json,
               test_failed_calibration_writes_nothing,
               test_undistort_identity_luts_approx_identity,
               test_undistort_invalid_luts_passthrough,
               test_undistort_shift_maps_frame,
               test_undistort_channel_separation,
               test_calibration_error_keys_translate):
        fn()
        print(f"PASS {fn.__name__}")
    print("All calibration tests passed")