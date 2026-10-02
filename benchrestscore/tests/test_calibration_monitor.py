# -*- coding: utf-8 -*-
"""Headless unit tests for the loss-of-calibration monitor (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import cv2
import numpy as np

from benchrestscore.calibration_monitor import (
    BackgroundModel,
    BackgroundMonitorThread,
    CheckResult,
    MonitorStatus,
    detect_keypoints,
    match_keypoints,
    draw_keypoints,
    otsu_threshold,
    table_mask,
    DEVIATION_THRESHOLD_MM,
    MIN_INLIER_RATIO,
    MIN_MATCHES,
    CHECK_CADENCE_S,
    HYSTERESIS,
    MIN_LEARN_KEYPOINTS,
    MAX_LEARN_KEYPOINTS,
    MAX_CHECK_KEYPOINTS,
    MAX_RANSAC_MATCHES,
    RANSAC_MAX_ITERS,
    REFERENCE_SCALE,
    REFERENCE_ALPHA,
)


class FakeCalibration:
    """Map: 1 NDC-Einheit == `s` mm; 1 px @ 320 Breite == s*2/320 mm."""

    def __init__(self, s=20.0):
        self.s = s
        self.mat = np.diag([1.0 / s, 1.0 / s, 1.0])   # Metrik -> NDC
        self.mati = np.diag([s, s, 1.0])              # NDC -> Metrik


W, H = 320, 240


def synthetic_table(seed=7):
    """Deterministischer, strukturierter 'Tisch' (graue Fläche + Rechtecke)."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W), 128, dtype=np.uint8)
    for _ in range(300):
        x0 = int(rng.integers(0, W - 20))
        y0 = int(rng.integers(0, H - 20))
        x1 = int(rng.integers(x0 + 5, min(x0 + 30, W)))
        y1 = int(rng.integers(y0 + 5, min(y0 + 30, H)))
        img[y0:y1, x0:x1] = int(rng.integers(0, 255))
    return img


def flat_image():
    return np.full((H, W), 128, dtype=np.uint8)


def test_constants_importable():
    assert DEVIATION_THRESHOLD_MM == 0.04
    assert 0.0 < MIN_INLIER_RATIO <= 1.0
    assert MIN_MATCHES >= 1
    assert CHECK_CADENCE_S > 0
    assert HYSTERESIS >= 1
    assert MIN_LEARN_KEYPOINTS >= 1
    assert MIN_LEARN_KEYPOINTS <= MAX_LEARN_KEYPOINTS
    assert MAX_CHECK_KEYPOINTS >= 1
    assert MAX_RANSAC_MATCHES >= MIN_MATCHES
    assert RANSAC_MAX_ITERS >= 1


def test_learn_caps_keypoint_count():
    img = synthetic_table()
    model = BackgroundModel()
    assert model.learn(img) is True
    assert model.keypoint_count <= MAX_LEARN_KEYPOINTS


def test_learn_sets_reference():
    img = cv2.cvtColor(synthetic_table(), cv2.COLOR_GRAY2BGR)
    model = BackgroundModel()
    assert model.learn(img, reference=img) is True
    assert model.has_reference is True
    rh, rw = model.reference.shape[:2]
    assert rh == H // REFERENCE_SCALE and rw == W // REFERENCE_SCALE
    assert model.reference.dtype == np.float32
    assert model.reference.ndim == 3 and model.reference.shape[2] == 3
    assert model.reference_raw is not None
    assert model.reference_shape == (H, W)
    # ohne Referenz -> has_reference False, Keypoint-Logik unverändert
    model2 = BackgroundModel()
    assert model2.learn(img) is True
    assert model2.has_reference is False
    assert model2.keypoint_count > 0


def test_update_reference_ema():
    img = cv2.cvtColor(synthetic_table(), cv2.COLOR_GRAY2BGR)
    model = BackgroundModel()
    assert model.learn(img, reference=img) is True
    rh, rw = model.reference.shape[:2]
    ref0 = model.reference.copy()
    raw0 = model.reference_raw.copy()
    bright = np.clip(img.astype(np.float32) + 20, 0, 255).astype(np.uint8)
    mask = np.ones((rh, rw), dtype=bool)
    model.update_reference(img, bright, mask, alpha=0.5)
    exp_und = cv2.resize(bright, (rw, rh), interpolation=cv2.INTER_AREA)
    expected = 0.5 * ref0 + 0.5 * exp_und.astype(np.float32)
    assert np.allclose(model.reference, expected, atol=1.0)
    exp_raw = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_AREA)
    expected_raw = 0.5 * raw0 + 0.5 * exp_raw.astype(np.float32)
    assert np.allclose(model.reference_raw, expected_raw, atol=1.0)


