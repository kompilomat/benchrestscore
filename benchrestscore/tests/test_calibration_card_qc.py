# -*- coding: utf-8 -*-
"""Headless unit tests for the calibration card quality check (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json

import cv2
import numpy as np

from benchrestscore.calibration_card_qc import (
    QC_SAMPLE_FRAMES,
    QC_TOLERANCE_MM,
    QC_WARN_MM,
    build_payload,
    check_card,
    detect_grid_metric,
    homography_align,
    render_overlay,
    rigid_align,
    save_result,
)
from benchrestscore.calibration import VMSCalibrate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE_PATH = os.path.join(REPO_ROOT, "benchrestscore", "data",
                            "calibration_card.png")


def _load_fixture():
    frame = cv2.imread(FIXTURE_PATH)
    assert frame is not None, f"Fixture fehlt: {FIXTURE_PATH}"
    return frame


def _calibrate():
    frame = _load_fixture()
    cal = VMSCalibrate(frame.shape[1], frame.shape[0])
    assert cal.calibrate(frame) is True, cal.error
    return cal, frame


def _apply_h(points, h):
    flat = np.hstack([points.reshape(-1, 2), np.ones((points.shape[0], 1))])
    out = flat @ h.T
    return (out[:, :2] / out[:, 2:3]).reshape(points.shape)


def _rigid_h(angle_deg, tx, ty):
    a = np.deg2rad(angle_deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, tx], [s, c, ty], [0.0, 0.0, 1.0]])


def _spread_grid(key):
    """Nicht-degeneriertes Punktraster (mm) als (n, 2)."""
    return np.array([[x, y]
                     for x in np.linspace(0.0, 150.0, 8)
                     for y in np.linspace(0.0, 80.0, 6)]) + np.float64(key)


# --- rigid_align (Rotation + Translation, constrained) ---


def test_rigid_align_removes_translation_and_rotation():
    base = _spread_grid(0.0)
    moved = _apply_h(base, _rigid_h(2.5, -6.0, 9.0))
    aligned = rigid_align(moved, base)
    assert np.abs(aligned - base).max() < 1e-6


def test_rigid_align_keeps_scale_error():
    base = _spread_grid(0.0)
    scaled = base * 1.0005  # globale Skalierung (Karte-) — bleibt im Fehlermaß
    aligned = rigid_align(scaled, base)
    d = np.abs(aligned - base).max()
    # Skalierung ist keine starre Transformation → sichtbar
    assert d > QC_TOLERANCE_MM * 0.5


def test_rigid_align_keeps_local_deviation():
    base = _spread_grid(0.0)
    moved = _apply_h(base, _rigid_h(1.0, 3.0, 4.0)).copy()
    moved[17, 0] += 0.03
    aligned = rigid_align(moved, base)
    d = np.linalg.norm(aligned - base, axis=1)
    assert d[17] > 0.02
    assert np.median(d) < 0.002


# --- check_card ---


def test_check_card_identical_in_spec():
    base = np.linspace(0.0, 1.0, 200).reshape(10, 10, 2)
    res = check_card(base, base.copy())
    assert res is not None
    assert res["pass"] is True
    assert res["max_um"] < 1e-3
    assert res["over_count"] == 0


def test_check_card_replaced_in_spec():
    base = np.stack(np.meshgrid(np.linspace(0, 150, 6),
                                np.linspace(0, 80, 4)), axis=-1)
    shifted = _apply_h(base.reshape(-1, 2), _rigid_h(1.2, 2.0, -3.0))
    res = check_card(base, shifted.reshape(base.shape), QC_TOLERANCE_MM)
    assert res["pass"] is True


def test_check_card_out_of_spec():
    base = _spread_grid(0.0).reshape(8, 6, 2)
    bad = base.copy()
    bad[1, 1] = [base[1, 1, 0] + 0.10, base[1, 1, 1]]  # > 75 µm -> out of spec
    res = check_card(base, bad, QC_TOLERANCE_MM)
    assert res["pass"] is False
    assert res["over_count"] >= 1


def test_check_card_orange_is_still_in_spec():
    # Abweichung zwischen 50 und 75 µm -> orange, aber noch in Spec
    base = _spread_grid(0.0).reshape(8, 6, 2)
    warn = base.copy()
    warn[1, 1] = [base[1, 1, 0] + 0.060, base[1, 1, 1]]  # 60 µm
    res = check_card(base, warn, QC_TOLERANCE_MM)
    assert res["pass"] is True
    assert res["over_count"] == 0
    assert res["max_um"] > QC_WARN_MM * 1000.0


def test_check_card_shape_mismatch_none():
    assert check_card(np.zeros((4, 4, 2)), np.zeros((5, 5, 2))) is None
    assert check_card(np.zeros((4, 4, 2)), np.zeros((4, 4, 3))) is None


# --- homography_align ---


def test_homography_align_removes_affine():
    base = _spread_grid(0.0)
    # Affine (Rotation + Translation + Skalierung) — die Homographie entfernt sie
    a = np.deg2rad(1.5)
    c, s = np.cos(a), np.sin(a)
    H = np.array([[c * 1.001, -s, 4.0],
                  [s, c * 0.999, -2.0],
                  [0.0, 0.0, 1.0]])
    moved = _apply_h(base, H)
    aligned = homography_align(moved, base)
    assert np.abs(aligned - base).max() < 1e-4


def test_homography_align_removes_perspective():
    base = _spread_grid(0.0)
    H = np.array([[1.0, 0.0, 3.0],
                  [0.0, 1.0, 1.0],
                  [0.0005, 0.0, 1.0]])
    moved = _apply_h(base, H)
    aligned = homography_align(moved, base)
    assert np.abs(aligned - base).max() < 1e-3


def test_homography_align_keeps_local_deviation():
    base = _spread_grid(0.0)
    H = _rigid_h(0.5, 2.0, 1.0)
    moved = _apply_h(base, H).copy()
    moved[17, 0] += 0.03
    aligned = homography_align(moved, base)
    d = np.linalg.norm(aligned - base, axis=1)
    assert d[17] > 0.02
    assert np.median(d) < 0.002


def test_check_card_removes_scale():
    # Skalierung (z.B. minimal anderer Abstand) wird durch die Homographie
    # herausgerechnet -> identische Karte bleibt in Spec
    base = _spread_grid(0.0).reshape(8, 6, 2)
    scaled = base * 1.0005
    res = check_card(base, scaled, QC_TOLERANCE_MM)
    assert res["pass"] is True


# --- Mehr-Frame-Mittelung ---


def test_detect_grid_metric_accepts_multiple_frames():
    cal, frame = _calibrate()
    frames = [frame, frame.copy(), frame.copy()]
    result = detect_grid_metric(frames, cal)
    assert result.metric_grid is not None
    single = detect_grid_metric(frame, cal)
    assert np.allclose(result.metric_grid, single.metric_grid, atol=1e-9)


# --- Einzelbild-Detektion (Fixture) ---


def test_detect_grid_metric_on_fixture_matches_reference():
    cal, frame = _calibrate()
    reference = np.asarray(cal.metric_grid)
    result = detect_grid_metric(frame, cal)
    assert result.metric_grid is not None
    assert result.metric_grid.shape == reference.shape
    res = check_card(reference, result.metric_grid, QC_TOLERANCE_MM)
    assert res["pass"] is True


def test_detect_grid_metric_failure_reports_circle_count():
    cal, _ = _calibrate()
    blank = np.full((720, 1280, 3), 200, dtype=np.uint8)
    result = detect_grid_metric(blank, cal)
    assert result.metric_grid is None
    assert isinstance(result.circle_count, int)


def test_detect_grid_metric_pixel_grid_in_display_space():
    cal, frame = _calibrate()
    result = detect_grid_metric(frame, cal)
    pix = np.asarray(result.pixel_grid)
    assert pix.shape == result.metric_grid.shape
    assert np.all(np.isfinite(pix))


# --- overlay / payload / persistence ---


def test_render_overlay_annotates():
    cal, frame = _calibrate()
    reference = np.asarray(cal.metric_grid)
    result = detect_grid_metric(frame, cal)
    res = check_card(reference, result.metric_grid, QC_TOLERANCE_MM)
    out = render_overlay(frame, result.pixel_grid, res["deviations_um"],
                         res["pass"])
    assert out.shape == frame.shape
    assert out.dtype == frame.dtype


def test_save_result_writes_json_and_png():
    import tempfile
    save_env = os.environ.get("XDG_CONFIG_HOME")
    with tempfile.TemporaryDirectory() as tmp_path:
        os.environ["XDG_CONFIG_HOME"] = tmp_path
        try:
            cal, frame = _calibrate()
            reference = np.asarray(cal.metric_grid)
            result = detect_grid_metric(frame, cal)
            res = check_card(reference, result.metric_grid, QC_TOLERANCE_MM)
            payload = build_payload(reference, result.metric_grid, res)
            overlay = render_overlay(frame, result.pixel_grid,
                                     res["deviations_um"], res["pass"])
            assert save_result(payload, overlay) is True
            cfg = os.path.join(tmp_path, "benchrestscore")
            assert os.path.exists(os.path.join(cfg, "last_card_check.json"))
            assert os.path.exists(
                os.path.join(cfg, "last_card_check_overlay.png"))
            with open(os.path.join(cfg, "last_card_check.json"),
                      encoding="utf-8") as f:
                data = json.load(f)
            assert data["pass"] is True
            assert data["tolerance_mm"] == QC_TOLERANCE_MM
            assert len(data["measured_grid"]) == result.metric_grid.shape[0]
        finally:
            if save_env is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = save_env