# -*- coding: utf-8 -*-
"""Headless unit tests for the font scale presets (no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from benchrestscore.fontconfig import (
    FONT_SCALES,
    DEFAULT_FONT_SCALE_KEY,
    compute_font_pixel_size,
)


def test_default_scale_is_normal():
    assert DEFAULT_FONT_SCALE_KEY == "normal"
    assert FONT_SCALES["normal"] == 1.0


def test_preset_factors():
    assert FONT_SCALES["normal"] == 1.0
    assert FONT_SCALES["large"] == 1.25
    assert FONT_SCALES["xlarge"] == 1.5


def test_reference_size_at_2160p():
    # 4K-Referenz: 28 px Basis bei 2160 -> Faktor-Skala streng aufsteigend
    assert compute_font_pixel_size(2160, "normal") == 28
    assert compute_font_pixel_size(2160, "large") == 35
    assert compute_font_pixel_size(2160, "xlarge") == 42


def test_strictly_ascending():
    # Bei jeder Fensterhöhe streng aufsteigend normal < large < xlarge
    for fb_h in (720, 900, 1080, 1440, 2160):
        n = compute_font_pixel_size(fb_h, "normal")
        l = compute_font_pixel_size(fb_h, "large")
        x = compute_font_pixel_size(fb_h, "xlarge")
        assert n < l < x, f"not ascending at {fb_h}px: {n}/{l}/{x}"


def test_common_resolutions_visibly_distinct():
    # Untergrenze skaliert mit: bei 1080p sind die Stufen klar unterscheidbar
    assert compute_font_pixel_size(1080, "normal") == 16
    assert compute_font_pixel_size(1080, "large") == 20
    assert compute_font_pixel_size(1080, "xlarge") == 24
    # Auch bei 720p (kleine Fenster) bleiben die Stufen sichtbar getrennt
    assert compute_font_pixel_size(720, "normal") == 16
    assert compute_font_pixel_size(720, "large") == 20
    assert compute_font_pixel_size(720, "xlarge") == 24


def test_floor_scales_with_preset():
    # Kleine Fenster: die Untergrenze wächst mit dem Faktor (16/20/24)
    assert compute_font_pixel_size(480, "normal") == 16
    assert compute_font_pixel_size(480, "large") == 20
    assert compute_font_pixel_size(480, "xlarge") == 24


def test_unknown_key_raises():
    try:
        compute_font_pixel_size(1080, "huge")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown key")


if __name__ == "__main__":
    for fn in (test_default_scale_is_normal, test_preset_factors,
               test_reference_size_at_2160p, test_strictly_ascending,
               test_common_resolutions_visibly_distinct,
               test_floor_scales_with_preset, test_unknown_key_raises):
        fn()
        print(f"PASS {fn.__name__}")
    print("All fontconfig tests passed")