def test_update_reference_noop_cases():
    img = cv2.cvtColor(synthetic_table(), cv2.COLOR_GRAY2BGR)
    bright = np.clip(img.astype(np.float32) + 20, 0, 255).astype(np.uint8)
    # ohne Referenz -> No-op
    m = BackgroundModel()
    m.update_reference(img, bright, np.ones((H, W), dtype=bool))
    assert m.reference is None
    # leere Maske -> keine Änderung
    model = BackgroundModel()
    assert model.learn(img, reference=img) is True
    ref0 = model.reference.copy()
    model.update_reference(img, bright,
                           np.zeros(model.reference.shape[:2], dtype=bool))
    assert np.array_equal(model.reference, ref0)
    # Masken in Frame-Größe werden auf Referenz-Skala toleriert
    model.update_reference(img, bright, np.ones((H, W), dtype=bool))
    assert not np.array_equal(model.reference, ref0)


def test_relearn_from_reference():
    img = cv2.cvtColor(synthetic_table(), cv2.COLOR_GRAY2BGR)
    model = BackgroundModel()
    assert model.learn(img, reference=img) is True
    model.relearn_from_reference()
    assert model.learned is True
    assert model.keypoint_count > 0
    assert model.check(img, FakeCalibration()).status == MonitorStatus.OK
    # ohne Roh-Referenz (Wiederherstellungs-Fall) -> No-op, bleibt gelernt
    m3 = BackgroundModel()
    assert m3.learn(img) is True
    m3.reference_raw = None
    m3.relearn_from_reference()
    assert m3.learned is True


def test_detect_keypoints_capped_by_nfeatures():
    img = synthetic_table()
    kps, _ = detect_keypoints(img, nfeatures=MAX_CHECK_KEYPOINTS)
    assert len(kps) <= MAX_CHECK_KEYPOINTS
    kps_low, _ = detect_keypoints(img, nfeatures=64)
    assert len(kps_low) <= 64


def test_match_keypoints_capped_by_max_matches():
    img = synthetic_table()
    _, desc = detect_keypoints(img, nfeatures=MAX_LEARN_KEYPOINTS)
    M = np.float32([[1, 0, 5], [0, 1, 0]])
    shifted = cv2.warpAffine(img, M, (W, H), borderValue=128)
    _, desc2 = detect_keypoints(shifted, nfeatures=MAX_CHECK_KEYPOINTS)
    src, dst = match_keypoints(desc, desc2, max_matches=64)
    assert len(src) <= 64
    assert src.shape == dst.shape


def test_detect_keypoints_on_texture():
    img = synthetic_table()
    kps, desc = detect_keypoints(img)
    assert len(kps) >= MIN_LEARN_KEYPOINTS
    assert desc is not None
    assert desc.shape[0] == len(kps)


def test_detect_keypoints_on_bgr_frame():
    img = synthetic_table()
    bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    kps, desc = detect_keypoints(bgr)
    assert len(kps) >= MIN_LEARN_KEYPOINTS
    assert desc is not None


def test_learn_accepts_structured_frame():
    model = BackgroundModel()
    assert model.learn(synthetic_table()) is True
    assert model.learned is True
    assert model.keypoint_count >= MIN_LEARN_KEYPOINTS


def test_learned_model_exposes_keypoints():
    model = BackgroundModel()
    img = synthetic_table()
    assert model.learn(img) is True
    kps = model.keypoints
    assert isinstance(kps, list)
    assert len(kps) == model.keypoint_count
    # neue Liste, keine Live-Referenz
    kps.append(None)
    assert len(model.keypoints) == model.keypoint_count
    # ungelernt -> leere Liste
    assert BackgroundModel().keypoints == []


def test_draw_keypoints_bgr_result():
    img = synthetic_table()
    kps, _ = detect_keypoints(img)
    out = draw_keypoints(img, kps)
    assert out is not None
    assert len(out.shape) == 3 and out.shape[2] == 3
    # grau -> BGR erzeugt; Keypoints heben sich visuell ab (mind. ein Pixel != Basis)
    assert out.shape[:2] == img.shape[:2]
    gray_in = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    assert np.any(out != gray_in)


def test_learn_rejects_sparse_frame():
    model = BackgroundModel()
    assert model.learn(flat_image()) is False
    assert model.learned is False


def test_match_returns_correspondences_after_shift():
    img = synthetic_table()
    _, desc = detect_keypoints(img)
    M = np.float32([[1, 0, 5], [0, 1, 0]])
    shifted = cv2.warpAffine(img, M, (W, H), borderValue=128)
    _, desc2 = detect_keypoints(shifted)
    src, dst = match_keypoints(desc, desc2)
    assert len(src) >= MIN_MATCHES
    assert src.shape == dst.shape


