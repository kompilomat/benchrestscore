# -*- coding: utf-8 -*-
"""Headless unit tests for the Anzeige-Filter (no window/GL).

Die Referenzfunktion `filter_pixel` ist der CPU-Spiegel des Shader-
Filter-Blocks (design.md D2). Neutralzustand = Identität; die Tests
decken alle Filter sowie die Orthogonalität des Controller-Zustands ab.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import tempfile

import numpy as np

from benchrestscore.controller import (
    AppController, AppState, BRSViewFilter, filter_pixel, tint_pixel,
    TINT_COLOR_RGB, TINT_OPACITY,
)
from benchrestscore.calibration_monitor import BackgroundModel
from benchrestscore.settings import save as settings_save

# Persistenz-Pfade in einem Temp-Config isolieren: Tests, die den Controller
# ohne expliziten `settings_path` bauen (Default-Config), dürfen nie ins echte
# ~/.config/benchrestscore/ lesen — der Standalone-Lauf wäre sonst von der
# realen Nutzer-Konfiguration abhängig (z.B. gespeicherte Filterwerte).
_TEST_CFG = tempfile.mkdtemp(prefix="brs_filters_cfg_")
os.environ["XDG_CONFIG_HOME"] = _TEST_CFG


def test_neutral_is_identity():
    f = BRSViewFilter()
    assert f.is_neutral()
    rgb = np.array([0.2, 0.4, 0.9])
    assert np.allclose(filter_pixel(rgb, f), rgb)


def test_gray_produces_equal_channels():
    f = BRSViewFilter(gray=True)
    out = filter_pixel(np.array([1.0, 0.0, 0.5]), f)
    assert np.allclose(out[0], out[1])
    assert np.allclose(out[1], out[2])


def test_invert():
    f = BRSViewFilter(invert=True)
    rgb = np.array([0.3, 0.6, 0.9])
    assert np.allclose(filter_pixel(rgb, f), 1.0 - rgb)


def test_contrast_moves_away_from_mid():
    base = np.array([0.4, 0.4, 0.4])
    low = filter_pixel(base, BRSViewFilter(contrast=0.8))
    high = filter_pixel(base, BRSViewFilter(contrast=1.5))
    assert abs(float(low[0]) - 0.5) < abs(float(base[0]) - 0.5)
    assert abs(float(high[0]) - 0.5) > abs(float(base[0]) - 0.5)


def test_brightness_is_monotonic():
    base = np.array([0.3, 0.3, 0.3])
    dark = filter_pixel(base, BRSViewFilter(brightness=-0.2))
    bright = filter_pixel(base, BRSViewFilter(brightness=0.2))
    assert np.all(bright >= dark)


def test_gamma_brightens_dark():
    base = np.array([0.3, 0.3, 0.3])
    assert filter_pixel(base, BRSViewFilter(gamma=0.6))[0] > base[0]
    assert filter_pixel(base, BRSViewFilter(gamma=1.6))[0] < base[0]


def test_saturation_zero_is_gray():
    f = BRSViewFilter(saturation=0.0)
    rgb = np.array([0.9, 0.3, 0.5])
    out = filter_pixel(rgb, f)
    assert np.allclose(out[0], out[1])
    assert np.allclose(out[1], out[2])


def test_neutral_parameter_combination_identity():
    rgb = np.array([0.55, 0.25, 0.85])
    f = BRSViewFilter(gray=True, invert=True, contrast=1.0, brightness=0.0,
                      saturation=1.0, gamma=1.0)
    out = filter_pixel(rgb, f)
    # graustufen + invert: beide kommutieren zu grauem Bild (Kanäle gleich)
    assert np.allclose(out[0], out[1])
    assert np.allclose(out[1], out[2])


def test_batch_vectorization():
    rgb = np.array([[0.2, 0.4, 0.9], [0.8, 0.1, 0.3]])
    f = BRSViewFilter(invert=True)
    out = filter_pixel(rgb, f)
    assert np.allclose(out[0], 1.0 - rgb[0])
    assert np.allclose(out[1], 1.0 - rgb[1])


def test_to_dict_roundtrip():
    f = BRSViewFilter(contrast=1.4, gamma=0.9, brightness=-0.1,
                      saturation=0.7, invert=True, gray=True, active=False,
                      tint=True)
    data = f.to_dict()
    assert data == {
        "active": False, "invert": True, "gray": True,
        "saturation": 0.7, "contrast": 1.4, "gamma": 0.9, "brightness": -0.1,
        "tint": True,
    }
    restored = BRSViewFilter.from_dict(data)
    assert restored.to_dict() == data


def test_from_dict_neutral_for_empty():
    assert BRSViewFilter.from_dict({}).is_neutral()
    assert BRSViewFilter.from_dict(None).is_neutral()


def test_from_dict_tolerates_invalid_values():
    # falscher Typ -> Default
    assert BRSViewFilter.from_dict({"contrast": "abc"}).contrast == 1.0
    assert BRSViewFilter.from_dict({"invert": "ja"}).invert is False
    # außerhalb des einstellbaren Bereichs -> Default
    assert BRSViewFilter.from_dict({"contrast": 9.9}).contrast == 1.0
    assert BRSViewFilter.from_dict({"gamma": -3.0}).gamma == 1.0
    assert BRSViewFilter.from_dict({"brightness": 5.0}).brightness == 0.0
    # gültige Ränder bleiben erhalten
    assert BRSViewFilter.from_dict({"saturation": 0.0}).saturation == 0.0
    assert BRSViewFilter.from_dict({"brightness": -0.5}).brightness == -0.5


def test_tint_flag_default_and_invalid():
    assert BRSViewFilter().tint is False
    assert BRSViewFilter.from_dict({}).tint is False
    assert BRSViewFilter.from_dict({"tint": "ja"}).tint is False
    assert BRSViewFilter.from_dict({"tint": True}).tint is True
    f = BRSViewFilter(tint=True)
    f.reset()
    assert f.tint is False


def test_tint_pixel_off_is_identity():
    rgb = np.array([0.2, 0.4, 0.9])
    assert np.allclose(tint_pixel(rgb, 1.0, 0.0), rgb)


def test_tint_pixel_mixes_color_on_mask():
    rgb = np.array([0.2, 0.4, 0.9])
    tc = np.asarray(TINT_COLOR_RGB, dtype=np.float64)
    # opak (Deckkraft 1) + Maske 1 -> Tint-Farbe
    assert np.allclose(tint_pixel(rgb, 1.0, 1.0), tc)
    # Maske 0 -> unverändert
    assert np.allclose(tint_pixel(rgb, 0.0, 1.0), rgb)
    # partielle Maske -> lineare Mischung
    out = tint_pixel(rgb, 0.5, 1.0)
    assert np.allclose(out, 0.5 * rgb + 0.5 * tc)
    # semitransparent (Deckkraft 0.5) auf Maske 1 -> halbe Mischung
    out = tint_pixel(rgb, 1.0, 0.5)
    assert np.allclose(out, 0.5 * rgb + 0.5 * tc)
    # Produkt aus Maske und Deckkraft (0.5 * 0.5)
    out = tint_pixel(rgb, 0.5, 0.5)
    assert np.allclose(out, 0.75 * rgb + 0.25 * tc)


def test_tint_pixel_batch_vectorization():
    batch = np.array([[0.2, 0.4, 0.9], [0.5, 0.5, 0.5]])
    mask = np.array([1.0, 0.0])
    out = tint_pixel(batch, mask, 1.0)
    assert np.allclose(out[0], TINT_COLOR_RGB)
    assert np.allclose(out[1], batch[1])


class Canvas:
    wants_exit = False
    font_scale = "normal"
    def request_font_scale(self, key):
        self.font_scale = key


def test_controller_filters_persist_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        c = AppController(Canvas(), settings_path=path)
        c.set_filter_param("contrast", 1.5)
        c.set_filter_param("invert", True)
        c.toggle_filters_active()
        c.toggle_background_tint()
        assert c.flush_filters_if_dirty() is True
        c2 = AppController(Canvas(), settings_path=path)
        assert c2.filters.contrast == 1.5
        assert c2.filters.invert is True
        assert c2.filters.active is False
        assert c2.filters.tint is False


def test_controller_tint_persist_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        c = AppController(Canvas(), settings_path=path)
        assert c.toggle_background_tint() is True
        assert c.flush_filters_if_dirty() is True
        c2 = AppController(Canvas(), settings_path=path)
        assert c2.filters.tint is False
        # kaputter Eintrag -> False (kein Verhalten)
        path_bad = os.path.join(td, "bad.json")
        settings_save({"filters": {"tint": "ja"}}, path=path_bad)
        c3 = AppController(Canvas(), settings_path=path_bad)
        assert c3.filters.tint is False


def test_controller_effective_tint_guarded_by_reference():
    c = AppController(Canvas())
    assert c.effective_tint() == (0.0, 0.0, 0.0, 0.0)
    # ohne Referenz bleibt das Tupel No-op, auch bei aktivem Flag
    assert c.toggle_background_tint() is True
    assert c.filters.tint is True
    assert c.effective_tint() == (0.0, 0.0, 0.0, 0.0)
    # mit Referenz -> (u_tint, RGB-Farbe) in Shader-Kanalreihenfolge;
    # u_tint = TINT_OPACITY (semitransparent, 0..1)
    model = BackgroundModel()
    model.set_reference(np.zeros((240, 320, 3), dtype=np.uint8))
    assert model.has_reference
    c.background_model = model
    assert c.effective_tint() == (TINT_OPACITY, TINT_COLOR_RGB[0],
                                  TINT_COLOR_RGB[1], TINT_COLOR_RGB[2])
    # Toggle aus -> No-op
    assert c.toggle_background_tint() is False
    assert c.effective_tint() == (0.0, 0.0, 0.0, 0.0)


def test_controller_loads_invalid_filters_neutral():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        settings_save({"filters": {"contrast": "kaputt", "active": "ja"}},
                      path=path)
        c = AppController(Canvas(), settings_path=path)
        assert c.filters.is_neutral()
        assert c.filters.active is False


def test_controller_flush_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        c = AppController(Canvas(), settings_path=path)
        assert c.flush_filters_if_dirty() is False  # nichts geändert
        c.set_filter_param("gamma", 0.8)
        assert c.flush_filters_if_dirty() is True
        assert c.flush_filters_if_dirty() is False  # erneuter Flush no-op


def test_controller_filters_are_orthogonal():
    c = AppController(Canvas())
    state = c.state
    assert c.filters.is_neutral()
    assert c.filters.active is False  # Start: Schalter aus
    assert c.effective_uniforms() == (1.0, 1.0, 0.0, 1.0, 0.0, 0.0)

    c.set_filter_param("contrast", 1.5)
    c.set_filter_param("invert", True)
    assert c.filters.contrast == 1.5
    assert c.filters.invert is True
    assert c.state is state  # FSM unverändert

    c.toggle_filters_active()
    assert c.filters.active is True
    assert c.effective_uniforms()[0] == 1.5  # Zustand wiederhergestellt
    assert c.state is state

    c.toggle_filters_active()
    assert c.filters.active is False
    assert c.effective_uniforms() == (1.0, 1.0, 0.0, 1.0, 0.0, 0.0)  # deaktiviert
    assert c.state is state

    c.reset_filters()
    assert c.filters.is_neutral()
    assert c.state is state


if __name__ == "__main__":
    for fn in (test_neutral_is_identity, test_gray_produces_equal_channels,
               test_invert, test_contrast_moves_away_from_mid,
               test_brightness_is_monotonic, test_gamma_brightens_dark,
               test_saturation_zero_is_gray, test_neutral_parameter_combination_identity,
               test_batch_vectorization, test_to_dict_roundtrip,
               test_from_dict_neutral_for_empty, test_from_dict_tolerates_invalid_values,
               test_tint_flag_default_and_invalid,
               test_tint_pixel_off_is_identity,
               test_tint_pixel_mixes_color_on_mask,
               test_tint_pixel_batch_vectorization,
               test_controller_filters_persist_roundtrip,
               test_controller_tint_persist_roundtrip,
               test_controller_effective_tint_guarded_by_reference,
               test_controller_loads_invalid_filters_neutral,
               test_controller_flush_is_idempotent,
               test_controller_filters_are_orthogonal):
        fn()
        print(f"PASS {fn.__name__}")
    print("All filter tests passed")