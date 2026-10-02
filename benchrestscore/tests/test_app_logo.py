# -*- coding: utf-8 -*-
"""Headless tests for the logo loader (no window/GL context)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from benchrestscore.app import load_logo_image, LOGO_PATH
PKG_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "logo.png")


def test_load_real_logo():
    # Die echte Logodatei liefert RGBA mit dem erwarteten Seitenverhältnis
    assert os.path.exists(LOGO_PATH), f"Logo fehlt: {LOGO_PATH}"
    result = load_logo_image(LOGO_PATH)
    assert result is not None
    rgba, aspect = result
    assert rgba.dtype == "uint8"
    assert rgba.ndim == 3 and rgba.shape[2] == 4
    assert rgba.shape[0] > 0 and rgba.shape[1] > 0
    # 1419 x 273 -> aspect ~ 5.2
    assert 5.0 < aspect < 5.5
    # Referenz-Decode: Identität mit direktem cv2-Laden (Kanalreihenfolge)
    ref = cv2.cvtColor(cv2.imread(PKG_DATA, cv2.IMREAD_UNCHANGED),
                       cv2.COLOR_BGRA2RGBA)
    assert (rgba == ref).all()


def test_load_missing_file_returns_none(capsys):
    result = load_logo_image("/tmp/opencode/no_such_logo_12345.png")
    assert result is None
    # Einmaliger Log-Eintrag statt Exception
    out = capsys.readouterr().out
    assert "logo unreadable or missing" in out


def test_load_corrupt_file_returns_none(tmp_path):
    p = tmp_path / "corrupt.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-real-png-payload")
    result = load_logo_image(str(p))
    assert result is None


def test_load_rgb_image_gets_alpha_channel(tmp_path):
    # BGR-Bild (ohne Alpha) wird mit opaken Alphakanal ergänzt
    bgr = (255 * np.ones((10, 20, 3), dtype="uint8"))
    p = tmp_path / "rgb.png"
    assert cv2.imwrite(str(p), bgr)
    result = load_logo_image(str(p))
    assert result is not None
    rgba, aspect = result
    assert rgba.shape == (10, 20, 4)
    assert (rgba[:, :, 3] == 255).all()
    assert aspect == 2.0
