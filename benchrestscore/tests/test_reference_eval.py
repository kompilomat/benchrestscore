# -*- coding: utf-8 -*-
"""Headless unit tests for the reference snapshot module (no window/GL)."""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import cv2
import numpy as np

from benchrestscore.reference_eval import (
    ReferenceData,
    BACKGROUND_JSON,
    BACKGROUND_PNG,
    CALIBRATION_JSON,
    CALIBRATION_PNG,
    CALIBRATION_OVERLAY_PNG,
    EVALUATION_PNG,
    RAW_PNG,
    METRICS_JSON,
    dataset_root,
    list_reference_samples,
    next_sample_dir,
    load_reference,
    load_reference_sample,
    save_sample,
    evaluate_automation,
    evaluate_automation_dataset,
)
from benchrestscore.calibration_monitor import BackgroundModel


W, H = 400, 400
S = 200.0


def _cal_matrices():
    mat = np.diag([1.0 / S, 1.0 / S, 1.0])   # Metrik -> NDC
    mati = np.diag([S, S, 1.0])              # NDC -> Metrik
    return mat, mati


def _table(seed=7, size=(W, H)):
    rng = np.random.default_rng(seed)
    img = np.full((size[1], size[0], 3), 0, dtype=np.uint8)
    for _ in range(800):
        x0 = int(rng.integers(0, size[0] - 10))
        y0 = int(rng.integers(0, size[1] - 10))
        w = int(rng.integers(4, 10))
        h = int(rng.integers(4, 10))
        img[y0:y0 + h, x0:x0 + w] = int(rng.integers(0, 100))
    return img


def _learned_model(table):
    model = BackgroundModel()
    assert model.learn(cv2.cvtColor(table, cv2.COLOR_BGR2GRAY),
                       reference=table) is True
    return model


class _Cal:
    calibrated = True
    mean = 40.0
    sd = 8.0
    A_correction = ""
    B_correction = ""

    def __init__(self, table):
        mat, mati = _cal_matrices()
        self.frame = table
        self.visual = table.copy()
        self.mat = mat
        self.mati = mati
        self.channel_params = np.zeros((3, 16))


def _metrics(table, points_mm, radius=16.0, name="6.5 mm"):
    mat, mati = _cal_matrices()
    return {
        "schema": 1,
        "width": table.shape[1],
        "height": table.shape[0],
        "caliber_name": name,
        "caliber_radius_mm": radius,
        "points": [{"x": float(x), "y": float(y)} for x, y in points_mm],
        "mat": mat.tolist(),
        "mati": mati.tolist(),
        "timestamp": "t",
    }


def test_save_sample_writes_complete_dataset(tmp_path):
    table = _table()
    frame = _table(seed=8)
    raw = _table(seed=9)
    model = _learned_model(table)
    cal = _Cal(table)
    sample = next_sample_dir(str(tmp_path))
    metrics = _metrics(table, [(0.0, 0.0)])
    assert save_sample(sample, cal, model, frame, metrics,
                       cal_frame=table, cal_visual=table, frame_raw=raw) is True
    for name in (CALIBRATION_JSON, CALIBRATION_PNG, CALIBRATION_OVERLAY_PNG,
                 BACKGROUND_JSON, BACKGROUND_PNG, EVALUATION_PNG, RAW_PNG,
                 METRICS_JSON):
        assert os.path.exists(os.path.join(sample, name)), name


def test_next_sample_numbering_ascending(tmp_path):
    os.makedirs(os.path.join(str(tmp_path), "sample_01"))
    os.makedirs(os.path.join(str(tmp_path), "sample_03"))
    assert os.path.basename(next_sample_dir(str(tmp_path))) == "sample_04"
    # sample_02 fehlt -> trotzdem sample_04 (höchste Nummer + 1)
    assert os.path.basename(list_reference_samples(str(tmp_path))[0]) == "sample_01"


def test_list_reference_samples_sorted(tmp_path):
    os.makedirs(os.path.join(str(tmp_path), "sample_02"))
    os.makedirs(os.path.join(str(tmp_path), "sample_01"))
    os.makedirs(os.path.join(str(tmp_path), "not_a_sample"))
    assert [os.path.basename(p) for p in list_reference_samples(str(tmp_path))] \
        == ["sample_01", "sample_02"]
    assert list_reference_samples(str(tmp_path / "leer")) == []


def test_load_reference_sample_roundtrip(tmp_path):
    table = _table()
    model = _learned_model(table)
    cal = _Cal(table)
    frame = _table(seed=10)
    points_mm = [(0.0, 0.0), (10.0, -5.0)]
    sample = next_sample_dir(str(tmp_path))
    assert save_sample(sample, cal, model, frame, _metrics(table, points_mm),
                       cal_frame=table, cal_visual=table) is True
    data, loaded_frame, loaded_model = load_reference_sample(sample)
    assert data is not None
    assert data.width == W and data.height == H
    assert data.caliber_radius_mm == 16.0
    assert data.points.shape == (2, 2)
    assert np.allclose(data.points, points_mm)
    assert np.allclose(data.mati, np.diag([S, S, 1.0]))
    assert loaded_frame is not None
    assert loaded_model.learned is True
    assert loaded_model.has_reference is True


