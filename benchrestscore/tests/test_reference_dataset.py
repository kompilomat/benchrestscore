# -*- coding: utf-8 -*-
"""Reale Referenz-Samples (`datasets/sample_*`) als Regressionstests.

Prüft die Klick-Automation (`evaluate_automation`) headless gegen die
manuelle Bewertung der realen Samples. Nutzt `BRS_REFERENCE_DATASET` bzw.
Repo-`datasets/`; ohne vorhandene Samples werden die Tests übersprungen.

Zwei Ebenen:
- **No-Regression-Guard** (grün): sichert das Niveau (alle Punkte gefunden,
  Max-Fehler < 3,0 mm) — eine Regression in der Automation färbt hier rot.
- **Ziel-Tests** (grün): Sub-mm pro Punkt (max < 1,0 mm), latch-frei
  (`n_latched == 0`) und robust gegen Klick-Versatz bis 10 px (max < 1,0 mm)
  sowie bis 25 px (max < 2,0 mm; 25 px ≈ 1 mm Versatz, physische Grenze).
  Keine xfail-Marker auf den Regressions-fähigen Zielen — Verschlechterungen
  werden sichtbar rot.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from benchrestscore.reference_eval import (
    evaluate_automation,
    evaluate_automation_dataset,
    list_reference_samples,
)

SAMPLES = list_reference_samples()
SAMPLE_NAMES = [os.path.basename(s) for s in SAMPLES]

NEEDS_SAMPLES = pytest.mark.skipif(
    not SAMPLES,
    reason="keine Referenz-Samples unter datasets/ bzw. BRS_REFERENCE_DATASET")

# Akzeptanz-Grenzen (siehe openspec: app/automation, app/reference-eval)
MAX_ERROR_MM_GUARD = 3.0
MAX_ERROR_MM_TARGET = 1.0
MEAN_ERROR_MM_TARGET = 1.0
MAX_ERROR_MM_JITTER25 = 2.0


def _result(sample_dir, jitter_px, seed=0):
    return evaluate_automation(sample_dir, click_jitter_px=jitter_px, seed=seed)


def _not_found(res):
    return [i for i, e in enumerate(res["errors_mm"]) if e is None]


# --- No-Regression-Guard: heutiges Niveau, exakter Klick -------------------

@NEEDS_SAMPLES
@pytest.mark.parametrize("sample", SAMPLES, ids=SAMPLE_NAMES)
def test_guard_all_points_found_exact_click(sample):
    res = _result(sample, 0)
    assert res is not None
    not_found = _not_found(res)
    assert not not_found, f"{os.path.basename(sample)}: nicht gefunden: {not_found}"


@NEEDS_SAMPLES
@pytest.mark.parametrize("sample", SAMPLES, ids=SAMPLE_NAMES)
def test_guard_max_error_under_3mm_exact_click(sample):
    res = _result(sample, 0)
    assert res is not None
    assert res["max_error_mm"] < MAX_ERROR_MM_GUARD, \
        f"{os.path.basename(sample)}: max_error_mm={res['max_error_mm']:.2f}"


# --- Ziel-Tests: Sub-mm, latch-frei, robust gegen Klick-Versatz ------------
# Latch-Fälle (sample_02 pt2, 05 pt4, 06 pt1, 10 pt3) sind behoben (0 Latches);
# der Fix nutzt enge Fit-Bounds um den Klick. Nur jitter=25 bleibt offen
# (physikalisch): 25 px Versatz ≈ 1 mm, schwache Lochränder nicht weiter
# korrigierbar -> Grenze 2,0 mm statt 1,0 mm.

@NEEDS_SAMPLES
def test_target_submm_all_samples():
    agg = evaluate_automation_dataset(SAMPLES, click_jitter_px=0, seed=0)
    assert agg["total_found"] == agg["total_points"], \
        f"nicht alle Punkte gefunden: {agg['total_found']}/{agg['total_points']}"
    for r in agg["samples"]:
        assert r["mean_error_mm"] < MEAN_ERROR_MM_TARGET, \
            f"{r['name']}: mean={r['mean_error_mm']:.2f}"
        assert r["max_error_mm"] < MAX_ERROR_MM_TARGET, \
            f"{r['name']}: max={r['max_error_mm']:.2f}"


@NEEDS_SAMPLES
def test_target_no_latches():
    agg = evaluate_automation_dataset(SAMPLES, click_jitter_px=0, seed=0)
    assert agg["total_latched"] == 0, \
        f"{agg['total_latched']} Latch-Ereignisse"


@NEEDS_SAMPLES
def test_target_jitter_25_robustness():
    # 25 px Versatz ≈ 1 mm (physikalische Grenze bei den realen Kalibern);
    # Spec-Grenze: max < 2,0 mm (statt 1,0 mm bei 0/10 px).
    agg = evaluate_automation_dataset(SAMPLES, click_jitter_px=25, seed=0)
    assert agg["max_error_mm"] < MAX_ERROR_MM_JITTER25, \
        f"jitter=25px: max_error_mm={agg['max_error_mm']:.2f}"


@NEEDS_SAMPLES
@pytest.mark.parametrize("jitter", (0, 10))
def test_target_jitter_robustness(jitter):
    agg = evaluate_automation_dataset(SAMPLES, click_jitter_px=jitter, seed=0)
    assert agg["max_error_mm"] < MAX_ERROR_MM_TARGET, \
        f"jitter={jitter}px: max_error_mm={agg['max_error_mm']:.2f}"


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