def test_check_identical_frame_is_ok():
    model = BackgroundModel()
    img = synthetic_table()
    assert model.learn(img) is True
    result = model.check(img, FakeCalibration())
    assert isinstance(result, CheckResult)
    assert result.status == MonitorStatus.OK
    assert result.deviation_mm < DEVIATION_THRESHOLD_MM


def test_check_shifted_frame_is_shifted_after_hysteresis():
    model = BackgroundModel()
    img = synthetic_table()
    assert model.learn(img) is True
    M = np.float32([[1, 0, 6], [0, 1, 0]])
    shifted = cv2.warpAffine(img, M, (W, H), borderValue=128)
    cal = FakeCalibration()
    # 6 px @ 320 Breite, s=20 -> erwartete Abweichung 20*2/320*6 = 0.75 mm
    first = model.check(shifted, cal)
    assert first.status == MonitorStatus.OK          # Hysterese: 1. Überschreitung
    assert first.deviation_mm >= DEVIATION_THRESHOLD_MM
    second = model.check(shifted, cal)
    assert second.status == MonitorStatus.SHIFTED    # 2. Überschreitung -> SHIFTED
    assert second.deviation_mm >= DEVIATION_THRESHOLD_MM
    # ein OK-Check setzt die Hysterese zurück
    assert model.check(img, cal).status == MonitorStatus.OK
    third = model.check(shifted, cal)
    assert third.status == MonitorStatus.OK          # Zähler wieder bei 1


def test_check_foreign_frame_is_unavailable():
    model = BackgroundModel()
    assert model.learn(synthetic_table()) is True
    other = np.random.default_rng(99).integers(0, 255, (H, W), dtype=np.uint8)
    result = model.check(other, FakeCalibration())
    assert result.status == MonitorStatus.UNAVAILABLE
    assert result.deviation_mm == 0.0


def test_check_without_model_is_unavailable():
    model = BackgroundModel()
    result = model.check(synthetic_table(), FakeCalibration())
    assert result.status == MonitorStatus.UNAVAILABLE


def test_deviation_mm_value_correct():
    model = BackgroundModel()
    img = synthetic_table()
    assert model.learn(img) is True
    M = np.float32([[1, 0, 6], [0, 1, 0]])
    shifted = cv2.warpAffine(img, M, (W, H), borderValue=128)
    model.check(shifted, FakeCalibration())
    second = model.check(shifted, FakeCalibration())
    assert second.status == MonitorStatus.SHIFTED
    # 20*2/320*6 = 0.75 mm, mit Toleranz für RANSAC/Interpolation
    assert abs(second.deviation_mm - 0.75) < 0.15


def test_monitor_thread_calls_callback_periodically_and_stops():
    import time as _time
    calls = []

    def cb():
        calls.append(_time.time())

    t = BackgroundMonitorThread(check_cb=cb, cadence=0.01)
    t.start()
    try:
        _time.sleep(0.06)
    finally:
        t.stop()
        t.join(timeout=2)
    assert not t.is_alive()
    assert len(calls) >= 3  # ~6 Ticks in 60 ms, großzügig untergrenzt


def test_monitor_thread_daemon_and_callback_exception_isolated():
    import time as _time
    calls = []

    def cb():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    t = BackgroundMonitorThread(check_cb=cb, cadence=0.01)
    assert t.daemon is True  # blockiert den Prozess-Exit nicht
    t.start()
    _time.sleep(0.03)
    t.stop()
    t.join(timeout=2)
    # Exception im ersten Tick hat den Thread nicht beendet
    assert len(calls) >= 2
    assert not t.is_alive()


def test_check_sets_diagnosis_info():
    model = BackgroundModel()
    img = synthetic_table()
    assert model.learn(img) is True
    # identischer Frame -> ok-Diagnose
    r = model.check(img, FakeCalibration())
    assert r.status == MonitorStatus.OK
    assert model.last_check_info["reason"] == "ok"
    # fremder Frame -> UNAVAILABLE mit reason
    other = np.random.default_rng(99).integers(0, 255, (H, W), dtype=np.uint8)
    model.check(other, FakeCalibration())
    info = model.last_check_info
    assert info["reason"] in ("no_matches", "no_homography", "low_inlier_ratio")
    assert "frame_keypoints" in info
    # unbeschädigtes Modell -> no_model
    assert BackgroundModel().check(img, FakeCalibration()).status == MonitorStatus.UNAVAILABLE
    assert BackgroundModel().last_check_info["reason"] == "no_model"