def test_load_reference_sample_missing_metrics(tmp_path):
    data, frame, model = load_reference_sample(str(tmp_path))
    assert data is None and frame is None and model is None


def test_load_reference_invalid(tmp_path):
    p = tmp_path / "metrics.json"
    p.write_text("kaputt", encoding="utf-8")
    assert load_reference(str(p)) is None
    assert load_reference(str(tmp_path / "fehlt.json")) is None


def test_evaluate_automation_against_manual(tmp_path):
    # Dunkler Tisch, helles Papier, hartes dunkles Loch: die Klick-Automation
    # findet es mit sub-mm-Genauigkeit (1 mm == 1 px @ S=200, 400x400).
    table = _table()
    frame = np.full_like(table, 255, dtype=np.uint8)
    hole_px = (200, 200)
    cv2.circle(frame, hole_px, 20, (0, 0, 0), -1)
    # manueller Punkt in Weltmetrik am Lochzentrum (200,200 px == (0,0) mm)
    points_mm = [(0.0, 0.0)]
    model = _learned_model(table)
    cal = _Cal(table)
    sample = next_sample_dir(str(tmp_path))
    assert save_sample(sample, cal, model, frame, _metrics(table, points_mm,
                                                           radius=20.0),
                       cal_frame=table, cal_visual=table) is True
    res = evaluate_automation(sample, click_jitter_px=3.0, seed=1)
    assert res is not None
    assert res["n_manual"] == 1
    assert res["errors_mm"][0] is not None
    assert res["errors_mm"][0] < 3.0, res["errors_mm"][0]


def test_evaluate_automation_reports_no_latch_structure(tmp_path):
    # Ein einzelnes Loch: latched=[False], n_latched=0, Struktur vollständig.
    table = _table()
    frame = np.full_like(table, 255, dtype=np.uint8)
    cv2.circle(frame, (200, 200), 20, (0, 0, 0), -1)
    points_mm = [(0.0, 0.0)]
    model = _learned_model(table)
    cal = _Cal(table)
    sample = next_sample_dir(str(tmp_path))
    assert save_sample(sample, cal, model, frame, _metrics(table, points_mm,
                                                           radius=20.0),
                       cal_frame=table, cal_visual=table) is True
    res = evaluate_automation(sample, click_jitter_px=3.0, seed=1)
    assert res is not None
    assert res["latched"] == [False]
    assert res["n_latched"] == 0
    assert len(res["latched"]) == len(res["errors_mm"])


def test_evaluate_automation_dataset_empty():
    res = evaluate_automation_dataset([])
    assert res["total_points"] == 0
    assert res["total_found"] == 0
    assert res["total_latched"] == 0
    assert res["samples"] == []
    assert res["mean_error_mm"] is None
    assert res["max_error_mm"] is None


def test_evaluate_automation_dataset_skips_unloadable(tmp_path):
    res = evaluate_automation_dataset([str(tmp_path / "fehlt")])
    assert res["total_points"] == 0
    assert res["total_found"] == 0


def test_evaluate_automation_dataset_aggregates(tmp_path):
    table = _table()
    frame = np.full_like(table, 255, dtype=np.uint8)
    cv2.circle(frame, (200, 200), 20, (0, 0, 0), -1)
    points_mm = [(0.0, 0.0)]
    model = _learned_model(table)
    cal = _Cal(table)
    sample = next_sample_dir(str(tmp_path))
    assert save_sample(sample, cal, model, frame, _metrics(table, points_mm,
                                                           radius=20.0),
                       cal_frame=table, cal_visual=table) is True
    res = evaluate_automation_dataset([sample, str(tmp_path / "fehlt")],
                                      click_jitter_px=3.0, seed=1)
    assert res["total_points"] == 1
    assert res["total_found"] == 1
    assert res["total_latched"] == 0
    assert len(res["samples"]) == 1
    entry = res["samples"][0]
    assert entry["name"].startswith("sample_")
    assert entry["n_manual"] == 1
    assert entry["n_found"] == 1
    assert entry["n_latched"] == 0
    assert entry["errors_mm"][0] is not None
    assert entry["mean_error_mm"] is not None


def test_dataset_root_env_override(monkeypatch):
    monkeypatch.setenv("BRS_REFERENCE_DATASET", "/tmp/xyz")
    assert dataset_root() == "/tmp/xyz"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            traceback.print_exc()
            raise