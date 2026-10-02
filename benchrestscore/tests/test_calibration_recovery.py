# -*- coding: utf-8 -*-
"""Headless unit tests for calibration recovery persistence (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import tempfile

import numpy as np

from benchrestscore import calibration_recovery as cr
from benchrestscore.calibration_monitor import BackgroundModel, MonitorStatus


W, H = 320, 240


def synthetic_table(seed=7):
    rng = np.random.default_rng(seed)
    img = np.full((H, W), 128, dtype=np.uint8)
    for _ in range(300):
        x0 = int(rng.integers(0, W - 20))
        y0 = int(rng.integers(0, H - 20))
        x1 = int(rng.integers(x0 + 5, min(x0 + 30, W)))
        y1 = int(rng.integers(y0 + 5, min(y0 + 30, H)))
        img[y0:y1, x0:x1] = int(rng.integers(0, 255))
    return img


def _with_config_dir():
    """Kapselt Tests gegen das echte Config-Verzeichnis ab (XDG_CONFIG_HOME)."""
    td = tempfile.mkdtemp(prefix="brs_cfg_")
    old = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = td
    return td, old


def _restore_env(old):
    if old is None:
        os.environ.pop("XDG_CONFIG_HOME", None)
    else:
        os.environ["XDG_CONFIG_HOME"] = old


def test_json_write_read_roundtrip():
    td, old = _with_config_dir()
    try:
        path = os.path.join(td, "benchrestscore", "sub", "x.json")
        assert cr.write_json(path, {"a": 1, "b": [1, 2]}) is True
        assert cr.read_json(path) == {"a": 1, "b": [1, 2]}
    finally:
        _restore_env(old)


def test_read_json_missing_or_bad_returns_none():
    td, old = _with_config_dir()
    try:
        assert cr.read_json(os.path.join(td, "does", "not", "exist.json")) is None
        bad = os.path.join(td, "bad.json")
        os.makedirs(os.path.dirname(bad), exist_ok=True)
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{not json")
        assert cr.read_json(bad) is None
    finally:
        _restore_env(old)


class FakeCal:
    def __init__(self):
        self.mati = np.diag([20.0, 20.0, 1.0])
        self.mat = np.diag([1.0 / 20, 1.0 / 20, 1.0])


def test_background_model_roundtrip_check_matches():
    import cv2
    img = synthetic_table()
    model = BackgroundModel()
    assert model.learn(img) is True
    data = model.to_dict()
    # Persistenz ergänzt Breite/Höhe
    data["width"] = W
    data["height"] = H
    data["keypoint_count"] = model.keypoint_count

    restored = BackgroundModel.restore(data)
    assert restored.learned is True
    assert restored.keypoint_count == model.keypoint_count
    assert restored.shape == (H, W)

    img_shift = cv2.warpAffine(img, np.float32([[1, 0, 4], [0, 1, 0]]), (W, H),
                               borderValue=128)
    m1 = model.check(img, FakeCal()).status
    m2 = restored.check(img, FakeCal()).status
    s1 = model.check(img_shift, FakeCal()).status
    s2 = restored.check(img_shift, FakeCal()).status
    assert m1 == m2 == MonitorStatus.OK
    assert s1 in (MonitorStatus.OK, MonitorStatus.SHIFTED)
    assert s2 == s1


def test_restore_rejects_sparse_data():
    assert BackgroundModel.restore(
        {"keypoints": [], "descriptors": []}).learned is False
    assert BackgroundModel.restore(
        {"keypoints": [{"x": 1, "y": 1}], "descriptors": [[0] * 32]}).learned is False


class _FakeCalForSession:
    """Minimaler Kalibrier-Typ für `save_full_session` (Sidecar-fähig)."""

    calibrated = True
    mean = 40.0
    sd = 8.0
    A_correction = "1.0L"
    B_correction = "0.0R"

    def __init__(self, frame):
        self.frame = frame          # BGR-Roh-Frame
        self.visual = frame.copy()  # Overlay (hier vereinfacht gleich)
        s = 20.0
        self.mat = np.diag([1.0 / s, 1.0 / s, 1.0])
        self.mati = np.diag([s, s, 1.0])
        self.channel_params = np.zeros((3, 16))


def test_save_full_session_writes_everything():
    import cv2
    import json
    img = synthetic_table()
    model = BackgroundModel()
    assert model.learn(img) is True
    td, old = _with_config_dir()
    try:
        cr.save_full_session(_FakeCalForSession(img), model, img, img)
        # Kalibrierung + Hintergrund + Marker (7 Dateien)
        expects = [
            cr.calibration_png_path(), cr.calibration_overlay_path(),
            cr.calibration_json_path(), cr.background_png_path(),
            cr.background_overlay_path(), cr.background_json_path(),
            cr.session_marker_path(),
        ]
        for p in expects:
            assert os.path.exists(p), f"missing {os.path.basename(p)}"
        sidecar = json.load(open(cr.calibration_json_path(), encoding="utf-8"))
        assert sidecar["ok"] is True
        assert sidecar["has_background"] is True
        assert sidecar["width"] == W and sidecar["height"] == H
        bg = json.load(open(cr.background_json_path(), encoding="utf-8"))
        assert len(bg["keypoints"]) == model.keypoint_count
        assert len(bg["descriptors"]) == model.keypoint_count
        assert bg["width"] == W and bg["height"] == H
        marker = cr.read_json(cr.session_marker_path())
        assert marker is not None
        assert marker["width"] == W and marker["height"] == H
    finally:
        _restore_env(old)


def test_load_background_restores_model():
    img = synthetic_table()
    model = BackgroundModel()
    assert model.learn(img) is True
    td, old = _with_config_dir()
    try:
        cr.save_full_session(_FakeCalForSession(img), model, img, img)
        loaded = cr.load_background(cr.background_json_path())
        assert loaded.learned is True
        assert loaded.keypoint_count == model.keypoint_count
        assert loaded.shape == (H, W)
        # kein gültiges JSON -> ungelernt
        load_missing = cr.load_background(os.path.join(td, "none.json"))
        assert load_missing.learned is False
    finally:
        _restore_env(old)


def test_load_background_attaches_reference_png():
    import cv2
    img = synthetic_table()
    model = BackgroundModel()
    assert model.learn(img) is True
    td, old = _with_config_dir()
    try:
        cr.save_full_session(_FakeCalForSession(img), model, img, img)
        loaded = cr.load_background(cr.background_json_path())
        assert loaded.learned is True
        assert loaded.has_reference is True
        rh, rw = loaded.reference.shape[:2]
        assert rh == H // 4 and rw == W // 4
        # fehlendes PNG -> weiterhin gelernt, aber ohne Referenz
        os.unlink(cr.background_png_path())
        loaded2 = cr.load_background(cr.background_json_path())
        assert loaded2.learned is True
        assert loaded2.has_reference is False
    finally:
        _restore_env(old)


def test_session_marker_lifecycle():
    td, old = _with_config_dir()
    try:
        assert not cr.has_valid_session()
        assert cr.write_session_marker(W, H, 100, "2026-09-04T00:00:00Z") is True
        # ohne valides Kalibrier-Sidecar -> keine gültige Session
        assert not cr.has_valid_session()
        assert cr.remove_session_marker() is True
        assert not cr.has_valid_session()
    finally:
        _restore_env(old)


def test_has_valid_session_full():
    img = synthetic_table()
    model = BackgroundModel()
    assert model.learn(img) is True
    td, old = _with_config_dir()
    try:
        cr.save_full_session(_FakeCalForSession(img), model, img, img)
        assert cr.has_valid_session()
        # Marker entfernen -> keine gültige Session mehr
        cr.remove_session_marker()
        assert not cr.has_valid_session()
    finally:
        _restore_env(old)


if __name__ == "__main__":
    for fn in (test_json_write_read_roundtrip,
               test_read_json_missing_or_bad_returns_none,
               test_background_model_roundtrip_check_matches,
               test_restore_rejects_sparse_data,
test_save_full_session_writes_everything,
                test_load_background_restores_model,
                test_load_background_attaches_reference_png,
                test_session_marker_lifecycle,
               test_has_valid_session_full):
        fn()
        print(f"PASS {fn.__name__}")
    print("All recovery tests passed")