def test_check_robust_to_exposure_but_rejects_other_content():
    # Belichtungs-/Weißabgleich-Drift (Kanal-Faktoren) darf den Check nicht zu
    # UNAVAILABLE zwingen; anderes Muster (Papier) bleibt UNAVAILABLE.
    img_gray = synthetic_table(seed=21)
    img = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    model = BackgroundModel()
    assert model.learn(img) is True
    cal = FakeCalibration()

    def wb(img, r, g, b):
        out = img.astype(np.float32)
        out[:, :, 0] *= b
        out[:, :, 1] *= g
        out[:, :, 2] *= r
        return np.clip(out, 0, 255).astype(np.uint8)

    # gleiche Szene, warme/kalte Farbverschiebung + leichter Gain
    assert model.check(wb(img, 1.4, 1.0, 0.6), cal).status == MonitorStatus.OK
    assert model.check(wb(img, 0.6, 1.0, 1.4), cal).status == MonitorStatus.OK
    assert model.check(wb(img, 1.5, 1.5, 1.5), cal).status == MonitorStatus.OK
    # andere Szene -> weiterhin UNAVAILABLE (RANSAC-Inlier-Diskriminator)
    other = np.random.default_rng(7).integers(0, 255, (H, W, 3), dtype=np.uint8)
    assert model.check(other, cal).status == MonitorStatus.UNAVAILABLE


def test_tint_mask_attributes_reset():
    m = BackgroundModel()
    assert m.tint_mask is None and m.tint_tick == 0
    img = cv2.cvtColor(synthetic_table(), cv2.COLOR_GRAY2BGR)
    assert m.learn(img, reference=img) is True
    assert m.tint_mask is None and m.tint_tick == 0
    # Neu-Lernen setzt eine veraltete Tint-Maske zurück
    m.tint_mask = np.ones((1, 1), dtype=np.uint8)
    m.tint_tick = 7
    assert m.learn(img, reference=img) is True
    assert m.tint_mask is None and m.tint_tick == 0
    # set_reference (Recovery) setzt ebenfalls zurück
    m.tint_mask = np.ones((1, 1), dtype=np.uint8)
    m.tint_tick = 7
    m.set_reference(img)
    assert m.tint_mask is None and m.tint_tick == 0
    # fehlgeschlagenes Lernen (zu strukturarm) setzt zurück
    m.tint_mask = np.ones((1, 1), dtype=np.uint8)
    m.tint_tick = 7
    assert m.learn(flat_image()) is False
    assert m.tint_mask is None and m.tint_tick == 0


def test_table_mask_threshold_parameter():
    img = np.full((H, W, 3), 128, dtype=np.uint8)
    # threshold=None => bisheriges Otsu-Verhalten (identisch zum Aufruf ohne)
    a = table_mask(img, img)
    b = table_mask(img, img, threshold=None)
    assert np.array_equal(a, b)
    # explizite Schwelle klassifiziert ohne Otsu: identische Bilder => dist 0
    assert table_mask(img, img, threshold=0.5).all()
    assert not table_mask(img, img, threshold=-1.0).any()


def test_table_mask_tight_relative_to_threshold():
    img = np.full((H, W, 3), 128, dtype=np.uint8)
    loose = table_mask(img, img, threshold=0.5)
    tight = table_mask(img, img, tight=True, threshold=0.5)
    # tight ist eine konservative Kern-Maske relativ zur übergebenen Schwelle
    assert (tight & ~loose).sum() == 0


if __name__ == "__main__":
    for fn in (test_constants_importable, test_detect_keypoints_on_texture,
               test_detect_keypoints_on_bgr_frame, test_learn_accepts_structured_frame,
               test_learned_model_exposes_keypoints, test_draw_keypoints_bgr_result,
               test_learn_rejects_sparse_frame, test_match_returns_correspondences_after_shift,
               test_check_identical_frame_is_ok, test_check_shifted_frame_is_shifted_after_hysteresis,
               test_check_foreign_frame_is_unavailable, test_check_without_model_is_unavailable,
               test_deviation_mm_value_correct,
               test_learn_caps_keypoint_count,
               test_learn_sets_reference,
               test_update_reference_ema,
               test_update_reference_noop_cases,
               test_relearn_from_reference,
               test_detect_keypoints_capped_by_nfeatures,
               test_match_keypoints_capped_by_max_matches,
               test_monitor_thread_calls_callback_periodically_and_stops,
               test_monitor_thread_daemon_and_callback_exception_isolated,
               test_check_sets_diagnosis_info,
               test_check_robust_to_exposure_but_rejects_other_content,
               test_tint_mask_attributes_reset,
               test_table_mask_threshold_parameter,
               test_table_mask_tight_relative_to_threshold):
        fn()
        print(f"PASS {fn.__name__}")
    print("All calibration-monitor tests passed")